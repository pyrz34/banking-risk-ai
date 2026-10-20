"""Gün 16: banka araçları testleri. Çalıştır: python tests\\banking_tools_testi.py
Ağ yok, gerçek Claude yok, e5 modeli yok (arama sahte vektörlerle). İlk çalıştırmada Excel okunur (~10 sn), sonra önbellekten (~1 sn).
Ölçtüğü: her araç doğru girdi alıp doğru çıktı veriyor mu, hatada düşmüyor mu, veri önbelleği güvenli mi, şema fonksiyonla uyumlu mu.
ÖLÇMEDİĞİ: gerçek e5 aramasının kalitesi ve Claude'un doğru aracı seçmesi (onları python src\\agent.py ile gör).
"""
import inspect
import json
import os
import shutil
import sys
import tempfile
import time
from types import SimpleNamespace

import numpy as np
import pandas as pd

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import agent  # noqa: E402
import api  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from tools import banking_tools as bt  # noqa: E402
from tools import veri  # noqa: E402

sonuclar = []


def kontrol(ad, ok, detay=""):
    sonuclar.append(bool(ok))
    print(f"{'PASS' if ok else 'FAIL'}  {ad}" + (f"  -> {detay}" if detay and not ok else ""))


def hata_var(r, parca=""):
    return isinstance(r, dict) and "error" in r and parca in r["error"]


istemci_api = TestClient(api.app)

# =============================================================== veri önbelleği
gecici = tempfile.mkdtemp()
try:
    xlsx = os.path.join(gecici, "mini.xlsx")
    pkl = os.path.join(gecici, "onbellek.pkl")

    def mini_excel(n_islem):
        with pd.ExcelWriter(xlsx) as w:
            pd.DataFrame({"customer_id": [1], "segment": ["retail"], "city": ["Ankara"], "risk_band": ["low"],
                          "onboard_date": [pd.Timestamp("2024-01-01")]}).to_excel(w, sheet_name="customers", index=False)
            pd.DataFrame({"account_id": [1], "customer_id": [1], "currency": ["TRY"],
                          "open_date": [pd.Timestamp("2024-01-01")], "account_type": ["vadesiz"]}).to_excel(w, sheet_name="accounts", index=False)
            pd.DataFrame({"txn_id": range(n_islem), "account_id": [1] * n_islem}).to_excel(w, sheet_name="transactions", index=False)

    mini_excel(3)
    t1 = veri.tablolar(xlsx, pkl)
    kontrol("veri: üç tablo döner, customers customer_id ile indeksli", set(t1) >= {"customers", "accounts", "transactions"} and t1["customers"].index.name == "customer_id")
    kontrol("veri: önbellek dosyası yazıldı, geçici (.tmp) dosya kalmadı", os.path.exists(pkl) and not os.path.exists(pkl + ".tmp"))

    orijinal = pd.read_excel
    pd.read_excel = lambda *a, **k: (_ for _ in ()).throw(AssertionError("Excel yeniden okundu"))
    try:
        kontrol("veri: ikinci çağrı bellekten, Excel'e dokunmaz", veri.tablolar(xlsx, pkl) is t1)
        veri._bellek.clear()
        t2 = veri.tablolar(xlsx, pkl)
        kontrol("veri: bellek boşken diskteki önbellekten okur, Excel'e dokunmaz", len(t2["transactions"]) == 3)
    finally:
        pd.read_excel = orijinal

    veri._bellek.clear()
    time.sleep(0.01)
    mini_excel(5)
    os.utime(xlsx, (time.time() + 5, time.time() + 5))  # değişme zamanı kesin farklı olsun
    t3 = veri.tablolar(xlsx, pkl)
    kontrol("veri: Excel değişince (imza farklı) eski önbellek yok sayılır, yeni veri okunur", len(t3["transactions"]) == 5, len(t3["transactions"]))

    veri._bellek.clear()
    with open(pkl, "wb") as f:
        f.write(b"bozuk")
    t4 = veri.tablolar(xlsx, pkl)
    kontrol("veri: bozuk önbellek dosyası çökertmez, yeniden üretilir", len(t4["transactions"]) == 5)
    veri._bellek.clear()
finally:
    shutil.rmtree(gecici, ignore_errors=True)

