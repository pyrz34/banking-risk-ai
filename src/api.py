import asyncio
import logging
import os
import threading
from contextlib import asynccontextmanager
from typing import Literal, Optional

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field, StrictInt

from risk_engine import BASE_DIR, VERI_DOSYASI, RiskEngine

ONBELLEK_DOSYASI = os.path.join(BASE_DIR, "data", "api_onbellek.pkl")
logger = logging.getLogger("risk_api")


class TransactionRequest(BaseModel):
    account_id: int
    amount: float
    status: Literal["OK", "FAILED"]
    channel: Literal["Web", "Mobile", "ATM", "Branch"]
    is_international: Literal[0, 1]


class RiskResponse(BaseModel):
    risk_score: int
    risk_label: str
    reasons: list[str]
    rule_ids: list[str] = []  # reasons ile aynı sırada; Gün 13 cache anahtarı için de kullanılacak


class PolicySource(BaseModel):
    no: int
    sayfa: int
    kodlar: list[str]
    skor: float
    atif_edildi: bool  # Claude cevapta bu kaynağa [no] ile atıf yaptı mı


class ExplainResponse(RiskResponse):
    explanation: str
    policy_sources: list[PolicySource]
    llm_used: bool


class InvestigateRequest(BaseModel):
    customer_id: StrictInt = Field(ge=1)  # "1", 1.0, true reddedilir; 0 ve negatifler reddedilir (422)


class MusteriOzeti(BaseModel):
    segment: str
    city: str
    risk_band: str
    onboard_date: str
    hesap_sayisi: int
    toplam_islem: int


class IslemOzeti(BaseModel):
    txn_id: int
    account_id: int
    txn_time: str
    channel: str
    txn_type: str
    amount: float
    merchant_category: str
    is_international: int
    counterparty_country: str
    status: str
    risk_score: int
    risk_label: str
    rule_ids: list[str]


class DogrulamaSonucu(BaseModel):
    kontrol: str
    gecti: bool
    detay: str


class IzOzeti(BaseModel):
    bitis: str
    arac_sirasi: list[str]
    girdi_token: int
    cikti_token: int
    sure_ms: Optional[int] = None


class InvestigateResponse(BaseModel):
    customer_id: int
    musteri: MusteriOzeti
    en_riskli_islemler: list[IslemOzeti]
    rapor: Optional[str] = None
    rapor_kaynagi: Literal["ajan", "aciklama", "yok"]  # hangi basamak cevap verdi (bkz. investigation_service.py)
    onbellekten: bool
    dogrulama: list[DogrulamaSonucu]  # yalnız ajan raporunda dolu; KABA ipucu, kanıt değil
    uyarilar: list[str]
    iz_ozeti: Optional[IzOzeti] = None
    sure_ms: int


def referans_verisi_yukle():
    """Hesap->segment tablosu ve segment ortalama/std'sini döner.
    İlk seferde Excel'den hesaplar (yavaş), sonra küçük bir dosyaya kaydeder."""
    if os.path.exists(ONBELLEK_DOSYASI):
        return pd.read_pickle(ONBELLEK_DOSYASI)

    sayfalar = pd.read_excel(VERI_DOSYASI, sheet_name=None)
    musteriler = sayfalar["customers"][["customer_id", "segment"]]
    hesaplar = sayfalar["accounts"][["account_id", "customer_id"]].merge(
        musteriler, on="customer_id"
    )
    islemler = sayfalar["transactions"].merge(hesaplar, on="account_id")

    veri = {
        "hesap_segment": hesaplar.set_index("account_id")["segment"],
        "segment_istatistik": islemler.groupby("segment")["amount"].agg(["mean", "std"]),
    }
    pd.to_pickle(veri, ONBELLEK_DOSYASI)
    return veri


def _isit():
    """Ağır yüklemeleri sunucu açılırken yap: Excel tabloları ve e5 modeli. İlk gerçek istek 10 sn beklemesin."""
    from tools import veri

    veri.tablolar()
    rag_getir()


