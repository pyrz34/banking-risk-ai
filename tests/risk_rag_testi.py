"""Gün 12: risk motoru + RAG entegrasyonu testleri. Çalıştır: python tests\\risk_rag_testi.py
Ağ yok, gerçek Claude/e5 çağrısı yok (hepsi sahte nesnelerle). Hızlı ve ücretsiz.
Bu testler 'bağlantılar doğru mu' sorusunu ölçer; açıklamanın KALİTESİNİ ölçmez (onu python src\\risk_rag.py ile gör).
"""
import os
import sys
from types import SimpleNamespace

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import rag_cevap  # noqa: E402
import risk_rag  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from risk_engine import RiskEngine  # noqa: E402

sonuclar = []


def kontrol(ad, ok, detay=""):
    sonuclar.append(ok)
    print(f"{'PASS' if ok else 'FAIL'}  {ad}" + (f"  -> {detay}" if detay and not ok else ""))


class SahteClaude:
    """messages.create çağrılarını kaydeder, hazır bir cevap döner."""

    def __init__(self, metin="Sahte açıklama."):
        self.metin = metin
        self.cagrilar = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.cagrilar.append(kw)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.metin)], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=10, output_tokens=5))


def chunk(i, sayfa=1, kodlar=()):
    return {"id": i, "text": f"kayıt {i}", "page": sayfa, "page_end": sayfa, "codes": list(kodlar)}


def sahte_arama(tablo):
    """tablo: {sorgu: [(skor, chunk), ...]}. Çağrılan sorguları da kaydeder."""
    cagrilar = []

    def arama(sorgu, chunklar, vektorler, model, k=3):
        cagrilar.append(sorgu)
        return tablo.get(sorgu, [])[:k]
    arama.cagrilar = cagrilar
    return arama


def risk(kurallar):
    """Gerçek motorun kural isimlerinden RiskEngine.calculate benzeri sonuç."""
    isimler = {"FAILED_TX": "Başarısız işlem (+30)", "RISKY_CHANNEL": "Riskli kanal: web (+15)",
               "INTERNATIONAL": "Yurtdışı işlem (+25)", "AMOUNT_ANOMALY": "Tutar anormal (z=9.0) (+30)"}
    return {"risk_score": 70, "risk_label": "suspicious",
            "reasons": [isimler[k] for k in kurallar], "rule_ids": list(kurallar)}


def rag_hic_cagrilmamali():
    raise AssertionError("rag_getir çağrılmamalıydı")


Q_INT, Q_AMT = risk_rag.KURAL_SORGULARI["INTERNATIONAL"], risk_rag.KURAL_SORGULARI["AMOUNT_ANOMALY"]

# 1) Kural kimlikleri motorda doğru ve reasons ile aynı sırada
motor = RiskEngine()
satir = {"status": "FAILED", "channel": "Web", "is_international": 1, "amount_z": 9.0}
s = motor.calculate(satir)
kontrol("Motor rule_ids: 4 kural, reasons ile aynı sırada ve uzunlukta",
        s["rule_ids"] == ["FAILED_TX", "RISKY_CHANNEL", "INTERNATIONAL", "AMOUNT_ANOMALY"]
        and len(s["rule_ids"]) == len(s["reasons"]), str(s))
kontrol("Hiçbir kural tetiklenmezse rule_ids ve reasons boş",
        motor.calculate({"status": "OK", "channel": "ATM", "is_international": 0, "amount_z": 0.1})["rule_ids"] == [])
kontrol("Her rule_id için bir arama sorgusu tanımlı",
        all(k in risk_rag.KURAL_SORGULARI for k in s["rule_ids"]))

# 2) Boş reasons: Claude ve model yükü yok
claude = SahteClaude()
r = risk_rag.aciklama_uret_rag({"risk_score": 0, "risk_label": "normal", "reasons": [], "rule_ids": []},
                               rag_hic_cagrilmamali, claude=claude)
kontrol("Boş reasons: Claude çağrılmadı, rag yüklenmedi, sabit cümle döndü",
        not claude.cagrilar and not r["llm_used"] and r["explanation"] == risk_rag.BOS_ACIKLAMA
        and r["policy_sources"] == [])

# 3) Normal akış: her kural için kendi sorgusuyla arama, prompt'ta nedenler ve kaynaklar
arama = sahte_arama({Q_INT: [(0.8, chunk(1, 37, ["T-001-3.28"]))], Q_AMT: [(0.7, chunk(2, 36, ["T-001-3.18"]))]})
claude = SahteClaude("Skor yüksek [1]. Tutar için rehberde doğrudan bir karşılık yok.")
r = risk_rag.aciklama_uret_rag(risk(["INTERNATIONAL", "AMOUNT_ANOMALY"]), lambda: (None, [], None),
                               claude=claude, arama=arama)
