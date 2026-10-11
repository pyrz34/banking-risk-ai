# PDF ten sayfa sayfa temiz metin çıkarma

import os
import re
import unicodedata

from pypdf import PdfReader

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PDF_YOLU = os.path.join(BASE_DIR, "documents", "masak_rehber.pdf")

# Sayfa 4'ten itibaren her sayfanın tepesinde tekrar eden başlık satırı.
# İçinde belge kodu geçen satırı komple atıyoruz.
BASLIK_DESENI = re.compile(r"MSK-RHB-ŞİB-001-2")


def sayfa_temizle(ham_metin, sayfa_no):
    """Bir sayfanın ham metnini temizler."""
    ham_metin = unicodedata.normalize("NFC", ham_metin)
    satirlar = []
    for satir in ham_metin.splitlines():
        satir = re.sub(r"[ \t]+", " ", satir).strip()  # fazla boşlukları teke indir
        if not satir:
            continue  # boş satırları at
        if BASLIK_DESENI.search(satir):
            continue  # tekrar eden başlık
        if satir == str(sayfa_no):
            continue  # tek başına duran sayfa numarası
        satirlar.append(satir)

    # Satır sonunda tire ile bölünmüş kelimeleri birleştir: "bildi-" + "rim" -> "bildirim"
    birlesik = []
    for satir in satirlar:
        if birlesik and birlesik[-1].endswith("-") and satir[:1].islower():
            birlesik[-1] = birlesik[-1][:-1] + satir
        else:
            birlesik.append(satir)
    return "\n".join(birlesik)


def pdf_yukle(yol=PDF_YOLU):
    """PDF'i okur, [{"page": n, "text": temiz_metin}, ...] döndürür. Boş sayfalar atlanır."""
    okuyucu = PdfReader(yol)
    sayfalar = []
    for i, sayfa in enumerate(okuyucu.pages, start=1):
        metin = sayfa_temizle(sayfa.extract_text() or "", i)
        if metin:
            sayfalar.append({"page": i, "text": metin})
    return sayfalar


if __name__ == "__main__":
    sayfalar = pdf_yukle()
    toplam_kelime = sum(len(s["text"].split()) for s in sayfalar)
    print(f"Dolu sayfa: {len(sayfalar)}  |  toplam kelime: {toplam_kelime}")
    for s in (sayfalar[0], sayfalar[4], sayfalar[38]):
        print(f"\n--- sayfa {s['page']} ({len(s['text'].split())} kelime) ---")
        print(s["text"][:500])
