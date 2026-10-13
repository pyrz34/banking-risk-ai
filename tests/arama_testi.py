"""Gün 9 ölçümleri. Çalıştır: python tests\\arama_testi.py
1) Token ölçümü : chunk'lar modelin token sınırına sığıyor mu?
2) Arama testi  : 13 soruda doğru chunk ilk 3'te çıkıyor mu? (embedding vs basit kelime araması BM25)
"""

import collections
import math
import os
import re
import sys

sys.path.insert(
    0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
)

from rag_index import ara, indeks_olustur, modeli_yukle  # noqa: E402

# (soru, chunk metninde geçmesi gereken ifade). Cevaplar PDF'ten elle doğrulandı.
SORULAR = [
    (
        "Cuma günü mesai bitimine yakın yapılan işlemler neden şüpheli sayılır?",
        "T-001-3.72",
    ),
    ("Uzun süredir kullanılmayan hesap birden hareketlenirse ne olur?", "T-001-3.54"),
    ("Müşteri profiline uymayan kripto borsası transferleri", "T-001-3.47"),
    ("Kiralık kasa ziyaretleri aniden artarsa", "T-001-3.95"),
    ("Yeni kurulan firma hesap açar açmaz yoğun nakit işlemi yapıyor", "T-001-3.92"),
    ("Aynı ATM'den çok sayıda cebe havale çekilmesi", "T-001-3.60"),
    ("Geliriyle uyuşmayan yüklü nakit çekimleri", "T-001-3.18"),
    ("Offshore veya riskli ülkelerle açıklamasız işlemler", "T-001-3.28"),
    ("Tefecilik suçu hangi şüphe kategorisinde yer alır?", "SK-01"),
    ("Bildirimi ertelemek için en fazla kaç iş günü beklenir?", "yedi iş gün"),
    ("Şüpheli işlem açıklaması en fazla kaç karakter olabilir?", "50.000"),
    ("Bildirim MASAK.Online üzerinden nasıl gönderilir?", "MASAK.Online"),
    (
        "dormant account suddenly becomes active",
        "T-001-3.54",
    ),  # İngilizce soru, Türkçe doküman
]


def bm25_hazirla(chunklar):
    def tok(t):
        return re.findall(r"\w+", t.replace("İ", "i").replace("I", "ı").lower())

    docs = [tok(c["text"]) for c in chunklar]
    n, ort = len(docs), sum(map(len, docs)) / len(docs)
    df = collections.Counter(w for d in docs for w in set(d))

    def ara_bm25(soru, k=3):
        sonuc = []
        for i, d in enumerate(docs):
            tf = collections.Counter(d)
            s = sum(
                math.log(1 + (n - df[w] + 0.5) / (df[w] + 0.5))
                * tf[w]
                * 2.2
                / (tf[w] + 1.2 * (0.25 + 0.75 * len(d) / ort))
                for w in tok(soru)
                if w in tf
            )
            sonuc.append((s, i))
        return [i for s, i in sorted(sonuc, reverse=True)[:k]]

    return ara_bm25


def token_olc(model, chunklar):
    tokenizer = getattr(model.model, "tokenizer", None)
    if tokenizer is None:
        print("Tokenizer'a erişilemedi, token ölçümü atlandı.")
        return
    kesme = dict(tokenizer.truncation or {})
    limit = kesme.get("max_length")
    # DİKKAT: tokenizer kesme açıkken encode() zaten limitte keser, gerçek uzunluğu göremeyiz.
    # Ölçerken kesmeyi kapatıp sonra eski ayarıyla geri açıyoruz.
    tokenizer.no_truncation()
    try:
        uzunluklar = [len(tokenizer.encode(c["text"]).ids) for c in chunklar]
    finally:
        if kesme:
            tokenizer.enable_truncation(**kesme)
    sirali = sorted(uzunluklar)
    kelimeler = sum(len(c["text"].split()) for c in chunklar)
    oran = sum(uzunluklar) / kelimeler
    print(f"Modelin kesme sınırı (fastembed tokenizer): {limit} token")
    print(
        f"Chunk token uzunluğu (kesilmemiş): min {sirali[0]} | medyan {sirali[len(sirali) // 2]} | "
        f"p95 {sirali[int(len(sirali) * 0.95)]} | maks {sirali[-1]}"
    )
    print(f"Ortalama {oran:.2f} token / kelime")
    for sinir in (128, 256):
        print(
            f"  {sinir} token'ı aşan chunk: {sum(u > sinir for u in uzunluklar)} / {len(uzunluklar)}"
        )
    if limit:
        kesilen = [u for u in uzunluklar if u > limit]
        kayip = sum(u - limit for u in kesilen) / max(1, sum(uzunluklar)) * 100
        print(
            f"  => modelin sınırında KESİLEN chunk: {len(kesilen)} / {len(uzunluklar)} "
            f"(token'ların %{kayip:.0f}'i modele hiç ulaşmıyor)"
        )
        print(
            f"  => öneri: MAKS_KELIME yaklaşık {int((limit - 25) / oran)} olmalı "
            f"(25 token [Bölüm] satırı payı)"
        )


def main():
    model = modeli_yukle()
    chunklar, vektorler = indeks_olustur(model)
    print(f"{len(chunklar)} chunk, vektör boyutu {vektorler.shape[1]}\n")

    print("=== 1) TOKEN ÖLÇÜMÜ ===")
    token_olc(model, chunklar)

    print("\n=== 2) ARAMA TESTİ ===")
    bm25 = bm25_hazirla(chunklar)
    e_top1 = e_top3 = b_top3 = 0
    siralar = []
    for soru, beklenen in SORULAR:
        tum_sonuc = ara(
            soru, chunklar, vektorler, model, k=len(chunklar)
        )  # tüm chunk'lar, benzerliğe göre sıralı
        sonuc = tum_sonuc[:3]
        sira = next(
            (i + 1 for i, (_, c) in enumerate(tum_sonuc) if beklenen in c["text"]), None
        )
        siralar.append(sira)
        e_hit = [beklenen in c["text"] for _, c in sonuc]
        b_hit = [beklenen in chunklar[i]["text"] for i in bm25(soru)]
        e_top1 += e_hit[0]
        e_top3 += any(e_hit)
        b_top3 += any(b_hit)
        isaret = "1." if e_hit[0] else ("3." if any(e_hit) else "--")
        print(
            f"[emb {isaret:>2}] [kelime {'OK' if any(b_hit) else '--'}] {soru[:58]:<58} "
            f"doğru chunk sırası: {sira} | sayfa {[c['page'] for _, c in sonuc]}"
        )
    n = len(SORULAR)
    print(f"\nEmbedding : ilk sırada {e_top1}/{n} | ilk 3'te {e_top3}/{n}")
    print(f"Kelime ara: ilk 3'te {b_top3}/{n}  (karşılaştırma için)")
    bulunan = sorted(x for x in siralar if x)
    print(
        f"Doğru chunk'ın embedding sırası (1 = en iyi): {bulunan}  | medyan {bulunan[len(bulunan) // 2] if bulunan else '-'}"
    )


if __name__ == "__main__":
    main()
