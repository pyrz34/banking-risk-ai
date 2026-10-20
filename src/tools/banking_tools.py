"""Gün 14–16: LLM'in çağırabileceği dört banka aracı.

Her aracın üç parçası var, hepsi bu dosyada ki birbirinden kopmasınlar:
  1. Python fonksiyonu     -> işi GERÇEKTEN yapan kod (deterministik, test edilir)
  2. TOOL_SCHEMAS          -> LLM'e "böyle bir araç var, şu argümanları alır" diyen tanım
  3. tool_calistir()       -> LLM'in istediği aracı adıyla bulup çalıştıran küçük dağıtıcı

Araçlar:
  get_risk_score          işlem -> risk skoru (risk motoru, /predict-risk ile aynı kod)
  get_customer_info       müşteri -> segment, şehir, risk bandı, hesaplar
  get_transaction_history müşteri -> işlemleri (en yeni ya da en riskli önce), her işlemde risk skoruyla
  search_risk_policy      sorgu -> MASAK rehberinden en yakın parçalar (SADECE arama, cevap üretmez)

LLM fonksiyonu ÇALIŞTIRMAZ. Sadece hangi aracı hangi argümanla istediğini söyler; çalıştıran bizim Python kodumuzdur.
Her araç hata olursa istisna fırlatmaz, {"error": "..."} döner. LLM hatayı da bir sonuç olarak okur.
"""
import logging
import os
import sys

import pandas as pd
from pydantic import ValidationError

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(KOK, "src")
if SRC not in sys.path:  # python src\agent.py da, testler de çalışsın
    sys.path.insert(0, SRC)

from tools import veri  # noqa: E402

logger = logging.getLogger("banking_tools")

VARSAYILAN_LIMIT = 5
MAKS_LIMIT = 20          # bir cevapta en fazla bu kadar işlem (her işlem ~250 karakter = token maliyeti)
SIRALAMALAR = ["recent", "risk"]
VARSAYILAN_K = 3
MAKS_K = 5               # rag_cevap.K ile aynı üst sınır
MAKS_SORGU_UZUNLUGU = 300


def _hata_metni(e):
    """pydantic doğrulama hatasını LLM'in okuyup düzeltebileceği kısa metne çevirir."""
    parcalar = []
    for h in e.errors():
        alan = ".".join(str(x) for x in h["loc"]) or "girdi"
        parcalar.append(f"{alan}: {h['msg']}")
    return "Geçersiz argüman: " + "; ".join(parcalar)


def _tam_sayi_degil(ad, deger, en_az=None, en_cok=None):
    """Tam sayı değilse (ya da aralık dışındaysa) hata sözlüğü, değilse None.
    bool, int'in alt sınıfı (True == 1) olduğu için ayrıca elenir. 4521.0 gibi float de kabul edilmez."""
    if isinstance(deger, bool) or not isinstance(deger, int):
        return {"error": f"Geçersiz argüman: {ad} tam sayı olmalı (gelen: {deger!r})"}
    if (en_az is not None and deger < en_az) or (en_cok is not None and deger > en_cok):
        return {"error": f"Geçersiz argüman: {ad} {en_az} ile {en_cok} arasında olmalı (gelen: {deger})"}
    return None


# ---------------------------------------------------------------- get_risk_score
def get_risk_score(account_id, amount, status, channel, is_international):
    """Bir işlem için risk skoru, etiketi, nedenleri ve kural kimliklerini döner.
    Hesaplama /predict-risk ile AYNI koddur (api.risk_hesapla), ikinci bir kopya yok."""
    from fastapi import HTTPException

    from api import TransactionRequest, risk_hesapla

    try:
        islem = TransactionRequest(account_id=account_id, amount=amount, status=status,
                                   channel=channel, is_international=is_international)
    except ValidationError as e:
        return {"error": _hata_metni(e)}
    try:
        return risk_hesapla(islem)
    except HTTPException as e:  # ör. olmayan hesap -> 404
        return {"error": str(e.detail)}


# ------------------------------------------------------------ get_customer_info
def get_customer_info(customer_id):
    """Müşterinin segmenti, şehri, risk bandı, kayıt tarihi ve hesapları."""
    hata = _tam_sayi_degil("customer_id", customer_id)
    if hata:
        return hata
    t = veri.tablolar()
    musteriler, hesaplar = t["customers"], t["accounts"]
    if customer_id not in musteriler.index:
        return {"error": f"customer_id {customer_id} bulunamadı"}
    m = musteriler.loc[customer_id]
    h = hesaplar[hesaplar["customer_id"] == customer_id]
    return {
        "customer_id": customer_id,
        "segment": str(m["segment"]),
        "city": str(m["city"]),
        "risk_band": str(m["risk_band"]),
        "onboard_date": m["onboard_date"].strftime("%Y-%m-%d"),
        "accounts": [
            {"account_id": int(r.account_id), "account_type": str(r.account_type), "currency": str(r.currency)}
            for r in h.itertuples()
        ],
    }


