"""Gün 14: tool calling testleri. Çalıştır: python tests\\tool_calling_testi.py
Ağ yok, gerçek Claude çağrısı yok (sahte istemci). Hızlı ve ücretsiz.
Ölçtüğü: araçlar doğru çalışıyor mu, hatada düşmüyor mu, şema fonksiyonla uyumlu mu, tek tur akışı doğru mesajları kuruyor mu.
ÖLÇMEDİĞİ: gerçek Claude'un doğru aracı seçmesi (onu python src\\tool_calling.py ile gör).
"""
import inspect
import json
import logging
import os
import sys
from types import SimpleNamespace
from typing import get_args

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import api  # noqa: E402
import rag_cevap  # noqa: E402
import tool_calling  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tools import banking_tools as bt  # noqa: E402

sonuclar = []


def kontrol(ad, ok, detay=""):
    sonuclar.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {ad}" + (f"  -> {detay}" if detay and not ok else ""))


# ---------- sahte Claude ----------
def metin_blok(t):
    return SimpleNamespace(type="text", text=t)


def arac_blok(id_, ad, girdi):
    return SimpleNamespace(type="tool_use", id=id_, name=ad, input=girdi)


def cevap(bloklar, stop, girdi=10, cikti=5):
    return SimpleNamespace(content=bloklar, stop_reason=stop,
                           usage=SimpleNamespace(input_tokens=girdi, output_tokens=cikti))


class SahteClaude:
    """Sırayla hazır cevapları döner. Her çağrının argümanlarını kaydeder (mesaj listesinin O ANKİ kopyasıyla)."""

    def __init__(self, *cevaplar):
        self.cevaplar = list(cevaplar)
        self.cagrilar = []
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        kw = dict(kw)
        kw["messages"] = list(kw["messages"])  # sonradan eklenenler bu kaydı bozmasın
        self.cagrilar.append(kw)
        return self.cevaplar[len(self.cagrilar) - 1]


GECERLI = dict(account_id=226, amount=50000, status="FAILED", channel="Web", is_international=1)

# ---------- araçlar ----------
istemci_api = TestClient(api.app)
beklenen = istemci_api.post("/predict-risk", json=GECERLI).json()
kontrol("get_risk_score: /predict-risk ile birebir aynı sonuç", bt.get_risk_score(**GECERLI) == beklenen, bt.get_risk_score(**GECERLI))
kontrol("get_risk_score: sonuçta skor, etiket, nedenler, rule_ids var",
        set(beklenen) == {"risk_score", "risk_label", "reasons", "rule_ids"})

r = bt.get_risk_score(**{**GECERLI, "channel": "web"})
kontrol("get_risk_score: geçersiz kanal -> error (istisna yok), alan adı geçiyor", "error" in r and "channel" in r["error"], r)
r = bt.get_risk_score(**{**GECERLI, "is_international": 2})
kontrol("get_risk_score: is_international=2 -> error", "error" in r and "is_international" in r["error"], r)
r = bt.get_risk_score(**{**GECERLI, "account_id": 99999})
kontrol("get_risk_score: olmayan hesap -> error, hesap no geçiyor", "error" in r and "99999" in r["error"], r)
r = bt.get_risk_score(**{**GECERLI, "amount": "çok"})
kontrol("get_risk_score: amount sayı değil -> error", "error" in r and "amount" in r["error"], r)

m = bt.get_customer_info(1)
kontrol("get_customer_info(1): alanlar", set(m) == {"customer_id", "segment", "city", "risk_band", "onboard_date", "accounts"}, m)
kontrol("get_customer_info(1): hesaplar veri setiyle uyumlu (1,2,3)", [a["account_id"] for a in m["accounts"]] == [1, 2, 3], m.get("accounts"))
kontrol("get_customer_info: sonuç JSON'a çevrilebilir", bool(json.dumps(m, ensure_ascii=False)))
r = bt.get_customer_info(4521)
kontrol("get_customer_info(4521): veri setinde yok (600 müşteri) -> error", "error" in r and "4521" in r["error"], r)
for kotu in ("1", 1.0, True, None):
    r = bt.get_customer_info(kotu)
    kontrol(f"get_customer_info({kotu!r}): tam sayı değil -> 'tam sayı' hatası", "tam sayı" in r.get("error", ""), r)

