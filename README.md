# Banking Risk AI

Bankacılık işlemleri için **kural tabanlı risk motoru + RAG + araç kullanan bir inceleme ajanı** denemesi. Bir **proof-of-concept**: çalışıyor ve test edildi, ama gerçek bir bankada kullanıma hazır değil (bkz. [Sınırlılıklar](#sınırlılıklar)).

Ne yapar:

1. **Risk motoru:** her işleme 0-100 skor, `normal` / `suspicious` etiketi ve hangi kuralın tetiklendiğini üretir. Deterministiktir, LLM kullanmaz.
2. **RAG:** MASAK şüpheli işlem bildirim rehberinden, tetiklenen kurala ilgili kısımları bulur ve Claude'a "sadece bu kaynaklara dayanarak, atıf yaparak açıkla" dedirtir. Rehberde yoksa "bulamadım" der.
3. **İnceleme ajanı:** "Müşteri 1'i incele" isteğinde Claude dört araçla (müşteri bilgisi, işlem geçmişi, risk skoru, rehber arama) veriyi toplar ve 5 başlıklı bir rapor yazar. Kararı analist verir, ajan hüküm vermez.
4. **API (FastAPI):** hepsi HTTP üzerinden. Claude çökse bile `/investigate` veriyi döndürür (zarif bozulma).

Detaylı mimari ve tasarım kararları: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Veri

Sentetik: 600 müşteri, hesaplar, 120.000 işlem (`seed=42`). Gerçek banka verisi yok, gerçek fraud etiketi de yok. Veri dosyası repoda bulunmuyor, `src/veri_uret.py` ile üretiliyor.

> **Uyarı:** `veri_uret.py` mevcut `data/bank_ops_risk_dataset.xlsx` dosyasının üzerine yazar. Yeniden üretirsen sonuç sayıları değişebilir ve `data/*.pkl` önbelleklerini silmen gerekir.

Rehber PDF'i de repoda yok. MASAK'ın şüpheli işlem bildirim rehberini kendin indirip `documents/masak_rehber.pdf` olarak koymalısın.

## Kurulum

Gereksinim: Python 3.14 ile geliştirildi ve denendi (başka sürümleri denemedim). Komutlar Windows PowerShell için.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python src\veri_uret.py                 # data\bank_ops_risk_dataset.xlsx üretir
# documents\masak_rehber.pdf dosyasını elle koy
```

Proje köküne `.env` dosyası aç (git'e girmez):

```text
ANTHROPIC_API_KEY=buraya_kendi_anahtarin
```

İlk kullanımda neler olur:
- **e5 embedding modeli** (`intfloat/multilingual-e5-large`, ~2,2 GB) indirilir. İlk açılışta 6-10 sn yükleme sürer.
- PDF'ten 257 parça (chunk) çıkarılıp `data/chunk_indeksi_e5.npz` olarak kaydedilir. Sonraki açılışlarda içerik değişmediyse yeniden hesaplanmaz.
- Risk motoru için segment istatistikleri `data/api_onbellek.pkl` dosyasına yazılır. Veriyi yeniden üretirsen bu dosyayı sil, içerik doğrulaması yapmıyor.

## Çalıştırma

```powershell
uvicorn api:app --app-dir src
```

`--app-dir src` şart: kod `from risk_engine import ...` biçiminde, düz modül adlarıyla import ediyor. Sunucu açılırken Excel tabloları ve e5 modeli önceden yüklenir (`RAG_ISITMA=0` ile kapatılır). Etkileşimli dokümantasyon: `http://127.0.0.1:8000/docs`.

| Uç nokta | Ne yapar | Claude kullanır mı |
|---|---|---|
| `POST /predict-risk` | İşlem → skor, etiket, nedenler, kural kimlikleri | Hayır |
| `POST /explain-risk` | Aynı + rehberden atıflı açıklama | Evet (kural tetiklenmediyse hayır) |
| `POST /investigate` | Müşteri incelemesi (aşağıda) | Evet |
| `GET /onbellek-durumu` | Önbellek isabet/ıska sayıları | Hayır |

## Demolar

Üç demo, sırayla. Sunucu açıkken ikinci bir PowerShell'de çalıştır. Türkçe karakterlerin düzgün görünmesi için cevabı UTF-8 olarak çözen satırlar kullanıldı.

**1) Normal işlem** (hiçbir kural tetiklenmez, Claude çağrılmaz):

```powershell
$p = '{"account_id":1,"amount":100,"status":"OK","channel":"ATM","is_international":0}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/predict-risk -ContentType "application/json" -Body $p | ConvertTo-Json
```

Beklenen: `risk_score: 0`, `risk_label: normal`, `reasons: []`.

**2) Yüksek riskli işlem:**

```powershell
$p = '{"account_id":2,"amount":14717,"status":"OK","channel":"Web","is_international":1}'
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/predict-risk -ContentType "application/json" -Body $p | ConvertTo-Json
```

