"""Gün 20c: önbellek simülasyon betiğinin testi. Çalıştır: python tests\\onbellek_simulasyon_testi.py
Ağ yok, Claude yok, Excel yok (küçük elle yapılmış tablo). Ölçtüğü: betik anahtarları ve oranı doğru hesaplıyor mu.
"""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import investigation_service as svc  # noqa: E402
import onbellek_simulasyon as sim  # noqa: E402
from risk_engine import RiskEngine  # noqa: E402

sonuclar = []


def kontrol(ad, ok, detay=""):
    sonuclar.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {ad}" + (f"  -> {detay}" if detay and not ok else ""))


# isabet üst sınırı
kontrol("Oran: 4 istek, 2 farklı anahtar -> (2, 4, 0.5)", sim.isabet_ust_siniri(["a", "a", "b", "b"]) == (2, 4, 0.5))
kontrol("Oran: hepsi farklı -> 0, hepsi aynı -> 1 - 1/n", sim.isabet_ust_siniri([1, 2, 3])[2] == 0 and sim.isabet_ust_siniri(["x"] * 4)[2] == 0.75)
try:
    sim.isabet_ust_siniri([])
    kontrol("Oran: boş akış ValueError", False)
except ValueError:
    kontrol("Oran: boş akış ValueError", True)

# gerçek motorla küçük tablo: 3 işlem, hepsi web + anomali, farklı z; 1 işlem hiç kural tetiklemez
motor = RiskEngine()
df = pd.DataFrame([
    {"status": "OK", "channel": "Web", "is_international": 1, "amount_z": 3.5},
    {"status": "OK", "channel": "Web", "is_international": 1, "amount_z": 9.1},
    {"status": "OK", "channel": "Mobile", "is_international": 1, "amount_z": 4.2},
    {"status": "OK", "channel": "ATM", "is_international": 0, "amount_z": 0.1},
])
r = sim.risk_sozlukleri(df, motor)
kontrol("Risk sözlükleri: kural tetiklemeyen işlem elenir (4 -> 3), alanlar var",
        len(r) == 3 and set(r[0]) == {"risk_score", "risk_label", "reasons", "rule_ids"} and r[0]["risk_score"] == 70, r)
kontrol("A anahtarı: z ve kanal ayırt etmez (3 işlem, 1 anahtar)", len({sim.anahtar_a(x) for x in r}) == 1)
kontrol("B anahtarı (z'li): her işlem ayrı (3 anahtar)", len({sim.anahtar_b(x) for x in r}) == 3)
kontrol("C anahtarı (şimdiki): z'yi yok sayar ama kanalı ayırır (web/mobile -> 2 anahtar)",
        len({svc.aciklama_anahtari(x) for x in r}) == 2)
kontrol("ANAHTARLAR üçüncüsü gerçekten servisin kendi anahtar fonksiyonu (sapma olmasın)", sim.ANAHTARLAR[2][1] is svc.aciklama_anahtari)

t = sim.tablo(r)
kontrol("Tablo: fiyat yoksa dolar '-', üç satır, oranlar yazılı", t.count("| - |") == 3 and "%66.7" in t and "%0.0" in t and "%33.3" in t, t)
t = sim.tablo(r, 0.01)
kontrol("Tablo: maliyet verilirse 'farklı anahtar x maliyet' (A: 1x0.01, B: 3x0.01)", "0.0100" in t and "0.0300" in t, t)

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
