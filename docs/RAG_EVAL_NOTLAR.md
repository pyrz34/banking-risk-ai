# RAG Değerlendirme: elle inceleme bulguları (Gün 13)

Kaynak: `data/rag_inceleme.txt` (33 soru, `python tests/rag_degerlendirme.py` ve `python tests/eval_oku.py` çıktısı).
Cevap ile atıf yapılan chunk cümle cümle karşılaştırıldı. İkinci okuyucu: Claude. Poyraz'ın kendi okumasıyla doğrulanması gerekir.

## Sonuç tablosu (otomatik ölçü)

| Küme | Arama | Cevap | Dayanaklı (vekil ölçü) | Cevapsızı reddetme |
|---|---|---|---|---|
| AYAR (4+3 soru, ayar yapıldı, skor şişik) | 4/4 | 4/4 | 4/4 | 3/3 |
| HELD-OUT (12+3 soru, bir kez hata ayıklamada görüldü) | 11/12 | 11/12 | 11/12 | 3/3 |
| TAZE (8+3 soru, Gün 13'te yazıldı, ayar görmedi) | 8/8 | 8/8 | 8/8 | 3/3 |

Otomatik ölçü tek hata gördü (#17). Elle okuyunca **bir hata daha** çıktı (#2, bulgu 2). Yani otomatik ölçü yetmiyor.

Sınırlar: taze sette sadece 8 cevaplı soru var, 8/8 ile %90 gerçek başarı ayırt edilemez. Taze soruları sistemin zayıf yönlerini bilen Claude yazdı. 100 % "genelleme garantisi" değil.

## Bulgular

### 1. #17: arama hatası + yanlış "yok" iddiası
- Soru: "Aynı konuyla ilgili birden çok kişi için kaç şüpheli işlem bildirim formu düzenlenir?"
- Cevap PDF sayfa **9**, "4.1 Formun Düzenlenmesine Dair Genel Hususlar" (ilk notta yanlışlıkla 8 yazılmıştı; hatalı chunk metadatasından alınmıştı, bkz. bulgu 6): "Aynı konuyla ilgili birden çok gerçek ve/veya tüzel kişi hakkında **tek bir ŞİB Formu** düzenlenir." (33 kelimelik kısa chunk).
- Soru bu cümleye kelimesi kelimesine benziyor. BM25 chunk'ı **1. sıraya** koyuyor (skor 26.2, ikincisi 10.1). e5 ilk 5'e bile almadı. Sebep tablo gürültüsü değil, kısa chunk'ın e5 vektöründe seyrelmesi (önceki varsayımımız yanlıştı).
- İkinci çalıştırmada model sadece "bulamadım" demedi, **"Rehberde ... bir sayı belirtilmemiştir"** diye yanlış bir yokluk iddiası yazdı. Rehber tek form diyor. Bankacılıkta "yok" demek yanlışsa, "bulamadım" demekten daha zararlı.
- Ayrıca atıf yaptığı [4] ve [5] kaynakları kaynaklı ama sorunun konusu dışında.
- Aday çözüm: hibrit arama (BM25 + e5). Kanıt tek soru. Tüm 33 soruyu bozmaması ve #17'yi düzeltmesi **ölçülmeden** karar verilmez.

### 2. #2: kaynağa sadık olmayan yorum (otomatik ölçü yakalamadı)
- Cevap: Rehber "bu tür bir durumun yalnızca parasal işlem içermediği için bildirime konu olabileceğini ve ... (H) bölümünde belirtilmesi gerektiğini" söylüyor [4].
- Kaynak [4] şunu söylüyor: parasal değer içermeyen ve bildirime gerekçe olan hususlar (örneğin kiralık kasa ziyaretleri) formun açıklama (H) bölümünde belirtilir, şüpheli işlem bilgileri alanı boş bırakılır. "Yalnızca ... için bildirime konu olabilir" kaynakta **yok**, model yanlış yorumladı.
- Atıf var, atıf yapılan chunk konuyla ilgili, bu yüzden "Dayanaklı" ✓ çıktı. Bu bir **yeni hata türü**: `CEVAP_KAYNAGA_SADIK_DEGIL`. Cümle kaynakla çelişmiyor değil ama kaynakta olmayan bir neden bağlıyor.
- Aynı soru önceki çalıştırmada doğru yanıtlanmıştı. Model çıktısı çalıştırmadan çalıştırmaya değişiyor, tek çalıştırma yetmez.

### 3. Gereksiz ya da tekrar eden "Rehberde bu bilgiyi bulamadım."
- #1: iki çalıştırmada da "gerekçe yok" cümlesinin ardından aynı anlamda sabit cümle ekleniyor (tekrar).
- #17: yanlış yokluk iddiasının ardından da ekleniyor.
- Sebep: `rag_cevap.py` kural 2'yi `BULAMADIM` sabit cümlesine bağladık, cümle hangi ayrıntının eksik olduğunu söylemiyor.
- Aday çözüm: "eksik ayrıntıyı adıyla belirt" ve "kaynakta yazmayan bir nedeni yorum olarak ekleme" kuralları. Değişiklik yapılırsa 7/7 + held-out + taze + değerlendirme tablosu birlikte tekrar ölçülür, her biri iki çalıştırma.

### 4. Küçük gözlemler
- #9: ilk cümle ("en fazla üç şüphe kategorisi seçilebilir") atıfsız, bilgi kaynakta var.
- #18: "yani 3 numaralı bildirimde önceki referans olarak 2 yazılmaz" kaynaktaki örnekten çıkarılmış bir sonuç, metinde aynen yok.
- #31, #32, #33 (taze cevapsız): doğru reddetti. #32'deki "saklama" tuzağı (vergi defteri bağlamı) çalışmadı, model tuzağa düşmedi.

### 5. Chunk metin kalitesi: PDF'ten gelen kelime bölünmeleri
"bu lunulduğunu", "o luşturulacak", "kate gorisi", "konus unu", "Tab losu", "mahiy etindeki". pypdf çıkarma kusuru. #17'nin sebebi değil. Diğer aramalara etkisi ölçülmedi.

### 6. Chunk sayfa metadatası yanlıştı: DÜZELTİLDİ (kaynak sayfası bilgisi artık PDF ile doğrulanıyor)
- `chunklama.py` kaynak satırları `(sayfa, satır)` olarak açıyor ama `birimlere_ayir` birimin sadece **ilk satırının sayfasını** tutuyor. Sayfa sınırını aşan uzun bir paragraf bölününce bütün alt chunk'lar ilk satırın sayfasını alıyor.
- Kanıt (PDF sayfaları pypdf ile ayrı ayrı arandı):
  - "dördüncü fıkrasında" (Hazine ve Maliye paragrafı): PDF sayfa **6**, chunk metadatası **5**.
  - "resmî internet sitesi": PDF sayfa **6**, chunk metadatası **5**.
  - "gönderilmemesi" (stok mal varlığı): PDF sayfa **8**, chunk metadatası **7**.
- Etkisi: `policy_sources[].sayfa` (API) ve CSV'deki `kaynak_sayfalari` bazı chunk'lar için 1 sayfa geri. Bankacılık bağlamında yanlış kaynak sayfası göstermek, atıf güvenini düşürür.
- **Düzeltme (`src/chunklama.py`):** birim artık satır başına sayfa listesi (`sayfalar`) taşıyor. Uzun birim bölünürken her parça kendi satırlarının sayfalarını alıyor (overlap ve tekrar eden kod satırı dahil), chunk `page` = en küçük, `page_end` = en büyük sayfa.
- **Doğrulama:**
  - 257 chunk'ın **metni, id'si, kodları, bölümü birebir aynı** (düzeltme öncesi/sonrası karşılaştırıldı). Embedding indeksi hash'i metinden hesaplandığı için yeniden hesaplanmaz.
  - 81 chunk'ın sayfa bilgisi değişti.
  - PDF'e göre sayfası uyuşmayan chunk: düzeltmeden önce 123 satır-tabanlı uyuşmazlık (çok sayıda chunk), düzeltmeden sonra **0**.
  - `tests/chunk_kontrol.py` artık her chunk'ın sayfasını PDF'le karşılaştırıyor ve üç bilinen cevabı sabitliyor ("dördüncü fıkrasında" → 6, "resmî internet sitesi" → 6, "tek bir ŞİB" → 9). Eski koda karşı bu kontroller **FAIL** veriyor (13/17), yeni kodla 17/17.
- Sayfa sınırını aşan chunk artık "7-8" gibi aralıkla gösteriliyor (LLM'e giden kaynak başlığında zaten aralık yazıyordu). API `policy_sources[].sayfa` alanı chunk'ın **başladığı** sayfayı verir.

## Soru bazlı kısa sonuç

| # | Sonuç | Not |
|---|---|---|
| 1 | ✓ | tekrar eden "bulamadım" (bulgu 3) |
| 2 | ✗ elle | kaynağa sadık olmayan yorum (bulgu 2) |
| 3–16 (#5–7 cevapsız hariç) | ✓ | #9 ilk cümle atıfsız (bulgu 4) |
| 5, 6, 7 | ✓ | doğru reddetti |
| 17 | ✗ | arama hatası + yanlış yokluk iddiası (bulgu 1) |
| 18 | ✓ | küçük çıkarım (bulgu 4) |
| 19 | ✓ | |
| 20–22 | ✓ | doğru reddetti |
| 23–30 | ✓ | taze cevaplı sorular |
| 31–33 | ✓ | taze cevapsız sorular, doğru reddetti |

## Sonraki adımlar (her biri 33 soruyla, iki çalıştırmada ölçülerek)

1. Cevapsız soruları PDF'te Ctrl+F ile doğrula (Poyraz).
2. Kural 2 + sadakat kuralı: "eksik ayrıntıyı adıyla belirt, kaynakta olmayanı yorumlama" (bulgu 2, 3).
3. Hibrit arama deneyi (BM25 + e5), taze sette de karşılaştır (bulgu 1).
4. ~~Chunk sayfa metadatası düzeltmesi + PDF'ten sayfa doğrulama testi (bulgu 6).~~ **Yapıldı.**
5. Hata türü tablosuna `CEVAP_KAYNAGA_SADIK_DEGIL` ekle. Otomatik tespiti zor, gerekirse ikinci bir LLM "hakem" çağrısı (maliyet/değer ölçülerek).
