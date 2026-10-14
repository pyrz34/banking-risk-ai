"""Gün 10: HELD-OUT değerlendirme. Bu sorular ayar yapılırken HİÇ görülmedi.
KURAL: sonucu gördükten sonra soruları, chunklamayı, promptu bu sonuca bakarak DEĞİŞTİRME.
Değiştirirsen bu set artık held-out değildir; yeni soru yazman gerekir.
Çalıştır: python tests\\held_out_testi.py   (gerçek Claude çağrısı yapar, küçük maliyet)

Eşleştirme boşluk ve büyük/küçük harf yok sayılarak yapılır (pypdf sürümüne göre kelimeler yapışık çıkabiliyor).
"""

import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)

from rag_cevap import cevapla  # noqa: E402
from rag_cevap_testi import sadece_bulamadim  # noqa: E402
from rag_index import indeks_olustur, modeli_yukle  # noqa: E402

# (soru, kaynakta geçmesi gereken ifade, cevapta geçmesi gereken ifadelerden BİRİ). PDF'ten elle doğrulandı.
CEVAPLI = [
    (
        "Şüpheli işlem açıklama alanına en az kaç karakter girilmesi zorunludur?",
        "100 karakter",
        ("100",),
    ),
    (
        "Bir bildirimde en fazla kaç şüphe kategorisi seçilebilir?",
        "en fazla üçü",
        ("üç", "3"),
    ),
    (
        "Terörizmin finansmanı için yeterli şüphe yoksa hangi bildirim kategorisi işaretlenmelidir?",
        "yeterli düzeyde",
        ("aklanması",),
    ),
    (
        "Kitle imha silahlarının yayılmasının finansmanı bildirimlerinde hangi şüphe kategorisi kullanılmalıdır?",
        "SK-36",
        ("SK-36",),
    ),
    (
        "Mal varlığının dondurulması kararının ihlali hangi kodla bildirilir?",
        "SK-35",
        ("SK-35",),
    ),
    (
        "Vadeli mevduat veya katılım hesabının hesap türü kodu nedir?",
        "HT-02",
        ("HT-02",),
    ),
    ("POS tefeciliği hangi şüphe kategorisi koduyla bildirilir?", "SK-02", ("SK-02",)),
    (
        "Şüpheli işlem bildiriminde bulunulduğunu müşteriye açıklayan görevli ne ile cezalandırılır?",
        "bir yıldan üç yıla",
        ("hapis",),
    ),
    (
        "Faks ile yapılan bildirimlerde ayrıca ne yapılması gerekir?",
        "form aslının posta",
        ("posta",),
    ),
    (
        "Aynı konuyla ilgili birden çok kişi için kaç şüpheli işlem bildirim formu düzenlenir?",
        "tek bir ŞİB",
        ("tek bir",),
    ),
    (
        "Aynı eylem için birden fazla ek bildirim gönderilecekse önceki referans numarası nasıl yazılır?",
        "zincirleme",
        ("ilk",),
    ),
    (
        "Gerekmediği halde ivedi olarak gönderilen bildirimler hangi soruna yol açar?",
        "yol açabileceği",
        ("ertelen",),
    ),
]
# Rehberde bu konular geçmiyor (PDF'te 'İngilizce', 'ödül', 'prim', 'diploma/mezun/sertifika' aratıldı)
CEVAPSIZ = [
    "Rehberin İngilizce sürümü hangi internet adresinden indirilir?",
    "Bildirim yapan bankacıya ödül ya da prim verilir mi?",
    "Bildirimi hazırlayan personelin hangi diplomaya sahip olması gerekir?",
]


def norm(metin):
    return re.sub(r"\s+", "", metin.lower())


def main():
    model = modeli_yukle()
    chunklar, vektorler = indeks_olustur(model)
    girdi = cikti = 0
    ret_ok = cev_ok = 0
    print("=== CEVABI REHBERDE OLAN SORULAR ===")
    for soru, beklenen, cevapta in CEVAPLI:
        s = cevapla(soru, chunklar, vektorler, model)
        girdi += s["kullanim"].input_tokens
        cikti += s["kullanim"].output_tokens
        sira = next(
            (k["no"] for k in s["kaynaklar"] if norm(beklenen) in norm(k["metin"])),
            None,
        )
        icerik = any(norm(x) in norm(s["cevap"]) for x in cevapta)
        dogru = icerik and not sadece_bulamadim(s["cevap"])
        ret_ok += sira is not None
        cev_ok += dogru
        print(
            f"\n[arama {'OK ' if sira else 'YOK'} | cevap {'OK ' if dogru else 'YOK'}] {soru}"
        )
        print(
            f"  doğru chunk kaynak no: {sira} | sayfalar {[k['sayfa'] for k in s['kaynaklar']]}"
        )
        print(f"  cevap: {s['cevap']}")

    print("\n=== CEVABI REHBERDE OLMAYAN SORULAR ===")
    bul_ok = 0
    for soru in CEVAPSIZ:
        s = cevapla(soru, chunklar, vektorler, model)
        girdi += s["kullanim"].input_tokens
        cikti += s["kullanim"].output_tokens
        ok = sadece_bulamadim(s["cevap"])
        bul_ok += ok
        print(f"\n[{'DOĞRU REDDETTİ' if ok else 'UYDURMA/YAN BİLGİ'}] {soru}")
        print(f"  cevap: {s['cevap']}")

    n, m = len(CEVAPLI), len(CEVAPSIZ)
    print(f"\n=== ÖZET (held-out, ayar yapılmadı) ===")
    print(f"Arama (doğru chunk ilk {len(s['kaynaklar'])}'te): {ret_ok}/{n}")
    print(f"Cevap doğru ve içerikli          : {cev_ok}/{n}")
    print(f"Cevapsızı doğru reddetme         : {bul_ok}/{m}")
    print(f"Toplam girdi token {girdi}, çıktı token {cikti}")


if __name__ == "__main__":
    main()
