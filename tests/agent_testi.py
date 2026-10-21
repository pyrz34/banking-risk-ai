"""Gün 15-17: agent döngüsü testleri. Çalıştır: python tests\\agent_testi.py
Ağ yok, gerçek Claude çağrısı yok (sahte istemci). Hızlı ve ücretsiz.
Ölçtüğü: döngü doğru kuruluyor mu, frenler (adım, token) çalışıyor mu, bitiş nedeni doğru mu, hata sonrası devam ediyor mu.
ÖLÇMEDİĞİ: gerçek Claude'un doğru karar verip vermediği (onu python src\\agent.py ile gör).
"""
import os
import sys
from types import SimpleNamespace

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import agent  # noqa: E402
import tool_calling  # noqa: E402
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
    return SimpleNamespace(content=bloklar, stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=girdi, output_tokens=cikti))


class SahteClaude:
    def __init__(self, *cevaplar):
        self.cevaplar = list(cevaplar)
        self.cagrilar = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        kw = dict(kw)
        kw["messages"] = list(kw["messages"])
        self.cagrilar.append(kw)
        return self.cevaplar[len(self.cagrilar) - 1]


def mesajlar_gecerli(mesajlar):
    """API kuralı: roller sırayla user/assistant/user..., her tool_use'a hemen sonraki user mesajında tool_result var."""
    for i, m in enumerate(mesajlar):
        if m["role"] != ("user" if i % 2 == 0 else "assistant"):
            return False, f"rol sırası bozuk (mesaj {i})"
        if m["role"] == "assistant" and isinstance(m["content"], list):
            idler = [b.id for b in m["content"] if getattr(b, "type", "") == "tool_use"]
            if idler:
                if i + 1 >= len(mesajlar):
                    return False, "tool_use cevapsız bitti"
                donen = [b["tool_use_id"] for b in mesajlar[i + 1]["content"] if b["type"] == "tool_result"]
                if donen != idler:
                    return False, f"id'ler uyuşmuyor {idler} != {donen}"
    return True, ""


GECERLI = dict(account_id=226, amount=50000, status="FAILED", channel="Web", is_international=1)
M1 = {"customer_id": 1}

# ---------- araçsız ----------
c = SahteClaude(cevap([metin_blok("Merhaba!")], "end_turn"))
s = agent.calistir("Merhaba", istemci=c)
kontrol("Araçsız: 1 çağrı, bitis=tamamlandi, cevap metni", len(c.cagrilar) == 1 and s["bitis"] == "tamamlandi" and s["cevap"] == "Merhaba!", s)
kw = c.cagrilar[0]
kontrol("İstek: model, araç şemaları, sistem mesajı, max_tokens",
        kw["model"] == tool_calling.MODEL and kw["tools"] is bt.TOOL_SCHEMAS and kw["system"] == agent.SISTEM_MESAJI
        and kw["max_tokens"] == tool_calling.MAKS_TOKEN)
kontrol("Varsayılanlar: max_steps 5, token bütçesi, düşünme payı", agent.MAKS_ADIM == 5 and agent.TOKEN_BUTCESI >= 10000 and agent.MAKS_TOKEN >= 2000)
kontrol("Sistem mesajı: sıralı araç kullanımı, hata sonrası düzeltme, veri/talimat kuralı",
        all(x in agent.SISTEM_MESAJI for x in ("önce o aracı", "error", "bir kez daha", "talimat")))

# ---------- Gün 17: sistem mesajı kural 9 ve sistem_mesaji parametresi ----------
kontrol("Kural 9 yeni sistem mesajında var, eskisinde yok",
        "9. " in agent.SISTEM_MESAJI and "9. " not in agent.SISTEM_MESAJI_ESKI and agent.KURAL_9 in agent.SISTEM_MESAJI)
