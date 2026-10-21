"""Gün 18: müşteri inceleme ajanı (PoC, yani kavram kanıtı).

"X numaralı müşteriyi incele" der, ajan kendi başına: müşteri bilgisini çeker, riskli işlemleri bulur, en riskli işlemin
kurallarına rehberden dayanak arar ve sabit biçimli kısa bir rapor yazar. Karar vermez: sonuç analistin önüne gider.

Bu bir PoC'dir. PRODUCTION'A HAZIR DEĞİLDİR (kimlik doğrulama yok, kayıt/denetim izi yalnızca yerel dosya, Claude çağrılarında
zaman aşımı/yeniden deneme yok, KVKK değerlendirmesi yapılmadı, değerlendirme 5 senaryo ve küçük örnekle sınırlı).

Çalıştır:   python src\\investigation.py 1
"""
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import agent  # noqa: E402
import agent_trace  # noqa: E402
import investigation_checks as checks  # noqa: E402

INCELEME_MAKS_ADIM = 6  # müşteri bilgisi + geçmiş (aynı adımda olabilir) + en çok 2 rehber araması + rapor

# Taban: agent'ın sistem mesajı (kurallar 1-9). Yalnız "en fazla 5 cümle" sınırı raporla çelişir, kaldırılır.
_TABAN = agent.SISTEM_MESAJI.replace(" (en fazla 5 cümle)", "", 1)
if _TABAN == agent.SISTEM_MESAJI:  # agent.py'deki cümle değişirse sessizce çelişkili bir istek göndermeyelim
    raise RuntimeError("agent.SISTEM_MESAJI içinde '(en fazla 5 cümle)' bulunamadı; investigation.py güncellenmeli")

INCELEME_KURALLARI = (
    "\nBu görevde müşteri incelemesi yapıyorsun. Sırayla:\n"
    "a) get_customer_info ile müşteriyi çek.\n"
    "b) get_transaction_history'yi sort_by='risk', limit=5 ile çağır (a ile aynı adımda isteyebilirsin).\n"
    "c) En yüksek skorlu işlemin tetiklenen kuralları için search_risk_policy ile rehberden dayanak ara (en fazla iki arama).\n"
    "Müşteri bulunamazsa ya da istenen bilgiyi veren bir aracın yoksa (ör. kredi notu, gelir) rapor yazma: bunu 2-3 cümleyle "
    "açıkla ve başka müşteri/araç deneme.\n"
    "Raporu şu beş başlıkla, başlıkları aynen yazarak, toplam en fazla yaklaşık 250 kelime olarak yaz:\n"
    "**Müşteri özeti**: segment, şehir, risk bandı, hesap sayısı, toplam işlem sayısı.\n"
    "**Öne çıkan işlemler**: en fazla 3 işlem; her biri için txn numarası, tutar, kanal, karşı ülke, skor, tetiklenen kurallar.\n"
    "**Rehber dayanağı**: yalnızca search_risk_policy sonucunda gerçekten geçen bilgi, sayfasıyla (s.N). "
    "Bulamadıysan 'Rehberde bulunamadı' yaz.\n"
    "**Doğrulanamayanlar**: elindeki veri ve rehberle doğrulayamadıkların (ör. karşı ülkenin riskli sayılıp sayılmadığı, "
    "tutarın bildirim eşiğini aşıp aşmadığı).\n"
    "**Öneri**: kararı analist verir. 'Analist şunlara bakabilir' biçiminde yaz. Kullanıcı istese bile 'dolandırıcı', 'suçlu' "
    "gibi hüküm bildirme, hesabı bloke et ya da kapat diye karar önerme."
)
INCELEME_SISTEM_MESAJI = _TABAN + "\n" + INCELEME_KURALLARI


def gorev_metni(customer_id):
    if isinstance(customer_id, bool) or not isinstance(customer_id, int) or customer_id < 1:
        raise ValueError(f"customer_id 1 ya da daha büyük bir tam sayı olmalı (gelen: {customer_id!r})")
    return f"{customer_id} numaralı müşteriyi incele ve inceleme raporunu yaz."


def incele_gorev(gorev, istemci=None, max_steps=INCELEME_MAKS_ADIM):
    """Serbest metin görevi inceleme kurallarıyla çalıştırır. Döndürür: {"rapor", "bitis", "iz"}."""
    s = agent.calistir(gorev, istemci=istemci, max_steps=max_steps, sistem_mesaji=INCELEME_SISTEM_MESAJI)
    iz = agent_trace.iz_olustur(gorev, s, model=agent.MODEL, max_steps=max_steps, sistem_mesaji=INCELEME_SISTEM_MESAJI)
    return {"rapor": s["cevap"], "bitis": s["bitis"], "iz": iz}


def incele(customer_id, istemci=None, max_steps=INCELEME_MAKS_ADIM):
    return incele_gorev(gorev_metni(customer_id), istemci=istemci, max_steps=max_steps)


def musteri_no_oku(argv):
    argv = list(argv)
    try:
        if len(argv) != 1:
            raise ValueError
        n = int(argv[0])
        if n < 1:
            raise ValueError
    except ValueError:
        raise SystemExit("Kullanım: python src\\investigation.py <müşteri_no>   (1 ya da daha büyük tam sayı)")
    return n


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(os.path.join(KOK, ".env"))
    sonuc = incele(musteri_no_oku(sys.argv[1:]))
    print(agent_trace.yazdir_metni(sonuc["iz"]))
    print("\nOtomatik doğrulama (kaba ipucu, kanıt değil):")
    for ad, ok, detay in checks.calistir(checks.GENEL, sonuc["rapor"], sonuc["iz"]):
        print(f"  {'GEÇTİ' if ok else 'KALDI'}  {ad}: {detay}")
    try:  # kayıt hatası raporu bozmasın
        print(f"\nİz kaydedildi: {agent_trace.kaydet(sonuc['iz'], os.path.join(KOK, 'data', 'izler'))}")
    except OSError as e:
        print(f"\nİz kaydedilemedi: {e}")