kontrol("Her kural kendi sabit sorgusuyla arandı (sırayla)", arama.cagrilar == [Q_INT, Q_AMT], str(arama.cagrilar))
c = claude.cagrilar[0]
mesaj = c["messages"][0]["content"]
kontrol("Claude tek kez, doğru model/sistem mesajı ve düşünme payı bırakan max_tokens ile çağrıldı",
        len(claude.cagrilar) == 1 and c["model"] == rag_cevap.MODEL and c["system"] == risk_rag.SISTEM_MESAJI
        and c["max_tokens"] == risk_rag.MAKS_TOKEN)
kontrol("Prompt: skor, etiket, kural_id: neden satırları ve numaralı KAYNAKLAR var",
        all(x in mesaj for x in ["Skor: 70", "Etiket: suspicious", "- INTERNATIONAL: Yurtdışı işlem (+25)",
                                 "- AMOUNT_ANOMALY: Tutar anormal (z=9.0) (+30)", "KAYNAKLAR:", "[1] (sayfa 37)",
                                 "[2] (sayfa 36)"]), mesaj)
kontrol("Sistem mesajı 'karşılığı yoksa dayanak uydurma' ve 'hukuki hüküm verme' kurallarını içeriyor",
        "doğrudan bir karşılık yok" in risk_rag.SISTEM_MESAJI and "Hukuki hüküm verme" in risk_rag.SISTEM_MESAJI)
kontrol("llm_used True, açıklama Claude'un metni", r["llm_used"] and r["explanation"].startswith("Skor yüksek [1]"))
kontrol("Atıf bayrağı: yalnız [1] atıf yapıldı",
        [k["atif_edildi"] for k in r["policy_sources"]] == [True, False], str(r["policy_sources"]))
kontrol("policy_sources alanları: no, sayfa, kodlar, skor",
        r["policy_sources"][0] == {"no": 1, "sayfa": 37, "kodlar": ["T-001-3.28"], "skor": 0.8, "atif_edildi": True})

# 4) Aynı chunk iki kuralda gelirse tek kez, en yüksek skorla
ortak = chunk(7, 40, ["T-001-3.5"])
arama = sahte_arama({Q_INT: [(0.5, ortak)], Q_AMT: [(0.9, ortak), (0.4, chunk(8))]})
sec = risk_rag.politika_ara(["INTERNATIONAL", "AMOUNT_ANOMALY"], [], None, None, arama=arama)
kontrol("Tekrar eden chunk teke iniyor, en yüksek skor tutuluyor",
        [(round(sk, 1), c["id"]) for sk, c in sec] == [(0.9, 7), (0.4, 8)], str(sec))

# 4b) Atıf ayrıştırma: Claude'un gerçek çıktısında '[3, T-001-3.18]' gibi karışık biçim görüldü
kontrol("Atıf biçimleri: [1] [1][2] [1, 2] [3, T-001-3.18] -> numaralar; kodsuz/numarasız -> boş",
        risk_rag.atif_numaralari("a [1]. b [1][2]. c [1, 2].") == {1, 2}
        and risk_rag.atif_numaralari("kural [3, T-001-3.18] ile örtüşüyor") == {3}
        and risk_rag.atif_numaralari("[T-001-3.18] ve (3) ve [x]") == set()
        and risk_rag.atif_numaralari("Atıf yok.") == set())
kontrol("Sistem mesajı atıfın yalnızca sayı olarak yazılmasını istiyor (örn. [3])",
        "yalnızca sayı olarak" in risk_rag.SISTEM_MESAJI)

# 5) Kaynak sayısı üst sınırı ve min_skor süzgeci
arama = sahte_arama({Q_INT: [(0.9, chunk(1)), (0.8, chunk(2))], Q_AMT: [(0.7, chunk(3)), (0.6, chunk(4))]})
sec = risk_rag.politika_ara(["INTERNATIONAL", "AMOUNT_ANOMALY"], [], None, None, maks=3, arama=arama)
kontrol("maks=3: round-robin (her kuralın en iyisi önce, sonra ikinciler)", [c["id"] for _, c in sec] == [1, 3, 2], str(sec))
arama = sahte_arama({Q_INT: [(0.5, chunk(1)), (0.5, chunk(2))], Q_AMT: [(0.99, chunk(3)), (0.98, chunk(4))],
                     risk_rag.KURAL_SORGULARI["RISKY_CHANNEL"]: [(0.97, chunk(5)), (0.96, chunk(6))]})
sec = risk_rag.politika_ara(["INTERNATIONAL", "AMOUNT_ANOMALY", "RISKY_CHANNEL"], [], None, None, maks=3, arama=arama)
kontrol("Üst sınıra takılsa da düşük skorlu kuralın en iyi kaydı elenmiyor (skorlar kurallar arası kıyaslanamaz)",
        [c["id"] for _, c in sec] == [1, 3, 5], str(sec))
arama = sahte_arama({Q_INT: [(0.9, chunk(1)), (0.8, chunk(2))], Q_AMT: [(0.7, chunk(3)), (0.6, chunk(4))]})
sec = risk_rag.politika_ara(["INTERNATIONAL", "AMOUNT_ANOMALY"], [], None, None, min_skor=0.75, arama=arama)
kontrol("min_skor=0.75: altındakiler atılıyor", [c["id"] for _, c in sec] == [1, 2], str(sec))

