"""Gün 13: RAG DEĞERLENDİRME TABLOSU. Amaç: RAG'in 'çalıştığını' değil, NEREDE HATA YAPTIĞINI görmek.
Çalıştır: python tests\\rag_degerlendirme.py   (gerçek e5 + gerçek Claude çağrısı; 22 soru, küçük maliyet)

Sorular yeni yazılmadı: rag_cevap_testi.py (AYAR seti: üzerinde prompt/chunk ayarı yaptık, skoru şişik)
ve held_out_testi.py (HELD-OUT seti: ayar yapılmadan önce yazıldı) içindeki soruları kullanır. Tablo iki kümeyi AYRI sayar.

Her soru için ölçülenler:
  Arama      : beklenen bilgi çekilen 5 chunk'tan birinde var mı (+ kaçıncı sırada, 5 chunk'ın kaçı alakalı)
  Cevap      : cevapta beklenen içerik var mı, sadece 'bulamadım' demedi mi
  Dayanaklı  : cevap [n] ile atıf yapıyor mu, atıf yaptığı chunk'lar beklenen bilgiyi GERÇEKTEN içeriyor mu
               (DİKKAT: bu otomatik bir vekil ölçü; cümle cümle dayanak kontrolü değil, onu elle yap: 'elle_not' sütunu)
  Hata türü  : aşağıdaki HATA_TURLERI'nden biri

Çıktılar: docs\\RAG_EVAL.md (commit edilecek), data\\rag_degerlendirme.csv (tam cevaplar; excel'de aç).
"""
import csv
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from rag_cevap import BULAMADIM, cevapla  # noqa: E402
from rag_index import BASE_DIR, indeks_olustur, modeli_yukle  # noqa: E402
from risk_rag import atif_numaralari  # noqa: E402

import held_out_testi  # noqa: E402
import rag_cevap_testi  # noqa: E402

HATA_TURLERI = {
    "ARAMA_KACTI": "Beklenen bilgi çekilen chunk'larda yok (sorun arama/chunklamada)",
    "MODEL_REDDETTI": "Bilgi chunk'larda VARDI ama model 'bulamadım' dedi (sorun prompt/model)",
    "CEVAP_EKSIK_YANLIS": "Model cevap verdi ama beklenen içerik cevapta yok",
    "ATIF_YOK": "Cevap doğru ama hiçbir [n] atfı yok (doğrulanamaz)",
    "ATIF_GECERSIZ": "Atıf numarası olmayan bir kaynağı gösteriyor",
    "ATIF_YANLIS_KAYNAK": "Atıf yaptığı chunk'lar beklenen bilgiyi içermiyor (dayanak şüpheli)",
    "RED_ARTI_ILGILI_BILGI": "Cevapsız soruda 'bulamadım' dedi ama yanına ilgili bilgi de yazdı (elle bak: uydurma mı, ilgisiz mi)",
    "UYDURMA_RISKI": "Cevapsız soruda 'bulamadım' demeden cevap yazdı (hallucination riski)",
}


def norm(metin):
    return re.sub(r"\s+", "", metin.lower())


def sadece_bulamadim(cevap):
    return rag_cevap_testi.sadece_bulamadim(cevap)


def degerlendir_cevapli(kaynaklar, cevap, beklenen_kaynak, beklenen_cevap):
    """kaynaklar: cevapla()['kaynaklar']. Döndürür: {arama, ilk_sira, alakali, cevap_ok, atif, dayanakli, hata}."""
    alakali_nolar = [k["no"] for k in kaynaklar if norm(beklenen_kaynak) in norm(k["metin"])]
    arama = bool(alakali_nolar)
    red = sadece_bulamadim(cevap)
    icerik = any(norm(x) in norm(cevap) for x in beklenen_cevap)
    cevap_ok = icerik and not red
    atif = sorted(atif_numaralari(cevap))
    gecerli = bool(atif) and all(1 <= n <= len(kaynaklar) for n in atif)
    dayanakli = cevap_ok and gecerli and any(n in alakali_nolar for n in atif)

    if red:
        hata = "MODEL_REDDETTI" if arama else "ARAMA_KACTI"
    elif not icerik:
        hata = "ARAMA_KACTI" if not arama else "CEVAP_EKSIK_YANLIS"
    elif not atif:
        hata = "ATIF_YOK"
    elif not gecerli:
        hata = "ATIF_GECERSIZ"
    elif not dayanakli:
        hata = "ATIF_YANLIS_KAYNAK"
    else:
        hata = "YOK"
    return {"arama": arama, "ilk_sira": alakali_nolar[0] if alakali_nolar else None,
            "alakali": len(alakali_nolar), "cevap_ok": cevap_ok, "atif": atif,
            "dayanakli": dayanakli, "hata": hata}


