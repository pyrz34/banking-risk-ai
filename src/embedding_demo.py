import numpy as np
from fastembed import TextEmbedding
from itertools import combinations

MODEL_ADI = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
model = TextEmbedding(MODEL_ADI)


def vektor_al(cumleler):
    "cümle listesini vektör listesine çevirme"
    return [np.array(v) for v in model.embed(cumleler)]


def benzerlik(a, b):
    "iki vektörün yönü ne kadar benzer 1= ayn yön 0= ilgisiz"
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))


if __name__ == "__main__":
    cumleler = [
        "International transactions can have elevated risk.",
        "Cross-border transactions may be risky. ",
        "Yurt dışı işlemler yüksek risk taşıyabilir.",
        "The cafeteria serves lunch at noon ",
    ]
    vektorler = vektor_al(cumleler)

    print("vektör boyutu:", len(vektorler[0]))
    print("ilk cümlenin ilk 5 sayısı:", vektorler[0][:5].round(3))
    print()
    for i, j in combinations(range(len(cumleler)), 2):
        print(
            f"{benzerlik(vektorler[i], vektorler[j]):.3f}  |  {cumleler[i]}  <->  {cumleler[j]}"
        )
