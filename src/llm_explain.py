import anthropic
from dotenv import load_dotenv
from risk_engine import BASE_DIR
import os

load_dotenv(os.path.join(BASE_DIR, ".env"))  # Antropic apikeyi .envden okur
MODEL = "claude-haiku-5-5"

client = anthropic.Anthropic()


SISTEM_MESAJI = (
    "Sen bir banka operasyon risk analistisin.Sana bir işlemin risk skoru,"
    "etiketi ve tetiklenen kurallar verilecek. Kısa(2-3 cümle),sade Türkçe bir"
    "açıklama yaz.Sadece verilen bilgileri kullan,kendine kendine yeni neden uydurma."
)


def aciklama_uret(risk_sonucu, temperature=None):
    nedenler = "\n".join(f"-{neden}" for neden in risk_sonucu["reasons"])
    kullanici_mesaji = (
        f"Risk skoru: {risk_sonucu['risk_score']}\n"
        f"Etiket : {risk_sonucu['risk_label']}\n"
        f"Nedenler:\n{nedenler}"
    )

    cevap = client.messages.create(
        model=MODEL,
        max_tokens=1000,
        system=SISTEM_MESAJI,
        messages=[{"role": "user", "content": kullanici_mesaji}],
    )
    metin = "".join(blok.text for blok in cevap.content if blok.type == "text")

    return metin, cevap.usage


if __name__ == "__main__":
    ornek = {
        "risk_score": 70,
        "risk_label": "suspicious",
        "reasons": [
            "İşlem riskli kanaldan yapılmış(+15)",
            "işlem yurtdışı (+25)",
            "Tutar anomalisi (Z-Score yüksek) (+30)",
        ],
    }
    metin, kullanim = aciklama_uret(ornek)
    print(metin)
    print(
        f"\ngirdi token : {kullanim.input_tokens},çıktı token:{kullanim.output_tokens}"
    )