kontrol("MAKS_TOKEN düşünme payı bırakacak kadar büyük (>= 2000; 1000'de gerçek denemede açıklama boş çıktı)",
        risk_rag.MAKS_TOKEN >= 2000, str(risk_rag.MAKS_TOKEN))

# 5b) Claude boş metin döndürürse (ör. bütün bütçe düşünmeye gitti) sessizce geçme, hata ver
bos = SahteClaude("")
try:
    risk_rag.aciklama_uret_rag(risk(["INTERNATIONAL"]), lambda: (None, [], None), claude=bos, arama=sahte_arama({}))
    hata = None
except RuntimeError as e:
    hata = str(e)
kontrol("Claude boş cevap dönerse RuntimeError (stop_reason ve token bilgisiyle), sessiz boş açıklama yok",
        hata is not None and "boş cevap" in hata and "max_tokens" in hata, str(hata))

# 6) Bilinmeyen kural: arama yok, prompt'ta 'kaynak yok' notu, kaynak listesi boş
arama = sahte_arama({})
claude = SahteClaude("Rehberde doğrudan karşılık yok.")
bilinmeyen = {"risk_score": 40, "risk_label": "normal", "reasons": ["Yeni kural (+40)"], "rule_ids": ["YENI_KURAL"]}
r = risk_rag.aciklama_uret_rag(bilinmeyen, lambda: (None, [], None), claude=claude, arama=arama)
kontrol("Bilinmeyen kural: arama yapılmadı, prompt 'kaynak bulunamadı' diyor, Claude yine de çağrıldı",
        arama.cagrilar == [] and "(rehberde ilgili kaynak bulunamadı)" in claude.cagrilar[0]["messages"][0]["content"]
        and r["policy_sources"] == [] and r["llm_used"])

# 7) API
import api  # noqa: E402

istemci = TestClient(api.app)
TEMEL = dict(account_id=1, amount=950000, status="OK", channel="Web", is_international=1)
asil_aciklama = risk_rag.aciklama_uret_rag
asil_rag_getir = api.rag_getir

p = istemci.post("/predict-risk", json=TEMEL).json()
kontrol("/predict-risk yanıtında rule_ids var ve reasons ile aynı uzunlukta",
        p["rule_ids"] == ["RISKY_CHANNEL", "INTERNATIONAL", "AMOUNT_ANOMALY"] and len(p["rule_ids"]) == len(p["reasons"]),
        str(p))

risk_rag.aciklama_uret_rag = lambda risk_sonucu, rag: {
    "explanation": "Sahte.", "llm_used": True, "usage": None,
    "policy_sources": [{"no": 1, "sayfa": 37, "kodlar": ["T-001-3.28"], "skor": 0.8, "atif_edildi": True}]}
e = istemci.post("/explain-risk", json=TEMEL)
j = e.json()
kontrol("/explain-risk: 200, risk alanları + explanation + policy_sources + llm_used",
        e.status_code == 200 and j["risk_score"] == p["risk_score"] and j["rule_ids"] == p["rule_ids"]
        and j["explanation"] == "Sahte." and j["llm_used"] is True and j["policy_sources"][0]["sayfa"] == 37, str(j))


def patla(*a, **k):
    raise RuntimeError("LLM çöktü")


risk_rag.aciklama_uret_rag = patla
import logging  # noqa: E402
logging.getLogger("risk_api").disabled = True  # api bu hatayı bilerek loglar, test çıktısı kirlenmesin
e = istemci.post("/explain-risk", json=TEMEL)
logging.getLogger("risk_api").disabled = False
j = e.json()
kontrol("LLM/rehber hatasında: 200 döner, risk sonucu korunur, llm_used False, açıklama hata notu",
        e.status_code == 200 and j["risk_score"] == p["risk_score"] and j["llm_used"] is False
        and "üretilemedi" in j["explanation"] and j["policy_sources"] == [], str(j))

risk_rag.aciklama_uret_rag = asil_aciklama


def rag_patlat():
    raise AssertionError("model yüklenmemeliydi")


api.rag_getir = rag_patlat
normal = {**TEMEL, "amount": 100, "is_international": 0, "channel": "ATM"}
e = istemci.post("/explain-risk", json=normal)
j = e.json()
kontrol("Hiç kural tetiklenmeyen işlemde: model yüklenmedi, Claude çağrılmadı, sabit açıklama",
        e.status_code == 200 and j["reasons"] == [] and j["llm_used"] is False
        and j["explanation"] == risk_rag.BOS_ACIKLAMA, str(j))
api.rag_getir = asil_rag_getir

e = istemci.post("/explain-risk", json={**TEMEL, "account_id": 999999})
kontrol("/explain-risk olmayan hesap: 404 (açıklama hatası olarak yutulmuyor)", e.status_code == 404, e.text)
e = istemci.post("/explain-risk", json={**TEMEL, "channel": "Telefon"})
kontrol("/explain-risk geçersiz kanal: 422", e.status_code == 422, e.text)

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
