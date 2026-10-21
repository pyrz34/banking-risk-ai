"""Gün 19: /investigate testleri. Çalıştır: python tests\\investigate_testi.py
Ağ yok, gerçek Claude/e5 yok (sahte istemci, sahte rehber vektörü; araçlar ve API gerçek). Hızlı ve ücretsiz.
Ölçtüğü: zarif bozulma merdiveni (ajan -> açıklama -> yalnız veri), önbellek (isabet, yenile, anahtar, yalnız başarılılar),
girdi doğrulama (404/422), ısıtma (açılışta model yükleme, hata olsa da açılma), LRU önbelleğin kendisi.
ÖLÇMEDİĞİ: gerçek Claude'un rapor kalitesi ve gerçek süre/maliyet (onlar tests\\inceleme_degerlendirme.py ve canlı denemeyle).
"""
import logging
import os
import sys
import threading
from types import SimpleNamespace

import numpy as np

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import agent  # noqa: E402
import api  # noqa: E402
import investigation as inv  # noqa: E402
import investigation_service as svc  # noqa: E402
import onbellek  # noqa: E402
import risk_rag  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tools import banking_tools as bt  # noqa: E402
from tools import veri  # noqa: E402

sonuclar = []


def kontrol(ad, ok, detay=""):
    sonuclar.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {ad}" + (f"  -> {detay}" if detay and not ok else ""))


def metin_blok(t):
    return SimpleNamespace(type="text", text=t)


def arac_blok(id_, ad, girdi):
    return SimpleNamespace(type="tool_use", id=id_, name=ad, input=girdi)


def cevap(bloklar, stop, girdi=10, cikti=5):
    return SimpleNamespace(content=bloklar, stop_reason=stop, usage=SimpleNamespace(input_tokens=girdi, output_tokens=cikti))


class SahteClaude:
    def __init__(self, *cevaplar):
        self.cevaplar = list(cevaplar)
        self.cagrilar = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.cagrilar.append(dict(kw))
        return self.cevaplar[len(self.cagrilar) - 1]


class CokenClaude:
    def __init__(self):
        self.cagri = 0
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.cagri += 1
        raise RuntimeError("Claude çöktü")


class SahteModel:
    def sorgu_vektoru(self, soru):
        return [np.array([1.0, 0.0, 0.0])]


def chunk(i, sayfa, son=None):
    return {"id": i, "text": f"rehber metni {i}", "page": sayfa, "page_end": son or sayfa, "codes": [], "section": "Bölüm"}


CHUNKLAR = [chunk(0, 5, 6), chunk(1, 8), chunk(2, 9)]
VEKT = np.array([[0.1, 1, 0], [0.9, 0.1, 0], [1.0, 0, 0]], dtype=np.float32)
VEKT = VEKT / np.linalg.norm(VEKT, axis=1, keepdims=True)
SAHTE_RAG = lambda: (SahteModel(), CHUNKLAR, VEKT)  # noqa: E731

ASIL = {"bt_rag": bt._rag, "api_rag": api.rag_getir, "aciklama": risk_rag.aciklama_uret_rag, "istemci": agent._istemci,
        "imza": svc._veri_imzasi, "gecmis": bt.get_transaction_history, "risk_skor": bt.get_risk_score, "claude": agent._claude,
        "tablolar": veri.tablolar}
bt._rag = SAHTE_RAG
api.rag_getir = SAHTE_RAG
logging.getLogger("risk_api").disabled = True  # API hataları bilerek loglar; test çıktısı kirlenmesin

TOP3 = bt.get_transaction_history(1, 3, "risk")["islemler"]
GERCEK = TOP3[0]["txn_id"]
RAPOR = (f"**Müşteri özeti**: Bireysel, 3 hesap.\n**Öne çıkan işlemler**: txn {GERCEK}, skor {TOP3[0]['risk_score']}.\n"
         "**Rehber dayanağı**: Bildirim zorunludur (s.9).\n**Doğrulanamayanlar**: Ülke riski.\n"
         "**Öneri**: Analist işlemi değerlendirebilir.")