# ------------------------------------------------------- get_transaction_history
def _islem_riski(r):
    """Bir işlem satırının risk sonucu. /predict-risk ile aynı kod yolu (api.risk_hesapla)."""
    from fastapi import HTTPException

    from api import TransactionRequest, risk_hesapla

    try:
        s = risk_hesapla(TransactionRequest(account_id=int(r.account_id), amount=float(r.amount), status=str(r.status),
                                            channel=str(r.channel), is_international=int(r.is_international)))
        return {"risk_score": s["risk_score"], "risk_label": s["risk_label"], "rule_ids": s["rule_ids"]}
    except (ValidationError, HTTPException):  # beklenmeyen değerli satır: skor yok, ama işlem listede kalır
        return {"risk_score": None, "risk_label": None, "rule_ids": []}


def get_transaction_history(customer_id, limit=VARSAYILAN_LIMIT, sort_by="recent"):
    """Müşterinin tüm hesaplarındaki işlemler. sort_by='recent': en yeni önce; 'risk': en yüksek risk skoru önce.
    Her işlemde deterministik risk skoru da gelir, en riskli işlemi bulmak için tek tek skor hesaplatmak gerekmez."""
    hata = _tam_sayi_degil("customer_id", customer_id) or _tam_sayi_degil("limit", limit, 1, MAKS_LIMIT)
    if hata:
        return hata
    if sort_by not in SIRALAMALAR:
        return {"error": f"Geçersiz argüman: sort_by {SIRALAMALAR} değerlerinden biri olmalı (gelen: {sort_by!r})"}
    t = veri.tablolar()
    if customer_id not in t["customers"].index:
        return {"error": f"customer_id {customer_id} bulunamadı"}

    hesap_idleri = t["accounts"].loc[t["accounts"]["customer_id"] == customer_id, "account_id"]
    islemler = t["transactions"][t["transactions"]["account_id"].isin(hesap_idleri)]
    toplam = len(islemler)

    if sort_by == "recent":
        secilen = islemler.sort_values(["txn_time", "txn_id"], ascending=False).head(limit)
        riskler = {r.txn_id: _islem_riski(r) for r in secilen.itertuples()}
    else:  # risk: hepsi için hesapla (bir müşteride yüzlerce satır), sonra en yüksek ilk
        riskler = {r.txn_id: _islem_riski(r) for r in islemler.itertuples()}
        secilen = islemler.assign(_risk=islemler["txn_id"].map(lambda i: riskler[i]["risk_score"] if riskler[i]["risk_score"] is not None else -1))
        secilen = secilen.sort_values(["_risk", "amount", "txn_time"], ascending=False).head(limit)

    return {
        "customer_id": customer_id,
        "toplam_islem": int(toplam),
        "donen": int(len(secilen)),
        "siralama": sort_by,
        "islemler": [
            {"txn_id": int(r.txn_id), "account_id": int(r.account_id),
             "txn_time": pd.Timestamp(r.txn_time).strftime("%Y-%m-%d %H:%M:%S"),
             "channel": str(r.channel), "txn_type": str(r.txn_type), "amount": float(r.amount),
             "merchant_category": str(r.merchant_category), "is_international": int(r.is_international),
             "counterparty_country": str(r.counterparty_country), "status": str(r.status), **riskler[r.txn_id]}
            for r in secilen.itertuples()
        ],
    }


# -------------------------------------------------------------- search_risk_policy
def _rag():
    """(model, chunklar, vektorler). /explain-risk ile AYNI yükleyici: model bellekte tek kez durur."""
    from api import rag_getir

    return rag_getir()


def search_risk_policy(query, k=VARSAYILAN_K):
    """MASAK Şüpheli İşlem Bildirim Rehberi'nde arama. SADECE arar: en yakın k parçayı (sayfa, kodlar, metin) döner.
    Cevabı yazmak çağıran modelin işi, burada ikinci bir Claude çağrısı yok (maliyet)."""
    if not isinstance(query, str) or not query.strip():
        return {"error": "Geçersiz argüman: query boş olmayan bir metin olmalı"}
    if len(query) > MAKS_SORGU_UZUNLUGU:
        return {"error": f"Geçersiz argüman: query en fazla {MAKS_SORGU_UZUNLUGU} karakter olmalı (gelen: {len(query)})"}
    hata = _tam_sayi_degil("k", k, 1, MAKS_K)
    if hata:
        return hata
    try:
        from rag_index import ara

        model, chunklar, vektorler = _rag()
        sonuclar = ara(query.strip(), chunklar, vektorler, model, k=k)
    except Exception:  # model/indeks/PDF sorunu: sunucuyu düşürme, ayrıntı log'a
        logger.exception("Rehber araması başarısız")
        return {"error": "Rehber araması şu an kullanılamıyor"}
    return {
        "sorgu": query.strip(),
        "sonuclar": [
            {"no": no, "sayfa": c["page"], "sayfa_son": c["page_end"], "bolum": c["section"],
             "kodlar": list(c["codes"]), "skor": round(float(skor), 4), "metin": c["text"]}
            for no, (skor, c) in enumerate(sonuclar, start=1)
        ],
    }