def degerlendir_cevapsiz(cevap):
    """Rehberde olmayan soru: doğrusu sadece 'bulamadım' demek."""
    if sadece_bulamadim(cevap):
        return {"arama": None, "ilk_sira": None, "alakali": None, "cevap_ok": True,
                "atif": [], "dayanakli": True, "hata": "YOK"}
    hata = "RED_ARTI_ILGILI_BILGI" if BULAMADIM.lower() in cevap.lower() else "UYDURMA_RISKI"
    return {"arama": None, "ilk_sira": None, "alakali": None, "cevap_ok": False,
            "atif": sorted(atif_numaralari(cevap)), "dayanakli": None, "hata": hata}


def soru_listesi():
    """Mevcut test setlerinden birleşik liste: [(kume, tur, soru, beklenen_kaynak, beklenen_cevap_tuple), ...]"""
    liste = []
    for soru, bek_k, bek_c in rag_cevap_testi.CEVAPLI:
        liste.append(("ayar", "cevaplı", soru, bek_k, (bek_c,)))
    for soru in rag_cevap_testi.CEVAPSIZ:
        liste.append(("ayar", "cevapsız", soru, "", ()))
    for soru, bek_k, bek_c in held_out_testi.CEVAPLI:
        liste.append(("held-out", "cevaplı", soru, bek_k, bek_c))
    for soru in held_out_testi.CEVAPSIZ:
        liste.append(("held-out", "cevapsız", soru, "", ()))
    return liste


def isaret(v, bos="—"):
    return bos if v is None else ("✓" if v else "✗")


def hucre(metin, n=70):
    metin = re.sub(r"\s+", " ", metin).replace("|", "/")
    return metin if len(metin) <= n else metin[: n - 1] + "…"


def ozet_satirlari(satirlar):
    cikti = []
    for kume in ("ayar", "held-out"):
        cv = [s for s in satirlar if s["kume"] == kume and s["tur"] == "cevaplı"]
        cs = [s for s in satirlar if s["kume"] == kume and s["tur"] == "cevapsız"]
        ad = "AYAR seti (ayar yapıldı, skor şişik)" if kume == "ayar" else "HELD-OUT seti (ayar yapılmadı)"
        cikti.append(f"**{ad}**")
        cikti.append(f"- Cevaplı sorular ({len(cv)}): arama {sum(s['arama'] for s in cv)}/{len(cv)}, "
                     f"cevap {sum(s['cevap_ok'] for s in cv)}/{len(cv)}, "
                     f"dayanaklı {sum(bool(s['dayanakli']) for s in cv)}/{len(cv)}")
        cikti.append(f"- Cevapsız sorular ({len(cs)}): doğru reddetme {sum(s['cevap_ok'] for s in cs)}/{len(cs)}")
        cikti.append("")
    return cikti


def markdown_uret(satirlar):
    m = ["# RAG Değerlendirme (Gün 13)", "",
         "Otomatik üretildi: `python tests\\rag_degerlendirme.py`. ✓ doğru, ✗ hata, — uygulanmaz, ? elle bakılmalı.",
         "`Dayanaklı` otomatik bir vekil ölçüdür (atıf var + atıf yapılan chunk beklenen bilgiyi içeriyor); "
         "cümle cümle dayanak kontrolü değildir.", "", "## Özet", ""]
    m += ozet_satirlari(satirlar)
    m += ["## Tablo", "",
          "| # | Küme | Soru | Arama | Cevap | Dayanaklı | Atıf | Hata türü |",
          "|---|------|------|-------|-------|-----------|------|-----------|"]
    for s in satirlar:
        atif = ",".join(f"[{n}]" for n in s["atif"]) or "-"
        dy = "?" if s["dayanakli"] is None else isaret(s["dayanakli"])
        m.append(f"| {s['no']} | {s['kume']} | {hucre(s['soru'])} | {isaret(s['arama'])} | "
                 f"{isaret(s['cevap_ok'])} | {dy} | {atif} | {s['hata']} |")
    m += ["", "## Hata türleri", ""]
    sayac = Counter(s["hata"] for s in satirlar if s["hata"] != "YOK")
    if not sayac:
        m.append("Otomatik ölçüde hata yok. Yine de cevapları elle oku (CSV).")
    for hata, adet in sayac.most_common():
        m.append(f"### {hata} ({adet}): {HATA_TURLERI[hata]}")
        for s in satirlar:
            if s["hata"] == hata:
                m.append(f"- #{s['no']} ({s['kume']}) {hucre(s['soru'], 110)}")
                m.append(f"  - cevap: {hucre(s['cevap'], 260)}")
        m.append("")
    m += ["## Elle inceleme notları (sen doldur)", "",
          "- Cevaplardaki kaynakta olmayan cümle var mı? (CSV'de `cevap` ile `kaynak_metinleri`ni yan yana oku)",
          "- `RED_ARTI_ILGILI_BILGI` olanlarda ek bilgi kaynakta gerçekten yazıyor mu?",
          ""]
    return "\n".join(m)


