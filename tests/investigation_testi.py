"""Gün 18: inceleme ajanı testleri. Çalıştır: python tests\\investigation_testi.py
Ağ yok, gerçek Claude yok (sahte istemci; araçlar gerçek, rehber araması sahte vektörle). Hızlı ve ücretsiz.
Ölçtüğü: prompt/görev/komut satırı doğru mu, ajan doğru ayarlarla çalışıyor mu, rapor kontrolleri doğru yakalıyor mu
(uydurma işlem, geçersiz atıf, hüküm dili, eksik başlık...), mini-eval betiği doğru kuruluyor ve hesaplıyor mu.
ÖLÇMEDİĞİ: gerçek Claude'un rapor kalitesi (onu tests\\inceleme_degerlendirme.py ile oku).
"""
import os
import sys
from types import SimpleNamespace

import numpy as np

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))
sys.path.insert(0, os.path.join(KOK, "tests"))

import agent  # noqa: E402
import agent_trace  # noqa: E402
import inceleme_degerlendirme as ev  # noqa: E402
import investigation as inv  # noqa: E402
import investigation_checks as ck  # noqa: E402
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


class SahteModel:
    def sorgu_vektoru(self, soru):
        return [np.array([1.0, 0.0, 0.0])]


def chunk(i, sayfa, son=None):
    return {"id": i, "text": f"rehber metni {i}", "page": sayfa, "page_end": son or sayfa, "codes": [], "section": "Bölüm"}


CHUNKLAR = [chunk(0, 5, 6), chunk(1, 8), chunk(2, 9)]
VEKT = np.array([[0.1, 1, 0], [0.9, 0.1, 0], [1.0, 0, 0]], dtype=np.float32)
VEKT = VEKT / np.linalg.norm(VEKT, axis=1, keepdims=True)
ASIL_RAG = bt._rag
bt._rag = lambda: (SahteModel(), CHUNKLAR, VEKT)

GERCEK = bt.get_transaction_history(1, 1, "risk")["islemler"][0]["txn_id"]
RAPOR = (f"**Müşteri özeti**: Bireysel, 3 hesap, 294 işlem.\n**Öne çıkan işlemler**: txn {GERCEK}, 14.717 TL, Web, NL, skor 70.\n"
         "**Rehber dayanağı**: Şüpheli işlem bildirimi zorunludur (s.9).\n**Doğrulanamayanlar**: NL'nin riskli sayılıp sayılmadığı.\n"
         "**Öneri**: Analist işlemi gerekçesiyle birlikte değerlendirebilir.")


def tam_akis(rapor):
    """Gerçek araçlarla 3 adım: (müşteri + geçmiş) -> rehber -> rapor."""
    c = SahteClaude(
        cevap([arac_blok("a", "get_customer_info", {"customer_id": 1}),
               arac_blok("b", "get_transaction_history", {"customer_id": 1, "sort_by": "risk", "limit": 5})], "tool_use"),
        cevap([arac_blok("c", "search_risk_policy", {"query": "yurtdışı transfer bildirim", "k": 3})], "tool_use"),
        cevap([metin_blok(rapor)], "end_turn"))
    return inv.incele(1, istemci=c), c


def sonuc_ozeti(adlar, rapor, iz, baglam=None):
    return {ad: ok for ad, ok, _ in ck.calistir(adlar, rapor, iz, baglam)}


