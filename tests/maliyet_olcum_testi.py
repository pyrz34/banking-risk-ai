"""Gün 20: maliyet ölçüm betiğinin testi. Çalıştır: python tests\\maliyet_olcum_testi.py
Ağ yok, gerçek Claude yok (sahte istemci). Ölçtüğü: betik doğru sayıları topluyor, özetliyor, tabloya koyuyor mu.
ÖLÇMEDİĞİ: gerçek token sayıları (onlar python tests\\maliyet_olcum.py ile gelir).
"""
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import maliyet_olcum as mo  # noqa: E402
import risk_rag  # noqa: E402

sonuclar = []


def kontrol(ad, ok, detay=""):
    sonuclar.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {ad}" + (f"  -> {detay}" if detay and not ok else ""))


class SahteClaude:
    def __init__(self, girdi=100, cikti=50, metin="Açıklama."):
        self.cagrilar = []
        self.girdi, self.cikti, self.metin = girdi, cikti, metin
        self.messages = SimpleNamespace(create=self._create)

    def _create(self, **kw):
        self.cagrilar.append(kw)
        blok = SimpleNamespace(type="text", text=self.metin)
        return SimpleNamespace(content=[blok] if self.metin is not None else [], stop_reason="end_turn",
                               usage=SimpleNamespace(input_tokens=self.girdi, output_tokens=self.cikti))


def saatli(adimlar):
    it = iter(adimlar)
    return lambda: next(it)


RISK = {"risk_score": 70, "risk_label": "suspicious", "rule_ids": ["RISKY_CHANNEL", "INTERNATIONAL"],
        "reasons": ["Riskli kanal: web (+15)", "Yurtdışı işlem (+25)"]}

# RAG'siz ölçüm
c = SahteClaude(120, 40)
o = mo.olc_ragsiz(RISK, c, saat=saatli([1.0, 1.25]))
kontrol("RAG'siz: token claude kullanımından, süre saatten (250 ms)", o == {"girdi": 120, "cikti": 40, "sure_ms": 250}, o)
m = c.cagrilar[0]["messages"][0]["content"]
kontrol("RAG'siz: istemde KAYNAKLAR yok, skor ve kurallar var, RAG'siz sistem istemi gidiyor",
        "KAYNAKLAR" not in m and "Skor: 70" in m and "RISKY_CHANNEL: Riskli kanal" in m
        and c.cagrilar[0]["system"] == mo.SISTEM_RAGSIZ and "KAYNAK" not in mo.SISTEM_RAGSIZ)
try:
    mo.olc_ragsiz(RISK, SahteClaude(metin=None))
    kontrol("RAG'siz: boş cevap RuntimeError", False)
except RuntimeError:
    kontrol("RAG'siz: boş cevap sessizce 0 token gibi sayılmaz, RuntimeError", True)

# RAG'li ölçüm: gerçek risk_rag.aciklama_uret_rag, sahte rehber
import numpy as np  # noqa: E402


class SahteModel:
    def sorgu_vektoru(self, soru):
        return [np.array([1.0, 0.0])]


CHUNKLAR = [{"id": 0, "text": "rehber metni 0", "page": 5, "page_end": 5, "codes": [], "section": "B"},
            {"id": 1, "text": "rehber metni 1", "page": 6, "page_end": 6, "codes": [], "section": "B"}]
VEKT = np.array([[1.0, 0.0], [0.9, 0.1]], dtype=np.float32)
RAG = lambda: (SahteModel(), CHUNKLAR, VEKT)  # noqa: E731
c = SahteClaude(900, 200)
o = mo.olc_ragli(RISK, RAG, c, saat=saatli([0.0, 2.0]))
kontrol("RAG'li: token ve süre doğru alınır (2000 ms)", o == {"girdi": 900, "cikti": 200, "sure_ms": 2000}, o)
kontrol("RAG'li: istemde KAYNAKLAR var (rehber gerçekten gitti)", "KAYNAKLAR" in c.cagrilar[0]["messages"][0]["content"]
        and "rehber metni" in c.cagrilar[0]["messages"][0]["content"] and c.cagrilar[0]["system"] == risk_rag.SISTEM_MESAJI)

# önbellek isabeti
sayac = []


def sahte_onbellekli_factory():
    durum = {"dolu": False}

    def f(risk, rag_getir, claude):
        sayac.append(1)
        if durum["dolu"]:
            return {"explanation": "x"}, True
        durum["dolu"] = True
        return {"explanation": "x"}, False
    return f


f = sahte_onbellekli_factory()
r = mo.olc_onbellek_isabet(RISK, RAG, object(), 3, f, saat=saatli([0, 0.001, 1, 1.002, 2, 2.0005]))
kontrol("Önbellek: 1 ıska çağrısı + 3 isabet ölçümü, hepsi 0 token", len(sayac) == 4 and len(r) == 3
        and all(x["girdi"] == 0 and x["cikti"] == 0 for x in r), (len(sayac), r))
kontrol("Önbellek: isabet süreleri ms olarak, yuvarlanmış (1, 2, 0.5)", [x["sure_ms"] for x in r] == [1.0, 2.0, 0.5], r)
try:
    mo.olc_onbellek_isabet(RISK, RAG, object(), 1, lambda *a: ({"explanation": "x"}, False))
    kontrol("Önbellek: isabet olmuyorsa RuntimeError", False)
except RuntimeError:
    kontrol("Önbellek: isabet olmuyorsa (anahtar tutarsız) RuntimeError, sessizce geçmez", True)

# özet
oz = mo.ozet([{"girdi": 100, "cikti": 10, "sure_ms": 1000}, {"girdi": 300, "cikti": 30, "sure_ms": 3000},
              {"girdi": 200, "cikti": 20, "sure_ms": 2000}])
kontrol("Özet: medyan ve aralıklar", oz == {"n": 3, "girdi_med": 200, "cikti_med": 20, "girdi_aralik": (100, 300),
                                            "cikti_aralik": (10, 30), "sure_med_ms": 2000}, oz)
try:
    mo.ozet([])
    kontrol("Özet: boş liste ValueError", False)
except ValueError:
    kontrol("Özet: boş liste ValueError", True)

# tablo / dolar
satir = [("A", oz)]
t = mo.tablo_md(satir)
kontrol("Tablo: fiyat yoksa dolar sütunu '-', uydurma sayı yok", t.rstrip().endswith("| - |") and "200 (100-300)" in t, t)
t = mo.tablo_md(satir, 0.10, 0.50)
beklenen = f"{(200 * 0.10 + 20 * 0.50) / 1e6:.6f}"
kontrol("Tablo: fiyatla dolar = (girdi*g + cikti*c)/1M, medyan üzerinden", beklenen in t, (beklenen, t))
kontrol("Süre metni: 1 sn altı ms, üstü sn", mo.sure_metni(128) == "128 ms" and mo.sure_metni(15946) == "15.9 sn")

# argüman okuma
kontrol("Argüman: varsayılan (3, ajan yok)", mo.tekrar_oku([]) == (3, False))
kontrol("Argüman: --tekrar 5 --ajan", mo.tekrar_oku(["--tekrar", "5", "--ajan"]) == (5, True))
for kotu in (["--tekrar"], ["--tekrar", "x"], ["--tekrar", "0"], ["--tekrar", "6"], ["--bilinmeyen"]):
    try:
        mo.tekrar_oku(kotu)
        kontrol(f"Argüman {kotu} SystemExit", False)
    except SystemExit:
        kontrol(f"Argüman {kotu} -> anlaşılır SystemExit", True)

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
