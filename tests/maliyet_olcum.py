"""Gün 20: maliyet ölçümü (GERÇEK Claude, küçük para harcar). Çalıştır:
    python tests\\maliyet_olcum.py [--tekrar N] [--ajan]          (N: 1-5, varsayılan 3)
İsteğe bağlı dolar sütunu için önce:  $env:GIRDI_FIYAT_1M="0.10"; $env:CIKTI_FIYAT_1M="0.50"   (fiyatı resmi sayfadan teyit et)

Aynı işlemi (skor 70, 3 kural) şu yollardan açıklatıp token ve süreyi ölçer:
  1) RAG'siz      : Claude'a sadece skor/etiket/nedenler gider (rehber yok)
  2) RAG'li       : aynı + kural başına rehberden gelen kaynaklar (/explain-risk'in yaptığı)
  3) RAG'li, önbellekten : aynı işlem ikinci kez, açıklama önbelleğinden (Claude'a gitmez)
  --ajan ile ek olarak: 4) müşteri incelemesi ıska  5) aynı inceleme önbellekten

Sonuç docs\\MALIYET_OLCUM.md dosyasına yazılır.
DİKKAT, ne ölçülür / ölçülmez:
  - RAG'siz ve RAG'li çağrıların SİSTEM İSTEMLERİ farklıdır (RAG'liyi kaynak kuralları da uzatır). Fark yalnız
    'rehber verisi' farkı değil, 'rehber verisi + onu kullanma kuralları' farkıdır.
  - Çıktı tokenlerine düşünme (thinking) tokenleri dahil, aynı girdiye her seferinde aynı sayı gelmez: min/medyan/maks verilir.
  - Tek bir işlem, birkaç tekrar: bir ortalama değil bir büyüklük sırası. Önbellek isabet ORANI burada ölçülmez (trafik gerekir).
"""
import os
import statistics
import sys
import time

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import agent_trace  # noqa: E402
import rag_cevap  # noqa: E402
import risk_rag  # noqa: E402
from tools import banking_tools as bt  # noqa: E402

ORNEK_ISLEM = dict(account_id=2, amount=14717, status="OK", channel="Web", is_international=1)
CIKTI_DOSYASI = os.path.join(KOK, "docs", "MALIYET_OLCUM.md")

SISTEM_RAGSIZ = (
    "Sen bir banka operasyon risk analistisin. Sana bir işlemin risk skoru, etiketi ve tetiklenen kurallar verilecek. Kurallar:\n"
    "1. Skor, etiket ve tetiklenen kurallar dışında yeni bir neden uydurma.\n"
    "2. İlk cümlede işlemin bu skoru neden aldığını tetiklenen kurallarla açıkla.\n"
    "3. Hukuki hüküm verme ('suçtur', 'bildirilmelidir' deme). Etiket suspicious ise 'incelenmesi önerilir' de.\n"
    "4. Sade Türkçe yaz, en fazla 5 cümle."
)


def risk_mesaji(risk):
    kurallar = "\n".join(f"- {kid}: {neden}" for kid, neden in zip(risk["rule_ids"], risk["reasons"]))
    return (f"RİSK SONUCU:\nSkor: {risk['risk_score']}\nEtiket: {risk['risk_label']}\nTetiklenen kurallar:\n{kurallar}")


def _kullanim(usage):
    return {"girdi": int(usage.input_tokens), "cikti": int(usage.output_tokens)}


def olc_ragsiz(risk, claude, saat=time.perf_counter):
    t0 = saat()
    c = claude.messages.create(model=rag_cevap.MODEL, max_tokens=risk_rag.MAKS_TOKEN, system=SISTEM_RAGSIZ,
                               messages=[{"role": "user", "content": risk_mesaji(risk)}])
    ms = round((saat() - t0) * 1000)
    metin = "".join(b.text for b in c.content if b.type == "text").strip()
    if not metin:
        raise RuntimeError(f"RAG'siz cevap boş (stop_reason={c.stop_reason})")
    return {**_kullanim(c.usage), "sure_ms": ms}


