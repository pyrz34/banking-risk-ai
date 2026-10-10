# Mimari (Gün 1)

Bu dosya, risk engine projemin şu an nasıl çalıştığını anlatıyor. Planda olup henüz yapmadığım şeyleri de açıkça yazdım.

## Şu anki akış

```text
veri_uret.py
   ↓  sentetik veri üretir
bank_ops_risk_dataset.xlsx   [customers, accounts, transactions]
   ↓
risk_engine.py
   ↓  pandas ile transactions sheet'ini okur
risk_skoru_hesaplama(row)    → her işlem için 0-100 skor
   ↓
skor >= 50 olanlar şüpheli
   ↓
supheli_islemler.xlsx
```

## Hangi dosya ne yapıyor

- **veri_uret.py**: 600 müşteri, hesapları ve 120.000 işlem üretiyor (seed=42), hepsini `bank_ops_risk_dataset.xlsx`'e yazıyor.
- **risk_engine.py**: `transactions` sheet'ini okuyor, her işleme puan veriyor, skoru 50 ve üstü olanları `supheli_islemler.xlsx`'e kaydediyor.
- **agent_audit.py**: şu an boş.

## Sorulara kendi cevaplarım

**Risk engine nereden veri alıyor?**
`bank_ops_risk_dataset.xlsx` dosyasındaki `transactions` sheet'ini pandas ile okuyor. Veriyi `veri_uret.py` üretmişti.

**Hangi feature'ları kullanıyor?**
Transactions tablosunda `txn_id, account_id, txn_time, channel, txn_type, amount, merchant_category, is_international, counterparty_country, status` kolonları var. Ama risk engine bunların sadece 4 tanesini kullanıyor: `status`, `channel`, `is_international`, `amount`. Geri kalanı (txn_time, merchant_category vb.) şu an skora girmiyor.
(Not: Her satır bir işlem (transaction), kolonlar ise feature. Feature, skoru hesaplarken kullandığımız bilgi. Yeni feature türetmeye (ör. "gece işlemi mi?") feature engineering deniyor, şu an yapmıyorum.)

**Score nasıl oluşuyor?**
Belirlediğim kurallara göre. Her kural sağlanırsa puan ekleniyor, toplam en fazla 100:

| Koşul | Puan |
|---|---|
| status FAILED veya ERROR | +30 |
| channel `mobile_unverified` veya `web` | +15 |
| is_international == 1 | +25 |
| amount > 5000 | +30 |

**Label nasıl oluşuyor?**
Şu an ayrı bir label kolonu yok. Sadece eşik var: skor 50 veya üstüyse işlem "şüpheli" listesine alınıyor. İleride buna `normal / suspicious` gibi gerçek bir label kolonu ekleyeceğim.

**Reasons nasıl oluşuyor?**
Şu an oluşmuyor, kod sadece puanları topluyor, hangi kuralın tetiklendiğini kaydetmiyor. Reasons, "bu işlem neden bu skoru aldı" demek, ör. "başarısız işlem (+30), yurtdışı (+25)". Hangi kural tetiklenince listeye bir açıklama ekleyerek üreteceğim (Gün 2c). İleride LLM bu reasons'ı doğal dile çevirecek.

## Eşik mantığı

Eşik 50. Tek başına hiçbir kural şüpheli yapmıyor, en az iki sinyal birleşmeli (başarısız + yurtdışı = 55, yurtdışı + yüksek tutar = 55, başarısız + yüksek tutar = 60). Kanal zayıf bir sinyal, tek başına bir şey ifade etmediği için puanı düşük.

## Baseline v1

- 120.000 işlem, **2893 şüpheli** (eşik 50)
- Referans dosya: `baseline.xlsx`
- Gün 2'de class'a çevirince sayı aynı çıkmalı.
- `veri_uret.py`'yi tekrar çalıştırmıyorum (veri değişirse karşılaştırma bozulur).

## Kodda olmayanlar

- Feature engineering (gece işlemi, işlem sıklığı vb.)
- Label kolonu
- Reasons
- `customers` ve `accounts` sheet'leri kullanılmıyor (müşteri segmenti skora girmiyor)

