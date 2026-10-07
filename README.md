# Banking Risk AI

Bankacılık işlemleri için kural tabanlı bir risk skoru üreten bir proje geliştiriyorum. Risk motoru her işleme 0-100 arası bir skor, bir etiket (suspicious / normal) ve skorun nedenlerini üretiyor. Bunun üzerine ileride RAG (politika dokümanlarından doğal dilde açıklama) ve bir agent katmanı eklemeyi planlıyorum.

## Veri
Sentetik veri kullanıyorum (600 müşteri, hesaplar, 120.000 işlem), gerçek banka verisi yok. Veri dosyası repo'da bulunmuyor, `src/veri_uret.py` ile üretiliyor. Not: veri yeniden üretilirse sonuç sayıları değişebilir.

## Kurulum
pip install -r requirements.txt
python src/veri_uret.py

## Kullanım
python src/risk_engine.py

Her işlem için tetiklenen kuralların puanları toplanır (başarısız işlem, riskli kanal, yurtdışı, segmentine göre anormal tutar). Skor 50 ve üstüyse işlem suspicious olur.

## Mimari
Detaylar için docs/ARCHITECTURE.md