def temiz():
    svc.RAPOR_ONBELLEK.temizle()
    svc.ACIKLAMA_ONBELLEK.temizle()
    risk_rag.aciklama_uret_rag = ASIL["aciklama"]
    bt.get_transaction_history = ASIL["gecmis"]
    bt.get_risk_score = ASIL["risk_skor"]
    agent._claude = ASIL["claude"]
    svc._veri_imzasi = ASIL["imza"]


def akis(rapor, tekrar=1):
    """Gerçek araçlarla 3 adımlık ajan akışı, `tekrar` kez art arda (her inceleme 3 Claude çağrısı)."""
    adimlar = []
    for _ in range(tekrar):
        adimlar += [
            cevap([arac_blok("a", "get_customer_info", {"customer_id": 1}),
                   arac_blok("b", "get_transaction_history", {"customer_id": 1, "sort_by": "risk", "limit": 5})], "tool_use"),
            cevap([arac_blok("c", "search_risk_policy", {"query": "yurtdışı transfer", "k": 3})], "tool_use"),
            cevap([metin_blok(rapor)], "end_turn")]
    return SahteClaude(*adimlar)


def sahte_aciklama(metin="Kural tabanlı açıklama.", llm=True, sayac=None):
    def f(risk, rag_getir, claude=None, **ayar):
        if sayac is not None:
            sayac.append(claude)
        return {"explanation": metin, "policy_sources": [], "llm_used": llm, "usage": object()}
    return f