## Bilinen sorunlar

1. **Kanal kuralı**: Kod `mobile_unverified` arıyor ama veride yok (veride `Mobile` var). Pratikte sadece `web` puan alıyor.
2. **Z-score yorumu yanıltıcı**: Yorumda Z-Score yazıyor ama kod sabit `amount > 5000` kullanıyor. Corporate müşterilerde tipik işlem zaten bu değerin üstünde. Z-score segmente göre hesaplanmalı, sadece yüksek taraf (z > eşik) risk sayılmalı.
3. **Kod import edilince direkt çalışıyor**: Fonksiyon/class yapısı yok.
4. **Veri sentetik ve rastgele**: Gerçek fraud etiketi yok, kurallar benim varsayımım.

## Açık işler

- [ ] Gün 2a: class'a çevir, baseline v1 ile aynı sonucu (2893) doğrula, commit
- [ ] Gün 2b: segmenti join ile ekle, sabit 5000 yerine z-score koy, baseline v2, ayrı commit
- [ ] Gün 2c: kanal listesini veriye göre düzelt, label + reasons ekle
- [ ] Gün 3: `.env`, `.gitignore`, `requirements.txt`
- [ ] Gün 5: LLM seçimi ve stajda veri paylaşımı konusunu mentora sor
## Gün 4: API kavramları

- **Request:** İstemcinin sunucuya gönderdiği istek. Adres ve paketten oluşur.
- **Response:** Sunucunun istemciye döndüğü cevap.
- **Neden POST:** Risk tahmini için işlem bilgilerini paket olarak göndermem gerekiyor. GET'te bilgi sadece adreste olur.
- **Neden JSON:** Python sözlüğüne benziyor, her dil ve sistem aynı biçimi anlıyor, ortak dil gibi.
- **Neden sözleşme:** İstek ve cevabın biçimini, hata kodlarını kod yazmadan önce sabitledim. Birden fazla ekip aynı API'ye bağlanınca standart bir pratik. Benim işime yaradığı yer `amount_z` sorununu koddan önce fark etmem oldu (`docs/API_CONTRACT.md`).

## Gün 5: API (FastAPI)

```text
istemci --POST /predict-risk (JSON)--> api.py
   ↓ TransactionRequest ile doğrula (hatalıysa 422)
   ↓ account_id -> segment bul (yoksa 404)
   ↓ segment ortalama/std ile amount_z hesapla
   ↓ RiskEngine.calculate() -> risk_score, risk_label, reasons
istemci <--200 + JSON-- RiskResponse
```

