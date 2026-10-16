"""Gün 13: değerlendirme mantığının testi. Çalıştır: python tests\\rag_degerlendirme_testi.py
Ağ yok, Claude/e5 yok. 'Değerlendirici doğru hata türünü koyuyor mu' sorusunu ölçer
(yoksa değerlendiricinin kendisi güvenilmez olur).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import rag_degerlendirme as rd  # noqa: E402

BEKLENEN_KAYNAK = "yedi iş gün"
BEKLENEN_CEVAP = ("yedi",)


def kaynak(no, metin):
    return {"no": no, "sayfa": 7, "kodlar": [], "skor": 0.8, "metin": metin}


ALAKALI = kaynak(1, "Erteleme süresi yedi iş gününü geçemez.")
ALAKASIZ = kaynak(2, "Faks ile yapılan bildirimler hakkında bilgi.")
KAYNAKLAR = [ALAKALI, ALAKASIZ]

sonuclar = []


def kontrol(ad, ok):
    sonuclar.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {ad}")


def cevapli(cevap, kaynaklar=KAYNAKLAR):
    return rd.degerlendir_cevapli(kaynaklar, cevap, BEKLENEN_KAYNAK, BEKLENEN_CEVAP)


# --- cevaplı sorular ---
d = cevapli("Erteleme yedi iş gününü geçemez [1].")
kontrol("Doğru cevap + doğru atıf: hata YOK, dayanaklı, arama ilk sırada",
        d["hata"] == "YOK" and d["dayanakli"] and d["arama"] and d["ilk_sira"] == 1 and d["alakali"] == 1)

d = cevapli("Rehberde bu bilgiyi bulamadım.", [ALAKASIZ])
kontrol("Chunk'larda bilgi yok + 'bulamadım': ARAMA_KACTI", d["hata"] == "ARAMA_KACTI" and not d["arama"])

d = cevapli("Rehberde bu bilgiyi bulamadım.")
kontrol("Bilgi chunk'ta VAR ama model reddetti: MODEL_REDDETTI (arama değil, model suçlu)",
        d["hata"] == "MODEL_REDDETTI" and d["arama"])

d = cevapli("Erteleme üç gündür [1].")
kontrol("Beklenen içerik cevapta yok (arama tamam): CEVAP_EKSIK_YANLIS", d["hata"] == "CEVAP_EKSIK_YANLIS")

d = cevapli("Erteleme yedi iş gününü geçemez.")
kontrol("Doğru ama atıf yok: ATIF_YOK, dayanaklı değil", d["hata"] == "ATIF_YOK" and not d["dayanakli"])

d = cevapli("Erteleme yedi iş gününü geçemez [7].")
kontrol("Olmayan kaynak numarası: ATIF_GECERSIZ", d["hata"] == "ATIF_GECERSIZ")

d = cevapli("Erteleme yedi iş gününü geçemez [2].")
kontrol("Atıf alakasız chunk'a: ATIF_YANLIS_KAYNAK", d["hata"] == "ATIF_YANLIS_KAYNAK" and not d["dayanakli"])

d = cevapli("Erteleme yedi iş gününü geçemez [1, 2].")
kontrol("[1, 2] biçimi: alakalı chunk atıflar arasında olduğu için dayanaklı", d["hata"] == "YOK" and d["atif"] == [1, 2])

d = rd.degerlendir_cevapli([kaynak(1, "yedi  iş\ngünü")], "Erteleme YEDİ iş günüdür [1].", BEKLENEN_KAYNAK, BEKLENEN_CEVAP)
kontrol("Boşluk/satır sonu/büyük harf farkı eşleşmeyi bozmuyor (pypdf farkları)", d["hata"] == "YOK")

# --- cevapsız sorular ---
d = rd.degerlendir_cevapsiz("Rehberde bu bilgiyi bulamadım.")
kontrol("Cevapsız + sadece 'bulamadım': doğru, hata YOK", d["cevap_ok"] and d["hata"] == "YOK")

d = rd.degerlendir_cevapsiz("Rehberde bu bilgiyi bulamadım. Ancak otomatik yazılımlar vardır [1].")
kontrol("Cevapsız + 'bulamadım' + ilgili bilgi: RED_ARTI_ILGILI_BILGI (yanlış sayılır, elle bakılır)",
        not d["cevap_ok"] and d["hata"] == "RED_ARTI_ILGILI_BILGI" and d["dayanakli"] is None)

d = rd.degerlendir_cevapsiz("Rehber bir yapay zeka modeli önerir.")
kontrol("Cevapsız + 'bulamadım' hiç yok: UYDURMA_RISKI", d["hata"] == "UYDURMA_RISKI" and not d["cevap_ok"])

# --- birleşik liste ve çıktılar ---
liste = rd.soru_listesi()
kontrol("Soru listesi: en az 10 soru, üç küme (ayar, held-out, taze), cevaplı + cevapsız var",
        len(liste) >= 10 and {x[0] for x in liste} == {"ayar", "held-out", "taze"} and {x[1] for x in liste} == {"cevaplı", "cevapsız"})
kontrol("Taze set: en az 5 cevaplı + 3 cevapsız, hiçbiri ayar/held-out sorularıyla aynı değil",
        sum(1 for x in liste if x[0] == "taze" and x[1] == "cevaplı") >= 5
        and sum(1 for x in liste if x[0] == "taze" and x[1] == "cevapsız") >= 3
        and not ({x[2] for x in liste if x[0] == "taze"} & {x[2] for x in liste if x[0] != "taze"}))
kontrol("Cevaplı sorularda beklenen bilgi dolu, cevapsızlarda boş",
        all(bool(x[3]) and bool(x[4]) for x in liste if x[1] == "cevaplı")
        and all(not x[3] and not x[4] for x in liste if x[1] == "cevapsız"))

satir_ok = dict(cevapli("Erteleme yedi iş gününü geçemez [1].") | {
    "no": 1, "kume": "held-out", "tur": "cevaplı", "soru": "Soru | ile\nsatır", "cevap": "cevap", "beklenen": "b",
    "sayfalar": "7", "kodlar": "-", "kaynak_metinleri": "x"})
satir_hata = dict(cevapli("Rehberde bu bilgiyi bulamadım.") | {
    "no": 2, "kume": "ayar", "tur": "cevaplı", "soru": "ikinci", "cevap": "Rehberde bu bilgiyi bulamadım.",
    "beklenen": "b", "sayfalar": "7", "kodlar": "-", "kaynak_metinleri": "x"})
md = rd.markdown_uret([satir_ok, satir_hata])
satirlar_tablo = [s for s in md.splitlines() if s.startswith("| ") and not s.startswith("| #")]
kontrol("Markdown: her soru bir tablo satırı, '|' ve satır sonu hücreyi bozmuyor",
        len(satirlar_tablo) == 2 and all(s.count("|") == 9 for s in satirlar_tablo))
kontrol("Markdown: hata türü bölümü hatalı soruyu listeliyor, hatasızı listelemiyor",
        "### MODEL_REDDETTI (1)" in md and "#2 (ayar)" in md and "#1 (held-out)" not in md)
kontrol("Markdown: özet AYAR ve HELD-OUT'u ayrı sayıyor", "AYAR seti" in md and "HELD-OUT seti" in md)
satir_taze = dict(satir_ok, kume="taze", no=3)
md3 = rd.markdown_uret([satir_ok, satir_hata, satir_taze])
kontrol("Markdown: TAZE set varsa ayrı özetlenir, yoksa özette boş TAZE başlığı çıkmaz",
        "TAZE set" in md3 and "TAZE set" not in md)

# --- taze sorulardaki beklenen ifadeler PDF'te gerçekten var mı (yazım hatası koruması; ağ ve Claude yok) ---
from chunklama import chunkla  # noqa: E402
from pdf_yukle import pdf_yukle  # noqa: E402
_pdf_chunk = " ".join(rd.norm(c["text"]) for c in chunkla(pdf_yukle()))
yok = [x[3] for x in liste if x[0] == "taze" and x[1] == "cevaplı" and rd.norm(x[3]) not in _pdf_chunk]
kontrol(f"Taze sorularda beklenen kaynak ifadesi PDF chunk'larında geçiyor (eksik: {yok})", not yok)
kontrol("Her hata türünün açıklaması var", all(d_ in rd.HATA_TURLERI for d_ in [
    "ARAMA_KACTI", "MODEL_REDDETTI", "CEVAP_EKSIK_YANLIS", "ATIF_YOK", "ATIF_GECERSIZ",
    "ATIF_YANLIS_KAYNAK", "RED_ARTI_ILGILI_BILGI", "UYDURMA_RISKI"]))

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
