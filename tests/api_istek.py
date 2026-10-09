import requests

URL = "http://127.0.0.1:8000/predict-risk"


def dene(isim, paket, beklenen_kod, beklenen_etiket=None):
    cevap = requests.post(URL, json=paket)
    tamam = cevap.status_code == beklenen_kod
    if beklenen_etiket is not None:
        tamam = tamam and cevap.json()["risk_label"] == beklenen_etiket
    print(
        "GEÇTİ" if tamam else "KALDI", "-", isim, "->", cevap.status_code, cevap.json()
    )
    return tamam


temel = {
    "account_id": 1,
    "amount": 950000,
    "status": "OK",
    "channel": "Web",
    "is_international": 1,
}

sonuclar = [
    dene("yüksek tutar + yurtdışı + web", temel, 200, "suspicious"),
    dene(
        "başarısız + yurtdışı",
        {**temel, "amount": 100, "status": "FAILED", "channel": "ATM"},
        200,
        "suspicious",
    ),
    dene(
        "sıradan işlem",
        {**temel, "amount": 100, "is_international": 0, "channel": "ATM"},
        200,
        "normal",
    ),
    dene("olmayan hesap", {**temel, "account_id": 999999}, 404),
    dene("tutar sayı değil", {**temel, "amount": "yüz lira"}, 422),
    dene("geçersiz kanal", {**temel, "channel": "Telefon"}, 422),
    dene("eksik alan", {"account_id": 1, "amount": 100}, 422),
]
print(f"\n{sum(sonuclar)}/{len(sonuclar)} test geçti")
