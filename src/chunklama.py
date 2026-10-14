"""Gün 8 - Adım 2: sayfalardan chunk üretme.

Girdi : pdf_yukle.pdf_yukle()  ->  [{"page": 5, "text": "..."}, ...]
Çıktı : [{"id", "text", "page", "page_end", "section", "codes", "kelime"}, ...]

Kurallar (rehberin yapısına göre):
  1. SK-xx ve T-001-x.y kodlu kısa kayıtlar ASLA bölünmez (bir kod = bir bütün).
     Çok uzun kayıtlar (kanun metni içerenler) bölünür ama her parçanın başına kod satırı tekrar yazılır.
  2. Başlık (1.1, 3.2.1 ...) ve grup başlığı (MÜŞTERİ PROFİLİNE İLİŞKİN TİPLER) bilgisi
     her chunk'ın başına "bölüm" satırı olarak yazılır, çünkü kısa bir kayıt tek başına anlamsız kalır.
  3. Kayıtlar MAKS_KELIME'yi aşmayacak şekilde yan yana paketlenir.
  4. Kayıt olmayan uzun düz yazı satır satır bölünür, chunk'lar arasında 1 satır örtüşme (overlap) olur.
"""

import re

from pdf_yukle import pdf_yukle

ILK_ICERIK_SAYFASI = (
    5  # 1-4: kapak, sürüm tablosu, içindekiler, tablo listesi -> arama gürültüsü
)
MAKS_KELIME = (
    50  # hedef üst sınır (embedding modeli ~128 token görüyor, Türkçede ~70-90 kelime)
)
MIN_KELIME = (
    20  # bundan küçük chunk'ı bölüm değişse bile yeni chunk'a ayırma, birleştir
)

MAKS_ESNEK = 75  # cümle ortasında kesmemek için MAKS_KELIME'yi en fazla bu kadara kadar aşabiliriz (~150 token, e5 sınırı 512)
CUMLE_SONU = (".", "!", "?", ":", ";")

KAYIT_DESENI = re.compile(r"^(SK-\d{2}|T-001-\d+\.\d+)\b")
KOD_DESENI = re.compile(r"\b(?:SK-\d{2}|T-001-\d+\.\d+)\b")
BASLIK_DESENI = re.compile(r"^\d{1,2}(?:\.\d{1,2})*\.? [A-ZÇĞİÖŞÜ]")
BUYUK_HARF = "A-ZÇĞİÖŞÜÂÎÛ"
KUCUK_HARF_DESENI = re.compile(r"[a-zçğıöşüâîû]")


def grup_basligi_mi(satir):
    """Grup başlığı: hiç küçük harf ve rakam yok, en az 5 büyük harf var, kod değil (örn. 'KÂR AMACI GÜTMEYEN ... TİPLER').
    Başlık 2 satıra yayılabiliyor ('... İLİŞKİN' / 'TİPLER'), o yüzden kısa satırlar da kabul."""
    return (
        not KUCUK_HARF_DESENI.search(satir)
        and not re.search(
            r"\d", satir
        )  # 'KK-08 API' gibi kanal/alan kodları grup başlığı değildir
        and len(re.findall(f"[{BUYUK_HARF}]", satir)) >= 5
        and not KOD_DESENI.search(satir)
    )


# tablolarda sayfa başına tekrar eden sütun başlıkları ve tablo altı başlıkları -> gürültü
GURULTU_DESENLERI = [
    re.compile(
        r"^KOD AD AÇIKLAMA İLGİLİ YASAL( DÜZENLEME\(LER\))?$"
    ),  # pypdf sürümüne göre 1 ya da 2 satır
    re.compile(r"^DÜZENLEME\(LER\)$"),
    re.compile(r"^KOD AÇIKLAMA$"),
    re.compile(r"^Tablo \d+ [-–] "),
]


def _kelime(satirlar):
    return sum(len(s.split()) for s in satirlar)


def satirlari_cikar(sayfalar):
    """Sayfaları [(sayfa_no, satır), ...] listesine açar; gürültü satırlarını atar."""
    cikti = []
    for sayfa in sayfalar:
        if sayfa["page"] < ILK_ICERIK_SAYFASI:
            continue
        for satir in sayfa["text"].split("\n"):
            if any(d.search(satir) for d in GURULTU_DESENLERI):
                continue
            cikti.append((sayfa["page"], satir))
    return cikti


def birimlere_ayir(satirlar):
    """Satırları 'birim'lere böler. Birim = bir kayıt (kodlu) ya da bir başlığın altındaki düz yazı.
    Her birim o anki bölüm bilgisini (başlık > grup) taşır."""
    birimler = []
    baslik, grup = "", ""
    simdiki = None
    onceki_grup = False  # bir önceki satır grup başlığıydı mı? (2 satırlık başlıkları birleştirmek için)

    def yeni(tur, sayfa):
        nonlocal simdiki
        simdiki = {
            "tur": tur,
            "satirlar": [],
            "page": sayfa,
            "section": " > ".join(x for x in (baslik, grup) if x),
        }
        birimler.append(simdiki)

    for sayfa, satir in satirlar:
        grup_mu = grup_basligi_mi(satir) and not BASLIK_DESENI.match(satir)
        if grup_mu:
            # önceki satır da grup başlığıysa aynı başlığın devamı: birleştir
            grup = f"{grup} {satir}" if onceki_grup else satir
            yeni(
                "duz", sayfa
            )  # bölüm bilgisi güncellensin diye yeni birim aç (içi boş kalırsa atılır)
            onceki_grup = True
            continue  # grup başlığı metne girmez, sadece bölüm bilgisi olur
        onceki_grup = False
        if KAYIT_DESENI.match(satir):
            yeni("kayit", sayfa)
        elif (
            BASLIK_DESENI.match(satir)
            and len(satir) < 80
            and not satir.endswith((".", ",", ";", ":"))
            or re.match(r"^\d\.\d+\. [A-ZÇĞİÖŞÜ]", satir)
            and len(satir) < 80
        ):
            baslik, grup = satir, ""
            yeni("duz", sayfa)
        elif simdiki is None:
            yeni("duz", sayfa)
        simdiki["satirlar"].append(satir)

    return [b for b in birimler if b["satirlar"]]