# =============================================================== get_transaction_history
t = veri.tablolar()
hesaplar1 = set(t["accounts"].loc[t["accounts"]["customer_id"] == 1, "account_id"])
tum1 = t["transactions"][t["transactions"]["account_id"].isin(hesaplar1)]

h = bt.get_transaction_history(1)
kontrol("history: varsayılan 5 işlem, en yeni önce, alanlar tam",
        h["donen"] == 5 and len(h["islemler"]) == 5 and h["siralama"] == "recent"
        and [x["txn_time"] for x in h["islemler"]] == sorted([x["txn_time"] for x in h["islemler"]], reverse=True)
        and set(h["islemler"][0]) == {"txn_id", "account_id", "txn_time", "channel", "txn_type", "amount", "merchant_category",
                                      "is_international", "counterparty_country", "status", "risk_score", "risk_label", "rule_ids"}, h)
kontrol("history: toplam_islem müşterinin hesaplarındaki gerçek sayı, işlemler sadece onun hesaplarından",
        h["toplam_islem"] == len(tum1) and all(x["account_id"] in hesaplar1 for x in h["islemler"]), (h["toplam_islem"], len(tum1)))
en_yeni = tum1.sort_values(["txn_time", "txn_id"], ascending=False).head(5)
kontrol("history: en yeni 5, veri setindeki en yeni 5 ile aynı", [x["txn_id"] for x in h["islemler"]] == list(en_yeni["txn_id"]))
kontrol("history: sonuç JSON'a çevrilebilir (numpy türü sızmamış)", bool(json.dumps(h, ensure_ascii=False)))

hr = bt.get_transaction_history(1, limit=20, sort_by="risk")
riskler = [x["risk_score"] for x in hr["islemler"]]
kontrol("history sort_by=risk: 20 işlem, risk skoru azalan sırada", len(riskler) == 20 and riskler == sorted(riskler, reverse=True), riskler)

en_yuksek = 0
for r in tum1.itertuples():  # kaba kuvvet: /predict-risk ile her işlemin skoru, en yüksek hangisi
    s = istemci_api.post("/predict-risk", json=dict(account_id=int(r.account_id), amount=float(r.amount), status=r.status,
                                                    channel=r.channel, is_international=int(r.is_international))).json()
    en_yuksek = max(en_yuksek, s["risk_score"])
kontrol("history sort_by=risk: ilk işlemin skoru, tüm işlemler arasındaki gerçek en yüksek skor (/predict-risk ile bağımsız hesap)",
        hr["islemler"][0]["risk_score"] == en_yuksek, (hr["islemler"][0]["risk_score"], en_yuksek))

uyum = True
for x in h["islemler"][:3] + hr["islemler"][:3]:
    s = istemci_api.post("/predict-risk", json=dict(account_id=x["account_id"], amount=x["amount"], status=x["status"],
                                                    channel=x["channel"], is_international=x["is_international"])).json()
    uyum &= s["risk_score"] == x["risk_score"] and s["risk_label"] == x["risk_label"] and s["rule_ids"] == x["rule_ids"]
kontrol("history: işlemdeki risk alanları /predict-risk ile birebir aynı (tek kod yolu)", uyum)

kontrol("history: limit=1 -> tek işlem", bt.get_transaction_history(1, limit=1)["donen"] == 1)
kontrol("history: müşteri 600 de çalışır (son müşteri)", "islemler" in bt.get_transaction_history(600))
kontrol("history: olmayan müşteri -> error, numarası geçiyor", hata_var(bt.get_transaction_history(4521), "4521"))
for kotu in ("1", 1.0, True, None):
    kontrol(f"history: customer_id={kotu!r} -> 'tam sayı' hatası", hata_var(bt.get_transaction_history(kotu), "tam sayı"))
for kotu in (0, 21, -1, "5", 5.0, True, None):
    kontrol(f"history: limit={kotu!r} -> hata", hata_var(bt.get_transaction_history(1, limit=kotu), "limit"))
for kotu in ("x", "RISK", "", None, 1):
    kontrol(f"history: sort_by={kotu!r} -> hata", hata_var(bt.get_transaction_history(1, sort_by=kotu), "sort_by"))

