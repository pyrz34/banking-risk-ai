"""Gün 9: chunk'ları vektöre çevir (indeks) ve soruya en yakın chunk'ları bul (arama).

İndeks = her chunk'ın vektörü. Bir kere hesaplanır, data/ içine kaydedilir.
Chunk'lar ya da model değişirse (hash farklı çıkar) otomatik yeniden hesaplanır.
Birden fazla embedding modeli denenebilir: MODELLER sözlüğü. Her modelin indeksi ayrı dosyada tutulur.
"""

import hashlib
import os

import numpy as np

from chunklama import chunkla
from pdf_yukle import pdf_yukle

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VARSAYILAN_MODEL = "e5"

# e5 modelleri soruya "query: ", metne "passage: " öneki ister. fastembed bunu OTOMATİK eklemez, biz ekliyoruz.
MODELLER = {
    "minilm": {
        "ad": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        "sorgu_oneki": "",
        "metin_oneki": "",
    },  # 384 boyut, 0.2 GB, 128 token
    "mpnet": {
        "ad": "sentence-transformers/paraphrase-multilingual-mpnet-base-v2",
        "sorgu_oneki": "",
        "metin_oneki": "",
    },  # 768 boyut, 1 GB, 512 token
    "e5": {
        "ad": "intfloat/multilingual-e5-large",
        "sorgu_oneki": "query: ",
        "metin_oneki": "passage: ",
    },  # 1024 boyut, 2.2 GB, 512 token
}


class EmbeddingModeli:
    """fastembed modelini önek kurallarıyla sarar. İndeks ve arama bu sınıf üzerinden konuşur."""

    def __init__(self, anahtar=VARSAYILAN_MODEL):
        if anahtar not in MODELLER:
            raise ValueError(
                f"Bilinmeyen model '{anahtar}'. Seçenekler: {list(MODELLER)}"
            )
        from fastembed import (
            TextEmbedding,
        )  # burada import: sadece model gerekince yavaş yüklensin

        self.anahtar = anahtar
        self.ayar = MODELLER[anahtar]
        self._model = TextEmbedding(self.ayar["ad"])
        self.model = (
            self._model.model
        )  # token ölçümü için (tokenizer'a buradan erişiliyor)

    def metin_vektorleri(self, metinler):
        return list(self._model.embed([self.ayar["metin_oneki"] + m for m in metinler]))

    def sorgu_vektoru(self, soru):
        return list(self._model.embed([self.ayar["sorgu_oneki"] + soru]))


def modeli_yukle(anahtar=None):
    return EmbeddingModeli(
        anahtar or os.environ.get("EMBEDDING_MODELI", VARSAYILAN_MODEL)
    )


def indeks_dosyasi(model):
    return os.path.join(BASE_DIR, "data", f"chunk_indeksi_{model.anahtar}.npz")


def _normalle(vektorler):
    """Her vektörü uzunluğu 1 olacak şekilde ölçekler. Böylece cosine similarity = sade çarpım (dot)."""
    vektorler = np.asarray(vektorler, dtype=np.float32)
    return vektorler / np.linalg.norm(vektorler, axis=1, keepdims=True)


def _hash(model, metinler):
    h = hashlib.sha256((model.ayar["ad"] + model.ayar["metin_oneki"]).encode("utf-8"))
    for m in metinler:
        h.update(m.encode("utf-8"))
    return h.hexdigest()


def indeks_olustur(model, zorla=False):
    """Döndürür: (chunklar, vektorler). Kayıtlı indeks güncelse diskten okur."""
    chunklar = chunkla(pdf_yukle())
    metinler = [c["text"] for c in chunklar]
    ozet = _hash(model, metinler)
    dosya = indeks_dosyasi(model)

    if not zorla and os.path.exists(dosya):
        kayit = np.load(dosya)
        if str(kayit["hash"]) == ozet:
            return chunklar, kayit["vektorler"]

    vektorler = _normalle(model.metin_vektorleri(metinler))
    os.makedirs(os.path.dirname(dosya), exist_ok=True)
    np.savez(dosya, vektorler=vektorler, hash=ozet)
    return chunklar, vektorler


def ara(soru, chunklar, vektorler, model, k=3):
    """Soruya en çok benzeyen k chunk'ı döndürür: [(skor, chunk), ...] (skor 0-1 arası, yüksek = yakın)."""
    soru_vektoru = _normalle(model.sorgu_vektoru(soru))[0]
    skorlar = vektorler @ soru_vektoru  # her chunk ile cosine similarity
    en_iyiler = np.argsort(-skorlar)[:k]  # en yüksek k skorun sıra numaraları
    return [(float(skorlar[i]), chunklar[i]) for i in en_iyiler]


if __name__ == "__main__":
    import sys

    # kullanım: python src\rag_index.py [model] [soru...]    örn: python src\rag_index.py e5 kripto borsası
    argumanlar = sys.argv[1:]
    anahtar = argumanlar.pop(0) if argumanlar and argumanlar[0] in MODELLER else None
    model = modeli_yukle(anahtar)
    chunklar, vektorler = indeks_olustur(model)
    print(
        f"İndeks hazır ({model.anahtar}): {vektorler.shape[0]} chunk x {vektorler.shape[1]} boyut"
    )
    soru = (
        " ".join(argumanlar)
        or "Cuma günü mesai bitimine yakın yapılan işlemler neden şüpheli?"
    )
    print(f"\nSoru: {soru}")
    for skor, c in ara(soru, chunklar, vektorler, model):
        print(f"\n--- skor {skor:.3f} | sayfa {c['page']} | chunk {c['id']} ---")
        print(c["text"][:350])
