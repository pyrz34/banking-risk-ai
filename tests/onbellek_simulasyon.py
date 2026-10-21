"""Gün 20c: açıklama önbelleği isabet oranı SİMÜLASYONU (Claude yok, ücretsiz). Çalıştır: python tests\\onbellek_simulasyon.py
Veri setindeki her işlem bir /explain-risk isteği olsun (kural tetikleyenler); aynı anahtarı paylaşanlar önbellekten gelir.
Üç anahtar tasarımı karşılaştırılır:
  A) etiket + rule_ids                              (ilk plan)
  B) etiket + skor + rule_ids + z'li neden metinleri (Gün 19'daki hâl)
  C) şimdiki: etiket + skor + rule_ids + z'siz nedenler (investigation_service.aciklama_anahtari)
İsabet üst sınırı = 1 - farklı_anahtar / istek_sayısı. Her anahtarın ilk görülmesi bir Claude çağrısı (ıska), gerisi isabet.
DİKKAT: önbellek sınırsız ve her işlem bir kez soruluyor varsayılır; gerçek trafik başka dağılır. Bir ÜST SINIR ve
karşılaştırma aracıdır, gerçek isabet oranı değil. Sadece veri setinin kural kümesi çeşitliliğini gösterir.
"""
import collections
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import investigation_service as svc  # noqa: E402


def risk_sozlukleri(df, motor):
    """DataFrame (amount_z'li) -> kural tetikleyen her işlem için RiskEngine.calculate benzeri sözlük."""
    sonuc = []
    for satir in df.to_dict("records"):
        kurallar = motor._triggered_rules(satir)
        if not kurallar:
            continue
        skor = min(sum(p for p, _, _ in kurallar), 100)
        sonuc.append({"risk_score": skor, "risk_label": motor.get_label(skor),
                      "reasons": [f"{n} (+{p})" for p, n, _ in kurallar], "rule_ids": [i for _, _, i in kurallar]})
    return sonuc


def anahtar_a(r):
    return (r["risk_label"], tuple(r["rule_ids"]))


def anahtar_b(r):
    return (r["risk_label"], r["risk_score"], tuple(r["rule_ids"]), tuple(r["reasons"]))


ANAHTARLAR = (("A plan (etiket+rule_ids)", anahtar_a),
              ("B Gün 19 (+skor+z'li neden)", anahtar_b),
              ("C şimdiki (+skor+z'siz neden)", svc.aciklama_anahtari))


def isabet_ust_siniri(anahtarlar):
    """Anahtar listesi (istek akışı) -> (farklı_anahtar, istek, isabet_oranı). Boş akış ValueError."""
    anahtarlar = list(anahtarlar)
    if not anahtarlar:
        raise ValueError("istek akışı boş")
    farkli = len(set(anahtarlar))
    return farkli, len(anahtarlar), 1 - farkli / len(anahtarlar)


def tablo(riskler, claude_maliyeti_usd=None):
    """riskler: sözlük listesi. Her tasarım için satır döner. Maliyet verilirse 'Claude çağrısı x maliyet' sütunu dolar."""
    satirlar = ["| Anahtar | Farklı anahtar (= Claude çağrısı) | İstek | İsabet üst sınırı | Tahmini USD |", "|---|---|---|---|---|"]
    for ad, f in ANAHTARLAR:
        farkli, n, oran = isabet_ust_siniri(f(r) for r in riskler)
        usd = "-" if claude_maliyeti_usd is None else f"{farkli * claude_maliyeti_usd:.4f}"
        satirlar.append(f"| {ad} | {farkli} | {n} | %{oran * 100:.1f} | {usd} |")
    return "\n".join(satirlar)


def main():
    import pandas as pd

    from risk_engine import VERI_DOSYASI, RiskEngine

    motor = RiskEngine()
    sayfalar = pd.read_excel(VERI_DOSYASI, sheet_name=None)
    df = motor.add_features(sayfalar["transactions"], sayfalar["accounts"], sayfalar["customers"])
    tum = risk_sozlukleri(df, motor)
    supheli = [r for r in tum if r["risk_label"] == "suspicious"]
    try:
        maliyet = float(os.environ["RAG_CAGRI_USD"])
    except (KeyError, ValueError):
        maliyet = None
    cikti = ["# Açıklama önbelleği simülasyonu\n",
             "Üretildi: `python tests\\onbellek_simulasyon.py`. Her işlem bir /explain-risk isteği sayıldı (Claude yok). "
             "Üst sınırdır, gerçek isabet oranı değildir (bkz. betiğin başı).\n",
             f"## Kural tetikleyen tüm işlemler ({len(tum)})\n", tablo(tum, maliyet),
             f"\n## Yalnız suspicious ({len(supheli)})\n", tablo(supheli, maliyet),
             "\nUSD sütunu yalnız `RAG_CAGRI_USD` (RAG'li bir açıklamanın tahmini maliyeti) verilirse dolar gösterir.\n"]
    metin = "\n".join(cikti)
    yol = os.path.join(KOK, "docs", "ONBELLEK_SIMULASYON.md")
    with open(yol, "w", encoding="utf-8") as f:
        f.write(metin)
    print(metin + f"\nYazıldı: {yol}")


if __name__ == "__main__":
    main()