# müşteri var ama işlemi yok: hata değil, boş liste
asil = veri.tablolar
sahte_t = dict(t)
sahte_t["customers"] = pd.concat([t["customers"], t["customers"].loc[[1]].rename(index={1: 9999})])
sahte_t["accounts"] = pd.concat([t["accounts"], pd.DataFrame([{"account_id": 99999, "customer_id": 9999, "currency": "TRY",
                                                               "open_date": pd.Timestamp("2024-01-01"), "account_type": "vadesiz"}])])
veri.tablolar = lambda *a, **k: sahte_t
try:
    bos = bt.get_transaction_history(9999)
    kontrol("history: işlemi olmayan müşteri -> hata değil, toplam 0 ve boş liste", bos.get("toplam_islem") == 0 and bos.get("islemler") == [], bos)
    bosr = bt.get_transaction_history(9999, sort_by="risk")
    kontrol("history: işlemi olmayan müşteri, sort_by=risk de çökmez", bosr.get("islemler") == [], bosr)
finally:
    veri.tablolar = asil

# =============================================================== get_customer_info (yeni veri katmanıyla)
c1 = bt.get_customer_info(1)
kontrol("customer_info: veri katmanına geçişten sonra da aynı sonuç (müşteri 1, hesaplar 1-3)",
        c1["customer_id"] == 1 and [a["account_id"] for a in c1["accounts"]] == [1, 2, 3] and set(c1) == {"customer_id", "segment", "city", "risk_band", "onboard_date", "accounts"})
kontrol("customer_info: olmayan müşteri -> error", hata_var(bt.get_customer_info(4521), "4521"))

# =============================================================== search_risk_policy (sahte arama verisiyle)
class SahteModel:
    def sorgu_vektoru(self, soru):
        return [np.array([1.0, 0.0, 0.0])]


def chunk(i, sayfa, son, kodlar, bolum="Bölüm"):
    return {"id": i, "text": f"kayıt {i}", "page": sayfa, "page_end": son, "codes": kodlar, "section": bolum}


chunklar = [chunk(0, 5, 5, []), chunk(1, 6, 7, ["T-001-3.1"], "6. Tipler"), chunk(2, 9, 9, ["SK-01"]), chunk(3, 10, 10, []), chunk(4, 11, 11, []), chunk(5, 12, 12, [])]
vekt = np.array([[0.1, 1, 0], [0.9, 0.1, 0], [1.0, 0, 0], [0.2, 1, 0], [0.5, 0.5, 0], [0.3, 0.9, 0]], dtype=np.float32)
vekt = vekt / np.linalg.norm(vekt, axis=1, keepdims=True)
asil_rag = bt._rag
cagrilar = []
bt._rag = lambda: (cagrilar.append(1) or (SahteModel(), chunklar, vekt))
try:
    s = bt.search_risk_policy("herhangi bir konu")
    kontrol("policy: varsayılan k=3, skora göre sıralı (en yakın chunk 2, sonra 1, sonra 4)", [x["metin"] for x in s["sonuclar"]] == ["kayıt 2", "kayıt 1", "kayıt 4"], s)
    kontrol("policy: sonuç alanları (no, sayfa, sayfa_son, bolum, kodlar, skor, metin), sayfa aralığı korunur",
            set(s["sonuclar"][1]) == {"no", "sayfa", "sayfa_son", "bolum", "kodlar", "skor", "metin"}
            and (s["sonuclar"][1]["sayfa"], s["sonuclar"][1]["sayfa_son"], s["sonuclar"][1]["kodlar"]) == (6, 7, ["T-001-3.1"])
            and [x["no"] for x in s["sonuclar"]] == [1, 2, 3], s)
    kontrol("policy: sorgu geri yansıtılır, sonuç JSON'a çevrilebilir (float32 sızmamış)", s["sorgu"] == "herhangi bir konu" and bool(json.dumps(s, ensure_ascii=False)))
    kontrol("policy: k=5 -> 5 sonuç, k=1 -> 1 sonuç", len(bt.search_risk_policy("x", k=5)["sonuclar"]) == 5 and len(bt.search_risk_policy("x", k=1)["sonuclar"]) == 1)
    kontrol("policy: sorgunun baş/son boşlukları temizlenir", bt.search_risk_policy("  kripto  ")["sorgu"] == "kripto")
    for kotu in (0, 6, -1, "3", 3.0, True, None):
        kontrol(f"policy: k={kotu!r} -> hata", hata_var(bt.search_risk_policy("x", k=kotu), "k"))
    for kotu in ("", "   ", None, 5, ["x"], "a" * 301):
        n = len(cagrilar)
        r = bt.search_risk_policy(kotu)
        kontrol(f"policy: query={str(kotu)[:12]!r}... -> hata, arama yapılmadı", hata_var(r, "query") and len(cagrilar) == n, r)
    kontrol("policy: 300 karakterlik sorgu kabul edilir (sınır dahil)", "sonuclar" in bt.search_risk_policy("a" * 300))

    # arama altyapısı çökerse
    def patla():
        raise RuntimeError("gizli-model-yolu")

    bt._rag = patla
    import logging
    logging.disable(logging.CRITICAL)
    r = bt.search_risk_policy("x")
    logging.disable(logging.NOTSET)
    kontrol("policy: model/indeks hatasında çökmez, kısa hata döner, iç ayrıntı sızmaz", hata_var(r, "kullanılamıyor") and "gizli-model-yolu" not in r["error"], r)
