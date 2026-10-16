# PLAN: Gün 13–20 (kalan iş)

Kaynak: kendi yol haritan (Gün 11–20 metinleri) + bizim konuşmalarda aldığımız kararlar.
Gün 1–10 metinlerini görmedim; Gün 1–12 "bitti" kabul edildi (Gün 9 Vector DB için aşağıya bak).

## Bitirdiğimiz yer

| Parça | Durum |
|---|---|
| Risk motoru (skor, reasons, rule_ids) | ✅ |
| FastAPI (`/predict-risk`, `/explain-risk`) | ✅ |
| RAG: chunk, e5 embedding, arama, atıflı cevap, "bulamadım" koruması | ✅ held-out: arama 11/12, cevap 11/12, reddetme 3/3 |
| Gün 12 entegrasyonu (skor → kural → politika → LLM açıklama) | ✅ commit 652fee5 |
| Vektör DB (Chroma/FAISS) | ⏸ atlandı (numpy + .npz, `ara()` tek değişim noktası) |

## Roadmap kuralları (senin metninden, bağlayıcı)

- Her gün sonu 5'li standart: **Concept, Mini demo, Project integration, Test, Commit.**
- Kapsam kayması: bir konu uzarsa yeni konu ekleme, **sonrakini küçült.**
- Öncelik: Project 9 → FastAPI → RAG → **9+5 entegrasyonu** → Tool calling → Agent. Zaman daralırsa **Agent küçülür**, 9+5 yarım kalmaz.
- Agent bir **proof-of-concept**. "Production-ready banking agent" iddiası yok.
- Deterministik işler tool/sistem tarafında kalır, agent her şeyi yapmaz.

**Zaman baskısı yok** (kullanıcı onayladı, 14 Ekim 2026), bu yüzden aşağıdaki **EK** satırlarının hepsi yapılır. Ek ≈ 4 saat. Zaman bolluğu yeni teknoloji eklemek için değil, mevcut parçaları derinlemesine anlamak ve ölçmek için kullanılır.

---

## Gün 13: RAG Evaluation (3–5 saat)

**Çıktı:** değerlendirme tablosu. **DONE:** RAG'in nerede hata yaptığını görebiliyorum.

- Betik hazır: `tests/rag_degerlendirme.py` → `docs/RAG_EVAL.md` + `data/rag_degerlendirme.csv`. 22 soru, 8 hata türü.
- **EK 🔥** `elle_not` sütunu: cevap ile `kaynak_metinleri` yan yana okunur, kaynakta olmayan cümle işaretlenir. Otomatik "Dayanaklı" sadece vekil ölçü.
- **EK 🟡 (30 dk)** 5–8 hiç görülmemiş soru. 22 sorunun hepsi bir şekilde ayar gördü, gerçek skor bilinmiyor.
- **Öğrenme:** arama hatası ile üretim hatasını ayırmak (retrieval mi, prompt mu suçlu).
- **Commit:** `feat: RAG evaluation table and error taxonomy (Day 13)`

## Gün 13.5: Vektör DB (EK 🟡, yapılacak)

- `ara()` arkasına Chroma (veya FAISS) konur, **aynı 22 soruyla** numpy ile karşılaştırılır. Değerlendirme betiği bunu ücretsiz ölçer.
- Neden: roadmap'in Gün 9'u ve Gün 19 diyagramındaki "Policy DB"; "vector DB kullandın mı?" sorusuna dürüst ve ölçülmüş cevap.
- Süre sınırı yok, ama kapsam sınırı var: sadece `ara()` arkası değişir, chunk/prompt ayarlarına dokunulmaz. Sonuç (daha iyi/aynı/daha kötü) ARCHITECTURE'a yazılır.
- Karşılaştırma `ara()` arayüzü değişmeden, 22 soruda arama başarısı + sıra ile yapılır.

## Gün 14: Tool Calling (4–5 saat)

**Çıktı:** User → LLM → tool seçimi → Python fonksiyonu → sonuç → LLM. **DONE:** LLM'in fonksiyonu seçip parametreyle çağırmasını anlıyorum.

- Sıra: önce `get_risk_score()`, sonra `get_customer_info()`, `search_risk_policy()`.
- Elimizdeki hazır parçalar: `risk_engine.calculate`, `risk_rag.politika_ara`, veri setindeki hesap sorgusu.
- **EK 🔥** geçersiz argüman ve olmayan müşteri için tool hata davranışı (`{"error": ...}`), LLM'e hata da bir sonuç olarak döner.
- **Öğrenme (kendi cümlenle):** LLM fonksiyonu **çalıştırmaz**, sadece hangi fonksiyonu hangi argümanla çağıracağını söyler. Çalıştıran Python'dur. Tool schema bu yüzden vardır.
- **Commit:** `feat: tool calling with risk score tool (Day 14)`

## Gün 15: Agent Fundamentals (3–4 saat)

**Çıktı:** basit çalışan agent. **DONE:** agent'ı normal LLM çağrısından ayıran şeyi kendi cümlelerimle açıklayabiliyorum.

- Üç kavram: LLM, LLM + tools, Agent (karar → tool → gözlem → sonraki adım → cevap döngüsü).
- **EK 🔥** `max_steps` sınırı ve durdurma koşulu (sonsuz döngü ve kontrolsüz maliyet koruması).
- Multi-agent, planner/executor: sadece kavramsal.
- **Commit:** `feat: minimal agent loop with step limit (Day 15)`

## Gün 16: Banking Tools (4–6 saat)

**Çıktı:** 4 tool: `get_customer_info`, `get_transaction_history`, `get_risk_score`, `search_risk_policy`. **DONE:** her tool doğru input alır, doğru output döner, hatada düzgün davranır.

