"""Gün 8 - chunk kalite kontrolü. Çalıştır: python tests\\chunk_kontrol.py
Her kontrol PASS/FAIL yazar. Biri FAIL ise çıkış kodu 1 olur."""

import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)
from chunklama import (
    KOD_DESENI,
    MAKS_ESNEK,
    MAKS_KELIME,
    chunkla,
    grup_basligi_mi,
    satirlari_cikar,
)  # noqa: E402
from pdf_yukle import pdf_yukle  # noqa: E402

sayfalar = pdf_yukle()
chunklar = chunkla(sayfalar)
satirlar = satirlari_cikar(sayfalar)
sonuclar = []


def kontrol(ad, ok, detay=""):
    sonuclar.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {ad}" + (f"  -> {detay}" if detay else ""))


# 1) Boyut: hiçbir chunk üst sınırı aşmamalı
asanlar = [c["id"] for c in chunklar if c["kelime"] > MAKS_ESNEK]
kontrol("Hiçbir chunk MAKS_ESNEK'i aşmıyor", not asanlar, str(asanlar))

# 2) Kapsama: PDF'teki hiçbir satır kaybolmamalı (grup başlıkları bölüm etiketine taşınıyor)
metin = "\n".join(c["text"] for c in chunklar)
etiketler = " ".join(c["section"] for c in chunklar)
# grup başlığı muafiyeti yalnızca T-001 bölümünde (sayfa 34+) geçerli; başka yerde kaybolan satır hatadır
eksik = [
    (p, l)
    for p, l in satirlar
    if l not in metin and not (p >= 34 and grup_basligi_mi(l) and l in etiketler)
]
kontrol(
    "PDF'teki her satır bir chunk'ta (veya bölüm etiketinde) var",
    not eksik,
    str(eksik[:3]),
)

# 3) Her T-001 kaydı en az bir chunk'ın satır başında olmalı
t_kodlari = {
    m.group(0) for _, l in satirlar for m in [re.match(r"^T-001-\d+\.\d+", l)] if m
}
chunk_satir_basi = {
    m.group(0)
    for c in chunklar
    for l in c["text"].split("\n")
    for m in [re.match(r"^T-001-\d+\.\d+", l)]
    if m
}
kontrol(
    f"{len(t_kodlari)} T-001 kaydının hepsi chunk'ta",
    t_kodlari == chunk_satir_basi,
    str(sorted(t_kodlari - chunk_satir_basi)[:5]),
)

# 4) Kısa kayıt bölünmemeli: kodun başladığı satırdan sonraki satırlar aynı chunk'ta olmalı
bolunen = []
kayit_baslari = [
    i
    for i, (_, l) in enumerate(satirlar)
    if re.match(r"^(SK-\d{2}|T-001-\d+\.\d+)\b", l)
]
for n, i in enumerate(kayit_baslari):
    son = kayit_baslari[n + 1] if n + 1 < len(kayit_baslari) else len(satirlar)
    govde = [l for _, l in satirlar[i:son] if not grup_basligi_mi(l)]
    if (
        sum(len(l.split()) for l in govde) <= MAKS_KELIME
        and "\n".join(govde) not in metin
    ):
        bolunen.append(govde[0][:30])
kontrol("MAKS_KELIME'den kısa hiçbir kayıt bölünmemiş", not bolunen, str(bolunen[:3]))

# 5) T-001 grup etiketi doğru mu? (T-001-n.x -> n numaralı grubun başlığı)
beklenen = {
    "1": "MÜŞTERİ PROFİLİNE",
    "2": "İŞLEMLERE İLİŞKİN TİPLER",
    "3": "BANKACILIK İŞLEMLERİNE",
    "4": "TERÖR ÖRGÜTLERİ İLE BAĞLANTISINDAN",
    "5": "KÂR AMACI GÜTMEYEN",
    "6": "KİTLE İMHA SİLAHLARININ",
}
yanlis = []
for c in chunklar:
    for m in re.finditer(r"^T-001-(\d+)\.\d+", c["text"], re.M):
        n = m.group(1)
        if beklenen[n] not in c["section"] or (
            n == "2" and "BANKACILIK" in c["section"]
        ):
            yanlis.append((m.group(0), c["section"][-40:]))
kontrol("Her T-001 kaydının bölüm etiketi doğru gruptan", not yanlis, str(yanlis[:3]))

# 6) Grup başlıkları tam (2 satırlık başlıklar birleşmiş, 'TİPLER' artığı yok)
parcali = [
    c["id"] for c in chunklar if re.search(r"^(TİPLER|İLİŞKİN)$", c["text"], re.M)
]
kontrol("Grup başlığı artığı (TİPLER) metne sızmamış", not parcali, str(parcali))
for g in ("TERÖR ÖRGÜTLERİ", "KİTLE İMHA"):
    tam = any(
        g in c["section"] and c["section"].rstrip().endswith("TİPLER") for c in chunklar
    )
    kontrol(f"'{g}...' başlığı sonuna kadar birleşmiş", tam)

# 6b) Tablo sütun başlıkları bölüm etiketine karışmamış (pypdf sürümüne göre satır düzeni değişebiliyor)
karisan = sorted(
    {
        c["section"][-45:]
        for c in chunklar
        if "KOD A" in c["section"] or "DÜZENLEME" in c["section"]
    }
)
kontrol("Tablo sütun başlığı bölüm etiketine karışmamış", not karisan, str(karisan[:2]))

# 7) Sayfa bilgisi tutarlı
kotu = [
    c["id"] for c in chunklar if c["page"] > c["page_end"] or not 5 <= c["page"] <= 45
]
kontrol("Sayfa aralıkları geçerli", not kotu, str(kotu))

# 8) Gürültü kalmamış
gurultu = [
    c["id"] for c in chunklar if "MSK-RHB" in c["text"] or "KOD AÇIKLAMA" in c["text"]
]
kontrol("Başlık/sütun başlığı gürültüsü yok", not gurultu, str(gurultu))
# 9) Düz yazı chunk'ları çoğunlukla cümle sonunda bitmeli (eskiden %61'i cümle ortasında bitiyordu)
duz = [c for c in chunklar if not KOD_DESENI.search(c["text"])]
yarim = [
    c["id"]
    for c in duz
    if not c["text"]
    .rstrip()
    .split("\n")[-1]
    .strip()
    .endswith((".", "!", "?", ":", ";"))
]
kontrol(
    "Kodsuz chunk'ların en çok %35'i cümle ortasında bitiyor",
    len(yarim) <= 0.35 * len(duz),
    f"{len(yarim)}/{len(duz)}",
)

# 10) Gerçek hata: 'açıklayamaz' ile ceza ('hapis') aynı chunk'ta olmalı
ceza = [
    c["id"] for c in chunklar if "açıklayamazlar" in c["text"] and "hapis" in c["text"]
]
kontrol(
    "Bildirimi açıklama yasağı ve cezası (hapis) aynı chunk'ta",
    len(ceza) == 1,
    str(ceza),
)
print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti | {len(chunklar)} chunk")
sys.exit(0 if all(sonuclar) else 1)