kontrol("Eski sistem mesajı 1-8'i aynen taşıyor, yeni olan onun üstüne yalnız kural 9 ekliyor (karşılaştırma tek farkı ölçer)",
        agent.SISTEM_MESAJI.startswith(agent.SISTEM_MESAJI_ESKI) and agent.SISTEM_MESAJI == agent.SISTEM_MESAJI_ESKI + "\n" + agent.KURAL_9
        and all(f"{i}. " in agent.SISTEM_MESAJI_ESKI for i in range(1, 9)))
kontrol("Kural 9: doğrulanamayan bağlantıyı söyle, ilgisiz atıf yok, rehberde olmayanı rehber gibi sunma",
        all(x in agent.KURAL_9 for x in ("doğrulayamadığını", "atıf", "rehber bilgisi gibi")))
c = SahteClaude(cevap([metin_blok("a")], "end_turn"), cevap([metin_blok("b")], "end_turn"))
agent.calistir("g", istemci=c, sistem_mesaji=agent.SISTEM_MESAJI_ESKI)
agent.calistir("g", istemci=c)
kontrol("sistem_mesaji parametresi isteğe gider; verilmezse varsayılan SISTEM_MESAJI",
        c.cagrilar[0]["system"] == agent.SISTEM_MESAJI_ESKI and c.cagrilar[1]["system"] == agent.SISTEM_MESAJI)

# ---------- Gün 17: süre ölçümü (sahte saat: her okuma 0.5 sn ilerler) ----------
class SahteSaat:
    def __init__(self):
        self.t = -0.5

    def __call__(self):
        self.t += 0.5
        return self.t


gercek_saat = agent._saat
agent._saat = SahteSaat()
try:
    c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use"), cevap([metin_blok("Tamam.")], "end_turn"))
    s = agent.calistir("g", istemci=c)
finally:
    agent._saat = gercek_saat
kontrol("Süre: Claude adımları 500 ms, araç 500 ms, toplam 3500 ms (sahte saatle tam değer)",
        [a["sure_ms"] for a in s["adimlar"]] == [500, 500] and s["adimlar"][0]["araclar"][0]["sure_ms"] == 500 and s["sure_ms"] == 3500,
        (s["adimlar"], s["sure_ms"]))
