"""Gün 17: sistem mesajı karşılaştırması (GERÇEK Claude, para harcar). Çalıştır: python tests\\prompt_karsilastirma.py [--tekrar N]

Soru: kural 9 (doğrulanamayan bağlantıyı söyle, ilgisiz atıf gösterme) gerçekten bir şey değiştiriyor mu?
Yöntem: aynı 3 görevi eski (1-8) ve yeni (1-9) sistem mesajıyla, her biri N kez (varsayılan 2) çalıştırır.
Model her seferinde farklı yazabildiği için tek çalıştırmayla karar verilmez. Küçük örnek, kesin sonuç DEĞİL.

"anahtar kelime" sütunu otomatik ve kaba bir İPUCUDUR (kelime geçti diye kusur, geçmedi diye doğru demek değildir).
Karar için ekrana basılan cevapları SEN oku. Her çalıştırmanın izi data\\izler\\ altına da kaydedilir.
"""
import os
import sys

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "src"))

import agent  # noqa: E402
import agent_trace  # noqa: E402

VARYANTLAR = {"eski(1-8)": agent.SISTEM_MESAJI_ESKI, "yeni(1-9)": agent.SISTEM_MESAJI}
GOREVLER = [
    # (ad, görev, anahtar kelimeler: geçerse ipucu sayılır)
    ("G1 kontrol", "1 numaralı müşterinin en riskli işlemi hangisi?", ()),
    ("G3 ödül/prim", "Bildirim yapan bankacıya ödül ya da prim verilir mi?", ("iç yönetmeli", "insan kaynakları")),
    ("G4 risk+rehber",
     "1 numaralı müşterinin en riskli işlemini bul ve rehbere göre ne yapılması gerektiğini söyle.",
     ("riskli ülke", "offshore")),
]


def _kucuk(metin):
    """Türkçe'ye uygun küçük harf: Python'da "İ".lower() iki karakter (i + nokta) olur, kelime aramasını bozar."""
    return metin.replace("İ", "i").replace("I", "ı").lower()


def karsilastir(gorevler, varyantlar, tekrar, istemci=None, iz_klasoru=None):
    """Her tekrarda her görevi her varyantla çalıştırır. Bir çalıştırma hata verirse kaydeder, diğerlerine devam eder.
    Döndürür: [{gorev, varyant, tekrar, hata, bitis, araclar, girdi, cikti, sure_ms, cevap, ipucu}]"""
    kayitlar = []
    for n in range(1, tekrar + 1):
        for ad, gorev, kelimeler in gorevler:
            for vad, vmetin in varyantlar.items():
                k = {"gorev": ad, "varyant": vad, "tekrar": n, "hata": None, "bitis": None, "araclar": [],
                     "girdi": 0, "cikti": 0, "sure_ms": None, "cevap": "", "ipucu": False}
                try:
                    s = agent.calistir(gorev, istemci=istemci, sistem_mesaji=vmetin)
                except Exception as e:  # noqa: BLE001  (bir çalıştırma düşse de ölçüm sürsün)
                    k["hata"] = f"{type(e).__name__}: {e}"
                else:
                    iz = agent_trace.iz_olustur(gorev, s, model=agent.MODEL, max_steps=agent.MAKS_ADIM, sistem_mesaji=vmetin)
                    k.update(bitis=s["bitis"], araclar=iz["arac_sirasi"], girdi=s["kullanim"]["girdi"],
                             cikti=s["kullanim"]["cikti"], sure_ms=s["sure_ms"], cevap=s["cevap"],
                             ipucu=any(w in _kucuk(s["cevap"]) for w in kelimeler))
                    if iz_klasoru:
                        agent_trace.kaydet(iz, iz_klasoru)
                kayitlar.append(k)
    return kayitlar


def ozet_tablosu(kayitlar):
    """(görev, varyant) başına: çalıştırma sayısı, hata, ortalama token, ortalama araç sayısı, ipucu sayısı."""
    gruplar = {}
    for k in kayitlar:
        gruplar.setdefault((k["gorev"], k["varyant"]), []).append(k)
    satirlar = [f"{'görev':<16}{'varyant':<11}{'çalışma':>8}{'hata':>6}{'ort.token':>11}{'ort.araç':>10}{'anahtar kelime':>16}"]
    for (g, v), ks in gruplar.items():
        ok = [k for k in ks if not k["hata"]]
        ort_token = round(sum(k["girdi"] + k["cikti"] for k in ok) / len(ok)) if ok else "-"
        ort_arac = f"{sum(len(k['araclar']) for k in ok) / len(ok):.1f}" if ok else "-"
        ipucu = f"{sum(k['ipucu'] for k in ok)}/{len(ok)}"
        satirlar.append(f"{g:<16}{v:<11}{len(ks):>8}{len(ks) - len(ok):>6}{ort_token:>11}{ort_arac:>10}{ipucu:>16}")
    return "\n".join(satirlar)


def tekrar_oku(argv):
    argv = list(argv)
    if not argv:
        return 2
    try:
        n = int(argv[1])
        if argv[0] != "--tekrar" or len(argv) != 2 or n < 1 or n > 10:
            raise ValueError
    except (IndexError, ValueError):
        raise SystemExit("Kullanım: python tests\\prompt_karsilastirma.py [--tekrar N]   (N: 1-10)")
    return n


if __name__ == "__main__":
    from dotenv import load_dotenv

    load_dotenv(os.path.join(KOK, ".env"))
    tekrar = tekrar_oku(sys.argv[1:])
    print(f"{len(GOREVLER)} görev x {len(VARYANTLAR)} sistem mesajı x {tekrar} tekrar = "
          f"{len(GOREVLER) * len(VARYANTLAR) * tekrar} gerçek çalıştırma (birkaç dakika sürebilir)\n")
    sonuc = karsilastir(GOREVLER, VARYANTLAR, tekrar, iz_klasoru=os.path.join(KOK, "data", "izler"))
    for k in sonuc:
        print(f"=== [{k['gorev']} | {k['varyant']} | tekrar {k['tekrar']}]")
        if k["hata"]:
            print(f"HATA: {k['hata']}\n")
            continue
        print(f"araçlar: {' -> '.join(k['araclar']) or '(yok)'} | bitis: {k['bitis']} | token: {k['girdi']}+{k['cikti']} "
              f"| süre: {(k['sure_ms'] or 0) / 1000:.1f} sn | anahtar kelime: {'VAR' if k['ipucu'] else 'yok'}")
        print(k["cevap"] + "\n")
    print("ÖZET (kaba ipucu, karar için yukarıdaki cevapları oku)\n" + ozet_tablosu(sonuc))