try:
    # =========================================================== LRU önbellek
    o = onbellek.LRUOnbellek(2)
    kontrol("LRU: boşken (False, None), ıska sayılır", o.al("a") == (False, None) and o.durum()["iska"] == 1)
    o.koy("a", {"x": 1})
    o.koy("b", {"x": 2})
    o.al("a")                  # a en yeni kullanılan oldu
    o.koy("c", {"x": 3})       # dolu: en eski kullanılan (b) atılmalı
    kontrol("LRU: dolunca en uzun süredir kullanılmayan atılır (b), okunan (a) kalır",
            o.al("b")[0] is False and o.al("a") == (True, {"x": 1}) and o.al("c")[0] is True and len(o) == 2)
    o.koy("a", {"x": 99})
    kontrol("LRU: aynı anahtara yazmak boyutu büyütmez, değeri yeniler", len(o) == 2 and o.al("a")[1] == {"x": 99})
    g = o.al("a")[1]
    g["x"] = -1
    iki = {"liste": [1]}
    o.koy("k", iki)
    iki["liste"].append(2)
    kontrol("LRU: dönen değeri değiştirmek de, koyduktan sonra orijinali değiştirmek de önbelleği bozmaz (kopya)",
            o.al("a")[1] == {"x": 99} and o.al("k")[1] == {"liste": [1]})
    d = o.durum()
    kontrol("LRU: durum isabet/ıska/boyut/maks sayar", d["maks_boyut"] == 2 and d["boyut"] == 2 and d["isabet"] >= 4 and d["iska"] >= 2, d)
    o.temizle()
    kontrol("LRU: temizle boyutu ve sayaçları sıfırlar", len(o) == 0 and o.durum()["isabet"] == 0 and o.durum()["iska"] == 0)
    for kotu in (0, -1, True, 1.0, "2", None):
        try:
            onbellek.LRUOnbellek(kotu)
            kontrol(f"LRU maks_boyut={kotu!r} ValueError", False)
        except ValueError:
            kontrol(f"LRU: maks_boyut={kotu!r} -> ValueError", True)
    o = onbellek.LRUOnbellek(50)
    hatalar = []

    def is_parcacigi(n):
        try:
            for i in range(300):
                o.koy((n, i % 80), {"i": i})
                o.al((n, (i * 7) % 80))
        except Exception as e:  # noqa: BLE001
            hatalar.append(e)

    ts = [threading.Thread(target=is_parcacigi, args=(n,)) for n in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    kontrol("LRU: 8 iş parçacığı eşzamanlı okuyup yazınca hata yok, boyut sınırı aşılmıyor", not hatalar and len(o) <= 50, hatalar[:1])

    # =========================================================== servis: müşteri yok, normal akış
    temiz()
    c = SahteClaude()
    try:
        svc.incele_servis(9999, SAHTE_RAG, istemci=c)
        kontrol("Müşteri yok: MusteriYok", False)
    except svc.MusteriYok as e:
        kontrol("Müşteri yok: MusteriYok, mesajda numara var, Claude hiç çağrılmadı", "9999" in str(e) and len(c.cagrilar) == 0)

    temiz()
    c = akis(RAPOR)
    r = svc.incele_servis(1, SAHTE_RAG, istemci=c)
    kontrol("Normal: ajan raporu, kaynak 'ajan', önbellekten değil, 3 Claude çağrısı, uyarı yok",
            r["rapor"] == RAPOR and r["rapor_kaynagi"] == "ajan" and r["onbellekten"] is False and len(c.cagrilar) == 3 and r["uyarilar"] == [], r)
    kontrol("Normal: müşteri özeti araçtaki veriyle aynı (segment, şehir, 3 hesap, toplam işlem)",
            r["musteri"] == {"segment": bt.get_customer_info(1)["segment"], "city": bt.get_customer_info(1)["city"],
                             "risk_band": bt.get_customer_info(1)["risk_band"], "onboard_date": bt.get_customer_info(1)["onboard_date"],
                             "hesap_sayisi": 3, "toplam_islem": bt.get_transaction_history(1, 1)["toplam_islem"]})
    kontrol("Normal: en riskli 3 işlem, skoru azalan, ilki gerçek en riskli, doğrudan veri katmanından (Claude'dan değil)",
            r["en_riskli_islemler"] == TOP3 and len(TOP3) == 3 and TOP3[0]["risk_score"] >= TOP3[1]["risk_score"] >= TOP3[2]["risk_score"])
    kontrol("Normal: doğrulama 4 kontrol (GENEL) ve hepsi geçti; iz özeti alanları",
            [d["kontrol"] for d in r["dogrulama"]] == ["tamamlandi", "uydurma_islem_yok", "atif_gecerli", "hukum_yok"]
            and all(d["gecti"] for d in r["dogrulama"]) and set(r["iz_ozeti"]) == {"bitis", "arac_sirasi", "girdi_token", "cikti_token", "sure_ms"}
            and r["iz_ozeti"]["arac_sirasi"] == ["get_customer_info", "get_transaction_history", "search_risk_policy"])
    try:
        api.InvestigateResponse(**r)
        sema_ok = True
    except Exception as e:  # noqa: BLE001
        sema_ok = str(e)
    kontrol("Normal: servis çıktısı API şemasına (InvestigateResponse) uyuyor", sema_ok is True, sema_ok)

    # =========================================================== önbellek: isabet, yenile, imza
    temiz()
    c = akis(RAPOR, 3)
    r1 = svc.incele_servis(1, SAHTE_RAG, istemci=c)
    r2 = svc.incele_servis(1, SAHTE_RAG, istemci=c)
    kontrol("Önbellek: aynı müşteri ikinci kez -> önbellekten, Claude'a yeni çağrı yok, aynı rapor ve doğrulama",
            r2["onbellekten"] is True and len(c.cagrilar) == 3 and r2["rapor"] == r1["rapor"] and r2["dogrulama"] == r1["dogrulama"]
            and svc.onbellek_durumu()["rapor"]["isabet"] == 1)
    r3 = svc.incele_servis(1, SAHTE_RAG, istemci=c, yenile=True)
    kontrol("Önbellek: yenile=True önbelleği atlar, ajan yeniden çalışır (3 çağrı daha), onbellekten False", len(c.cagrilar) == 6 and r3["onbellekten"] is False)
    svc._veri_imzasi = lambda: ("degisti", 1)
    r4 = svc.incele_servis(1, SAHTE_RAG, istemci=c)
    kontrol("Önbellek: veri imzası değişince (Excel yenilendi) eski rapor kullanılmaz", r4["onbellekten"] is False and len(c.cagrilar) == 9)

    # =========================================================== zarif bozulma merdiveni
    temiz()
    sayac = []
    risk_rag.aciklama_uret_rag = sahte_aciklama(sayac=sayac)
    ck = CokenClaude()
    r = svc.incele_servis(1, SAHTE_RAG, istemci=ck)
    kontrol("Basamak 2: ajan çökünce kural-tabanlı açıklama döner (kaynak 'aciklama'), 200 gibi tam cevap, iki uyarı",
            r["rapor"] == "Kural tabanlı açıklama." and r["rapor_kaynagi"] == "aciklama" and r["dogrulama"] == [] and r["iz_ozeti"] is None
            and len(r["uyarilar"]) == 2 and "Ajan raporu üretilemedi" in r["uyarilar"][0] and "kural-tabanlı" in r["uyarilar"][1], r["uyarilar"])
    kontrol("Basamak 2: veri katmanı çıktısı yine tam (müşteri + 3 işlem)", r["en_riskli_islemler"] == TOP3 and r["musteri"]["hesap_sayisi"] == 3)
    kontrol("Basamak 2: açıklamaya verilen Claude, ajanın kullandığı (zaman aşımlı) istemci", sayac == [ck])
    r = svc.incele_servis(1, SAHTE_RAG, istemci=ck)
    kontrol("Basamak 2: ajan hatası önbelleğe girmez (ajan yine denenir), açıklama önbellekten gelir (Claude'a yeni açıklama çağrısı yok)",
            ck.cagri == 2 and len(sayac) == 1 and r["onbellekten"] is True and len(svc.RAPOR_ONBELLEK) == 0)

    temiz()
    risk_rag.aciklama_uret_rag = sahte_aciklama()
    c = SahteClaude(*[cevap([arac_blok(f"t{i}", "get_customer_info", {"customer_id": 1})], "tool_use") for i in range(10)])
    r = svc.incele_servis(1, SAHTE_RAG, istemci=c)
    kontrol("Basamak 2: ajan adım sınırında kesilirse (tamamlanmadı) rapor olarak KULLANILMAZ, açıklamaya düşülür, bitis uyarıda, önbelleğe girmez",
            r["rapor_kaynagi"] == "aciklama" and "adim_siniri" in r["uyarilar"][0] and len(svc.RAPOR_ONBELLEK) == 0 and len(c.cagrilar) == 6, r["uyarilar"])

    temiz()

    def patla(*a, **k):
        raise RuntimeError("açıklama çöktü")

    risk_rag.aciklama_uret_rag = patla
    r = svc.incele_servis(1, SAHTE_RAG, istemci=CokenClaude())
    kontrol("Basamak 3: ajan ve açıklama çökerse istisna yok; rapor None, kaynak 'yok', veri yine dolu, iki uyarı",
            r["rapor"] is None and r["rapor_kaynagi"] == "yok" and r["en_riskli_islemler"] == TOP3 and len(r["uyarilar"]) == 2
            and "açıklaması da üretilemedi" in r["uyarilar"][1])

    temiz()
    bt.get_transaction_history = lambda *a, **k: {"customer_id": 1, "toplam_islem": 0, "donen": 0, "siralama": "risk", "islemler": []}
    c = SahteClaude()
    r = svc.incele_servis(1, SAHTE_RAG, istemci=c)
    kontrol("İşlemi olmayan müşteri: Claude çağrılmaz, rapor yok, açıklayıcı uyarı, 200 gibi tam cevap",
            len(c.cagrilar) == 0 and r["rapor_kaynagi"] == "yok" and r["en_riskli_islemler"] == [] and "işlem kaydı yok" in r["uyarilar"][0])
    bt.get_transaction_history = lambda *a, **k: {"error": "bozuk"}
    try:
        svc.incele_servis(1, SAHTE_RAG, istemci=SahteClaude())
        kontrol("Geçmiş hata verirse RuntimeError", False)
    except RuntimeError as e:
        kontrol("Müşteri var ama geçmiş hata veriyorsa çekirdek bozuk: RuntimeError (sessizce 'yok' dönmez)", "bozuk" in str(e))
    temiz()

    # =========================================================== doğrulama bayrakları
    c = akis(RAPOR + "\nAyrıca txn 99999 de şüpheli.")
    r = svc.incele_servis(1, SAHTE_RAG, istemci=c)
    kalan = [d["kontrol"] for d in r["dogrulama"] if not d["gecti"]]
    kontrol("Doğrulama kaldıysa rapor yine döner (gizlenmez), kalan kontrol listede, uyarıda adı geçer",
            r["rapor_kaynagi"] == "ajan" and kalan == ["uydurma_islem_yok"] and any("uydurma_islem_yok" in u for u in r["uyarilar"]), r["uyarilar"])
    r2 = svc.incele_servis(1, SAHTE_RAG, istemci=c)
    kontrol("Önbellekten gelen rapor için de aynı uyarı yeniden üretilir", r2["onbellekten"] is True and any("uydurma_islem_yok" in u for u in r2["uyarilar"]))

    # =========================================================== açıklama önbellek anahtarı
    temiz()
    cagri = []
    risk_rag.aciklama_uret_rag = sahte_aciklama(sayac=cagri)
    rk = {"risk_score": 70, "risk_label": "suspicious", "rule_ids": ["RISKY_CHANNEL", "AMOUNT_ANOMALY"],
          "reasons": ["Riskli kanal: web (+15)", "Tutar anormal (z=9.0) (+30)"]}
    a1, h1 = svc.aciklama_onbellekli(rk, SAHTE_RAG, "claude")
    a2, h2 = svc.aciklama_onbellekli(dict(rk), SAHTE_RAG, "claude")
    kontrol("Açıklama önbelleği: aynı etiket+skor+kural+neden -> ikinci çağrı önbellekten, Claude'a yeni çağrı yok", (h1, h2) == (False, True) and len(cagri) == 1 and a1 == a2)
    rk2 = {**rk, "reasons": ["Riskli kanal: web (+15)", "Tutar anormal (z=7.2) (+30)"]}
    _, h3 = svc.aciklama_onbellekli(rk2, SAHTE_RAG, "claude")
    kontrol("Açıklama önbelleği: kurallar aynı ama z değeri farklıysa ISKA (yanlış z'yi başka işleme göstermeyiz)", h3 is False and len(cagri) == 2)
    rk3 = {**rk, "risk_score": 75}
    _, h4 = svc.aciklama_onbellekli(rk3, SAHTE_RAG, "claude")
    kontrol("Açıklama önbelleği: skor farklıysa ISKA", h4 is False and len(cagri) == 3)
    svc.ACIKLAMA_ONBELLEK.temizle()
    risk_rag.aciklama_uret_rag = sahte_aciklama(llm=False)
    svc.aciklama_onbellekli({**rk, "reasons": [], "rule_ids": []}, SAHTE_RAG, None)
    kontrol("Açıklama önbelleği: Claude'un üretmediği (llm_used False, sabit cümle) sonuç saklanmaz", len(svc.ACIKLAMA_ONBELLEK) == 0)
    risk_rag.aciklama_uret_rag = patla
    try:
        svc.aciklama_onbellekli(rk, SAHTE_RAG, "claude")
    except RuntimeError:
        pass
    kontrol("Açıklama önbelleği: hata olursa hiçbir şey saklanmaz, istisna yukarı çıkar", len(svc.ACIKLAMA_ONBELLEK) == 0)

    # =========================================================== açıklama basamağında istemci kurma
    temiz()
    risk_rag.aciklama_uret_rag = sahte_aciklama()

    def istemci_kurma(*a, **k):
        raise AssertionError("kural yokken Claude istemcisi kurulmamalıydı")

    agent._claude = istemci_kurma
    bt.get_risk_score = lambda *a, **k: {"risk_score": 0, "risk_label": "normal", "reasons": [], "rule_ids": []}
    r = svc.incele_servis(1, SAHTE_RAG, istemci=None, ajan=lambda cid, istemci=None: (_ for _ in ()).throw(RuntimeError("x")))
    kontrol("Kural tetiklenmeyen işlemde açıklama basamağı Claude istemcisi kurmaz (anahtarsız ortamda bile çökmez)", r["rapor_kaynagi"] == "aciklama", r["uyarilar"])
    temiz()

    # =========================================================== süre ölçümü
    sayac_saat = iter([10.0, 10.5])
    r = svc.incele_servis(1, SAHTE_RAG, istemci=akis(RAPOR), saat=lambda: next(sayac_saat))
    kontrol("sure_ms: başlangıç ve bitiş okumasından hesaplanır (0.5 sn = 500 ms)", r["sure_ms"] == 500, r["sure_ms"])
    temiz()

    # =========================================================== API: gerçek HTTP katmanı
    istemci = TestClient(api.app)
    agent._istemci = akis(RAPOR, 3)
    e = istemci.post("/investigate", json={"customer_id": 1})
    j = e.json()
    kontrol("API: 200, şema alanları tam, ilk işlem gerçek en riskli, ajan raporu",
            e.status_code == 200 and set(j) == {"customer_id", "musteri", "en_riskli_islemler", "rapor", "rapor_kaynagi", "onbellekten",
                                                "dogrulama", "uyarilar", "iz_ozeti", "sure_ms"}
            and j["en_riskli_islemler"][0]["txn_id"] == GERCEK and j["rapor_kaynagi"] == "ajan" and j["rapor"] == RAPOR, str(j)[:300])
    e2 = istemci.post("/investigate", json={"customer_id": 1})
    kontrol("API: ikinci istek önbellekten (Claude'a yeni çağrı yok)", e2.json()["onbellekten"] is True and len(agent._istemci.cagrilar) == 3)
    e3 = istemci.post("/investigate?yenile=true", json={"customer_id": 1})
    kontrol("API: ?yenile=true ajanı yeniden çalıştırır", e3.json()["onbellekten"] is False and len(agent._istemci.cagrilar) == 6)
    d = istemci.get("/onbellek-durumu").json()
    kontrol("API: /onbellek-durumu rapor ve açıklama sayaçlarını verir (isabet>=1)", d["rapor"]["isabet"] >= 1 and set(d["aciklama"]) == {"boyut", "maks_boyut", "isabet", "iska"}, str(d))
    e = istemci.post("/investigate", json={"customer_id": 9999})
    kontrol("API: olmayan müşteri -> 404, mesajda numara", e.status_code == 404 and "9999" in e.json()["detail"], e.text)
    for ad, govde in (("sıfır", {"customer_id": 0}), ("negatif", {"customer_id": -5}), ("metin '1'", {"customer_id": "1"}),
                      ("ondalık", {"customer_id": 1.5}), ("bool", {"customer_id": True}), ("alan yok", {}), ("yanlış ad", {"musteri": 1}),
                      ("null", {"customer_id": None})):
        e = istemci.post("/investigate", json=govde)
        kontrol(f"API: geçersiz girdi ({ad}) -> 422", e.status_code == 422, f"{e.status_code} {e.text[:100]}")
    kontrol("API: gövdesiz istek -> 422", istemci.post("/investigate").status_code == 422)

    temiz()
    risk_rag.aciklama_uret_rag = sahte_aciklama("Açıklama metni.")
    agent._istemci = CokenClaude()
    e = istemci.post("/investigate", json={"customer_id": 1})
    j = e.json()
    kontrol("API: Claude çökerse HÂLÂ 200, kaynak 'aciklama', veri tam", e.status_code == 200 and j["rapor_kaynagi"] == "aciklama" and j["rapor"] == "Açıklama metni."
            and j["en_riskli_islemler"][0]["txn_id"] == GERCEK, e.text[:200])
    svc.ACIKLAMA_ONBELLEK.temizle()  # önceki adımın açıklaması önbellekte; "her şey çöktü" için temiz başla
    risk_rag.aciklama_uret_rag = patla
    e = istemci.post("/investigate?yenile=true", json={"customer_id": 1})
    j = e.json()
    kontrol("API: her şey çökerse HÂLÂ 200, rapor null, kaynak 'yok', veri tam, iki uyarı",
            e.status_code == 200 and j["rapor"] is None and j["rapor_kaynagi"] == "yok" and j["en_riskli_islemler"][0]["txn_id"] == GERCEK and len(j["uyarilar"]) == 2, e.text[:200])
    temiz()
    kontrol("API: eski uç noktalar bozulmadı (/predict-risk 200)",
            istemci.post("/predict-risk", json={"account_id": 1, "amount": 100, "status": "OK", "channel": "ATM", "is_international": 0}).status_code == 200)

    # =========================================================== şema, gerçek veri satırlarıyla
    hatali = []
    for cid in range(1, 101):
        for satir in bt.get_transaction_history(cid, 3, "risk")["islemler"]:
            try:
                api.IslemOzeti(**satir)
            except Exception as ex:  # noqa: BLE001
                hatali.append((cid, str(ex)[:80]))
        try:
            b = bt.get_customer_info(cid)
            api.MusteriOzeti(segment=b["segment"], city=b["city"], risk_band=b["risk_band"], onboard_date=b["onboard_date"],
                             hesap_sayisi=len(b["accounts"]), toplam_islem=1)
        except Exception as ex:  # noqa: BLE001
            hatali.append((cid, str(ex)[:80]))
    kontrol("Şema: ilk 100 müşterinin müşteri özeti ve en riskli 3 işlemi API modeline uyuyor (tip uyuşmazlığı 500 vermez)", not hatali, hatali[:2])

    # =========================================================== ısıtma (lifespan)
    cagri = []
    sirali = []
    veri.tablolar = lambda *a, **k: (sirali.append("veri"), ASIL["tablolar"](*a, **k))[1]
    api.rag_getir = lambda: sirali.append("rag")
    os.environ.pop("RAG_ISITMA", None)
    with TestClient(api.app) as ic:
        ic.get("/")
    kontrol("Isıtma: sunucu açılırken veri tabloları ve rehber modeli yüklenir (sırayla)", sirali == ["veri", "rag"], sirali)
    sirali.clear()
    os.environ["RAG_ISITMA"] = "0"
    with TestClient(api.app) as ic:
        ic.get("/")
    kontrol("Isıtma: RAG_ISITMA=0 ile kapatılabilir", sirali == [])
    os.environ.pop("RAG_ISITMA", None)

    def isitma_patla():
        raise RuntimeError("model indirilemedi")

    api.rag_getir = isitma_patla
    with TestClient(api.app) as ic:
        a = ic.get("/").status_code
        b = ic.post("/predict-risk", json={"account_id": 1, "amount": 100, "status": "OK", "channel": "ATM", "is_international": 0}).status_code
    kontrol("Isıtma: model yüklenemese bile sunucu açılır ve istek karşılar (graceful), ilk gerçek istekte yeniden denenir", (a, b) == (200, 200), (a, b))
    api.rag_getir = SAHTE_RAG
    veri.tablolar = ASIL["tablolar"]
finally:
    bt._rag = ASIL["bt_rag"]
    api.rag_getir = ASIL["api_rag"]
    risk_rag.aciklama_uret_rag = ASIL["aciklama"]
    agent._istemci = ASIL["istemci"]
    agent._claude = ASIL["claude"]
    svc._veri_imzasi = ASIL["imza"]
    bt.get_transaction_history = ASIL["gecmis"]
    bt.get_risk_score = ASIL["risk_skor"]
    veri.tablolar = ASIL["tablolar"]
    os.environ.pop("RAG_ISITMA", None)
    logging.getLogger("risk_api").disabled = False

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
