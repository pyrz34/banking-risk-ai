# RAG Değerlendirme (Gün 13)

Otomatik üretildi: `python tests\rag_degerlendirme.py`. ✓ doğru, ✗ hata, — uygulanmaz, ? elle bakılmalı.
`Dayanaklı` otomatik bir vekil ölçüdür (atıf var + atıf yapılan chunk beklenen bilgiyi içeriyor); cümle cümle dayanak kontrolü değildir.

## Özet

**AYAR seti (ayar yapıldı, skor şişik)**
- Cevaplı sorular (4): arama 4/4, cevap 4/4, dayanaklı 4/4
- Cevapsız sorular (3): doğru reddetme 3/3

**HELD-OUT seti (ayar yapılmadı)**
- Cevaplı sorular (12): arama 11/12, cevap 11/12, dayanaklı 11/12
- Cevapsız sorular (3): doğru reddetme 3/3

**TAZE set (Gün 13'te yazıldı, hiç ayar görmedi; en dürüst ölçü)**
- Cevaplı sorular (8): arama 8/8, cevap 8/8, dayanaklı 8/8
- Cevapsız sorular (3): doğru reddetme 3/3

## Tablo

| # | Küme | Soru | Arama | Cevap | Dayanaklı | Atıf | Hata türü |
|---|------|------|-------|-------|-----------|------|-----------|
| 1 | ayar | Cuma günü mesai bitimine yakın saatlerde transfer talep eden müşteri … | ✓ | ✓ | ✓ | [1] | YOK |
| 2 | ayar | Kiralık kasa ziyaretleri aniden artarsa bu bir şüpheli işlem gösterge… | ✓ | ✓ | ✓ | [3],[4] | YOK |
| 3 | ayar | Tefecilik hangi şüphe kategorisi koduyla bildirilir? | ✓ | ✓ | ✓ | [1],[2] | YOK |
| 4 | ayar | Bildirimi ertelemek için en fazla kaç iş günü beklenir? | ✓ | ✓ | ✓ | [1] | YOK |
| 5 | ayar | Şüpheli işlem bildirimi yapmayan bankaya hangi idari para cezası uygu… | — | ✓ | ✓ | - | YOK |
| 6 | ayar | Rehber hangi yapay zeka modelinin şüpheli işlem tespitinde kullanılma… | — | ✓ | ✓ | - | YOK |
| 7 | ayar | Rehbere göre bulut tabanlı sistemlerde müşteri verisi nasıl saklanmal… | — | ✓ | ✓ | - | YOK |
| 8 | held-out | Şüpheli işlem açıklama alanına en az kaç karakter girilmesi zorunludu… | ✓ | ✓ | ✓ | [1] | YOK |
| 9 | held-out | Bir bildirimde en fazla kaç şüphe kategorisi seçilebilir? | ✓ | ✓ | ✓ | [1],[3] | YOK |
| 10 | held-out | Terörizmin finansmanı için yeterli şüphe yoksa hangi bildirim kategor… | ✓ | ✓ | ✓ | [1] | YOK |
| 11 | held-out | Kitle imha silahlarının yayılmasının finansmanı bildirimlerinde hangi… | ✓ | ✓ | ✓ | [1] | YOK |
| 12 | held-out | Mal varlığının dondurulması kararının ihlali hangi kodla bildirilir? | ✓ | ✓ | ✓ | [1],[2] | YOK |
| 13 | held-out | Vadeli mevduat veya katılım hesabının hesap türü kodu nedir? | ✓ | ✓ | ✓ | [1] | YOK |
| 14 | held-out | POS tefeciliği hangi şüphe kategorisi koduyla bildirilir? | ✓ | ✓ | ✓ | [1],[2] | YOK |
| 15 | held-out | Şüpheli işlem bildiriminde bulunulduğunu müşteriye açıklayan görevli … | ✓ | ✓ | ✓ | [1] | YOK |
| 16 | held-out | Faks ile yapılan bildirimlerde ayrıca ne yapılması gerekir? | ✓ | ✓ | ✓ | [1] | YOK |
| 17 | held-out | Aynı konuyla ilgili birden çok kişi için kaç şüpheli işlem bildirim f… | ✗ | ✗ | ✗ | [2],[4],[5] | ARAMA_KACTI |
| 18 | held-out | Aynı eylem için birden fazla ek bildirim gönderilecekse önceki refera… | ✓ | ✓ | ✓ | [1],[3] | YOK |
| 19 | held-out | Gerekmediği halde ivedi olarak gönderilen bildirimler hangi soruna yo… | ✓ | ✓ | ✓ | [1] | YOK |
| 20 | held-out | Rehberin İngilizce sürümü hangi internet adresinden indirilir? | — | ✓ | ✓ | - | YOK |
| 21 | held-out | Bildirim yapan bankacıya ödül ya da prim verilir mi? | — | ✓ | ✓ | - | YOK |
| 22 | held-out | Bildirimi hazırlayan personelin hangi diplomaya sahip olması gerekir? | — | ✓ | ✓ | - | YOK |
| 23 | taze | MASAK.Online sistemine giriş yetkisi almak için yükümlü kurum hangi b… | ✓ | ✓ | ✓ | [1],[2] | YOK |
| 24 | taze | Bir bankanın uyum görevlisi değişirse MASAK.Online için ne yapılması … | ✓ | ✓ | ✓ | [1] | YOK |
| 25 | taze | Rehbere göre hangi tarihten sonra şüpheli işlem bildirimleri yalnızca… | ✓ | ✓ | ✓ | [1] | YOK |
| 26 | taze | Elde tutulan (stok) mal varlıkları için yapılan bildirimlerde ertelem… | ✓ | ✓ | ✓ | [1] | YOK |
| 27 | taze | Bu rehber bankalar dışında hangi kuruluş için de geçerlidir? | ✓ | ✓ | ✓ | [1],[3] | YOK |
| 28 | taze | Hazine ve Maliye Bakanlığı'na şüpheli işlem bildirim formlarının düze… | ✓ | ✓ | ✓ | [1] | YOK |
| 29 | taze | MASAK'ın yayımladığı bildirim rehberleri nerede duyurulur? | ✓ | ✓ | ✓ | [1] | YOK |
| 30 | taze | Erteleme talebiyle bildirim yapmak için yalnızca şüphe yeterli midir? | ✓ | ✓ | ✓ | [2],[5] | YOK |
| 31 | taze | MASAK, bildirimi gönderen bankaya geri bildirimi kaç gün içinde verir? | — | ✓ | ✓ | - | YOK |
| 32 | taze | Rehbere göre bildirim verileri kişisel verilerin korunması mevzuatı k… | — | ✓ | ✓ | - | YOK |
| 33 | taze | Bildirimlerin gönderilmesi için MASAK'a ödenen ücret ve harç ne kadar… | — | ✓ | ✓ | - | YOK |

## Hata türleri

### ARAMA_KACTI (1): Beklenen bilgi çekilen chunk'larda yok (sorun arama/chunklamada)
- #17 (held-out) Aynı konuyla ilgili birden çok kişi için kaç şüpheli işlem bildirim formu düzenlenir?
  - cevap: Rehberde, birden çok kişi için kaç şüpheli işlem bildirim formu düzenleneceği konusunda bir bilgi bulamadım. Rehberde bu bilgiyi bulamadım. İşlemle ilişkili kişilerin bilgilerine ayrı ayrı yer verilmelidir [4]. Birden fazla tüzel kişi için formun D bölümü, bi…

## Elle inceleme notları (sen doldur)

- Cevaplardaki kaynakta olmayan cümle var mı? (CSV'de `cevap` ile `kaynak_metinleri`ni yan yana oku)
- `RED_ARTI_ILGILI_BILGI` olanlarda ek bilgi kaynakta gerçekten yazıyor mu?