# ------------------------------------------------------------- şemalar ve dağıtıcı
FONKSIYONLAR = {
    "get_risk_score": get_risk_score,
    "get_customer_info": get_customer_info,
    "get_transaction_history": get_transaction_history,
    "search_risk_policy": search_risk_policy,
}

TOOL_SCHEMAS = [
    {
        "name": "get_risk_score",
        "description": (
            "Tek bir banka işlemi için deterministik risk motorunu çalıştırır ve risk skorunu (0-100), "
            "etiketi (normal/suspicious), nedenleri ve kural kimliklerini döner. Risk skorunu kendin tahmin etme, "
            "bu aracı kullan. Hesap bulunamazsa ya da argüman geçersizse 'error' alanı döner."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "account_id": {"type": "integer", "description": "İşlemin yapıldığı hesap numarası"},
                "amount": {"type": "number", "description": "İşlem tutarı"},
                "status": {"type": "string", "enum": ["OK", "FAILED"], "description": "İşlem durumu"},
                "channel": {"type": "string", "enum": ["Web", "Mobile", "ATM", "Branch"], "description": "İşlem kanalı"},
                "is_international": {"type": "integer", "enum": [0, 1], "description": "Yurtdışı işlemse 1, değilse 0"},
            },
            "required": ["account_id", "amount", "status", "channel", "is_international"],
        },
    },
    {
        "name": "get_customer_info",
        "description": (
            "Bir müşterinin kayıtlı bilgilerini döner: segment, şehir, risk bandı, kayıt tarihi ve hesapları. "
            "Müşteri bilgisini uydurma, bu aracı kullan. Müşteri bulunamazsa 'error' alanı döner."
        ),
        "input_schema": {
            "type": "object",
            "properties": {"customer_id": {"type": "integer", "description": "Müşteri numarası"}},
            "required": ["customer_id"],
        },
    },
    {
        "name": "get_transaction_history",
        "description": (
            "Bir müşterinin tüm hesaplarındaki işlemleri döner (tutar, kanal, durum, ülke vb.). Her işlemle birlikte "
            "deterministik risk skoru, etiketi ve kural kimlikleri de gelir. En riskli işlemi bulmak için işlemleri "
            f"tek tek get_risk_score ile hesaplatma: sort_by='risk' ver. En fazla {MAKS_LIMIT} işlem döner. "
            "Müşteri bulunamazsa 'error' alanı döner."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "customer_id": {"type": "integer", "description": "Müşteri numarası"},
                "limit": {"type": "integer", "minimum": 1, "maximum": MAKS_LIMIT, "default": VARSAYILAN_LIMIT,
                          "description": "Kaç işlem döneceği"},
                "sort_by": {"type": "string", "enum": SIRALAMALAR, "default": "recent",
                            "description": "'recent': en yeni işlemler önce, 'risk': en yüksek risk skoru önce"},
            },
            "required": ["customer_id"],
        },
    },
    {
        "name": "search_risk_policy",
        "description": (
            "MASAK Şüpheli İşlem Bildirim Rehberi'nde (bankalar) arama yapar ve sorguya en yakın rehber parçalarını "
            "(sayfa, kayıt kodları, metin) döner. Rehberde ne yazdığını söylemek için bu aracı kullan, kendi bilginle "
            "cevap verme. Bu araç yalnızca arar, cevap yazmaz: dönen parçalar sorunla ilgili değilse rehberde "
            "bulamadığını söyle. Sorguyu rehberin diliyle (Türkçe, konu odaklı) yaz."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "maxLength": MAKS_SORGU_UZUNLUGU, "description": "Rehberde aranacak konu ya da soru"},
                "k": {"type": "integer", "minimum": 1, "maximum": MAKS_K, "default": VARSAYILAN_K,
                      "description": "Kaç rehber parçası döneceği"},
            },
            "required": ["query"],
        },
    },
]


def tool_calistir(ad, girdi):
    """LLM'in istediği aracı adıyla bulup çalıştırır. Hiçbir durumda istisna fırlatmaz, dict döner."""
    fonksiyon = FONKSIYONLAR.get(ad)
    if fonksiyon is None:
        return {"error": f"'{ad}' adında bir araç yok. Kullanılabilir araçlar: {', '.join(FONKSIYONLAR)}"}
    if not isinstance(girdi, dict):
        return {"error": "Geçersiz argüman: girdi bir nesne (dict) olmalı"}
    try:
        return fonksiyon(**girdi)
    except TypeError as e:  # eksik ya da fazla argüman adı
        return {"error": f"Geçersiz argüman: {e}"}
    except Exception as e:  # beklenmeyen hata: sunucuyu düşürme, LLM'e kısa bilgi ver, ayrıntı log'a
        logger.exception("Araç çalışırken beklenmeyen hata: %s", ad)
        return {"error": f"Araç çalışırken beklenmeyen hata ({type(e).__name__})"}
