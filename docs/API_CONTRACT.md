# API Sözleşmesi (Gün 4)

Bu dosya, risk motorunu dışarıya açacak API'nin nasıl konuşacağını anlatıyor. Kod yazmadan önce sözleşmeyi yazdım, böylece Gün 5'te FastAPI'de neyi kuracağımı biliyorum.

## Temel fikir

- **Request**, fonksiyonun parametreleri gibi: işlemin bilgileri.
- **Response**, fonksiyonun return değeri gibi: skor, etiket, nedenler.
- Veri **JSON** olarak gidip geliyor, çünkü JSON Python sözlüğüne çok benziyor ve her dil okuyabiliyor.
- Veri paketle gittiği için POST kullanıyorum. GET'te bilgi sadece adreste olur, işlem bilgisini adrese yazmak hem düzensiz hem güvensiz.

## Endpoint

`POST /predict-risk`

## İstek (request)

```json
{
  "account_id": 1,
  "amount": 950000,
  "status": "OK",
  "channel": "Web",
  "is_international": 1
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `account_id` | sayı | Hesap numarası. Müşteri ve segment bundan bulunur |
| `amount` | sayı | İşlem tutarı |
| `status` | metin | `OK` veya `FAILED` |
| `channel` | metin | `Web`, `Mobile`, `ATM` veya `Branch` |
| `is_international` | sayı | 0 veya 1 |

`amount_z` istekte **yok**. Onu sunucu hesaplar.

## Cevap (response), 200

```json
{
  "risk_score": 70,
  "risk_label": "suspicious",
  "reasons": [
    "İşlem riskli kanaldan yapılmış (+15)",
    "İşlem yurtdışı (+25)",
    "Tutar anomalisi (Z-Score yüksek) (+30)"
  ]
}
```

| Alan | Tip | Açıklama |
|---|---|---|
| `risk_score` | sayı | Tetiklenen kuralların puan toplamı, en fazla 100 |
| `risk_label` | metin | Skor 50 ve üstüyse `suspicious`, değilse `normal` |
| `reasons` | liste | Tetiklenen her kuralın metni, boş olabilir |

Bu üç alan `RiskEngine.calculate()` metodunun döndüğü şeyle aynı.

## Hata durumları

| Durum | Kod | Ne zaman |
|---|---|---|
| Hesap bulunamadı | 404 | Paket doğru ama `account_id` sistemde yok |
| Geçersiz paket | 422 | Alan eksik, ya da tip yanlış (`amount` sayı değil) |
| Sunucu hatası | 500 | Sunucunun kendi kodu çöktü, istemcinin suçu değil |

Hata cevabı örneği (404):

```json
{ "detail": "account_id 999999 bulunamadı" }
```

## Sunucu içeride ne yapıyor

1. Paketi doğrular (eksik alan, yanlış tip varsa 422).
2. `account_id` ile hesabı, hesapla müşteriyi, müşteriyle segmenti bulur (bulamazsa 404).
3. O segmentin ortalama ve std'sini kullanıp `amount_z` hesaplar.
4. `RiskEngine.calculate()` çağrılır, sonuç JSON olarak döner.

Veri ve segment ortalama/std tablosu sunucu açılırken **bir kez** yüklenir. Excel okumak yaklaşık bir dakika sürüyor, her istekte okunamaz.

## Kararlar ve nedenleri

- **`amount_z`'yi client göndermiyor.** Her client kendi hesabıyla gönderirse aynı işlem farklı skor alır. Skoru hesaplayan tek yer sunucu olmalı.
- **Segment yerine `account_id` kullanıyorum.** Client yanlış segment gönderirse z değişirdi. `account_id` ile sunucu segmenti kendi verisinden bulur. Ayrıca gerçek bir işlem kaydında hesap numarası zaten vardır.
- **`RiskEngine`'e dokunmuyorum.** `amount_z`'yi API katmanı hesaplayıp satırın içine koyar.

## Bilinen kısıtlar

- Motorda `status` için `ERROR` değeri de kontrol ediliyor, ama veride sadece `OK` ve `FAILED` var. Zararsız.
- Sunucu verisi açılışta yüklendiği için veri değişirse sunucuyu yeniden başlatmak gerekir.
- Veri sentetik, gerçek bir kimlik doğrulama (API anahtarı) şu an yok. Gerçek bankada olması şart.