@asynccontextmanager
async def omur(uygulama):
    if os.environ.get("RAG_ISITMA", "1") != "0":  # RAG_ISITMA=0: ısıtmayı kapat (hızlı geliştirme/test)
        try:
            await asyncio.to_thread(_isit)
        except Exception:  # noqa: BLE001  (ısıtma başarısız olsa da sunucu açılsın; ilk istekte tekrar denenir)
            logger.exception("Isıtma başarısız; model ilk gerçek istekte yüklenecek")
    yield


app = FastAPI(lifespan=omur)
motor = RiskEngine()
referans = referans_verisi_yukle()  # sunucu açılırken bir kez


@app.get("/")
def ana_sayfa():
    return {"mesaj": "Risk Engine API'ye hoş geldiniz!"}


def risk_hesapla(islem):
    """İşlem -> risk motoru sonucu (skor, etiket, nedenler, rule_ids). İki uç nokta da bunu kullanır."""
    if islem.account_id not in referans["hesap_segment"].index:
        raise HTTPException(
            status_code=404, detail=f"account_id {islem.account_id} bulunamadı"
        )

    segment = referans["hesap_segment"][islem.account_id]
    ist = referans["segment_istatistik"].loc[segment]
    amount_z = (islem.amount - ist["mean"]) / ist["std"]

    satir = pd.Series(
        {
            "status": islem.status,
            "channel": islem.channel,
            "is_international": islem.is_international,
            "amount": islem.amount,
            "amount_z": amount_z,
        }
    )
    return motor.calculate(satir)


@app.post("/predict-risk", response_model=RiskResponse)
def predict_risk(islem: TransactionRequest):
    return risk_hesapla(islem)


_rag = None
_rag_kilidi = threading.Lock()


def rag_getir():
    """e5 modeli + chunk indeksi. Ağır (birkaç sn, ~2 GB), o yüzden ilk gerçekten gerektiğinde yüklenir."""
    global _rag
    with _rag_kilidi:  # iki istek aynı anda ilk yüklemeyi tetiklerse model iki kez yüklenmesin
        if _rag is None:
            from rag_index import indeks_olustur, modeli_yukle

            model = modeli_yukle()
            chunklar, vektorler = indeks_olustur(model)
            _rag = (model, chunklar, vektorler)
    return _rag


@app.post("/explain-risk", response_model=ExplainResponse)
def explain_risk(islem: TransactionRequest):
    risk = risk_hesapla(islem)  # bu kısım hata verirse (404 gibi) olduğu gibi döner
    try:
        from investigation_service import aciklama_onbellekli

        # Önbellekli: aynı kural kümesi/etiket/skor için Claude'a ikinci kez gidilmez (maliyet ve süre). Açıklamadaki
        # tutar sapması (z) sayısı yazılmaz; `reasons` alanı z'yi taşımaya devam eder.
        sonuc, _ = aciklama_onbellekli(risk, rag_getir, None)
    except Exception:
        # Açıklama ek bir özellik: LLM/rehber tarafı çökse bile risk sonucu yine dönmeli.
        logger.exception("Açıklama üretilemedi")
        sonuc = {"explanation": "Açıklama şu an üretilemedi. Risk sonucu geçerlidir.",
                 "policy_sources": [], "llm_used": False}
    return {**risk, **sonuc}


@app.post("/investigate", response_model=InvestigateResponse)
def investigate(istek: InvestigateRequest, yenile: bool = False):
    """Müşteri incelemesi: veri katmanı + ajan raporu, ajan çökerse açıklama, o da çökerse yalnız veri (hepsi 200).
    Müşteri yoksa 404. yenile=true: önbellekteki ajan raporunu atlayıp yeniden üretir."""
    from investigation_service import MusteriYok, incele_servis

    try:
        return incele_servis(istek.customer_id, rag_getir=rag_getir, yenile=yenile)
    except MusteriYok as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.get("/onbellek-durumu")
def onbellek_durumu():
    """Önbellek isabet/ıska sayıları (kişisel veri yok). Isabet oranını gerçek kullanımda ölçmek için."""
    from investigation_service import onbellek_durumu as durum

    return durum()