# ---------- dağıtıcı ----------
kontrol("tool_calistir: bilinmeyen araç -> error, kullanılabilir araçları listeliyor",
        "error" in (r := bt.tool_calistir("yok", {})) and "get_risk_score" in r["error"], r)
kontrol("tool_calistir: fazla argüman adı -> error", "error" in bt.tool_calistir("get_customer_info", {"x": 1}))
kontrol("tool_calistir: eksik argüman -> error", "error" in bt.tool_calistir("get_customer_info", {}))
kontrol("tool_calistir: girdi dict değil -> error", "error" in bt.tool_calistir("get_customer_info", [1]))


def patla(**kw):
    raise KeyError("gizli-ayrinti")


bt.FONKSIYONLAR["get_customer_info"], eski = patla, bt.FONKSIYONLAR["get_customer_info"]
logging.disable(logging.CRITICAL)  # beklenen hatanın log çıktısı ekranı kirletmesin
r = bt.tool_calistir("get_customer_info", {"customer_id": 1})
logging.disable(logging.NOTSET)
bt.FONKSIYONLAR["get_customer_info"] = eski
kontrol("tool_calistir: beklenmeyen istisna yakalanır, istisna türü var, iç ayrıntı sızmaz",
        "error" in r and "KeyError" in r["error"] and "gizli-ayrinti" not in r["error"], r)

# ---------- şema fonksiyonla uyumlu mu ----------
sema = {s["name"]: s for s in bt.TOOL_SCHEMAS}
kontrol("Şema: araç adları FONKSIYONLAR ile aynı", set(sema) == set(bt.FONKSIYONLAR), (set(sema), set(bt.FONKSIYONLAR)))
uyum = True
for ad, s in sema.items():
    parametreler = list(inspect.signature(bt.FONKSIYONLAR[ad]).parameters)
    sch = s["input_schema"]
    uyum &= sch["type"] == "object" and list(sch["properties"]) == parametreler and sch["required"] == parametreler
    uyum &= bool(s["description"].strip()) and all(p.get("description") for p in sch["properties"].values())
kontrol("Şema: properties ve required fonksiyon parametreleriyle aynı (adlar, sıra), açıklamalar dolu", uyum)

alanlar = api.TransactionRequest.model_fields
props = sema["get_risk_score"]["input_schema"]["properties"]
kontrol("Şema: enum değerleri API modelindeki Literal'lerle aynı (kopya kaymasın)",
        all(props[a]["enum"] == list(get_args(alanlar[a].annotation)) for a in ("status", "channel", "is_international")),
        {a: (props[a]["enum"], get_args(alanlar[a].annotation)) for a in ("status", "channel", "is_international")})
kontrol("Şema: JSON'a çevrilebilir", bool(json.dumps(bt.TOOL_SCHEMAS)))

# ---------- tek tur akışı ----------
c = SahteClaude(cevap([metin_blok("Merhaba, size nasıl yardımcı olabilirim?")], "end_turn"))
s = tool_calling.soru_sor("Merhaba", istemci=c)
kontrol("Araçsız: 1 çağrı, iz boş, cevap metni döner, tur_siniri False",
        len(c.cagrilar) == 1 and s["iz"] == [] and s["cevap"].startswith("Merhaba") and s["tur_siniri"] is False, s)
kw = c.cagrilar[0]
kontrol("İstek: model, araç şemaları, sistem mesajı ve max_tokens gönderildi",
        kw["model"] == tool_calling.MODEL and kw["tools"] is bt.TOOL_SCHEMAS and kw["system"] == tool_calling.SISTEM_MESAJI
        and kw["max_tokens"] == tool_calling.MAKS_TOKEN)
kontrol("MODEL rag_cevap.MODEL ile aynı", tool_calling.MODEL == rag_cevap.MODEL)
kontrol("MAKS_TOKEN düşünme payı bırakacak kadar büyük (>= 2000)", tool_calling.MAKS_TOKEN >= 2000)
kontrol("Sistem mesajı araç kullanımı, hata ve veri/talimat kurallarını içeriyor",
        all(x in tool_calling.SISTEM_MESAJI for x in ("get_risk_score", "get_customer_info", "error", "talimat")))