def olc_ragli(risk, rag_getir, claude, saat=time.perf_counter):
    t0 = saat()
    s = risk_rag.aciklama_uret_rag(risk, rag_getir, claude=claude)
    ms = round((saat() - t0) * 1000)
    return {**_kullanim(s["usage"]), "sure_ms": ms}


def olc_onbellek_isabet(risk, rag_getir, claude, tekrar, aciklama_onbellekli, saat=time.perf_counter):
    """Önce bir ıska (gerçek çağrı, önbelleği doldurur), sonra `tekrar` isabet. Isabetler Claude'a gitmez: 0 token."""
    aciklama_onbellekli(risk, rag_getir, claude)
    sonuc = []
    for _ in range(tekrar):
        t0 = saat()
        _, onbellekten = aciklama_onbellekli(risk, rag_getir, claude)
        ms = (saat() - t0) * 1000
        if not onbellekten:
            raise RuntimeError("Beklenen önbellek isabeti olmadı (anahtar tutarsız?)")
        sonuc.append({"girdi": 0, "cikti": 0, "sure_ms": round(ms, 2)})
    return sonuc


def ozet(olcumler):
    """[{girdi, cikti, sure_ms}, ...] -> medyan/min/maks özeti."""
    if not olcumler:
        raise ValueError("ölçüm yok")
    g = [o["girdi"] for o in olcumler]
    c = [o["cikti"] for o in olcumler]
    s = [o["sure_ms"] for o in olcumler]
    return {"n": len(olcumler), "girdi_med": statistics.median(g), "cikti_med": statistics.median(c),
            "girdi_aralik": (min(g), max(g)), "cikti_aralik": (min(c), max(c)), "sure_med_ms": statistics.median(s)}


def usd(o, girdi_1m, cikti_1m):
    return agent_trace.maliyet_usd({"girdi": o["girdi_med"], "cikti": o["cikti_med"]}, girdi_1m, cikti_1m)


def sure_metni(ms):
    return f"{ms:g} ms" if ms < 1000 else f"{ms / 1000:.1f} sn"


def tablo_md(satirlar, girdi_1m=None, cikti_1m=None):
    """satirlar: [(ad, ozet_sozlugu)]. Fiyat yoksa dolar sütunu '-' (uydurma sayı üretmeyiz)."""
    ust = ["| Yol | n | Girdi token (medyan, aralık) | Çıktı token (medyan, aralık) | Süre (medyan) | Tahmini USD (medyan) |",
           "|---|---|---|---|---|---|"]
    for ad, o in satirlar:
        d = usd(o, girdi_1m, cikti_1m)
        ust.append(f"| {ad} | {o['n']} | {o['girdi_med']:g} ({o['girdi_aralik'][0]}-{o['girdi_aralik'][1]}) | "
                   f"{o['cikti_med']:g} ({o['cikti_aralik'][0]}-{o['cikti_aralik'][1]}) | "
                   f"{sure_metni(o['sure_med_ms'])} | {'-' if d is None else f'{d:.6f}'} |")
    return "\n".join(ust)


def tekrar_oku(argv):
    tekrar, ajan = 3, False
    a = list(argv)
    while a:
        x = a.pop(0)
        if x == "--ajan":
            ajan = True
        elif x == "--tekrar":
            try:
                tekrar = int(a.pop(0))
            except (IndexError, ValueError):
                raise SystemExit("--tekrar bir tam sayı ister (1-5)")
            if not 1 <= tekrar <= 5:
                raise SystemExit("--tekrar 1 ile 5 arasında olmalı")
        else:
            raise SystemExit(f"Bilinmeyen argüman: {x}. Kullanım: python tests\\maliyet_olcum.py [--tekrar N] [--ajan]")
    return tekrar, ajan