- Her tool tek başına test edilir (`get_customer_info(4521)` gibi).
- **EK 🟡** tool kodları şimdiden `src/tools/` altında başlar (final repo yapısına uyum, Gün 20'de taşıma işi azalır).
- **Kontrol:** veri setinde müşteri/işlem geçmişi gerçekten var mı, 4521 gibi bir id çalışıyor mu. İlk iş bu.
- **Commit:** `feat: banking tools with tests (Day 16)`

## Gün 17: Agent Workflow (5–6 saat) 🔴

**Çıktı:** tek soru birden çok tool çağrısı tetikler. **DONE:** doğru tool seçimi, sonucu kullanma, gerekirse başka tool çağırma, final cevap.

- **EK 🔥** agent trace: her adımda hangi tool, hangi argüman, kaç token. Hem hata ayıklama hem Gün 20 demo hem maliyet ölçümü için.
- Deterministik işler tool tarafında kalır.
- **Commit:** `feat: multi-tool agent workflow with trace (Day 17)`

## Gün 18: Risk Investigation Agent PoC (5–7 saat) 🔴

**Çıktı:** "Analyze customer 4521" → müşteri bilgisi, işlem geçmişi, skor, nedenler, politika, açıklama. **DONE:** Project 9 ve 5'i tool olarak kullanarak anlamlı sonuç.

- **EK 🟡 (1 saat)** Gün 13'teki yöntemin agent'a uygulanması: 5 senaryo, "beklenen tool sırası" ile gerçek sıra karşılaştırılır. Agent'ın **nerede** hata yaptığı görünür.
- Dil: "Agentic AI proof-of-concept". Production iddiası yok.
- **Commit:** `feat: add risk investigation agent (Day 18)`

## Gün 19: End-to-End (5–7 saat) 🔴

**Çıktı:** "Analyze customer 4521 and explain the highest-risk transaction" tek istekten final cevaba çalışır, mümkünse FastAPI üzerinden. **DONE:** sistem baştan sona çalışıyor.

- **EK 🟡 (1 saat)** `/investigate` endpoint, hata olunca `/explain-risk`'teki gibi **zarif düşüş** (risk sonucu her zaman döner).
- **EK 🟡 (1 saat)** cache: anahtar = `etiket + sıralı rule_ids`. Müdürlüğün temel hedefi verim ve maliyet olduğu için mantıklı. Önce/sonra token ve isabet oranı ölçülür.
- **Commit:** `feat: end-to-end investigation API (Day 19)`

## Gün 20: Finalization (5–6 saat), yeni teknoloji yok

- README: Problem, Dataset, Architecture, Risk Engine, RAG, Agent, Setup, Usage, Examples, Limitations, Future Work.
- Mimari diyagram, 3 demo (normal işlem, yüksek riskli işlem, agent müşteri inceliyor).
- Testler: Risk Engine, RAG retrieval, API, Tool, Agent basic. (Çoğu zaten var.)
- **Repo düzeni** (`src/risk_engine/ rag/ agent/ tools/ api/`): testler yeşilken **tek commit** (`refactor: package layout`), önce ve sonra tüm testler geçmeli.
- `docs/ARCHITECTURE.md` (tek seferde): vektör DB kararı, kural–politika örtüşmesinin kaba olması, düşünme token maliyeti, form tablosu chunk gürültüsü, held-out dürüstlüğü (hangi set ayar gördü).
- **Limitations / Future Work:** INTERNATIONAL kuralına ülke alanı, AMOUNT_ANOMALY'yi gelirle karşılaştırma, dış sorular seti.
- Temizlik: kullanılmayan `llm_explain.py`, `git log -p --all -S"sk-ant" --oneline` boş mu.
- **Commit:** `docs: README, architecture, demos (Day 20)`

---

## Zaman tekrar daralırsa (şu an gerekmiyor, yedek sıra)

1. Vektör DB ve cache EK'leri
2. Taze sorular, agent mini-eval
3. Gün 15'i Gün 14 ile birleştir
4. Gün 17 ve 18'i küçült
5. **Asla yarım kalmaz:** 9+5 entegrasyonu (bitti ✅), README ve demo

Kapsam kuralı zamandan bağımsız geçerli: bir konu uzarsa yeni konu ekleme, sonrakini küçült.

## Final cümle ve kanıtı

| Cümledeki parça | Kanıt |
|---|---|
| Deterministik risk motoru skor ve neden üretir | ✅ `risk_engine.py`, `/predict-risk` |
| RAG ilgili politikayı getirir, LLM açıklamasını temellendirir | ✅ `/explain-risk`, değerlendirme tablosu (Gün 13) |
| Agent risk, müşteri, işlem, politika tool'larını kullanır | 🔲 Gün 14–18 |
| Şüpheli aktiviteyi araştırır | 🔲 Gün 18–19 |

## Öğrenme sistemi (kod öğrenmek için)

- Her gün sonu: `docs/OGRENME_NOTLARI.md` dosyasına **kendi kelimelerinle 3 cümle**: bugün ne yaptık, neden öyle, nerede kırılır.
- Bekleyen: `chunklama.py` satır satır anlatımı. Gün 13 içinde 30 dk'lık bir blok.
- Roadmap'in DONE kriterleri zaten "kendi cümlelerimle açıklayabiliyorum" diyor (Gün 14, 15). Bu sınav değil, mentor sunumunun provası.
- README'de ve mentorla konuşmada kodu nasıl geliştirdiğini dürüst anlat ("Claude ile eşli çalıştım, şu parçaları kendim yazdım/anladım/değiştirdim"). Her parçayı kendi cümlenle anlatabilmek gerçek güvence.

## Süre

Roadmap: Gün 13–20 toplam ≈ 34–46 saat. EK'ler ≈ +4 saat, hepsi kesilebilir.
