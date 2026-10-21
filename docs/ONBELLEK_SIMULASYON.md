# Açıklama önbelleği simülasyonu

Üretildi: `python tests\onbellek_simulasyon.py`. Her işlem bir /explain-risk isteği sayıldı (Claude yok). Üst sınırdır, gerçek isabet oranı değildir (bkz. betiğin başı).

## Kural tetikleyen tüm işlemler (81447)

| Anahtar | Farklı anahtar (= Claude çağrısı) | İstek | İsabet üst sınırı | Tahmini USD |
|---|---|---|---|---|
| A plan (etiket+rule_ids) | 14 | 81447 | %100.0 | 0.0146 |
| B Gün 19 (+skor+z'li neden) | 390 | 81447 | %99.5 | 0.4056 |
| C şimdiki (+skor+z'siz neden) | 22 | 81447 | %100.0 | 0.0229 |

## Yalnız suspicious (401)

| Anahtar | Farklı anahtar (= Claude çağrısı) | İstek | İsabet üst sınırı | Tahmini USD |
|---|---|---|---|---|
| A plan (etiket+rule_ids) | 7 | 401 | %98.3 | 0.0073 |
| B Gün 19 (+skor+z'li neden) | 145 | 401 | %63.8 | 0.1508 |
| C şimdiki (+skor+z'siz neden) | 11 | 401 | %97.3 | 0.0114 |

USD sütunu yalnız `RAG_CAGRI_USD` (RAG'li bir açıklamanın tahmini maliyeti) verilirse dolar gösterir.