finally:
    bt._rag = asil_rag

# =============================================================== şema ve dağıtıcı
sema = {s["name"]: s for s in bt.TOOL_SCHEMAS}
kontrol("şema: dört araç, adlar FONKSIYONLAR ile aynı", set(sema) == set(bt.FONKSIYONLAR) == {"get_risk_score", "get_customer_info", "get_transaction_history", "search_risk_policy"})
varsayilan_ok = True
for ad, s in sema.items():
    imza = inspect.signature(bt.FONKSIYONLAR[ad]).parameters
    for isim, p in imza.items():
        ozellik = s["input_schema"]["properties"][isim]
        if p.default is not inspect.Parameter.empty:
            varsayilan_ok &= ozellik.get("default") == p.default
kontrol("şema: varsayılan değerler fonksiyonlarla aynı (limit=5, sort_by=recent, k=3)", varsayilan_ok)
ph = sema["get_transaction_history"]["input_schema"]["properties"]
ps = sema["search_risk_policy"]["input_schema"]["properties"]
kontrol("şema: sınırlar kodla aynı (limit 1-MAKS_LIMIT, k 1-MAKS_K, sort_by enum, query uzunluğu)",
        (ph["limit"]["minimum"], ph["limit"]["maximum"]) == (1, bt.MAKS_LIMIT) and ph["sort_by"]["enum"] == bt.SIRALAMALAR
        and (ps["k"]["minimum"], ps["k"]["maximum"]) == (1, bt.MAKS_K) and ps["query"]["maxLength"] == bt.MAKS_SORGU_UZUNLUGU)
kontrol("şema: her aracın açıklaması dolu, tüm parametrelerin açıklaması dolu",
        all(s["description"].strip() and all(p.get("description") for p in s["input_schema"]["properties"].values()) for s in bt.TOOL_SCHEMAS))
kontrol("şema: JSON'a çevrilebilir", bool(json.dumps(bt.TOOL_SCHEMAS)))
kontrol("agent sistem mesajı dört aracın adını da anıyor, sort_by='risk' ve hukuki hüküm kuralları var",
        all(a in agent.SISTEM_MESAJI for a in bt.FONKSIYONLAR) and "sort_by='risk'" in agent.SISTEM_MESAJI and "Hukuki hüküm verme" in agent.SISTEM_MESAJI)

r = bt.tool_calistir("get_transaction_history", {"customer_id": 1, "limit": 2, "sort_by": "risk"})
kontrol("tool_calistir: yeni araç Claude'un vereceği biçimde (dict) çalışır", r.get("donen") == 2, r)
kontrol("tool_calistir: history'ye eksik argüman -> error", hata_var(bt.tool_calistir("get_transaction_history", {})))
kontrol("tool_calistir: policy'ye fazla argüman adı -> error", hata_var(bt.tool_calistir("search_risk_policy", {"query": "x", "limit": 3})))

print(f"\n{sum(sonuclar)}/{len(sonuclar)} kontrol geçti")
sys.exit(0 if all(sonuclar) else 1)