agent._saat = SahteSaat()
try:
    s = agent.calistir("g", istemci=SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use")), max_steps=1)
finally:
    agent._saat = gercek_saat
kontrol("Süre: sınırda çalıştırılmayan araçta sure_ms None, adımda ve toplamda var",
        s["adimlar"][0]["araclar"][0]["sure_ms"] is None and s["adimlar"][0]["sure_ms"] == 500 and s["sure_ms"] == 1500, s)
s = agent.calistir("g", istemci=SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use"), cevap([metin_blok("T")], "end_turn")))
kontrol("Süre: gerçek saatle de tam sayı ve sıfırdan büyük değil eşit/büyük (negatif olamaz)",
        isinstance(s["sure_ms"], int) and s["sure_ms"] >= 0 and all(isinstance(a["sure_ms"], int) and a["sure_ms"] >= 0 for a in s["adimlar"])
        and s["adimlar"][0]["araclar"][0]["sure_ms"] >= 0)

# ---------- Gün 19: zaman aşımı ve toplam süre sınırı ----------
import anthropic  # noqa: E402

yakalanan = {}


class SahteAnthropic:
    def __init__(self, **kw):
        yakalanan.update(kw)


asil_anthropic, asil_istemci = anthropic.Anthropic, agent._istemci
anthropic.Anthropic, agent._istemci = SahteAnthropic, None
try:
    ilk = agent._claude()
    ikinci = agent._claude()
finally:
    anthropic.Anthropic, agent._istemci = asil_anthropic, asil_istemci
kontrol("Claude istemcisi zaman aşımı ve yeniden deneme ayarıyla kurulur, tek kez (aynı nesne)",
        yakalanan == {"timeout": agent.CLAUDE_ZAMAN_ASIMI, "max_retries": agent.CLAUDE_YENIDEN_DENEME} and ilk is ikinci
        and 0 < agent.CLAUDE_ZAMAN_ASIMI <= 120 and 0 <= agent.CLAUDE_YENIDEN_DENEME <= 5, yakalanan)


def saatli(c, **kw):
    agent._saat = SahteSaat()
    try:
        return agent.calistir("g", istemci=c, **kw)
    finally:
        agent._saat = gercek_saat


c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use"), cevap([metin_blok("T")], "end_turn"))
s = saatli(c, sure_siniri_sn=1.0)
kontrol("Süre sınırı: araç isteği geldiğinde süre aşılmışsa yeni çağrı yok, bitis=sure_siniri, araç çalıştırılmadı, notta süre var",
        len(c.cagrilar) == 1 and s["bitis"] == "sure_siniri" and s["adimlar"][0]["araclar"][0]["calistirildi"] is False
        and "süre sınırı (1 sn)" in s["cevap"], s)
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use"), cevap([metin_blok("T")], "end_turn"))
s = saatli(c, sure_siniri_sn=60)
kontrol("Süre sınırı: süre dolmadıysa döngü sürer", len(c.cagrilar) == 2 and s["bitis"] == "tamamlandi")
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use"), cevap([metin_blok("T")], "end_turn"))
s = saatli(c, sure_siniri_sn=None)
kontrol("Süre sınırı verilmezse (None) hiç devreye girmez", s["bitis"] == "tamamlandi")
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use"))
s = saatli(c, max_steps=1, sure_siniri_sn=0.001)
kontrol("Süre sınırı ve adım sınırı birlikte: adım sınırı önce kontrol edilir", s["bitis"] == "adim_siniri")
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use", 600, 600))
s = saatli(c, sure_siniri_sn=0.001, token_butcesi=1000)
kontrol("Süre sınırı ve token sınırı birlikte: süre önce kontrol edilir", s["bitis"] == "sure_siniri")
for kotu in (0, -1, float("nan")):
    try:
        agent.calistir("g", istemci=SahteClaude(), sure_siniri_sn=kotu)
        kontrol(f"sure_siniri_sn={kotu} ValueError", False)
    except ValueError:
        kontrol(f"sure_siniri_sn={kotu} -> ValueError", True)

# ---------- sıralı iki araç (bağımlı) ----------
c = SahteClaude(
    cevap([arac_blok("a", "get_customer_info", M1)], "tool_use", 100, 10),
    cevap([metin_blok("Hesap 1'i kullanıyorum."), arac_blok("b", "get_risk_score", {**GECERLI, "account_id": 1})], "tool_use", 200, 20),
    cevap([metin_blok("Risk düşük.")], "end_turn", 300, 30),
)
s = agent.calistir("görev", istemci=c)
kontrol("Sıralı: 3 çağrı, 3 adım, bitis=tamamlandi, cevap sonuncudan", len(c.cagrilar) == 3 and len(s["adimlar"]) == 3 and s["bitis"] == "tamamlandi" and s["cevap"] == "Risk düşük.", s["bitis"])
kontrol("Mesaj yapısı her çağrıda geçerli (rol sırası, tool_use/tool_result id eşleşmesi)",
        all(mesajlar_gecerli(k["messages"])[0] for k in c.cagrilar), [mesajlar_gecerli(k["messages"]) for k in c.cagrilar])
m3 = c.cagrilar[2]["messages"]
kontrol("3. çağrı geçmişi: 1. aracın sonucu da, 2. aracın sonucu da orada (Claude önceki sonuçları görüyor)",
        len(m3) == 5 and '"segment"' in m3[2]["content"][0]["content"] and '"risk_score"' in m3[4]["content"][0]["content"])
kontrol("2. adım gerçekten 1. adımın sonucuna bağlı çağrı yaptı (account_id=1) ve araç çalıştı",
        s["adimlar"][1]["araclar"][0]["girdi"]["account_id"] == 1 and "risk_score" in s["adimlar"][1]["araclar"][0]["sonuc"])
kontrol("Adım kaydı: adim, durum, araclar, token alanları",
        all(set(a) == {"adim", "durum", "araclar", "girdi_token", "cikti_token", "sure_ms"} for a in s["adimlar"])
        and [a["adim"] for a in s["adimlar"]] == [1, 2, 3] and [a["durum"] for a in s["adimlar"]] == ["tool_use", "tool_use", "end_turn"])
kontrol("Token toplamı üç çağrıyı topluyor", s["kullanim"] == {"girdi": 600, "cikti": 60, "cagri": 3}, s["kullanim"])

# ---------- adım freni ----------
def hep_arac(n):
    return [cevap([arac_blok(f"t{i}", "get_customer_info", M1)], "tool_use") for i in range(n)]


c = SahteClaude(*hep_arac(10))
s = agent.calistir("görev", istemci=c, max_steps=3)
kontrol("Adım freni: tam 3 çağrı yapılır, 4. yok, bitis=adim_siniri", len(c.cagrilar) == 3 and s["bitis"] == "adim_siniri", (len(c.cagrilar), s["bitis"]))
son = s["adimlar"][-1]["araclar"]
kontrol("Sınırdaki araç isteği çalıştırılmadı, sadece kaydedildi", len(son) == 1 and son[0]["calistirildi"] is False and son[0]["sonuc"] is None, son)
kontrol("Önceki adımların araçları çalıştırıldı", all(r["calistirildi"] for a in s["adimlar"][:-1] for r in a["araclar"]))
kontrol("Sınırda cevapta durdurma notu var (boş cevap yok)", "Durduruldu" in s["cevap"] and "max_steps=3" in s["cevap"], s["cevap"])
kontrol("max_steps=1: tek çağrı, araç çalıştırılmaz", (lambda cc: (agent.calistir("g", istemci=cc, max_steps=1)["bitis"] == "adim_siniri", len(cc.cagrilar)))(SahteClaude(*hep_arac(3))) == (True, 1))
c = SahteClaude(cevap([metin_blok("Bakıyorum."), arac_blok("x", "get_customer_info", M1)], "tool_use"))
s = agent.calistir("g", istemci=c, max_steps=1)
kontrol("Sınırda Claude'un yazdığı metin korunur", s["cevap"].startswith("Bakıyorum.") and "Durduruldu" in s["cevap"], s["cevap"])
for kotu in (0, -1):
    try:
        agent.calistir("g", istemci=SahteClaude(), max_steps=kotu)
        kontrol(f"max_steps={kotu} ValueError", False)
    except ValueError:
        kontrol(f"max_steps={kotu} ValueError fırlatır", True)

# ---------- token freni ----------
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use", 900, 200), cevap([metin_blok("x")], "end_turn"))
s = agent.calistir("g", istemci=c, token_butcesi=1000)
kontrol("Token freni: bütçe aşılınca yeni çağrı yok, bitis=token_siniri, araç çalıştırılmadı",
        len(c.cagrilar) == 1 and s["bitis"] == "token_siniri" and s["adimlar"][0]["araclar"][0]["calistirildi"] is False and "token bütçesi" in s["cevap"], s)
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use", 400, 100), cevap([metin_blok("Tamam.")], "end_turn"))
s = agent.calistir("g", istemci=c, token_butcesi=1000)
kontrol("Bütçe altındaysa döngü devam eder", len(c.cagrilar) == 2 and s["bitis"] == "tamamlandi")
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use", 500, 500), cevap([metin_blok("x")], "end_turn"))
kontrol("Bütçeye tam eşitlik de durdurur (>=)", agent.calistir("g", istemci=c, token_butcesi=1000)["bitis"] == "token_siniri")
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1)], "tool_use", 600, 600))
kontrol("Adım sınırı ve token sınırı birlikte: son adımda 'adim_siniri' (önce o kontrol edilir)", agent.calistir("g", istemci=c, max_steps=1, token_butcesi=1000)["bitis"] == "adim_siniri")