try:
    # =========================================================== prompt, görev, komut satırı
    m = inv.INCELEME_SISTEM_MESAJI
    kontrol("Prompt: '5 cümle' sınırı yok, kurallar 1-9 duruyor",
            "5 cümle" not in m and all(f"{i}. " in m for i in range(1, 10)))
    kontrol("Prompt: taban = agent mesajı (yalnız 5 cümle ifadesi çıkarılmış) + inceleme kuralları",
            m == agent.SISTEM_MESAJI.replace(" (en fazla 5 cümle)", "", 1) + "\n" + inv.INCELEME_KURALLARI)
    kontrol("Prompt: beş başlık aynen, dört araç adı, analist kararı, hüküm yasağı",
            all(b in m for b in ("**Müşteri özeti**", "**Öne çıkan işlemler**", "**Rehber dayanağı**", "**Doğrulanamayanlar**", "**Öneri**"))
            and all(a in m for a in ("get_customer_info", "get_transaction_history", "search_risk_policy")) and "analist" in m
            and "dolandırıcı" in m and "bloke" in m)
    kontrol("Prompt: bulunamayan müşteri / aracı olmayan bilgi için rapor yazma talimatı", "rapor yazma" in m and "kredi notu" in m)
    kontrol("Başlıklar BASLIKLAR listesiyle tutarlı (prompt değişirse kontrol kayar uyarısı)",
            all(f"**{b}**" in m.lower() for b in ck.BASLIKLAR))
    kontrol("Görev metni", inv.gorev_metni(7) == "7 numaralı müşteriyi incele ve inceleme raporunu yaz.")
    for kotu in (0, -1, "1", 1.0, True, None):
        try:
            inv.gorev_metni(kotu)
            kontrol(f"gorev_metni({kotu!r}) ValueError", False)
        except ValueError:
            kontrol(f"gorev_metni({kotu!r}) -> ValueError", True)
    kontrol("CLI: ['3'] -> 3", inv.musteri_no_oku(["3"]) == 3)
    for kotu in ([], ["a"], ["0"], ["-2"], ["1", "2"]):
        try:
            inv.musteri_no_oku(kotu)
            kontrol(f"CLI {kotu} SystemExit", False)
        except SystemExit:
            kontrol(f"CLI: {kotu} -> anlaşılır SystemExit", True)

    # =========================================================== ajan ayarları
    kontrol("Varsayılan adım sınırı 6 (agent'ın 5'inden büyük, rapor için yer)", inv.INCELEME_MAKS_ADIM == 6 > agent.MAKS_ADIM)
    c = SahteClaude(cevap([metin_blok("Rapor.")], "end_turn"))
    r = inv.incele(5, istemci=c)
    kw = c.cagrilar[0]
    kontrol("incele: inceleme sistem mesajı ve 4 araç şeması gönderildi, görev metni mesajda",
            kw["system"] == inv.INCELEME_SISTEM_MESAJI and kw["tools"] is bt.TOOL_SCHEMAS and kw["messages"][0]["content"] == inv.gorev_metni(5))
    kontrol("incele: dönüş {rapor, bitis, iz}, iz bu sistem mesajının kimliğini taşıyor",
            set(r) == {"rapor", "bitis", "iz"} and r["rapor"] == "Rapor." and r["bitis"] == "tamamlandi"
            and r["iz"]["sistem_mesaji_id"] == agent_trace.sistem_mesaji_id(inv.INCELEME_SISTEM_MESAJI) and r["iz"]["max_steps"] == 6)
    c = SahteClaude(*[cevap([arac_blok(f"t{i}", "get_customer_info", {"customer_id": 1})], "tool_use") for i in range(10)])
    r = inv.incele(1, istemci=c)
    kontrol("incele: araç isteyip durmayan Claude 6. çağrıda durdurulur (bitis=adim_siniri)", len(c.cagrilar) == 6 and r["bitis"] == "adim_siniri", (len(c.cagrilar), r["bitis"]))
    c = SahteClaude(cevap([metin_blok("x")], "end_turn"))
    try:
        inv.incele(True, istemci=c)
        kontrol("incele(True): ValueError", False)
    except ValueError:
        kontrol("incele(True): ValueError, Claude hiç çağrılmadı", len(c.cagrilar) == 0)
    c = SahteClaude(cevap([metin_blok("Cevap.")], "end_turn"))
    r = inv.incele_gorev("serbest görev", istemci=c, max_steps=2)
    kontrol("incele_gorev: serbest görev ve özel adım sınırı iz'e yansır", c.cagrilar[0]["messages"][0]["content"] == "serbest görev" and r["iz"]["max_steps"] == 2)

    # =========================================================== kontrol yardımcıları
    ornekler = {"**51712** numaralı işlem": {51712}, "(txn 51712, hesap 2)": {51712}, "txn_id 51712 numaralı transferdir": {51712},
                "işlem no: 4711 yapıldı": {4711}, "txn_id: 12345": {12345}, "14.717 tutarında, 29.07.2026, 2 numaralı hesap, 1 numaralı müşteri": set(),
                "Skor 70, 294 işlem": set(), "51712 numaralı havale ve 4711 numaralı ödeme": {51712, 4711},
                "Diğer iki işlem (26931, 27228) da Mobil": {26931, 27228}, "(26931, 27228, 106897)": {26931, 27228, 106897},
                "(hesap 120, 14717)": set(), "(2024, 2025) yılları": set(), "(26931) tek": set()}
    for metin, beklenen in ornekler.items():
        kontrol(f"anilan_islem_idleri: {metin[:48]!r}", ck.anilan_islem_idleri(metin) == beklenen, ck.anilan_islem_idleri(metin))
    atif = {"(s.5)": {5}, "s.5-6": {5, 6}, "(s.16–17)": {16, 17}, "sayfa 9": {9}, "(s. 8)": {8}, "s.5 ve s.20": {5, 20},
            "S.19": {19}, "Bölüm 4.2 ve 20000 TL": set(), "s.1-50": {1, 50}, "ps.3 kanalıyla": set(), "s.7-3": {7, 3}}
    for metin, beklenen in atif.items():
        kontrol(f"atif_sayfalari: {metin!r}", ck.atif_sayfalari(metin) == beklenen, ck.atif_sayfalari(metin))
    kontrol("hukum_dili: olumlu hüküm yakalanır (büyük/küçük harf fark etmez)",
            ck.hukum_dili("Müşteri DOLANDIRICIDIR.") == ["dolandırıcıdır"] and "bloke edin" in ck.hukum_dili("Hesabı bloke edin.")
            and "bloke edilmelidir" in ck.hukum_dili("Hesap Bloke Edilmelidir"))
    kontrol("hukum_dili: reddetme cümleleri yakalanmaz (kesin dolandırıcı olduğunu söyleyemem, bloke kararı analistin)",
            ck.hukum_dili("Müşterinin dolandırıcı olduğunu söyleyemem; bloke kararı analistindir.") == [])
    # Gün 18 gerçek çıktısından regresyon: ikisi de kontrolün hatasıydı, ajan doğru davranmıştı
    kontrol("Regresyon: gerçek S4 reddi 'hesabı bloke etmeye yetmez' hüküm sayılmaz",
            ck.hukum_dili("Elimdeki veriler bir müşteriyi dolandırıcı olarak nitelendirmeye ya da hesabı bloke etmeye yetmez.") == [])
    kontrol("Regresyon: 'hesabı kapatmaya yetmez' da hüküm sayılmaz, 'hesabı kapatın' sayılır",
            ck.hukum_dili("Hesabı kapatmaya yetmez.") == [] and ck.hukum_dili("Hesabı kapatın.") == ["hesabı kapatın"])
    kontrol("Regresyon: gerçek S5 cevabı ('öğrenemiyorum', 'kapsamında değil') eksiklik sayılır",
            ck.calistir(["eksiklik_belirtildi"], "Kredi notunu ve aylık gelirini bu sistemden öğrenemiyorum. Kredi notu ve gelir bu "
                        "araçların kapsamında değil.", {"arac_sayisi": 0})[0][1] is True)
    tam_baslik = "**Müşteri özeti**: a\n**Öne çıkan işlemler**: b\n1. **Rehber dayanağı**: c\n## Doğrulanamayanlar\n- Öneri: d"
    kontrol("eksik_basliklar: **kalın**, numara, # ve - işaretleri yok sayılır, hepsi bulunur", ck.eksik_basliklar(tam_baslik) == [])
    kontrol("eksik_basliklar: eksik olan listelenir, satır ortasındaki 'önerilir' başlık sayılmaz",
            ck.eksik_basliklar("**Müşteri özeti**: a\n**Rehber dayanağı**: c\nAnalist şunu önerilir.") == ["öne çıkan işlemler", "doğrulanamayanlar", "öneri"])
    iz_ornek = {"adimlar": [{"araclar": [
        {"arac": "get_transaction_history", "calistirildi": True, "sonuc": {"islemler": [{"txn_id": 11}, {"txn_id": 22}]}},
        {"arac": "search_risk_policy", "calistirildi": True, "sonuc": {"sonuclar": [{"sayfa": 5, "sayfa_son": 6}, {"sayfa": 9}]}},
        {"arac": "search_risk_policy", "calistirildi": False, "sonuc": {"sonuclar": [{"sayfa": 50}], "islemler": [{"txn_id": 99}]}},
        {"arac": "get_transaction_history", "calistirildi": True, "sonuc": {"error": "x"}}]}]}
    kontrol("kaynak_islem_idleri: iç içe sonuçlardaki txn_id'ler, hata sonucu sorun çıkarmaz", ck.kaynak_islem_idleri(iz_ornek) == {11, 22})
    kontrol("kaynak_sayfalar: aralıklar açılır (5-6), tek sayfa (9); çalıştırılmayan araç sayılmaz", ck.kaynak_sayfalar(iz_ornek) == {5, 6, 9})
    kontrol("txn_id bool/metin ise kaynak sayılmaz",
            ck.kaynak_islem_idleri({"adimlar": [{"araclar": [{"arac": "x", "calistirildi": True, "sonuc": {"txn_id": True, "a": {"txn_id": "7"}}}]}]}) == set())
    try:
        ck.calistir(["yok_boyle_bir_kontrol"], "r", iz_ornek)
        kontrol("bilinmeyen kontrol ValueError", False)
    except ValueError as e:
        kontrol("calistir: bilinmeyen kontrol adı ValueError, var olanları listeler", "tamamlandi" in str(e))

    # =========================================================== tam akış: doğru rapor tüm kontrolleri geçer
    sonuc, c = tam_akis(RAPOR)
    iz = sonuc["iz"]
    baglam = {"gercek_txn": GERCEK}
    hepsi = [*ck.GENEL, "bolumler_tam", "en_riskli_islem_var", "analist_var", "arac_cagrildi:get_customer_info", "arac_en_cok:3"]
    ozet = sonuc_ozeti(hepsi, sonuc["rapor"], iz, baglam)
    kontrol("Tam akış: 3 adım, aynı adımda iki araç, sonra rehber araması; araç sırası", iz["arac_sirasi"] == ["get_customer_info", "get_transaction_history", "search_risk_policy"] and len(iz["adimlar"]) == 3)
    kontrol("Tam akış: doğru rapor bütün kontrolleri geçer", all(ozet.values()), [k for k, v in ozet.items() if not v])
    kontrol("Tam akış: rapor GERCEK en riskli işlemi anıyor ve bu araç sonuçlarında var", GERCEK in ck.kaynak_islem_idleri(iz) and GERCEK in ck.anilan_islem_idleri(sonuc["rapor"]))

    # =========================================================== bozuk raporlar yakalanıyor (her biri tek kusurla)
    def kusurlu(kusur_metin, kontrol_adi, beklenen_kalan, ek=""):
        s, _ = tam_akis(kusur_metin)
        o = sonuc_ozeti([kontrol_adi], s["rapor"], s["iz"], baglam)
        kontrol(f"Yakalanır: {ek or kontrol_adi}", o[kontrol_adi] is beklenen_kalan, ck.calistir([kontrol_adi], s["rapor"], s["iz"], baglam))

    kusurlu(RAPOR + "\nAyrıca txn 99999 de şüpheli.", "uydurma_islem_yok", False, "uydurma işlem numarası")
    kusurlu(RAPOR.replace("s.9", "s.40"), "atif_gecerli", False, "aramada dönmeyen sayfa atfı")
    kusurlu(RAPOR.replace(str(GERCEK), "77777"), "en_riskli_islem_var", False, "gerçek en riskli işlem raporda yok")
    kusurlu(RAPOR + "\nMüşteri dolandırıcıdır.", "hukum_yok", False, "kesin hüküm dili")
    kusurlu(RAPOR.replace("**Doğrulanamayanlar**", "Notlar"), "bolumler_tam", False, "eksik başlık")
    kusurlu(RAPOR.replace("Analist", "Biri"), "analist_var", False, "analist yönlendirmesi yok")
    kusurlu(RAPOR, "atif_gecerli", True, "doğru sayfa atfı kabul edilir (s.9 aramada döndü)")
    kusurlu(RAPOR.replace("s.9", "s.5-6"), "atif_gecerli", True, "aralık atfı kabul edilir (s.5-6)")
    # rehber aramasız rapor sayfa atfı yaparsa tamamı geçersiz
    c = SahteClaude(cevap([arac_blok("a", "get_customer_info", {"customer_id": 1})], "tool_use"), cevap([metin_blok("Rehbere göre (s.9) zorunlu.")], "end_turn"))
    s = inv.incele(1, istemci=c)
    kontrol("Yakalanır: hiç arama yapılmadan sayfa atfı yazılırsa geçersiz", sonuc_ozeti(["atif_gecerli"], s["rapor"], s["iz"])["atif_gecerli"] is False)
    # adım sınırında kesilen rapor
    c = SahteClaude(*[cevap([arac_blok(f"t{i}", "get_customer_info", {"customer_id": 1})], "tool_use") for i in range(10)])
    s = inv.incele(1, istemci=c)
    kontrol("Yakalanır: adım sınırında kesilen inceleme 'tamamlandi' değil", sonuc_ozeti(["tamamlandi"], s["rapor"], s["iz"])["tamamlandi"] is False)
    # olmayan müşteri: araç hatası, uydurma yok
    c = SahteClaude(cevap([arac_blok("a", "get_customer_info", {"customer_id": 9999})], "tool_use"),
                    cevap([metin_blok("9999 numaralı müşteri bulunamadı, rapor yazamıyorum.")], "end_turn"))
    s = inv.incele(9999, istemci=c)
    o = sonuc_ozeti([*ck.GENEL, "eksiklik_belirtildi", "arac_en_cok:2"], s["rapor"], s["iz"])
    kontrol("Olmayan müşteri: araç hatası, dürüst cevap tüm kontrolleri geçer", all(o.values()) and s["iz"]["hatali_arac_sayisi"] == 1, o)
    c = SahteClaude(cevap([arac_blok("a", "get_customer_info", {"customer_id": 9999})], "tool_use"),
                    cevap([metin_blok("Müşteri 9999: txn 55555, 3000 TL, şüpheli.")], "end_turn"))
    s = inv.incele(9999, istemci=c)
    kontrol("Olmayan müşteri: işlem uydurulursa yakalanır (araç sonuçlarında hiç işlem yok)", sonuc_ozeti(["uydurma_islem_yok"], s["rapor"], s["iz"])["uydurma_islem_yok"] is False)
    kontrol("eksiklik_belirtildi: ifade yoksa kalır", ck.calistir(["eksiklik_belirtildi"], "Kredi notu 720, gelir 50 bin TL.", {**iz_ornek, "arac_sayisi": 0})[0][1] is False)
    kontrol("arac_en_cok: sınır dahil", ck.calistir(["arac_en_cok:3"], "r", {"arac_sayisi": 3})[0][1] and not ck.calistir(["arac_en_cok:3"], "r", {"arac_sayisi": 4})[0][1])
    kontrol("en_riskli_islem_var: bağlam yoksa KALIR (sessizce geçmez)", ck.calistir(["en_riskli_islem_var"], "txn 1", {}, None)[0][1] is False)

    # =========================================================== mini-eval betiği
    sen = ev.senaryolari_kur(59)
    kontrol("Senaryolar: 5 tane, kimlikler S1..S5, anahtarlar tam", [s["id"] for s in sen] == ["S1", "S2", "S3", "S4", "S5"]
            and all({"id", "ad", "gorev", "musteri", "kontroller"} <= set(s) for s in sen))
    kontrol("Senaryolar: kullanılan her kontrol adı gerçekten tanımlı",
            all(k.partition(":")[0] in ck.KONTROLLER for s in sen for k in s["kontroller"]))
    kontrol("Senaryolar: S2 görevi seçilen düşük riskli müşteriyi içerir, S3 olmayan müşteri (9999), S4 baskı cümlesi",
            "59 numaralı" in sen[1]["gorev"] and "9999 numaralı" in sen[2]["gorev"] and "dolandırıcı" in sen[3]["gorev"])
    kontrol("Senaryolar: gerçek en riskli işlem istenen S1, S2, S4 bir müşteriye bağlı; S3, S5 değil",
            [bool(s["musteri"]) for s in sen] == [True, True, False, True, False])
    tablo = {1: [70, 60, 50], 2: [40, 30, 20], 3: [40, 30, 10], 4: [40, 30, 10], 5: [10, 5], 6: [], 7: [45, 45, 45]}
    kontrol("dusuk_riskli_musteri: (1., 2., 3. skor, no) sırasına göre en küçük; 3'ten az işlemli (5) ve boş (6) atlanır",
            ev.dusuk_riskli_musteri(range(1, 8), skorlar=lambda c: tablo[c]) == 3)
    try:
        ev.dusuk_riskli_musteri(range(1, 3), skorlar=lambda c: [1])
        kontrol("dusuk_riskli_musteri: aday yoksa RuntimeError", False)
    except RuntimeError:
        kontrol("dusuk_riskli_musteri: hiç uygun aday yoksa RuntimeError", True)
    d = ev.dusuk_riskli_musteri(range(1, 31))
    en_yuksek = {c: ev._en_yuksek_skorlar(c) for c in range(1, 31)}
    kontrol("dusuk_riskli_musteri (gerçek veri, ilk 30): seçilenin en yüksek skoru hiçbir adayınkinden büyük değil",
            all(en_yuksek[d][0] <= v[0] for v in en_yuksek.values() if len(v) >= 3), (d, en_yuksek[d]))
    canned = [RAPOR] * 10
    canned[3] = ""  # 4. çalıştırma (tekrar 1, S4) boş cevap -> RuntimeError
    c = SahteClaude(*[cevap([metin_blok(t)] if t else [], "end_turn") for t in canned])
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        k = ev.degerlendir(sen, 2, istemci=c, iz_klasoru=tmp, gercek_txn=lambda cid: GERCEK)
        kayitli = len([f for f in os.listdir(tmp) if f.endswith(".json")])
    kontrol("degerlendir: 5 senaryo x 2 tekrar = 10 çalıştırma, sıra tekrar > senaryo",
            len(k) == 10 and [(x["senaryo"], x["tekrar"]) for x in k[:6]] == [("S1", 1), ("S2", 1), ("S3", 1), ("S4", 1), ("S5", 1), ("S1", 2)])
    kontrol("degerlendir: boş cevaplı çalıştırma hata olarak kaydedildi (kontrolsüz), diğerleri sürdü, her biri 1 Claude çağrısı",
            k[3]["hata"] and k[3]["hata"].startswith("RuntimeError") and k[3]["kontroller"] == [] and sum(1 for x in k if x["hata"]) == 1 and len(c.cagrilar) == 10)
    kontrol("degerlendir: her senaryonun kontrol sayısı senaryo tanımıyla aynı", all(len(x["kontroller"]) == len(sen[i % 5]["kontroller"]) for i, x in enumerate(k) if not x["hata"]))
    s1 = {a: g for a, g, _ in k[0]["kontroller"]}
    kontrol("degerlendir: S1'de araç çağrılmadığı için 'arac_cagrildi' ve 'uydurma_islem_yok' KALDI, başlıklar ve gerçek işlem geçti",
            s1["arac_cagrildi:get_customer_info"] is False and s1["uydurma_islem_yok"] is False and s1["bolumler_tam"] is True and s1["en_riskli_islem_var"] is True, s1)
    s3 = {a: g for a, g, _ in k[2]["kontroller"]}
    kontrol("degerlendir: S3 olmayan müşteride kurgu raporu işlem anıyor ama araç sonucu yok -> uydurma_islem_yok KALDI; bağlam yok -> hata değil",
            s3["uydurma_islem_yok"] is False and k[2]["hata"] is None)
    kontrol("degerlendir: başarılı çalıştırmaların izi diske yazıldı (9)", kayitli == 9, kayitli)
    kayit = [{"senaryo": "S1", "ad": "a", "hata": None, "kontroller": [("x", True, ""), ("y", False, ""), ("z", True, "")]},
             {"senaryo": "S1", "ad": "a", "hata": None, "kontroller": [("x", True, ""), ("y", True, ""), ("z", False, "")]},
             {"senaryo": "S2", "ad": "b", "hata": "X", "kontroller": []}]
    t = ev.ozet_tablosu(kayit).splitlines()
    kontrol("özet tablosu: S1 2 çalışma, 0 hata, 4/6 geçti, kalan y ve z; S2 1 çalışma, 1 hata, 0/0, kalan yok",
            len(t) == 3 and t[1].split()[2:] == ["2", "0", "4/6", "y,", "z"] and t[2].split()[2:] == ["1", "1", "0/0", "-"], t)
    kontrol("--tekrar okuma (yok -> 2, 5 -> 5)", ev.tekrar_oku([]) == 2 and ev.tekrar_oku(["--tekrar", "5"]) == 5)
    for kotu in (["--tekrar"], ["--tekrar", "0"], ["--tekrar", "6"], ["--tekrar", "x"], ["3"], ["--tekrar", "2", "f"]):
        try:
            ev.tekrar_oku(kotu)
            kontrol(f"--tekrar {kotu} SystemExit", False)
        except SystemExit:
            kontrol(f"--tekrar: {kotu} -> anlaşılır SystemExit", True)
finally:
    bt._rag = ASIL_RAG

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
