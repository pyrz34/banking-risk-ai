import hashlib
import os
import numpy as np

from chunklama import chunkla
from pdf_yukle import pdf_yukle

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEKS_DOSYASI = os.path.join(BASE_DIR, "data", "chunk_indeksi.npz")
MODEL_ADI = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"


def modeli_yukle():
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL_ADI)


def _normalle(vektorler):
    vektorler = np.asarray(vektorler, dtype=np.float32)
    return vektorler / np.linalg.norm(vektorler, axis=1, keepdims=True)


def _hash(metinler):
    h = hashlib.sha256(MODEL_ADI.encode("utf-8"))
    for m in metinler:
        h.update(m.encode("utf-8"))
    return h.hexdigest()


def indeks_olustur(model, zorla=False):
    chunklar = chunkla(pdf_yukle())
    metinler = [c["text"] for c in chunklar]
    ozet = _hash(metinler)

    if not zorla and os.path.exists(INDEKS_DOSYASI):
        kayit = np.load(INDEKS_DOSYASI)
        if str(kayit["hash"]) == ozet:
            return chunklar, kayit["vektorler"]

    vektorler = _normalle(list(model.embed(metinler)))
    os.makedirs(os.path.dirname(INDEKS_DOSYASI), exist_ok=True)
    np.savez(INDEKS_DOSYASI, vektorler=vektorler, hash=ozet)
    return chunklar, vektorler


def ara(soru, chunklar, vektorler, model, k=3):
    soru_vektoru = _normalle(list(model.embed([soru])))[0]
    skorlar = vektorler @ soru_vektoru
    en_iyiler = np.argsort(-skorlar)[:k]
    return [(float(skorlar[i]), chunklar[i]) for i in en_iyiler]


if __name__ == "__main__":
    import sys

    model = modeli_yukle()
    chunklar, vektorler = indeks_olustur(model)
    print(f"indeks hazır: {vektorler.shape[0]} chunk x {vektorler.shape[1]} boyut ")
    soru = "".join(
        sys.argv[1:] or "Cuma günü mesai bitimine yakın yapılan işlemler neden şüpheli?"
    )
    print(f"\nSoru: {soru}")
    for skor, c in ara(soru, chunklar, vektorler, model):
        print(f"\n---skor {skor:.3f} | sayfa{c['page']} | chunk {c['id']} ---")
        print(c["text"][:350])
