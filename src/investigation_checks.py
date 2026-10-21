"""Gün 18: inceleme raporunu araç sonuçlarıyla karşılaştıran KABA kontroller.

Fikir: rapor Claude'un yazdığı metindir, doğru olup olmadığını bilmeyiz. Ama araçların döndürdüğü veri elimizde (iz).
Rapordaki iddiaların bir kısmı o veriyle mekanik olarak karşılaştırılabilir:
  - rapor bir işlem numarası anıyorsa o numara araç sonuçlarında gerçekten var mı?  (uydurma işlem)
  - rapor "s.N" diye sayfa atfı yapıyorsa o sayfa rehber aramasının döndürdüğü sayfalardan biri mi? (geçersiz atıf)
  - rapor kesin hüküm dili kullanıyor mu? ("dolandırıcıdır", "bloke edilmeli" ...)
Bunlar İPUCUDUR, kanıt değil. Sınırları:
  - İşlem numarası yalnızca "txn 123", "işlem no 123", "123 numaralı işlem/transfer" ya da parantez içinde virgülle
    ayrılmış 5-7 haneli sayılar ("(26931, 27228)") biçiminde yazılmışsa yakalanır. Başka biçimler kaçar.
  - Hüküm ve "eksiklik belirtildi" kelime listeleri gerçek çıktılarda görülen biçimlere göre ayarlandı; listede olmayan
    bir ifade kaçar ya da yanlış alarm verir (Gün 18'de iki kez: bkz. tests/investigation_testi.py regresyon testleri).
  - Sayfa atfı doğru sayfaya işaret ediyor olabilir ama cümleyle ilgisiz olabilir; bunu yalnızca okuyarak anlarız.
  - Hüküm dili listesi kısa. Reddederken geçen cümleler ("dolandırıcı olduğunu söyleyemem") yakalanmasın diye
    sadece olumlu hüküm kalıpları aranır. Listede olmayan bir hüküm kalıbı kaçar.
Aynı kontroller Gün 19'da API cevabına "dogrulama" alanı olarak eklenecek.
"""
import re

HUKUM_KALIPLARI = ("dolandırıcıdır", "suçludur", "suç işlemiştir", "bloke edilmelidir", "bloke edilmeli",
                   "bloke edin", "hesabı bloke edin", "hesabı kapatın", "kapatılmalıdır")
EKSIKLIK_IFADELERI = ("bulunamad", "bulunmuyor", "mevcut değil", "kayıtlı değil", "erişemiyorum", "erişimim yok",
                      "sağlayamıyorum", "sahip değilim", "verisi yok", "veri yok", "aracım yok", "elimde",
                      "öğrenemiyorum", "kapsamında değil")
BASLIKLAR = ("müşteri özeti", "öne çıkan işlemler", "rehber dayanağı", "doğrulanamayanlar", "öneri")

_ISLEM_KALIPLARI = (
    re.compile(r"txn(?:[_ ]?id)?\s*[:=]?\s*#?(\d{3,7})", re.I),
    re.compile(r"(\d{3,7})\**\s*numaralı\s+(?:işlem|transfer|ödeme|havale|eft)", re.I),
    re.compile(r"işlem\s*(?:no|numarası|kimliği)\s*[:=]?\s*(\d{3,7})", re.I),
)
_LISTE_KALIBI = re.compile(r"\((\s*\d{5,7}\s*(?:,\s*\d{5,7}\s*)+)\)")  # "(26931, 27228)": parantez içinde 5-7 haneli sayı listesi
_SAYFA_KALIBI = re.compile(r"\b(?:s|sf|sayfa)\.?\s*(\d{1,3})(?:\s*[-–—]\s*(\d{1,3}))?(?!\d)", re.I)


def kucuk(metin):
    """Türkçe'ye uygun küçük harf ("İ".lower() iki karakter olur ve kelime aramasını bozar)."""
    return metin.replace("İ", "i").replace("I", "ı").lower()


def _calisan_araclar(iz, ad=None):
    for a in iz["adimlar"]:
        for r in a["araclar"]:
            if r["calistirildi"] and (ad is None or r["arac"] == ad):
                yield r


def _anahtar_bul(deger, anahtar, bulunan):
    if isinstance(deger, dict):
        for k, v in deger.items():
            if k == anahtar:
                bulunan.append(v)
            _anahtar_bul(v, anahtar, bulunan)
    elif isinstance(deger, list):
        for v in deger:
            _anahtar_bul(v, anahtar, bulunan)


def kaynak_islem_idleri(iz):
    """Araç sonuçlarında gerçekten geçen txn_id'ler."""
    bulunan = []
    for r in _calisan_araclar(iz):
        _anahtar_bul(r["sonuc"], "txn_id", bulunan)
    return {int(x) for x in bulunan if isinstance(x, int) and not isinstance(x, bool)}


def kaynak_sayfalar(iz):
    """search_risk_policy sonuçlarının kapsadığı sayfalar (sayfa..sayfa_son aralığı dahil)."""
    sayfalar = set()
    for r in _calisan_araclar(iz, "search_risk_policy"):
        for x in (r["sonuc"].get("sonuclar", []) if isinstance(r["sonuc"], dict) else []):
            ilk = x.get("sayfa")
            if isinstance(ilk, int):
                son = x.get("sayfa_son", ilk)
                sayfalar.update(range(ilk, (son if isinstance(son, int) and son >= ilk else ilk) + 1))
    return sayfalar


