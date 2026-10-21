"""Gün 19: /investigate'in iş mantığı (FastAPI'den bağımsız, test edilebilir).

Akış, "zarif bozulma" (graceful degradation) merdiveniyle: her basamak bir öncekinin çökmesine karşı sigortadır.
  0. Veri katmanı (ARAÇ KODU, Claude yok): müşteri özeti + en riskli 3 işlem. Müşteri yoksa MusteriYok. Bu katman hata verirse
     hata verir (çekirdek bozuksa 200 dönmek yalan olur).
  1. Ajan raporu (Gün 18): tamamlanırsa döner + rapor araç sonuçlarıyla kaba kontrollerden geçer (dogrulama). Başarılı rapor
     önbelleğe girer (müşteri, veri imzası, prompt kimliği anahtarıyla). Hata/zaman aşımı/adım-süre sınırı -> 2'ye düşer.
  2. En riskli işlemin kural-tabanlı açıklaması (Gün 12 RAG): önbellek anahtarı (etiket, skor, kural_idleri, nedenler).
     Hata verirse -> 3'e düşer.
  3. Rapor yok; veri katmanının çıktısı yine döner.
Hangi basamağın cevap verdiği `rapor_kaynagi` alanında ("ajan" | "aciklama" | "yok") ve nedenler `uyarilar` alanında yazar.

Önbellek notu: açıklama anahtarında NEDENLER metni de var, yalnız kural_idleri değil. Çünkü nedenler tutar sapmasını (z=9.0)
içeriyor ve açıklama bunu aktarabilir; yalnız etiket+kural_idleriyle saklasaydık başka işlemin z değerini yanlış gösterirdik.
Bedeli: AMOUNT_ANOMALY'li işlemlerde isabet oranı düşük, diğerlerinde yüksek. Gerçek oran çalışırken ölçülür (durum()).
Sınırlar: tek-uçuş (single-flight) yok: aynı müşteri aynı anda iki kez sorulursa ajan iki kez çalışır. Kimlik doğrulama yok.
"""
import logging
import os
import sys
import time

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import agent  # noqa: E402
import agent_trace  # noqa: E402
import investigation  # noqa: E402
import investigation_checks as checks  # noqa: E402
import risk_rag  # noqa: E402
from onbellek import LRUOnbellek  # noqa: E402
from tools import banking_tools as bt  # noqa: E402
from tools import veri  # noqa: E402

logger = logging.getLogger("risk_api")

RAPOR_ONBELLEK = LRUOnbellek(128)
ACIKLAMA_ONBELLEK = LRUOnbellek(256)
EN_RISKLI_ISLEM_SAYISI = 3


class MusteriYok(Exception):
    """Müşteri veri setinde yok (API bunu 404'e çevirir)."""


def _veri_imzasi():
    return veri.tablolar()["imza"]


def aciklama_onbellekli(risk, rag_getir, claude):
    """risk_rag.aciklama_uret_rag'ı önbellekle sarar. Döndürür: (sonuç, onbellekten_mi). Yalnız Claude'un ürettiği
    başarılı açıklamalar saklanır; hata durumunda istisna olduğu gibi yukarı çıkar (önbelleğe bir şey girmez)."""
    anahtar = (risk["risk_label"], risk["risk_score"], tuple(risk["rule_ids"]), tuple(risk["reasons"]))
    bulundu, deger = ACIKLAMA_ONBELLEK.al(anahtar)
    if bulundu:
        return deger, True
    ham = risk_rag.aciklama_uret_rag(risk, rag_getir, claude=claude)
    sonuc = {"explanation": ham["explanation"], "policy_sources": ham["policy_sources"], "llm_used": ham["llm_used"]}
    if sonuc["llm_used"]:
        ACIKLAMA_ONBELLEK.koy(anahtar, sonuc)
    return sonuc, False


def _iz_ozeti(iz):
    return {"bitis": iz["bitis"], "arac_sirasi": list(iz["arac_sirasi"]), "girdi_token": iz["kullanim"]["girdi"],
            "cikti_token": iz["kullanim"]["cikti"], "sure_ms": iz["sure_ms"]}


def _ajan_raporu(customer_id, istemci, yenile, uyarilar, ajan):
    """Başarılıysa {"rapor", "dogrulama", "iz_ozeti"} ve önbellekten_mi; olmazsa (None, False) ve uyarı ekler."""
    anahtar = (customer_id, _veri_imzasi(), agent_trace.sistem_mesaji_id(investigation.INCELEME_SISTEM_MESAJI))
    if not yenile:
        bulundu, kayit = RAPOR_ONBELLEK.al(anahtar)
        if bulundu:
            return kayit, True
    try:
        r = ajan(customer_id, istemci=istemci)
    except Exception:  # noqa: BLE001  (Claude/ağ/araç hatası ne olursa olsun bir alt basamağa düşeriz)
        logger.exception("Ajan raporu üretilemedi (müşteri %s)", customer_id)
        uyarilar.append("Ajan raporu üretilemedi (Claude ya da araç hatası).")
        return None, False
    if r["bitis"] != "tamamlandi":
        uyarilar.append(f"Ajan raporu tamamlanamadı (bitis={r['bitis']}).")
        return None, False
    dogrulama = [{"kontrol": a, "gecti": g, "detay": d} for a, g, d in checks.calistir(checks.GENEL, r["rapor"], r["iz"])]
    kayit = {"rapor": r["rapor"], "dogrulama": dogrulama, "iz_ozeti": _iz_ozeti(r["iz"])}
    RAPOR_ONBELLEK.koy(anahtar, kayit)
    return kayit, False


