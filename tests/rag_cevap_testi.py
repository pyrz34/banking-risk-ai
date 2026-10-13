"""Gün 10: RAG uçtan uca test (GERÇEK Claude çağrısı yapar, küçük bir maliyeti var).
Çalıştır: python tests\\rag_cevap_testi.py
  - Cevabı rehberde olan sorular: doğru kayıt kaynaklarda mı + cevap 'bulamadım' demiyor mu + kaynak numarası var mı
  - Cevabı rehberde OLMAYAN sorular: cevap 'bulamadım' diyor mu (uydurma yok mu)
"""

import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)

from rag_cevap import BULAMADIM, cevapla  # noqa: E402
from rag_index import indeks_olustur, modeli_yukle  # noqa: E402

# (soru, kaynaklarda geçmesi gereken ifade). Cevaplar PDF'ten elle doğrulandı.
CEVAPLI = [
    (
        "Cuma günü mesai bitimine yakın saatlerde transfer talep eden müşteri neden şüpheli sayılır?",
        "T-001-3.72",
        "T-001-3.72",
    ),
    (
        "Kiralık kasa ziyaretleri aniden artarsa bu bir şüpheli işlem göstergesi midir?",
        "T-001-3.95",
        "T-001-3.95",
    ),
    ("Tefecilik hangi şüphe kategorisi koduyla bildirilir?", "SK-01", "SK-01"),
    ("Bildirimi ertelemek için en fazla kaç iş günü beklenir?", "yedi iş gün", "yedi"),
]
# Rehberde bu konular geçmiyor (PDF'te 'idari para', 'yaptırım', 'yapay zeka', 'bulut' aratıldı: 0 sonuç)
CEVAPSIZ = [
    "Şüpheli işlem bildirimi yapmayan bankaya hangi idari para cezası uygulanır?",
    "Rehber hangi yapay zeka modelinin şüpheli işlem tespitinde kullanılmasını öneriyor?",
    "Rehbere göre bulut tabanlı sistemlerde müşteri verisi nasıl saklanmalı?",
]


def sadece_bulamadim(cevap):
    """Cevap esasen 'bulamadım' cümlesinden mi ibaret? (kısmi cevap içinde geçmesi sayılmaz)"""
    temiz = re.sub(r"[\s.\"']+$", "", cevap.strip().lower())
    return temiz == BULAMADIM.lower().rstrip(".") or (
        BULAMADIM.lower() in cevap.lower() and len(cevap) < 60
    )


def main():
    model = modeli_yukle()
    chunklar, vektorler = indeks_olustur(model)
    sonuclar, girdi, cikti = [], 0, 0

    def goster(baslik, soru, s, ok, neden):
        print(f"\n[{'GEÇTİ' if ok else 'KALDI'}] {baslik}: {soru}")
        print(f"  cevap: {s['cevap']}")
        print(
            f"  kaynak sayfaları: {[k['sayfa'] for k in s['kaynaklar']]}"
            + ("" if ok else f"  | sorun: {neden}")
        )

    print("=== CEVABI REHBERDE OLAN SORULAR ===")
    for soru, beklenen, cevapta in CEVAPLI:
        s = cevapla(soru, chunklar, vektorler, model)
        girdi += s["kullanim"].input_tokens
        cikti += s["kullanim"].output_tokens
        bulundu = any(beklenen in k["metin"] for k in s["kaynaklar"])
        bulamadi = sadece_bulamadim(s["cevap"])
        kaynakli = bool(re.search(r"\[\d\]", s["cevap"]))
        icerik = cevapta.lower() in s["cevap"].lower()
        ok = bulundu and not bulamadi and kaynakli and icerik
        neden = (
            ("doğru kayıt kaynaklarda yok " if not bulundu else "")
            + ("sadece 'bulamadım' dedi " if bulamadi else "")
            + ("kaynak numarası yok " if not kaynakli else "")
            + (f"cevapta '{cevapta}' yok" if not icerik else "")
        )
        sonuclar.append(ok)
        goster("cevaplı", soru, s, ok, neden.strip())

    print("\n=== CEVABI REHBERDE OLMAYAN SORULAR (uydurmamalı) ===")
    for soru in CEVAPSIZ:
        s = cevapla(soru, chunklar, vektorler, model)
        girdi += s["kullanim"].input_tokens
        cikti += s["kullanim"].output_tokens
        ok = sadece_bulamadim(s["cevap"])
        sonuclar.append(ok)
        goster("cevapsız", soru, s, ok, "'bulamadım' demedi, cevap uydurmuş olabilir")

    print(
        f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti | toplam girdi token {girdi}, çıktı token {cikti}"
    )
    sys.exit(0 if all(sonuclar) else 1)


if __name__ == "__main__":
    main()
