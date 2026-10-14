import logging
import os
import threading
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

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
    rule_ids: list[
        str
    ] = []  # reasons ile aynı sırada; Gün 13 cache anahtarı için de kullanılacak


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
        "segment_istatistik": islemler.groupby("segment")["amount"].agg(
            ["mean", "std"]
        ),
    }
    pd.to_pickle(veri, ONBELLEK_DOSYASI)
    return veri


app = FastAPI()
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
    with (
        _rag_kilidi
    ):  # iki istek aynı anda ilk yüklemeyi tetiklerse model iki kez yüklenmesin
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
        from risk_rag import aciklama_uret_rag

        sonuc = aciklama_uret_rag(risk, rag_getir)
    except Exception:
        # Açıklama ek bir özellik: LLM/rehber tarafı çökse bile risk sonucu yine dönmeli.
        logger.exception("Açıklama üretilemedi")
        sonuc = {
            "explanation": "Açıklama şu an üretilemedi. Risk sonucu geçerlidir.",
            "policy_sources": [],
            "llm_used": False,
        }
    return {**risk, **sonuc}