def main(argv):
    tekrar, ajan = tekrar_oku(argv)
    import investigation_service as svc
    from api import rag_getir

    risk = bt.get_risk_score(ORNEK_ISLEM["account_id"], ORNEK_ISLEM["amount"], ORNEK_ISLEM["status"],
                             ORNEK_ISLEM["channel"], ORNEK_ISLEM["is_international"])
    if "error" in risk or not risk["reasons"]:
        raise SystemExit(f"Örnek işlem beklenen riski üretmedi: {risk}")
    print(f"Örnek işlem: skor {risk['risk_score']}, kurallar {risk['rule_ids']}")
    claude = rag_cevap._claude()
    print("Rehber modeli ısıtılıyor (ilk yükleme 6-10 sn)...")
    rag_getir()

    satirlar = []
    print(f"RAG'siz x{tekrar} ...")
    satirlar.append(("RAG'siz açıklama", ozet([olc_ragsiz(risk, claude) for _ in range(tekrar)])))
    print(f"RAG'li x{tekrar} ...")
    satirlar.append(("RAG'li açıklama (/explain-risk)", ozet([olc_ragli(risk, rag_getir, claude) for _ in range(tekrar)])))
    print("Önbellek isabeti (1 gerçek çağrı + isabetler) ...")
    svc.ACIKLAMA_ONBELLEK.temizle()
    satirlar.append(("RAG'li açıklama, önbellekten",
                     ozet(olc_onbellek_isabet(risk, rag_getir, claude, tekrar, svc.aciklama_onbellekli))))
    if ajan:
        print("Müşteri incelemesi (ıska ve isabet) ...")
        svc.RAPOR_ONBELLEK.temizle()
        r1 = svc.incele_servis(1, rag_getir, yenile=True)
        r2 = svc.incele_servis(1, rag_getir)
        if r1["rapor_kaynagi"] != "ajan" or not r2["onbellekten"]:
            raise SystemExit(f"Ajan ölçümü beklenen yolu izlemedi: {r1['rapor_kaynagi']}, onbellekten={r2['onbellekten']}")
        iz = r1["iz_ozeti"]
        satirlar.append(("Müşteri incelemesi (ajan), ıska",
                         ozet([{"girdi": iz["girdi_token"], "cikti": iz["cikti_token"], "sure_ms": r1["sure_ms"]}])))
        satirlar.append(("Müşteri incelemesi (ajan), önbellekten",
                         ozet([{"girdi": 0, "cikti": 0, "sure_ms": r2["sure_ms"]}])))

    g, c = agent_trace.fiyatlar_env()
    tablo = tablo_md(satirlar, g, c)
    fiyat = ("Fiyat: girdi {} / çıktı {} USD (1M token)".format(g, c) if g is not None
             else "Fiyat verilmedi (GIRDI_FIYAT_1M / CIKTI_FIYAT_1M): dolar sütunu boş")
    metin = (f"# Maliyet ölçümü\n\nÜretildi: `python tests\\maliyet_olcum.py`. Örnek işlem: skor {risk['risk_score']}, "
             f"kurallar {', '.join(risk['rule_ids'])}. Model: `{rag_cevap.MODEL}`. {fiyat}.\n\n{tablo}\n\n"
             "Notlar: RAG'siz ve RAG'li yolların sistem istemleri farklıdır (fark = rehber verisi + onu kullanma kuralları). "
             "Çıktı tokenlerine düşünme tokenleri dahildir. Tek işlem, az tekrar: büyüklük sırasıdır, ortalama değil. "
             "Önbellek isabet oranı gerçek trafik olmadan ölçülemez; burada yalnız bir isabetin maliyeti ölçüldü.\n")
    os.makedirs(os.path.dirname(CIKTI_DOSYASI), exist_ok=True)
    with open(CIKTI_DOSYASI, "w", encoding="utf-8") as f:
        f.write(metin)
    print("\n" + tablo + f"\n\n{fiyat}\nYazıldı: {CIKTI_DOSYASI}")


if __name__ == "__main__":
    main(sys.argv[1:])
