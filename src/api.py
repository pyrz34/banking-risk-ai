import os
from typing import Literal

import pandas as pd
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


from risk_engine import BASE_DIR, VERI_DOSYASI, RiskEngine

ONBELLEK_DOSYASI = os.path.join(BASE_DIR, "data", "api_onbellek.pkl")


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


def referans_verisi_yukle():
    # ilk seferde excelden yavaş hesaplicak yavaşlığı gidermek için küçük bir dosyaya kaydedecez
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
    return {"mesaj": "Risk Engine API' ye hoş geldiniz"}


@app.post("/predict-risk", response_model=RiskResponse)
def predict_risk(islem: TransactionRequest):
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