def _chunk_olustur(satirlar, sayfa, sayfa_son, bolum):
    govde = "\n".join(satirlar)
    # Chunk zaten başlıkla başlıyorsa bölüm satırı tekrar olur, ekleme
    metin = f"[Bölüm: {bolum}]\n{govde}" if bolum and satirlar[0] != bolum else govde
    return {
        "text": metin,
        "page": sayfa,
        "page_end": sayfa_son,
        "section": bolum,
        "codes": KOD_DESENI.findall(govde),
        "kelime": _kelime(satirlar),
    }


def uzun_birimi_bol(birim):
    """MAKS_KELIME'den uzun birimi satır satır böler, parçalar arasında 1 satır overlap bırakır.
    Kayıtta (kodlu) ilk satır (kod + ad) sonraki parçaların başına da eklenir."""
    ilk_satir = birim["satirlar"][0] if birim["tur"] == "kayit" else None
    parcalar, simdiki = [], []
    for satir in birim["satirlar"]:
        toplam = _kelime(simdiki) + len(satir.split())
        # Limit aşıldıysa kes, AMA son satır cümleyi bitirmiyorsa (nokta vb. yok) cümle bitene kadar devam et.
        # Mutlak üst sınır MAKS_ESNEK: noktasız çok uzun satır dizisi sonsuza uzamasın.
        kes = simdiki and (
            toplam > MAKS_ESNEK
            or (toplam > MAKS_KELIME and simdiki[-1].endswith(CUMLE_SONU))
        )
        if kes:
            parcalar.append(simdiki)
            simdiki = [simdiki[-1]]  # overlap: önceki parçanın son satırı
            if ilk_satir and simdiki[0] != ilk_satir:
                simdiki = [ilk_satir] + simdiki
        simdiki.append(satir)
    if simdiki:
        parcalar.append(simdiki)
    return [{**birim, "satirlar": p} for p in parcalar]


def chunkla(sayfalar):
    birimler = []
    for b in birimlere_ayir(satirlari_cikar(sayfalar)):
        if _kelime(b["satirlar"]) > MAKS_KELIME:
            birimler.extend(uzun_birimi_bol(b))
        else:
            birimler.append(b)

    chunklar, satirlar, sayfa, bolum = [], [], None, ""

    def bosalt():
        nonlocal satirlar, sayfa, bolum
        if satirlar:
            chunklar.append(_chunk_olustur(satirlar, sayfa, son_sayfa, bolum))
        satirlar, sayfa = [], None

    son_sayfa = None
    for b in birimler:
        kelime = _kelime(b["satirlar"])
        sig_miyor = satirlar and _kelime(satirlar) + kelime > MAKS_KELIME
        # Bölüm değişince chunk kapanır. İstisna: ikisi de kısa düz yazıysa birleştir (küçük chunk olmasın).
        # Kodlu kayıtlarda ASLA birleştirme: aksi halde bir grubun kaydı yanlış grup etiketi alır.
        kodlu = bool(satirlar) and (
            b["tur"] == "kayit" or any(KOD_DESENI.search(x) for x in satirlar)
        )
        bolum_degisti = (
            satirlar
            and b["section"] != bolum
            and (_kelime(satirlar) >= MIN_KELIME or kodlu)
        )
        if sig_miyor or bolum_degisti:
            bosalt()
        if not satirlar:
            sayfa, bolum = b["page"], b["section"]
        satirlar.extend(b["satirlar"])
        son_sayfa = b["page"]
    bosalt()

    for i, c in enumerate(chunklar):
        c["id"] = i
    return chunklar


if __name__ == "__main__":
    chunklar = chunkla(pdf_yukle())
    kelimeler = [c["kelime"] for c in chunklar]
    print(f"Chunk sayısı: {len(chunklar)}")
    print(
        f"Kelime: min {min(kelimeler)} | ortalama {sum(kelimeler) / len(kelimeler):.0f} | maks {max(kelimeler)}"
    )
    tum_kodlar = [k for c in chunklar for k in c["codes"]]
    print(f"Toplam kod: {len(tum_kodlar)} | farklı kod: {len(set(tum_kodlar))}")
    for i in (0, 12, len(chunklar) // 2, len(chunklar) - 1):
        c = chunklar[i]
        print(
            f"\n--- chunk {c['id']} | sayfa {c['page']}-{c['page_end']} | {c['kelime']} kelime ---"
        )
        print(c["text"][:450])
