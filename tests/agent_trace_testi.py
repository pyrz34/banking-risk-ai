"""Gün 17: ajan izi testleri. Çalıştır: python tests\\agent_trace_testi.py
Ağ yok, gerçek Claude yok (sahte istemci; araçlar gerçek, rehber araması sahte vektörle).
Ölçtüğü: iz doğru kuruluyor mu (araç sırası, hata/sınır sayıları, token, süre), ekrana okunur basılıyor mu, diske doğru
ve güvenli yazılıyor mu, karşılaştırma betiği her varyantı doğru sistem mesajıyla çalıştırıyor mu.
ÖLÇMEDİĞİ: gerçek Claude'un cevabının kalitesi (onu tests\\prompt_karsilastirma.py ile oku).
"""
import json
import os
import sys
import tempfile
from datetime import datetime
from types import SimpleNamespace

import numpy as np

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))
sys.path.insert(0, os.path.join(KOK, "tests"))

import agent  # noqa: E402
import agent_trace as at  # noqa: E402
import prompt_karsilastirma as pk  # noqa: E402
from tools import banking_tools as bt  # noqa: E402

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


class SahteSaat:
    """Her okumada 0.5 sn ilerler: süreler elle hesaplanabilir (kaç kez okunduğu = kaç kez 500 ms)."""
    def __init__(self):
        self.t = -0.5

    def __call__(self):
        self.t += 0.5
        return self.t


class SahteModel:
    def sorgu_vektoru(self, soru):
        return [np.array([1.0, 0.0, 0.0])]


def chunk(i, sayfa):
    return {"id": i, "text": f"rehber metni {i}", "page": sayfa, "page_end": sayfa, "codes": [], "section": "Bölüm"}


SAHTE_CHUNKLAR = [chunk(0, 5), chunk(1, 6), chunk(2, 9)]
SAHTE_VEKT = np.array([[0.1, 1, 0], [0.9, 0.1, 0], [1.0, 0, 0]], dtype=np.float32)
SAHTE_VEKT = SAHTE_VEKT / np.linalg.norm(SAHTE_VEKT, axis=1, keepdims=True)

GERCEK_SAAT = agent._saat
ASIL_RAG = bt._rag
ZAMAN = datetime(2026, 10, 20, 12, 0, 0)
GECERLI = dict(account_id=226, amount=50000, status="FAILED", channel="Web", is_international=1)


def saatli_calistir(c, **kw):
    agent._saat = SahteSaat()
    try:
        return agent.calistir("görev", istemci=c, **kw)
    finally:
        agent._saat = GERCEK_SAAT


def kur(gorev, sonuc, **kw):
    return at.iz_olustur(gorev, sonuc, model="m", max_steps=5, sistem_mesaji=agent.SISTEM_MESAJI, zaman=ZAMAN, **kw)


def json_gidis_donus(iz):
    try:
        return json.loads(json.dumps(iz, ensure_ascii=False)) == iz
    except TypeError:
        return False