def csv_yaz(yol, satirlar):
    alanlar = ["no", "kume", "tur", "soru", "beklenen_bilgi", "kaynak_sayfalari", "kaynak_kodlari",
               "alakali_chunk_sayisi", "ilk_alakali_sira", "arama_ok", "cevap", "cevap_ok", "atif_edilen",
               "dayanakli", "hata", "kaynak_metinleri", "elle_not"]
    with open(yol, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=alanlar, delimiter=";")
        w.writeheader()
        for s in satirlar:
            w.writerow({
                "no": s["no"], "kume": s["kume"], "tur": s["tur"], "soru": s["soru"],
                "beklenen_bilgi": s["beklenen"], "kaynak_sayfalari": s["sayfalar"], "kaynak_kodlari": s["kodlar"],
                "alakali_chunk_sayisi": s["alakali"], "ilk_alakali_sira": s["ilk_sira"],
                "arama_ok": s["arama"], "cevap": s["cevap"], "cevap_ok": s["cevap_ok"],
                "atif_edilen": ",".join(map(str, s["atif"])), "dayanakli": s["dayanakli"], "hata": s["hata"],
                "kaynak_metinleri": s["kaynak_metinleri"], "elle_not": "",
            })


def main():
    model = modeli_yukle()
    chunklar, vektorler = indeks_olustur(model)
    satirlar = []
    girdi = cikti = 0
    for no, (kume, tur, soru, bek_k, bek_c) in enumerate(soru_listesi(), start=1):
        s = cevapla(soru, chunklar, vektorler, model)
        girdi += s["kullanim"].input_tokens
        cikti += s["kullanim"].output_tokens
        d = (degerlendir_cevapli(s["kaynaklar"], s["cevap"], bek_k, bek_c) if tur == "cevaplı"
             else degerlendir_cevapsiz(s["cevap"]))
        d.update({
            "no": no, "kume": kume, "tur": tur, "soru": soru,
            "beklenen": bek_k or "(rehberde yok: 'bulamadım' demeli)", "cevap": s["cevap"],
            "sayfalar": ",".join(str(k["sayfa"]) for k in s["kaynaklar"]),
            "kodlar": " | ".join(",".join(k["kodlar"]) or "-" for k in s["kaynaklar"]),
            "kaynak_metinleri": "\n\n".join(f"[{k['no']}] {k['metin']}" for k in s["kaynaklar"]),
        })
        satirlar.append(d)
        print(f"[{no:2}/{len(soru_listesi())}] {kume:8} {tur:8} arama {isaret(d['arama'])} cevap {isaret(d['cevap_ok'])} "
              f"hata={d['hata']} | {hucre(soru, 60)}")

    md = markdown_uret(satirlar)
    os.makedirs(os.path.join(BASE_DIR, "docs"), exist_ok=True)
    md_yol = os.path.join(BASE_DIR, "docs", "RAG_EVAL.md")
    csv_yol = os.path.join(BASE_DIR, "data", "rag_degerlendirme.csv")
    with open(md_yol, "w", encoding="utf-8") as f:
        f.write(md)
    csv_yaz(csv_yol, satirlar)
    print("\n" + "\n".join(ozet_satirlari(satirlar)))
    print(f"Toplam girdi token {girdi}, çıktı token {cikti}")
    print(f"Yazıldı: {md_yol}\nYazıldı: {csv_yol}")


if __name__ == "__main__":
    main()
