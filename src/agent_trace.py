"""Gün 17: ajan izi (trace).

Agent bir görevi birkaç adımda çözer. "Ne oldu?" sorusunun cevabı İZDİR: hangi adımda hangi araç hangi argümanla
çağrıldı, ne döndü, ne kadar sürdü, kaç token gitti. İz olmadan bir agent'a güvenemezsin (neden yanlış cevap verdi?
neden pahalı? neden yavaş?). Bu modül iki iş yapar:
  1. calistir() sonucundan düz, JSON'a çevrilebilir bir iz sözlüğü kurar (iz_olustur)
  2. izi ekrana okunur şekilde yazar (yazdir_metni) ve diske kaydeder (kaydet)

Önemli: iz dosyasında müşteri verisi (araç sonuçları) olduğu için bu dosyalar repoya GİRMEMELİ (data/izler/).
Maliyet: fiyatı kodun içine yazmıyoruz (fiyat değişir, yanlış olursa yanıltır). İstersen ortam değişkeniyle ver:
  GIRDI_FIYAT_1M ve CIKTI_FIYAT_1M (milyon token başına USD). Verilmezse maliyet gösterilmez.
"""
import copy
import hashlib
import json
import math
import os
from datetime import datetime

IZ_SURUMU = 1
EKRAN_SONUC_UZUNLUGU = 300  # ekranda araç sonucu bu kadar karakterle sınırlanır; diskteki iz tam sonucu tutar


def ozetle(deger, uzunluk=EKRAN_SONUC_UZUNLUGU):
    """Uzun metni/sözlüğü ekran için kısaltır. Kısaltılırsa ne kadarının atıldığını söyler."""
    metin = deger if isinstance(deger, str) else json.dumps(deger, ensure_ascii=False, default=str)
    if len(metin) <= uzunluk:
        return metin
    return metin[:uzunluk] + f"... (+{len(metin) - uzunluk} karakter)"


def sistem_mesaji_id(sistem_mesaji):
    """Hangi sistem mesajıyla çalıştığını izden anlamak için kısa parmak izi (iki iz karşılaştırılırken lazım)."""
    return hashlib.sha256(sistem_mesaji.encode("utf-8")).hexdigest()[:8]


def maliyet_usd(kullanim, girdi_1m, cikti_1m):
    """Milyon token başına fiyatlarla yaklaşık maliyet. Fiyat yoksa None (uydurma sayı üretmeyiz)."""
    if girdi_1m is None or cikti_1m is None:
        return None
    return round((kullanim["girdi"] * girdi_1m + kullanim["cikti"] * cikti_1m) / 1_000_000, 6)


def fiyatlar_env(env=None):
    """GIRDI_FIYAT_1M / CIKTI_FIYAT_1M ortam değişkenlerini okur. Eksik, bozuk, negatif ya da sonsuzsa (None, None)."""
    env = os.environ if env is None else env
    try:
        g, c = float(env["GIRDI_FIYAT_1M"]), float(env["CIKTI_FIYAT_1M"])
    except (KeyError, ValueError):
        return None, None
    if not (math.isfinite(g) and math.isfinite(c) and g >= 0 and c >= 0):
        return None, None
    return g, c


def iz_olustur(gorev, sonuc, *, model, max_steps, sistem_mesaji, zaman=None, girdi_1m=None, cikti_1m=None):
    """agent.calistir() sonucundan iz sözlüğü kurar. sonuc'un kopyasını alır (sonradan değişse iz bozulmaz)."""
    adimlar = copy.deepcopy(sonuc["adimlar"])
    calisan = [r for a in adimlar for r in a["araclar"] if r["calistirildi"]]
    hatali = [r for r in calisan if isinstance(r["sonuc"], dict) and "error" in r["sonuc"]]
    kullanim = dict(sonuc["kullanim"])
    return {
        "surum": IZ_SURUMU,
        "zaman": (zaman or datetime.now()).isoformat(timespec="seconds"),
        "model": model,
        "sistem_mesaji_id": sistem_mesaji_id(sistem_mesaji),
        "gorev": gorev,
        "max_steps": max_steps,
        "bitis": sonuc["bitis"],
        "cevap": sonuc["cevap"],
        "kullanim": kullanim,
        "sure_ms": sonuc.get("sure_ms"),
        "maliyet_usd": maliyet_usd(kullanim, girdi_1m, cikti_1m),
        "arac_sirasi": [r["arac"] for r in calisan],
        "arac_sayisi": len(calisan),
        "hatali_arac_sayisi": len(hatali),
        "calistirilmayan_arac_sayisi": sum(1 for a in adimlar for r in a["araclar"] if not r["calistirildi"]),
        "adimlar": adimlar,
    }


def _sn(ms):
    return "?" if ms is None else f"{ms / 1000:.1f} sn"


def yazdir_metni(iz):
    """İzi insan için okunur metne çevirir. Uzun araç sonuçları kısaltılır; tamamı diskteki iz dosyasında durur."""
    satirlar = [f"Görev: {iz['gorev']}", f"(max_steps={iz['max_steps']})", ""]
    for a in iz["adimlar"]:
        satirlar.append(f"Adım {a['adim']} [{a['durum']}] girdi {a['girdi_token']} / çıktı {a['cikti_token']} token, "
                        f"Claude {_sn(a.get('sure_ms'))}")
        for r in a["araclar"]:
            if r["calistirildi"]:
                satirlar.append(f"   {r['arac']}({json.dumps(r['girdi'], ensure_ascii=False)}) [{_sn(r.get('sure_ms'))}]")
                satirlar.append(f"   -> {ozetle(r['sonuc'])}")
            else:
                satirlar.append(f"   {r['arac']}({json.dumps(r['girdi'], ensure_ascii=False)})  (ÇALIŞTIRILMADI: sınır)")
    u = iz["kullanim"]
    satirlar += ["", "Cevap:", iz["cevap"], ""]
    ozet = (f"Bitiş nedeni: {iz['bitis']} | Claude çağrısı: {u['cagri']} | girdi token: {u['girdi']} | "
            f"çıktı token: {u['cikti']} | toplam süre: {_sn(iz['sure_ms'])}")
    satirlar.append(ozet)
    satirlar.append(f"Araçlar: {' -> '.join(iz['arac_sirasi']) or '(yok)'} | hatalı araç: {iz['hatali_arac_sayisi']} | "
                    f"sistem mesajı: {iz['sistem_mesaji_id']}")
    if iz["maliyet_usd"] is not None:
        satirlar.append(f"Yaklaşık maliyet: ${iz['maliyet_usd']:.4f}")
    return "\n".join(satirlar)


def kaydet(iz, klasor, simdi=None):
    """İzi klasore tek bir JSON dosyası olarak yazar (önce .tmp, sonra yeniden adlandırma: yarım dosya kalmaz).
    Dosya adı zaman damgalıdır, aynı ada denk gelirse sayaç eklenir (üstüne yazmaz). Yolu döndürür."""
    os.makedirs(klasor, exist_ok=True)
    damga = (simdi or datetime.now()).strftime("%Y%m%d-%H%M%S-%f")
    yol = os.path.join(klasor, f"iz_{damga}.json")
    n = 1
    while os.path.exists(yol):
        yol = os.path.join(klasor, f"iz_{damga}_{n}.json")
        n += 1
    gecici = yol + ".tmp"
    try:
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(iz, f, ensure_ascii=False, indent=2)
        os.replace(gecici, yol)
    finally:
        if os.path.exists(gecici):
            os.remove(gecici)
    return yol