- Segment tablosu `data/api_onbellek.pkl` dosyasında saklanıyor (ilk açılışta Excel'den üretilir, sonra hızlı). Veri yeniden üretilirse bu dosyayı sil.
- `tests/api_istek.py`: sunucuya 7 istek atıp 200/404/422 kontrol ediyor, 7/7 geçiyor.
- Çalıştırma: `python -m uvicorn api:app --reload --app-dir src`

## Açık işler (güncel)

- [x] Gün 4: API sözleşmesi
- [x] Gün 5: FastAPI endpoint + istemci testi
- [ ] Gün 5: mentora LLM seçimi ve veri paylaşımı konusunu sor
- [ ] Gün 12: `_triggered_rules`'a `rule_id` ekle (cache anahtarı için)
- [ ] Gün 13: LLM cache + maliyet deneyi (cache kapalı/açık)
- [ ] İsteğe bağlı: `log` ile z-score, yurtdışı + yüksek tutar bonusu
- [ ] Sonra: projeye özel sanal ortam (`.venv`), şu an `base` kullanıyorum

- [ ] API'ye LLM açıklamasını bağlarken: `reasons` boşsa LLM'i çağırma, sabit metin dön (model boş girdide kendi iç yorumunu sızdırıyor)
- [ ] Gün 13: cache ayrıca cevap tutarlılığı sağlıyor (bu modelde `temperature` desteklenmiyor, aynı girdiye aynı cevap garanti değil)
- [ ] Model seçimi: `MODEL` şu an Haiku 5.5. Maliyet deneyinde Sonnet ile cevap kalitesi karşılaştırması yap
## Gün 6: LLM temelleri

`src/llm_explain.py`: risk sonucunu (skor, etiket, nedenler) Claude'a verip 2-3 cümlelik Türkçe açıklama yazdırıyor. Model: Haiku 5.5 (maliyet nedeniyle). Anahtar `.env` dosyasında, git'e girmiyor.

- **Token:** Örnek çağrıda girdi 215, çıktı 105 token. Maliyet bu sayılardan çıkıyor.
- **System / user mesajı:** System mesajı modelin rolü ve kuralları (her çağrıda aynı), user mesajı işleme göre değişen kısım.
- **Temperature:** Bu modelde desteklenmiyor (API 400 döndü), aynı girdiye aynı cümleler gelmiyor. Cevabı sabitlemenin yolu cache.
- **Cevap blok listesi:** Cevap tek metin değil, bloklardan oluşuyor (düşünme bloğu olabiliyor). Sadece `type == "text"` olanları birleştiriyorum.
- **Hallucination testi:** `reasons` boşken model neden uydurmadı, ama kendi iç yorumunu yazdı ("kullanıcı boş bırakmış"). Boş nedenlerde LLM'i çağırmayacağız, sabit metin dönecek.
- **LLM henüz API'ye bağlı değil.** Entegrasyon Gün 12'de.

## Gün 7: Embeddings

`src/embedding_demo.py`: cümleleri vektöre çeviriyor (fastembed, çok dilli MiniLM, 384 boyut, bilgisayarda çalışıyor) ve cosine similarity ile karşılaştırıyor. Anthropic'in kendi embedding modeli yok, bu yüzden yerel model kullanıyorum. Claude hâlâ cevabı yazan model.

Embedding, cümleyi anlamını temsil eden sayı listesine çevirir. RAG'de buna ihtiyaç var çünkü sorudaki kelimelerle belgedeki kelimeler çoğu zaman aynı olmuyor. Soruyu ve belge parçalarını vektöre çevirip anlamca en yakın parçaları buluyorum, sonra bu parçaları LLM'e verip cevap yazdırıyorum. Embedding bulur, Claude yazar.

| Çift | Benzerlik |
|---|---|
| İngilizce ↔ Türkçe (aynı anlam) | 0.799 |
| İngilizce ↔ İngilizce (International / Cross-border) | 0.717 |
| Türkçe ↔ Cross-border | 0.756 |
| Herhangi biri ↔ kafeterya | -0.09 ile -0.04 |

- Model çok dilli, Türkçe ve İngilizce aynı anlamı eşliyor.
- **Küçük metin farkları benzerliği oynatıyor:** Cümlenin sonuna nokta eklemek 0.690'ı 0.717'ye çıkardı. Belge metni temizliği önemli (Gün 8'de PDF'ten gelen bozuk boşluk ve kırık kelimeler).
- 0.7 gibi kesin bir eşik yok, gerçek belgelerle Gün 10'da bakacağım.

## Açık işler (güncel)

- [x] Gün 6: LLM temelleri, `llm_explain.py`
- [x] Gün 7: Embeddings, `embedding_demo.py`
- [ ] Gün 8: PDF yükleme ve chunk'lama (belgeler: MASAK rehberi vb.)
- [ ] 🟡 Gün 9'dan ÖNCE: projeye özel `.venv` oluştur (base'de anthropic, fastembed kurulumları paket çatışması uyarısı verdi)
- [ ] LLM açıklamasını API'ye bağlarken: `reasons` boşsa LLM'i çağırma
- [ ] Gün 12: `_triggered_rules`'a `rule_id` ekle
- [ ] Gün 13: LLM cache ve maliyet deneyi (cache hem maliyet hem tutarlılık)
- [ ] Maliyet deneyinde Haiku ile Sonnet'in cevap kalitesini karşılaştır