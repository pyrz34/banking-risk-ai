"""Gün 14: LLM'in çağırabileceği araçlar (tools).

Üç parça var, hepsi bu dosyada ki birbirinden kopmasınlar:
  1. Python fonksiyonu     -> işi GERÇEKTEN yapan kod (deterministik, test edilir)
  2. TOOL_SCHEMAS          -> LLM'e "böyle bir araç var, şu argümanları alır" diyen tanım
  3. tool_calistir()       -> LLM'in istediği aracı adıyla bulup çalıştıran küçük dağıtıcı

LLM fonksiyonu ÇALIŞTIRMAZ. Sadece hangi aracı hangi argümanla istediğini söyler; çalıştıran bizim Python kodumuzdur.
Her araç hata olursa istisna fırlatmaz, {"error": "..."} döner. LLM hatayı da bir sonuç olarak okur.
"""
import logging
import os
import sys
from functools import lru_cache

import pandas as pd
from pydantic import ValidationError

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(KOK, "src")
if SRC not in sys.path:  # python src\tool_calling.py da, testler de çalışsın
    sys.path.insert(0, SRC)

from risk_engine import VERI_DOSYASI  # noqa: E402

logger = logging.getLogger("banking_tools")


def _hata_metni(e):
    """pydantic doğrulama hatasını LLM'in okuyup düzeltebileceği kısa metne çevirir."""
    parcalar = []
    for h in e.errors():
        alan = ".".join(str(x) for x in h["loc"]) or "girdi"
        parcalar.append(f"{alan}: {h['msg']}")
    return "Geçersiz argüman: " + "; ".join(parcalar)


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


@lru_cache(maxsize=1)
def _musteri_tablolari():
    """customers ve accounts sayfaları (transactions'ı okumaz). İlk çağrıda yüklenir, sonra bellekte kalır."""
    s = pd.read_excel(VERI_DOSYASI, sheet_name=["customers", "accounts"])
    return s["customers"].set_index("customer_id"), s["accounts"]


def get_customer_info(customer_id):
    """Müşterinin segmenti, şehri, risk bandı, kayıt tarihi ve hesapları."""
    # bool, int'in alt sınıfı: True == 1 olduğu için ayrıca elenir. 4521.0 gibi float de kabul edilmez.
    if isinstance(customer_id, bool) or not isinstance(customer_id, int):
        return {"error": f"Geçersiz argüman: customer_id tam sayı olmalı (gelen: {customer_id!r})"}
    musteriler, hesaplar = _musteri_tablolari()
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


FONKSIYONLAR = {"get_risk_score": get_risk_score, "get_customer_info": get_customer_info}

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
