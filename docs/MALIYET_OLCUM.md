# Maliyet ölçümü

Üretildi: `python tests\maliyet_olcum.py`. Örnek işlem: skor 70, kurallar RISKY_CHANNEL, INTERNATIONAL, AMOUNT_ANOMALY. Model: `claude-haiku-5-5`. Fiyat: girdi 0.1 / çıktı 0.5 USD (1M token).

| Yol | n | Girdi token (medyan, aralık) | Çıktı token (medyan, aralık) | Süre (medyan) | Tahmini USD (medyan) |
|---|---|---|---|---|---|
| RAG'siz açıklama | 3 | 369 (369-369) | 406 (231-507) | 2.5 sn | 0.000240 |
| RAG'li açıklama (/explain-risk) | 3 | 1974 (1974-1974) | 1691 (1404-2100) | 8.0 sn | 0.001043 |
| RAG'li açıklama, önbellekten | 3 | 0 (0-0) | 0 (0-0) | 0.02 ms | 0.000000 |
| Müşteri incelemesi (ajan), ıska | 1 | 14683 (14683-14683) | 2301 (2301-2301) | 17.8 sn | 0.002619 |
| Müşteri incelemesi (ajan), önbellekten | 1 | 0 (0-0) | 0 (0-0) | 45 ms | 0.000000 |

Notlar: RAG'siz ve RAG'li yolların sistem istemleri farklıdır (fark = rehber verisi + onu kullanma kuralları). Çıktı tokenlerine düşünme tokenleri dahildir. Tek işlem, az tekrar: büyüklük sırasıdır, ortalama değil. Önbellek isabet oranı gerçek trafik olmadan ölçülemez; burada yalnız bir isabetin maliyeti ölçüldü.