# ---------- hata sonrası devam (Gün 14'te yapılamazdı) ----------
c = SahteClaude(
    cevap([arac_blok("a", "get_risk_score", {**GECERLI, "channel": "web"})], "tool_use"),
    cevap([arac_blok("b", "get_risk_score", GECERLI)], "tool_use"),
    cevap([metin_blok("Skor 100.")], "end_turn"),
)
s = agent.calistir("g", istemci=c)
tr1 = c.cagrilar[1]["messages"][2]["content"][0]
tr2 = c.cagrilar[2]["messages"][4]["content"][0]
kontrol("Hata sonrası: 1. sonuç is_error, Claude argümanı düzeltip tekrar çağırdı, 2. sonuç başarılı, döngü tamamlandı",
        tr1.get("is_error") is True and "is_error" not in tr2 and s["bitis"] == "tamamlandi" and s["cevap"] == "Skor 100.", (tr1, tr2))
c = SahteClaude(cevap([arac_blok("a", "uydur", {})], "tool_use"), cevap([metin_blok("Yapamam.")], "end_turn"))
s = agent.calistir("g", istemci=c)
kontrol("Uydurma araç adı: is_error, döngü çökmeden devam eder", c.cagrilar[1]["messages"][2]["content"][0].get("is_error") is True and s["bitis"] == "tamamlandi")

