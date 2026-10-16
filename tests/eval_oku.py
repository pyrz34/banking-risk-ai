"""Gün 13: elle grounding incelemesi için OKUNABİLİR görünüm (Excel'de satırlar çok uzuyor).
Çalıştır: python tests\\eval_oku.py        -> data\\rag_inceleme.txt dosyasını yazar (VS Code'da aç, Alt+Z ile satır kaydırmayı aç)

Girdi: data\\rag_degerlendirme.csv (python tests\\rag_degerlendirme.py üretir). Gerçek Claude çağrısı YOK.
Her soru için: soru, beklenen bilgi, cevap, atıf yapılan chunk'lar. Beklenen ifade chunk içinde ⟦ ⟧ ile işaretlenir.
Senin işin: cevaptaki HER cümle bu chunk'larda yazıyor mu? Sayı/kod birebir aynı mı? [n] doğru chunk'ı mı gösteriyor?
"""
import csv
import os
import re
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GIRDI = os.path.join(BASE_DIR, "data", "rag_degerlendirme.csv")
CIKTI = os.path.join(BASE_DIR, "data", "rag_inceleme.txt")

CHUNK_AYIRICI = re.compile(r"\n\n(?=\[\d+\] )")
ISARET_AC, ISARET_KAPA = "⟦", "⟧"


def chunklari_ayir(kaynak_metinleri):
    """'[1] metin\\n\\n[2] metin' -> {1: 'metin', 2: 'metin'}"""
    sonuc = {}
    for parca in CHUNK_AYIRICI.split(kaynak_metinleri.strip()):
        m = re.match(r"\[(\d+)\] (.*)", parca, flags=re.S)
        if m:
            sonuc[int(m.group(1))] = m.group(2)
    return sonuc


def isaretle(metin, ifade):
    """İfadeyi boşluk ve büyük/küçük harf farkını yok sayarak ⟦ ⟧ içine alır (pypdf kelime yapıştırabiliyor)."""
    harfler = re.sub(r"\s+", "", ifade)
    if not harfler:
        return metin
    desen = re.compile(r"\s*".join(re.escape(h) for h in harfler), flags=re.I)
    return desen.sub(lambda m: f"{ISARET_AC}{m.group(0)}{ISARET_KAPA}", metin)


def atif_listesi(metin):
    return [int(x) for x in re.findall(r"\d+", metin or "")]


def blok_uret(satir):
    cevapli = satir["tur"] == "cevaplı"
    chunklar = chunklari_ayir(satir["kaynak_metinleri"])
    atiflar = atif_listesi(satir["atif_edilen"])
    s = ["=" * 78,
         f"#{satir['no']} [{satir['kume']}] {satir['tur']} | otomatik hata türü: {satir['hata']}",
         f"SORU : {satir['soru']}",
         f"BEKLENEN: {satir['beklenen_bilgi']}",
         f"CEVAP: {satir['cevap']}",
         f"ATIF YAPILAN: {atiflar or 'yok'} | arama ilk alakalı sıra: {satir['ilk_alakali_sira'] or '-'}", ""]
    if not cevapli:
        s.append("(Rehberde olmayan soru: doğrusu sadece 'bulamadım' demek. Cevapta başka bilgi varsa kaynakla karşılaştır.)")
    gosterilecek = atiflar if atiflar else ([] if not cevapli else sorted(chunklar))
    if cevapli and not atiflar:
        s.append("(Atıf yok: aşağıda çekilen TÜM chunk'lar. Beklenen bilgi hangisinde?)")
    for no in gosterilecek:
        if no in chunklar:
            ham = chunklar[no]
            s.append(f"--- chunk [{no}] ---")
            s.append(isaretle(ham, satir["beklenen_bilgi"]) if cevapli else ham)
            s.append("")
        else:
            s.append(f"--- chunk [{no}] YOK (cevap olmayan bir kaynağa atıf yapıyor) ---\n")
    s.append("ELLE NOT: ______________________________________________")
    s.append("")
    return "\n".join(s)


def main():
    if not os.path.exists(GIRDI):
        sys.exit(f"{GIRDI} yok. Önce: python tests\\rag_degerlendirme.py")
    with open(GIRDI, newline="", encoding="utf-8-sig") as f:
        satirlar = list(csv.DictReader(f, delimiter=";"))
    blok = [blok_uret(s) for s in satirlar]
    with open(CIKTI, "w", encoding="utf-8") as f:
        f.write("\n".join(blok))
    print(f"{len(satirlar)} soru yazıldı: {CIKTI}")
    print("VS Code'da aç, satır kaydırma için Alt+Z.")


if __name__ == "__main__":
    main()