Beklenen: `risk_score: 70`, `suspicious`, kurallar `RISKY_CHANNEL`, `INTERNATIONAL`, `AMOUNT_ANOMALY`. Aynı gövdeyi `/explain-risk`'e atarsan Claude rehberden atıflı açıklama yazar.

**3) Ajan müşteriyi inceliyor** (gerçek Claude çağrısı, yaklaşık 14-16 sn):

```powershell
$r = Invoke-WebRequest -Method Post -Uri http://127.0.0.1:8000/investigate -ContentType "application/json" -Body '{"customer_id": 1}' -UseBasicParsing
$j = [Text.Encoding]::UTF8.GetString($r.RawContentStream.ToArray()) | ConvertFrom-Json
$j.rapor
$j.rapor_kaynagi; $j.onbellekten; $j.sure_ms
$j.dogrulama | Format-Table kontrol, gecti, detay -AutoSize
```

Cevap alanları: müşteri özeti, en riskli 3 işlem (veri katmanından, Claude'dan bağımsız), `rapor` (5 başlık: Müşteri özeti, Öne çıkan işlemler, Rehber dayanağı, Doğrulanamayanlar, Öneri), `rapor_kaynagi`, `dogrulama` (otomatik kaba kontroller), `uyarilar`, `iz_ozeti`. İkinci çağrı önbellekten gelir (~0,1 sn); `?yenile=true` önbelleği atlar.

**Zarif bozulma:** `rapor_kaynagi` üç değerden biri olur.
- `ajan`: ajan raporu.
- `aciklama`: ajan başarısız olursa en riskli işlemin kural tabanlı açıklaması.
- `yok`: o da başarısız olursa yalnız veri. Müşteri varsa yanıt her zaman 200, yoksa 404.

Denemek için sunucuyu `$env:ANTHROPIC_BASE_URL = "http://127.0.0.1:9"` ile başlat (Claude erişilemez olur).

## Testler

Her test dosyası `python tests\<ad>.py` ile çalışır, sonunda `N/N kontrol geçti` yazar.

**Çevrimdışı ve ücretsiz** (sahte Claude / sahte rehber, gerçek araçlar):

| Dosya | Kontrol |
|---|---|
| `agent_testi.py` | 50 |
| `agent_trace_testi.py` | 58 |
| `banking_tools_testi.py` | 65 |
| `tool_calling_testi.py` | 39 |
| `investigation_testi.py` | 98 |
| `investigate_testi.py` | 60 |
| `risk_rag_testi.py` | 26 |
| `rag_degerlendirme_testi.py` | 21 |

**Gerçek Claude çağırır (küçük maliyet):** `held_out_testi.py`, `rag_cevap_testi.py`, `inceleme_degerlendirme.py` (ajan mini değerlendirmesi), `rag_degerlendirme.py`.

**Diğer:** `arama_testi.py` yerel e5 modelini kullanır (Claude yok). `api_istek.py` çalışan sunucuya 7 istek atar.

Bir testin geçmesi, ilgili davranışın doğru olduğu anlamına gelir. Gerçek Claude'un cevap kalitesini sahte istemcili testler ölçmez. Onu yukarıdaki gerçek-Claude testleri ve canlı denemeler ölçer.

## Ölçümler

**RAG** (`docs/RAG_EVAL.md`, 33 soru, otomatik üretildi):

| Küme | Cevaplı: arama / cevap | Cevapsız: doğru reddetme |
|---|---|---|
| Ayar seti (ayar yapıldı, skor şişik) | 4/4, 4/4 | 3/3 |
| Held-out (ayar yapılmadı) | 11/12, 11/12 | 3/3 |
| Taze (hiç ayar görmedi) | 8/8, 8/8 | 3/3 |

Küme boyutları küçük, güven aralığı geniş. "Dayanaklı" otomatik bir vekil ölçüdür (atıf var ve atıf yapılan parça beklenen bilgiyi içeriyor), cümle cümle doğrulama değildir.

**İnceleme ajanı** (gerçek koşular, tek müşteri üzerinde):

| Ölçüm | Değer |
|---|---|
| Süre | 11-27 sn (müşteri 1: 13,7 ve 15,9 sn) |
| Token | yaklaşık 15-18k girdi + 2,4-2,8k çıktı (aynı görevde değişir) |
| Eksik/kapsam dışı görev | 3,5-7k token |

### Maliyet

Model: `claude-haiku-5-5`. Üçüncü taraf kaynaklara göre (resmi fiyat sayfasını doğrudan açamadım, kullanmadan önce [resmi sayfadan](https://platform.claude.com/docs/en/about-claude/pricing) teyit et) fiyat 100K tokene kadar olan promptlarda 1M girdi tokeni başına 0,10 USD, 1M çıktı tokeni başına 0,50 USD.

Ölçtüğüm iki müşteri-1 incelemesi (15.087 girdi + 2.807 çıktı ve 14.683 girdi + 2.429 çıktı) bu fiyatla yaklaşık **0,003 USD** tutuyor. Çıktı tokenlerine düşünme (thinking) tokenleri de dahil. Önbellekten gelen çağrı Claude'a gitmediği için ücretsiz. İz dosyalarında maliyeti görmek için çalıştırmadan önce:

```powershell
$env:GIRDI_FIYAT_1M = "0.10"; $env:CIKTI_FIYAT_1M = "0.50"
```

## Proje yapısı

```text
src/            kaynak kod (düz modüller, katman haritası docs/ARCHITECTURE.md'de)
  tools/        ajanın kullandığı araçlar ve veri erişimi
tests/          testler ve değerlendirme betikleri
docs/           mimari, RAG değerlendirmesi, API sözleşmesi, plan, öğrenme notları
data/           üretilen veri ve önbellekler (git'te yok)
documents/      rehber PDF'i (git'te yok)
```

`src/embedding_demo.py` bir öğrenme demosudur (embedding benzerliği), sistemin parçası değildir. Yürütme izleri `data/izler/` altına yazılır ve **müşteri verisi içerir**, bu yüzden `.gitignore`'dadır.

## Sınırlılıklar

- **Veri sentetik, kurallar benim varsayımım.** Gerçek fraud etiketi olmadığı için risk motorunun doğruluğu (precision/recall) ölçülemiyor. Skor "bu kurallar tetiklendi" demektir, "bu işlem dolandırıcılık" değil.
- **Kurallar basit:** `INTERNATIONAL` kuralı ülkeyi bilmiyor (sadece bayrak), `AMOUNT_ANOMALY` müşterinin gelirine değil segment ortalamasına göre z-skoru kullanıyor.
- **Kural–politika eşleşmesi kaba.** Rehber `RISKY_CHANNEL` gibi kuralların tanımını içermiyor. Eşleşme sorgu metinleriyle (`KURAL_SORGULARI`) yaklaşık kuruluyor. Ajan kendi arama sorgusunu yazdığı için bulunan rehber kanıtı çalıştırmadan çalıştırmaya değişiyor ve bazen işlemle pek ilgisiz çıkıyor.
- **RAG değerlendirmesi küçük.** Ayar seti şişik, held-out ve taze kümeler küçük (12 ve 8 cevaplı soru), tek bir hatalı örnek oranı belirgin değiştirir. Vektör veritabanı (Chroma/FAISS) denenmedi, numpy + `.npz` kullanılıyor, karşılaştırma yapılmadı.
- **Ajan değerlendirmesi küçük** (5 senaryo, birkaç tekrar). Rapor kontrolleri (`uydurma_islem_yok`, `atif_gecerli`, `hukum_yok` vb.) kaba kural tabanlı ipuçlarıdır, kanıt değildir. Örneğin ülke kodu gibi sayısal olmayan iddiaları denetlemez.
- **Güvenlik:** kimlik doğrulama yok, KVKK/mevzuat değerlendirmesi yapılmadı. Müşteri verisi içeren iz dosyaları diskte duruyor.
- **Süre garantisi sınırlı.** Her Claude isteği 60 sn ile sınırlı (2 yeniden deneme) ve ajanın toplam süresi 120 sn ile sınırlı. Ajan başarısız olduktan sonra çalışan açıklama basamağının ayrı bir toplam süre sınırı yok, yani Claude yavaşladığında (bağlantı açık ama cevap gelmiyor) en kötü durum gecikmesi belirsiz. Claude'a hiç ulaşılamayan senaryoda ölçtüğüm toplam süre 15,8 sn.
- **Önbellek** bellekte tutulur: sunucu yeniden başlayınca silinir, birden çok süreçte paylaşılmaz, aynı anda gelen iki aynı istek ikisi de Claude'a gider.
- **Model davranışı değişebilir.** Aynı girdiye her seferinde aynı cevap garanti değil (kullanılan modelde `temperature` desteklenmiyor).

## Gelecek çalışma

- `INTERNATIONAL` kuralına karşı ülke bilgisi, `AMOUNT_ANOMALY`'de gelirle karşılaştırma.
- Rehber kanıtını deterministik yapmak: ajanın kendi sorgusu yerine `KURAL_SORGULARI` (ölçerek karşılaştırılmalı), düşük riskli müşterilerde gereksiz rehber aramasını atlamak.
- Daha büyük ve dışarıdan hazırlanmış soru seti, vektör veritabanı karşılaştırması.
- Sayısal iddiaları (tutar, skor) araç sonuçlarıyla karşılaştıran kontrol.
- Kimlik doğrulama, iz dosyalarının saklama politikası, toplam süre sınırının her basamağa yayılması.

## Nasıl geliştirildi

Bu proje Claude ile eşli çalışılarak geliştirildi: kodun büyük kısmı birlikte yazıldı ve test edildi; her adımı çalıştırıp çıktısını inceledim. Hangi parçaları kendim yazdığımı/değiştirdiğimi ve anladığımı `docs/Ogrenme_Notlari.md` dosyasında kendi cümlelerimle anlatıyorum.