# ---------- aynı cevapta iki araç ----------
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", M1), arac_blok("b", "get_risk_score", GECERLI)], "tool_use"),
                cevap([metin_blok("Tamam.")], "end_turn"))
s = agent.calistir("g", istemci=c)
kontrol("Aynı cevapta iki araç: tek adım, iki sonuç, geçerli mesaj yapısı",
        len(s["adimlar"][0]["araclar"]) == 2 and mesajlar_gecerli(c.cagrilar[1]["messages"])[0])

# ---------- diğer bitişler ----------
c = SahteClaude(cevap([metin_blok("Yarım kal")], "max_tokens"))
s = agent.calistir("g", istemci=c)
kontrol("stop_reason=max_tokens: 'tamamlandi' DEĞİL, bitis=durdu:max_tokens", s["bitis"] == "durdu:max_tokens" and s["cevap"] == "Yarım kal", s["bitis"])
c = SahteClaude(cevap([], "tool_use"))
try:
    agent.calistir("g", istemci=c)
    kontrol("tool_use ama araç bloğu yok + metin yok: RuntimeError", False)
except RuntimeError:
    kontrol("tool_use ama araç bloğu yok + metin yok: RuntimeError (boş user mesajı gönderilmez)", True)
c = SahteClaude(cevap([metin_blok("Bir şey")], "tool_use"))
kontrol("tool_use ama araç bloğu yok, metin var: bitis=durdu:tool_use_bos", agent.calistir("g", istemci=c)["bitis"] == "durdu:tool_use_bos")
try:
    agent.calistir("g", istemci=SahteClaude(cevap([], "end_turn")))
    kontrol("Boş cevap RuntimeError", False)
except RuntimeError as e:
    kontrol("Boş cevap: RuntimeError, stop_reason bilgisi içinde", "end_turn" in str(e))

# ---------- komut satırı ----------
kontrol("CLI: bayrak yok -> varsayılan adım, soru birleşir", agent.argumanlari_ayir(["a", "b"]) == (agent.MAKS_ADIM, "a b"))
kontrol("CLI: --max-steps 3 soru", agent.argumanlari_ayir(["--max-steps", "3", "soru", "metni"]) == (3, "soru metni"))
for kotu in (["--max-steps"], ["--max-steps", "x", "s"], ["--max-steps", "0", "s"]):
    try:
        agent.argumanlari_ayir(kotu)
        kontrol(f"CLI: {kotu} -> SystemExit", False)
    except SystemExit:
        kontrol(f"CLI: {kotu} -> anlaşılır SystemExit", True)

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