bt._rag = lambda: (SahteModel(), SAHTE_CHUNKLAR, SAHTE_VEKT)
try:
    # =========================================================== yardımcılar
    kontrol("ozetle: kısa metin aynen", at.ozetle("kısa") == "kısa")
    o = at.ozetle("ş" * 500, 100)
    kontrol("ozetle: uzun metin kesilir, atılan karakter sayısı yazılır, Türkçe karakter bozulmaz", o == "ş" * 100 + "... (+400 karakter)", o)
    kontrol("ozetle: sözlük JSON metnine çevrilip kısaltılır, tam sınırda kısaltmaz",
            at.ozetle({"a": "ğ" * 50}, 1000).startswith('{"a": "ğğ') and at.ozetle("x" * 100, 100) == "x" * 100)
    i1, i2 = at.sistem_mesaji_id(agent.SISTEM_MESAJI), at.sistem_mesaji_id(agent.SISTEM_MESAJI_ESKI)
    kontrol("sistem_mesaji_id: 8 karakter, aynı metinde aynı, eski/yeni farklı",
            len(i1) == 8 and i1 == at.sistem_mesaji_id(agent.SISTEM_MESAJI) and i1 != i2 and all(ch in "0123456789abcdef" for ch in i1))
    kontrol("maliyet: (1000 girdi x 3 + 500 çıktı x 15) / 1M = 0.0105", at.maliyet_usd({"girdi": 1000, "cikti": 500}, 3, 15) == 0.0105)
    kontrol("maliyet: fiyat yoksa None (uydurma sayı yok)",
            at.maliyet_usd({"girdi": 1, "cikti": 1}, None, 15) is None and at.maliyet_usd({"girdi": 1, "cikti": 1}, 3, None) is None)
    kontrol("fiyatlar_env: geçerli değerler okunur", at.fiyatlar_env({"GIRDI_FIYAT_1M": "3", "CIKTI_FIYAT_1M": "15.5"}) == (3.0, 15.5))
    for ad, env in (("eksik", {"GIRDI_FIYAT_1M": "3"}), ("bozuk", {"GIRDI_FIYAT_1M": "x", "CIKTI_FIYAT_1M": "1"}),
                    ("negatif", {"GIRDI_FIYAT_1M": "-1", "CIKTI_FIYAT_1M": "1"}), ("nan", {"GIRDI_FIYAT_1M": "nan", "CIKTI_FIYAT_1M": "1"}),
                    ("sonsuz", {"GIRDI_FIYAT_1M": "inf", "CIKTI_FIYAT_1M": "1"}), ("boş", {})):
        kontrol(f"fiyatlar_env: {ad} -> (None, None)", at.fiyatlar_env(env) == (None, None))

    # =========================================================== senaryo A: tek araç
    ARGA = {"customer_id": 1, "sort_by": "risk", "limit": 1}
    sA = saatli_calistir(SahteClaude(cevap([arac_blok("a", "get_transaction_history", ARGA)], "tool_use", 2000, 100),
                                     cevap([metin_blok("En riskli işlem 51712.")], "end_turn", 2400, 200)))
    izA = kur("1 numaralı müşterinin en riskli işlemi?", sA, girdi_1m=3, cikti_1m=15)
    gercek = bt.get_transaction_history(1, 1, "risk")
    kontrol("A tek araç: araç sırası, sayılar, bitiş", izA["arac_sirasi"] == ["get_transaction_history"] and izA["arac_sayisi"] == 1
            and izA["hatali_arac_sayisi"] == 0 and izA["calistirilmayan_arac_sayisi"] == 0 and izA["bitis"] == "tamamlandi", izA)
    kontrol("A: görev, model, max_steps, zaman, sürüm, sistem mesajı kimliği, cevap",
            (izA["gorev"], izA["model"], izA["max_steps"], izA["zaman"], izA["surum"], izA["cevap"])
            == ("1 numaralı müşterinin en riskli işlemi?", "m", 5, "2026-10-20T12:00:00", 1, "En riskli işlem 51712.")
            and izA["sistem_mesaji_id"] == at.sistem_mesaji_id(agent.SISTEM_MESAJI))
    kontrol("A: token toplamı, süre (3500 ms), maliyet (4400x3 + 300x15)/1M = 0.0177",
            izA["kullanim"] == {"girdi": 4400, "cikti": 300, "cagri": 2} and izA["sure_ms"] == 3500 and izA["maliyet_usd"] == 0.0177, izA)
    kontrol("A: izdeki araç girdisi Claude'un verdiği, sonuç aracın gerçek sonucu (tam, kısaltılmamış)",
            izA["adimlar"][0]["araclar"][0]["girdi"] == ARGA and izA["adimlar"][0]["araclar"][0]["sonuc"] == gercek)
    kontrol("A: maliyet fiyat verilmezse None", kur("g", sA)["maliyet_usd"] is None)
    kontrol("A: iz JSON'a çevrilip geri okununca aynı (özel tür sızmamış)", json_gidis_donus(izA))
    sA["cevap"] = "sonradan değişti"
    sA["adimlar"][0]["araclar"][0]["sonuc"]["x"] = 1
    kontrol("A: iz kopya, sonuç sözlüğü sonradan değişse iz bozulmaz", izA["cevap"] == "En riskli işlem 51712." and "x" not in izA["adimlar"][0]["araclar"][0]["sonuc"])

    # =========================================================== senaryo B: iki bağımlı araç (geçmiş -> rehber)
    SORGU = {"query": "yurtdışı transfer şüpheli işlem bildirimi", "k": 3}
    sB = saatli_calistir(SahteClaude(cevap([arac_blok("a", "get_transaction_history", {"customer_id": 1, "sort_by": "risk", "limit": 5})], "tool_use"),
                                     cevap([arac_blok("b", "search_risk_policy", SORGU)], "tool_use"),
                                     cevap([metin_blok("Rehberde doğrudan talimat bulamadım.")], "end_turn")))
    izB = kur("risk + rehber", sB)
    kontrol("B iki araç: sıra geçmiş -> rehber, 3 adım, 2 araç, hata yok",
            izB["arac_sirasi"] == ["get_transaction_history", "search_risk_policy"] and len(izB["adimlar"]) == 3 and izB["arac_sayisi"] == 2 and izB["hatali_arac_sayisi"] == 0, izB["arac_sirasi"])
    pol = izB["adimlar"][1]["araclar"][0]
    kontrol("B: rehber aracının girdisi Claude'un yazdığı sorgu, sonuç sayfaya göre sıralı (en yakın chunk s.9)",
            pol["girdi"] == SORGU and [x["sayfa"] for x in pol["sonuc"]["sonuclar"]] == [9, 6, 5], pol)
    kontrol("B: süre 5500 ms (3 Claude + 2 araç adımı x 500, + başlangıç/bitiş okuması)", izB["sure_ms"] == 5500 and all(a["sure_ms"] == 500 for a in izB["adimlar"]), izB["sure_ms"])
    kontrol("B: iz JSON'a çevrilip geri okununca aynı", json_gidis_donus(izB))

    # =========================================================== senaryo C: hata, sonra düzeltme
    sC = saatli_calistir(SahteClaude(cevap([arac_blok("a", "get_risk_score", {**GECERLI, "channel": "web"})], "tool_use"),
                                     cevap([arac_blok("b", "get_risk_score", GECERLI)], "tool_use"),
                                     cevap([metin_blok("Skor 100.")], "end_turn")))
    izC = kur("hata düzeltme", sC)
    kontrol("C hata sonrası düzeltme: 2 araç çalıştı, 1'i hatalı, sonunda tamamlandı",
            izC["arac_sayisi"] == 2 and izC["hatali_arac_sayisi"] == 1 and izC["bitis"] == "tamamlandi" and "error" in izC["adimlar"][0]["araclar"][0]["sonuc"]
            and "error" not in izC["adimlar"][1]["araclar"][0]["sonuc"], izC)
    sU = saatli_calistir(SahteClaude(cevap([arac_blok("a", "uydur", {})], "tool_use"), cevap([metin_blok("Yapamam.")], "end_turn")))
    kontrol("C: uydurma araç adı hatalı araç sayılır", kur("g", sU)["hatali_arac_sayisi"] == 1)

    # =========================================================== senaryo D: sınır, E: aynı adımda iki araç, F: araçsız
    M1 = {"customer_id": 1}
    sD = saatli_calistir(SahteClaude(*[cevap([arac_blok(f"t{i}", "get_customer_info", M1)], "tool_use") for i in range(5)]), max_steps=2)
    izD = kur("sınır", sD)
    kontrol("D adım sınırı: 1 araç çalıştı, 1 araç çalıştırılmadı, bitis=adim_siniri, sayılar ayrı tutuluyor",
            izD["bitis"] == "adim_siniri" and izD["arac_sayisi"] == 1 and izD["calistirilmayan_arac_sayisi"] == 1 and izD["arac_sirasi"] == ["get_customer_info"], izD)
    sE = saatli_calistir(SahteClaude(cevap([arac_blok("a", "get_customer_info", M1), arac_blok("b", "get_risk_score", GECERLI)], "tool_use"),
                                     cevap([metin_blok("Tamam.")], "end_turn")))
    kontrol("E aynı adımda iki araç: araç sırası Claude'un istediği sıra", kur("g", sE)["arac_sirasi"] == ["get_customer_info", "get_risk_score"])
    sF = saatli_calistir(SahteClaude(cevap([metin_blok("Merhaba!")], "end_turn")))
    izF = kur("selam", sF)
    kontrol("F araçsız: araç sırası boş, sayılar 0", izF["arac_sirasi"] == [] and izF["arac_sayisi"] == 0 and izF["hatali_arac_sayisi"] == 0)

    # =========================================================== ekrana yazdırma
    yB = at.yazdir_metni(izB)
    tam_sonuc = json.dumps(izB["adimlar"][0]["araclar"][0]["sonuc"], ensure_ascii=False)
    kontrol("yazdir: görev, adım satırları, süreler, araçlar, bitiş, cevap",
            all(x in yB for x in ("Görev: risk + rehber", "Adım 1 [tool_use]", "Claude 0.5 sn", "[0.5 sn]", "get_transaction_history(",
                                  "Bitiş nedeni: tamamlandi", "toplam süre: 5.5 sn", "Rehberde doğrudan talimat bulamadım.")), yB)
    kontrol("yazdir: araç sırası ve sistem mesajı kimliği yazılı",
            "Araçlar: get_transaction_history -> search_risk_policy" in yB and f"sistem mesajı: {izB['sistem_mesaji_id']}" in yB)
    kontrol("yazdir: uzun araç sonucu kısaltılır (ekranda tamamı yok), tamamı izin içinde duruyor",
            len(tam_sonuc) > at.EKRAN_SONUC_UZUNLUGU and "karakter)" in yB and tam_sonuc not in yB and izB["adimlar"][0]["araclar"][0]["sonuc"]["donen"] == 5)
    kontrol("yazdir: fiyat yoksa maliyet satırı yok, varsa var", "maliyet" not in yB.lower() and "Yaklaşık maliyet: $0.0177" in at.yazdir_metni(izA))
    kontrol("yazdir: çalıştırılmayan araç işaretli", "ÇALIŞTIRILMADI" in at.yazdir_metni(izD))
    kontrol("yazdir: araçsız çalıştırmada 'Araçlar: (yok)'", "Araçlar: (yok)" in at.yazdir_metni(izF))
    eski = json.loads(json.dumps(izB))
    eski["sure_ms"] = None
    for a in eski["adimlar"]:
        a.pop("sure_ms")
        for r in a["araclar"]:
            r.pop("sure_ms")
    kontrol("yazdir: süre bilgisi olmayan (eski/eksik) iz çökmez, '?' yazar", "toplam süre: ?" in at.yazdir_metni(eski) and "Claude ?" in at.yazdir_metni(eski))

    # =========================================================== diske kaydetme
    with tempfile.TemporaryDirectory() as tmp:
        klasor = os.path.join(tmp, "data", "izler")
        izK = kur("şüpheli işlem", sA)
        izK["cevap"] = "şüpheli işlem bulundu"
        yol = at.kaydet(izK, klasor, simdi=ZAMAN)
        kontrol("kaydet: olmayan iç içe klasörü oluşturur, dosya adı zaman damgalı", os.path.dirname(yol) == klasor and os.path.basename(yol) == "iz_20261020-120000-000000.json", yol)
        ham = open(yol, encoding="utf-8").read()
        kontrol("kaydet: dosya geri okununca iz ile aynı, Türkçe karakter \\u kaçışına çevrilmemiş", json.loads(ham) == izK and "şüpheli" in ham)
        kontrol("kaydet: .tmp dosyası kalmadı", all(f.endswith(".json") for f in os.listdir(klasor)))
        izK2 = dict(izK, cevap="ikinci")
        yol2 = at.kaydet(izK2, klasor, simdi=ZAMAN)
        kontrol("kaydet: aynı damgada üstüne yazmaz, sayaçlı yeni dosya açar, ilki bozulmaz",
                yol2 != yol and os.path.exists(yol) and json.load(open(yol, encoding="utf-8"))["cevap"] == "şüpheli işlem bulundu" and json.load(open(yol2, encoding="utf-8"))["cevap"] == "ikinci", (yol, yol2))
        yol3 = at.kaydet(izK, klasor)
        kontrol("kaydet: simdi verilmezse gerçek zamanla kaydeder", os.path.exists(yol3) and len(os.listdir(klasor)) == 3)
        dosya = os.path.join(tmp, "dosya.txt")
        open(dosya, "w").write("x")
        try:
            at.kaydet(izK, dosya)
            kontrol("kaydet: klasör yolu aslında dosyaysa OSError", False)
        except OSError:
            kontrol("kaydet: klasör yolu aslında dosyaysa OSError (main bunu yakalayıp cevabı korur)", True)
        yeni = os.path.join(tmp, "bozuk")
        try:
            at.kaydet({"x": {1, 2}}, yeni)
            kontrol("kaydet: JSON'a çevrilemeyen iz TypeError", False)
        except TypeError:
            kontrol("kaydet: JSON'a çevrilemeyen iz hata verir ve yarım/.tmp dosya bırakmaz", os.listdir(yeni) == [])

    # =========================================================== karşılaştırma betiği
    kontrol("betik: 3 görev, 2 varyant; eski=1-8, yeni=1-9",
            len(pk.GOREVLER) == 3 and list(pk.VARYANTLAR) == ["eski(1-8)", "yeni(1-9)"] and pk.VARYANTLAR["eski(1-8)"] == agent.SISTEM_MESAJI_ESKI
            and pk.VARYANTLAR["yeni(1-9)"] == agent.SISTEM_MESAJI)
    kontrol("betik: Türkçe küçük harf (İ, I)", pk._kucuk("İç Yönetmeliğine IŞIK") == "iç yönetmeliğine ışık")
    metinler = ["a"] * 12
    metinler[1] = "İç yönetmeliğe bakın"      # G1 yeni değil: sıra 1 = G1 yeni, ipucu kelimesi yok görevde
    metinler[2] = "Bankanızın İç Yönetmeliğine bakın."   # G3 eski -> ipucu VAR
    metinler[4] = ""                           # G4 eski, ilk tekrar -> boş cevap -> RuntimeError
    metinler[5] = "Bu ülke riskli ülke olarak geçiyor."  # G4 yeni -> ipucu VAR
    c = SahteClaude(*[cevap([metin_blok(m)] if m else [], "end_turn") for m in metinler])
    with tempfile.TemporaryDirectory() as tmp:
        k = pk.karsilastir(pk.GOREVLER, pk.VARYANTLAR, 2, istemci=c, iz_klasoru=tmp)
        kayitli = len([f for f in os.listdir(tmp) if f.endswith(".json")])
    kontrol("betik: 3 görev x 2 varyant x 2 tekrar = 12 çalıştırma, sıra tekrar > görev > varyant",
            len(k) == 12 and [(x["gorev"][:2], x["varyant"][:4], x["tekrar"]) for x in k[:6]]
            == [("G1", "eski", 1), ("G1", "yeni", 1), ("G3", "eski", 1), ("G3", "yeni", 1), ("G4", "eski", 1), ("G4", "yeni", 1)])
    kontrol("betik: her çalıştırma kendi varyantının sistem mesajıyla çağrıldı (eski, yeni, eski, yeni...)",
            [x["system"] for x in c.cagrilar] == [agent.SISTEM_MESAJI_ESKI, agent.SISTEM_MESAJI] * 6)
    kontrol("betik: boş cevap veren çalıştırma hata olarak kaydedildi, diğerleri sürdü",
            k[4]["hata"] is not None and k[4]["hata"].startswith("RuntimeError") and sum(1 for x in k if x["hata"]) == 1 and len(c.cagrilar) == 12, k[4])
    kontrol("betik: anahtar kelime ipucu (İ'li metinde de) doğru işaretlendi, ilgisiz görevde işaretlenmedi",
            k[2]["ipucu"] is True and k[5]["ipucu"] is True and k[1]["ipucu"] is False and k[0]["ipucu"] is False, [x["ipucu"] for x in k])
    kontrol("betik: başarılı her çalıştırmanın izi diske yazıldı (11), hatalı olan yazılmadı", kayitli == 11, kayitli)
    kayitlar = [
        {"gorev": "G", "varyant": "v", "hata": None, "girdi": 100, "cikti": 50, "araclar": ["a"], "ipucu": True},
        {"gorev": "G", "varyant": "v", "hata": None, "girdi": 200, "cikti": 50, "araclar": ["a", "b", "c"], "ipucu": False},
        {"gorev": "G", "varyant": "v", "hata": "X", "girdi": 0, "cikti": 0, "araclar": [], "ipucu": False},
        {"gorev": "H", "varyant": "v", "hata": "X", "girdi": 0, "cikti": 0, "araclar": [], "ipucu": False},
    ]
    tablo = pk.ozet_tablosu(kayitlar).splitlines()
    kontrol("özet tablosu: başlık + 2 grup; ortalamalar yalnız başarılı çalıştırmalardan (token 200, araç 2.0), hata sayılır, ipucu 1/2",
            len(tablo) == 3 and tablo[1].split() == ["G", "v", "3", "1", "200", "2.0", "1/2"] and tablo[2].split() == ["H", "v", "1", "1", "-", "-", "0/0"], tablo)
    kontrol("betik: --tekrar okuma (yok -> 2, 3 -> 3)", pk.tekrar_oku([]) == 2 and pk.tekrar_oku(["--tekrar", "3"]) == 3 and pk.tekrar_oku(["--tekrar", "10"]) == 10)
    for kotu in (["--tekrar"], ["--tekrar", "0"], ["--tekrar", "11"], ["--tekrar", "x"], ["3"], ["--tekrar", "3", "fazla"]):
        try:
            pk.tekrar_oku(kotu)
            kontrol(f"betik: {kotu} -> SystemExit", False)
        except SystemExit:
            kontrol(f"betik: {kotu} -> anlaşılır SystemExit", True)
finally:
    bt._rag = ASIL_RAG
    agent._saat = GERCEK_SAAT

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