def _aciklama_raporu(en_riskli, rag_getir, istemci, uyarilar):
    """2. basamak: en riskli işlemin kural-tabanlı açıklaması. Döndürür: (metin, onbellekten_mi); başarısızsa (None, False)."""
    try:
        risk = bt.get_risk_score(en_riskli["account_id"], en_riskli["amount"], en_riskli["status"], en_riskli["channel"],
                                 en_riskli["is_international"])
        if "error" in risk:
            raise RuntimeError(risk["error"])
        claude = istemci
        if claude is None and risk["reasons"]:  # kural yoksa Claude'a gerek yok, istemci kurmayalım
            claude = agent._claude()
        sonuc, onbellekten = aciklama_onbellekli(risk, rag_getir, claude)
        return sonuc["explanation"], onbellekten
    except Exception:  # noqa: BLE001
        logger.exception("En riskli işlem açıklaması üretilemedi")
        uyarilar.append("En riskli işlemin açıklaması da üretilemedi; yalnızca veri döndü.")
        return None, False


def incele_servis(customer_id, rag_getir, istemci=None, yenile=False, ajan=None, saat=time.perf_counter):
    """Döndürür (API cevabı): customer_id, musteri, en_riskli_islemler, rapor, rapor_kaynagi, onbellekten, dogrulama,
    uyarilar, iz_ozeti, sure_ms. Müşteri yoksa MusteriYok."""
    t0 = saat()
    ajan = ajan or investigation.incele
    bilgi = bt.get_customer_info(customer_id)
    if "error" in bilgi:
        raise MusteriYok(bilgi["error"])
    gecmis = bt.get_transaction_history(customer_id, EN_RISKLI_ISLEM_SAYISI, "risk")
    if "error" in gecmis:  # müşteri var ama geçmiş hata veriyorsa çekirdek bozuk demektir: gizlemeyelim
        raise RuntimeError(f"İşlem geçmişi okunamadı: {gecmis['error']}")
    islemler = gecmis["islemler"]

    cevap = {
        "customer_id": customer_id,
        "musteri": {"segment": bilgi["segment"], "city": bilgi["city"], "risk_band": bilgi["risk_band"],
                    "onboard_date": bilgi["onboard_date"], "hesap_sayisi": len(bilgi["accounts"]),
                    "toplam_islem": gecmis["toplam_islem"]},
        "en_riskli_islemler": islemler,
        "rapor": None, "rapor_kaynagi": "yok", "onbellekten": False, "dogrulama": [], "uyarilar": [], "iz_ozeti": None,
    }
    uyarilar = cevap["uyarilar"]
    if not islemler:
        uyarilar.append("Müşterinin işlem kaydı yok; rapor üretilmedi.")
    else:
        kayit, onbellekten = _ajan_raporu(customer_id, istemci, yenile, uyarilar, ajan)
        if kayit is not None:
            cevap.update(rapor=kayit["rapor"], rapor_kaynagi="ajan", onbellekten=onbellekten,
                         dogrulama=kayit["dogrulama"], iz_ozeti=kayit["iz_ozeti"])
            for d in kayit["dogrulama"]:
                if not d["gecti"]:
                    uyarilar.append(f"Otomatik kontrol kaldı: {d['kontrol']} ({d['detay']}). Kaba bir ipucudur, raporu okuyun.")
        else:
            aciklama, onbellekten = _aciklama_raporu(islemler[0], rag_getir, istemci, uyarilar)
            if aciklama is not None:
                cevap.update(rapor=aciklama, rapor_kaynagi="aciklama", onbellekten=onbellekten)
                uyarilar.append("Ajan raporu yerine en riskli işlemin kural-tabanlı açıklaması döndü.")
    cevap["sure_ms"] = round((saat() - t0) * 1000)
    logger.info("investigate müşteri=%s kaynak=%s onbellekten=%s uyari=%d sure_ms=%d", customer_id, cevap["rapor_kaynagi"],
                cevap["onbellekten"], len(uyarilar), cevap["sure_ms"])
    return cevap


def onbellek_durumu():
    return {"rapor": RAPOR_ONBELLEK.durum(), "aciklama": ACIKLAMA_ONBELLEK.durum()}