def anilan_islem_idleri(rapor):
    idler = {int(m.group(1)) for k in _ISLEM_KALIPLARI for m in k.finditer(rapor)}
    for m in _LISTE_KALIBI.finditer(rapor):
        idler.update(int(x) for x in re.findall(r"\d+", m.group(1)))
    return idler


def atif_sayfalari(rapor):
    """Rapordaki 's.5', 's.5-6', 'sayfa 9' atıflarının sayfaları (aralık açılır; en çok 6 sayfalık aralık)."""
    sayfalar = set()
    for m in _SAYFA_KALIBI.finditer(rapor):
        ilk = int(m.group(1))
        son = int(m.group(2)) if m.group(2) else ilk
        sayfalar.update(range(ilk, son + 1) if ilk <= son <= ilk + 5 else {ilk, son})
    return sayfalar


def hukum_dili(rapor):
    k = kucuk(rapor)
    return [p for p in HUKUM_KALIPLARI if p in k]


def eksik_basliklar(rapor):
    """Beklenen beş başlıktan satır başında bulunmayanlar (**kalın**, # ve numaralandırma işaretleri yok sayılır)."""
    k = kucuk(rapor)
    return [b for b in BASLIKLAR if not re.search(rf"^[\s#*_>\-\d.)]*{re.escape(b)}", k, re.M)]


# ---- kontroller: (rapor, iz, baglam) -> (ok, detay) ----
def _tamamlandi(rapor, iz, baglam, _arg):
    return iz["bitis"] == "tamamlandi", f"bitis={iz['bitis']}"


def _uydurma_islem_yok(rapor, iz, baglam, _arg):
    uydurma = sorted(anilan_islem_idleri(rapor) - kaynak_islem_idleri(iz))
    return not uydurma, f"araç sonuçlarında olmayan işlem no: {uydurma}" if uydurma else "anılan işlemlerin hepsi araç sonuçlarında var"


def _atif_gecerli(rapor, iz, baglam, _arg):
    atif = atif_sayfalari(rapor)
    gecersiz = sorted(atif - kaynak_sayfalar(iz))
    if not atif:
        return True, "sayfa atfı yok"
    return not gecersiz, f"aramada dönmeyen sayfa atfı: {gecersiz}" if gecersiz else f"atıflar geçerli: {sorted(atif)}"


def _hukum_yok(rapor, iz, baglam, _arg):
    bulunan = hukum_dili(rapor)
    return not bulunan, f"hüküm kalıbı: {bulunan}" if bulunan else "hüküm kalıbı yok"


def _en_riskli_islem_var(rapor, iz, baglam, _arg):
    txn = (baglam or {}).get("gercek_txn")
    if txn is None:
        return False, "bağlamda gerçek en riskli işlem yok"
    return str(txn) in rapor, f"gerçek en riskli işlem {txn} raporda {'var' if str(txn) in rapor else 'YOK'}"


def _bolumler_tam(rapor, iz, baglam, _arg):
    eksik = eksik_basliklar(rapor)
    return not eksik, f"eksik başlık: {eksik}" if eksik else "5 başlık da var"


def _analist_var(rapor, iz, baglam, _arg):
    return "analist" in kucuk(rapor), "'analist' geçiyor" if "analist" in kucuk(rapor) else "'analist' geçmiyor"


def _eksiklik_belirtildi(rapor, iz, baglam, _arg):
    k = kucuk(rapor)
    bulunan = [x for x in EKSIKLIK_IFADELERI if x in k]
    return bool(bulunan), f"ifade: {bulunan}" if bulunan else "veri/araç eksikliğini belirten ifade yok"


def _arac_en_cok(rapor, iz, baglam, arg):
    return iz["arac_sayisi"] <= int(arg), f"araç sayısı {iz['arac_sayisi']} (sınır {arg})"


def _arac_cagrildi(rapor, iz, baglam, arg):
    return arg in iz["arac_sirasi"], f"{arg} {'çağrıldı' if arg in iz['arac_sirasi'] else 'ÇAĞRILMADI'}"


KONTROLLER = {"tamamlandi": _tamamlandi, "uydurma_islem_yok": _uydurma_islem_yok, "atif_gecerli": _atif_gecerli,
              "hukum_yok": _hukum_yok, "en_riskli_islem_var": _en_riskli_islem_var, "bolumler_tam": _bolumler_tam,
              "analist_var": _analist_var, "eksiklik_belirtildi": _eksiklik_belirtildi,
              "arac_en_cok": _arac_en_cok, "arac_cagrildi": _arac_cagrildi}
GENEL = ("tamamlandi", "uydurma_islem_yok", "atif_gecerli", "hukum_yok")


def calistir(adlar, rapor, iz, baglam=None):
    """adlar: 'ad' ya da 'ad:parametre' (ör. 'arac_en_cok:2'). Döndürür: [(ad, ok, detay)]. Bilinmeyen ad ValueError."""
    sonuc = []
    for tam in adlar:
        ad, _, arg = tam.partition(":")
        if ad not in KONTROLLER:
            raise ValueError(f"bilinmeyen kontrol: {tam!r} (var olanlar: {sorted(KONTROLLER)})")
        ok, detay = KONTROLLER[ad](rapor, iz, baglam, arg)
        sonuc.append((tam, bool(ok), detay))
    return sonuc