ilk = cevap([metin_blok("Aracı çağırıyorum."), arac_blok("toolu_1", "get_risk_score", GECERLI)], "tool_use", girdi=100, cikti=20)
c = SahteClaude(ilk, cevap([metin_blok("Skor 100, şüpheli.")], "end_turn", girdi=150, cikti=30))
s = tool_calling.soru_sor("riski nedir", istemci=c)
kontrol("Araçlı: 2 Claude çağrısı, cevap ikincisinden", len(c.cagrilar) == 2 and s["cevap"] == "Skor 100, şüpheli.", s)
m2 = c.cagrilar[1]["messages"]
kontrol("2. çağrı mesajları: user, assistant (1. cevabın bloklarının AYNISI, metin dahil), user(tool_result)",
        [x["role"] for x in m2] == ["user", "assistant", "user"] and m2[1]["content"] is ilk.content, [x["role"] for x in m2])
tr = m2[2]["content"]
kontrol("tool_result: tool_use_id eşleşiyor, içerik aracın gerçek sonucunun JSON'u, is_error yok",
        len(tr) == 1 and tr[0]["type"] == "tool_result" and tr[0]["tool_use_id"] == "toolu_1"
        and json.loads(tr[0]["content"]) == beklenen and "is_error" not in tr[0], tr)
kontrol("İz: araç adı, Claude'un verdiği argümanlar, sonuç", s["iz"] == [{"arac": "get_risk_score", "girdi": GECERLI, "sonuc": beklenen}], s["iz"])
kontrol("Token toplamı iki çağrıyı topluyor", s["kullanim"] == {"girdi": 250, "cikti": 50, "cagri": 2}, s["kullanim"])
kontrol("2. çağrıda da araçlar gönderiliyor", c.cagrilar[1]["tools"] is bt.TOOL_SCHEMAS)

# hata sonucu
c = SahteClaude(cevap([arac_blok("t1", "get_customer_info", {"customer_id": 4521})], "tool_use"),
                cevap([metin_blok("Müşteri bulunamadı.")], "end_turn"))
s = tool_calling.soru_sor("4521 kimdir", istemci=c)
tr = c.cagrilar[1]["messages"][2]["content"][0]
kontrol("Araç hatası: tool_result is_error=True, hata metni içerikte, çökme yok, Claude son cevabı yazıyor",
        tr.get("is_error") is True and "4521" in json.loads(tr["content"])["error"] and s["cevap"] == "Müşteri bulunamadı.", tr)

# Claude olmayan araç uydurursa
c = SahteClaude(cevap([arac_blok("t1", "delete_everything", {})], "tool_use"), cevap([metin_blok("Yapamam.")], "end_turn"))
s = tool_calling.soru_sor("x", istemci=c)
tr = c.cagrilar[1]["messages"][2]["content"][0]
kontrol("Uydurma araç adı: is_error sonucu, çökme yok", tr.get("is_error") is True and "araç yok" in json.loads(tr["content"])["error"], tr)

# aynı cevapta iki araç
c = SahteClaude(cevap([arac_blok("a", "get_customer_info", {"customer_id": 1}),
                       arac_blok("b", "get_risk_score", GECERLI)], "tool_use"),
                cevap([metin_blok("Tamam.")], "end_turn"))
s = tool_calling.soru_sor("ikisi", istemci=c)
tr = c.cagrilar[1]["messages"][2]["content"]
kontrol("Aynı cevapta iki araç: iki tool_result, aynı sırada, doğru id'lerle",
        [t["tool_use_id"] for t in tr] == ["a", "b"] and [i["arac"] for i in s["iz"]] == ["get_customer_info", "get_risk_score"], tr)

# tur sınırı
c = SahteClaude(cevap([arac_blok("t1", "get_customer_info", {"customer_id": 1})], "tool_use"),
                cevap([metin_blok("Bir de riske bakayım."), arac_blok("t2", "get_risk_score", GECERLI)], "tool_use"))
s = tool_calling.soru_sor("x", istemci=c)
kontrol("Tur sınırı: Claude 2. kez araç isterse 3. çağrı YOK, tur_siniri True, cevapta not var",
        len(c.cagrilar) == 2 and s["tur_siniri"] is True and "Gün 14" in s["cevap"] and s["cevap"].startswith("Bir de riske"), s)

# boş cevap
c = SahteClaude(cevap([], "max_tokens"))
try:
    tool_calling.soru_sor("x", istemci=c)
    kontrol("Boş cevap RuntimeError fırlatır", False)
except RuntimeError as e:
    kontrol("Boş cevap: RuntimeError, stop_reason bilgisi içinde", "max_tokens" in str(e))

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
