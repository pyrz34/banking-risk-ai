"""Gün 16: araçların okuduğu tablolar (müşteri, hesap, işlem) ve diske önbellek.

Excel'den 120.000 işlemi okumak ~10 sn sürüyor, aynı veriyi pickle'dan okumak ~0,1 sn. O yüzden ilk okumada
data/araclar_onbellek.pkl'e yazılır. Önbellek KAYNAK DOSYANIN İMZASINA (boyut + değişme zamanı) bağlı:
Excel değişirse imza tutmaz, önbellek yok sayılıp yeniden üretilir (eski veriyle sessizce çalışma riski yok).
Dosya bozuksa da (yarım yazılmış, sürüm farkı) yeniden üretilir. Yazma önce geçici dosyaya, sonra yer değiştirme (os.replace):
yazma sırasında çökülürse yarım dosya kalmaz.
"""
import os

import pandas as pd

KOK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
VERI_DOSYASI = os.path.join(KOK, "data", "bank_ops_risk_dataset.xlsx")
ONBELLEK_DOSYASI = os.path.join(KOK, "data", "araclar_onbellek.pkl")
SAYFALAR = ["customers", "accounts", "transactions"]

_bellek = {}  # (kaynak, imza) -> tablolar; süreç boyunca bellekte


def imza(yol):
    d = os.stat(yol)
    return (d.st_size, int(d.st_mtime))


def tablolar(kaynak=VERI_DOSYASI, onbellek=ONBELLEK_DOSYASI):
    """Döndürür: {"customers": (customer_id indeksli), "accounts", "transactions"} DataFrame'leri."""
    im = imza(kaynak)
    anahtar = (os.path.abspath(kaynak), im)
    if anahtar in _bellek:
        return _bellek[anahtar]

    veri = None
    if os.path.exists(onbellek):
        try:
            kayit = pd.read_pickle(onbellek)
            if kayit.get("imza") == im and set(SAYFALAR) <= set(kayit):
                veri = kayit
        except Exception:  # bozuk/uyumsuz önbellek: yok say, yeniden üret
            veri = None

    if veri is None:
        s = pd.read_excel(kaynak, sheet_name=SAYFALAR)
        veri = {"imza": im, "customers": s["customers"].set_index("customer_id"),
                "accounts": s["accounts"], "transactions": s["transactions"]}
        gecici = onbellek + ".tmp"
        pd.to_pickle(veri, gecici)
        os.replace(gecici, onbellek)

    _bellek[anahtar] = veri
    return veri
