## Gün 13: RAG Evaluation (16 Ekim 2026)

- **Ne yaptım:** RAG'e 33 soru sordum (ayar, held-out ve hiç görmediği taze set; cevaplı ve rehberde olmayan sorular karışık) ve sonuçları bir tabloya döktüm. Otomatik ölçüde neredeyse hepsi doğru görünüyordu, ama sonra cevapları kaynak chunk'larla yan yana tek tek okudum, PDF'te de Ctrl+F ile kendim kontrol ettim.
- **Neden öyle yaptım:** Otomatik ölçü sadece "beklenen kelime cevapta geçiyor mu" diye bakıyor. #17'de beklenen ifade "tek" idi, cevapta "tek bir seferde" geçtiği için yanlış cevap ✓ aldı. Elle okumasaydım RAG'in doğru çalıştığını sanacaktım.
- **Nerede kırılır:** #17'de doğru cümle PDF s.9'da vardı ama arama onu getirilen ilk 5 chunk'a sokmadı (arama hatası), model de gördüğü chunk'larla "Rehberde bulamadım" dedi, bu da rehber hakkında yanlış bir yokluk iddiası. Bir de model her çalıştırmada farklı yazıyor (#2 bir seferde kaynakta olmayan yorum yaptı, sonra doğru yazdı), o yüzden tek çalıştırmaya güvenemem. Taze set sadece 8 cevaplı soru ve onu Claude yazdı, yani genelleme kanıtı değil.
- **Ek:** Chunk sayfa numaralarında hata vardı (uzun paragraf sayfa sınırını aşınca bütün parçalara ilk satırın sayfası yazılıyordu). Düzelttik, artık test PDF'teki gerçek sayfalarla karşılaştırıyor.
- **Henüz anlamadığım:** `chunklama.py` satır satır nasıl çalışıyor (birim, chunk, sayfa takibi).
## Gün 14: Tool Calling (17 Ekim 2026)

- **Ne yaptım:** Claude'a iki araç tanımı verdim (get_risk_score ve get_customer_info) ve dört soru sordum. Soruya göre doğru aracı seçti, argümanları kendisi doldurdu, aracı benim Python kodum çalıştırdı, sonucu geri verince Claude cevabı yazdı.
- **Neden öyle:** Claude fonksiyonu çalıştırmaz, sadece hangi fonksiyonu hangi argümanla istediğini söyler. Risk skorunu kendisi tahmin ederse uydurabilir, o yüzden skor motordan gelir. Şema (araç tanımı) bu yüzden önemli: Claude neyi çağırabileceğini oradan öğreniyor.
- **Nerede kırılır:** Olmayan müşteri (4521) sorulduğunda araç `error` döndü, Claude bunu uydurmadan "bulunamadı" diye aktardı, ama bu davranış prompt kuralına bağlı, garanti değil. Araç tanımları her çağrıda gönderildiği için "Merhaba" bile 1134 token tutuyor, araç turu iki çağrı olduğundan maliyet ikiye katlanıyor. Şu an tek tur var: Claude ikinci bir araç isterse yapamıyoruz, o yüzden döngü (Gün 15) gerekecek.
## Gün 16 – Banking Tools

- Agent'a 4 araç verdim: get_customer_info, get_transaction_history, get_risk_score, search_risk_policy.
- Araçlar hata olunca exception fırlatmıyor, {"error": ...} döndürüyor; Claude hatayı okuyup düzeltebiliyor.
- Her işlemin risk skorunu get_transaction_history içinde hesaplattık. Böyle olunca Claude "en riskli işlem" sorusunu tek çağrıda cevapladı (sort_by="risk", limit=1).
- search_risk_policy mevcut RAG'i (api.rag_getir) kullanıyor, ikinci bir model yüklemiyor.
- veri.py Excel'i okuyup önbelleğe alıyor; Excel değişirse (boyut + tarih imzası) önbellek geçersiz sayılıyor.
- Testler: banking_tools 65/65, tool_calling 39/39, agent 34/34, risk_rag 26/26 geçti.
- Gerçek çalıştırma: 4 görevin hepsi bitti. "Ödül/prim" sorusunda rehberde olmadığı için "bulamadım" dedi.
- Gördüğüm sorun: 4. görevde Claude Hollanda'yı "riskli ülke" tipine bağlar gibi yazdı, ama bunu hiçbir araç doğrulamadı. Gün 17-18'de prompt kuralı + mini-eval ile ölçeceğiz.
- İlk çağrıda girdi 2265 token; araç şemaları her adımda tekrar gönderildiği için pahalı.
heyo
## Gün 17 – Agent Workflow ve İz (trace)

- Agent'a iz ekledik: her adımda hangi araç, hangi argüman, ne kadar sürdü, kaç token. İz data\izler\ altına JSON olarak kaydediliyor (müşteri verisi içerdiği için repoya girmiyor, .gitignore'da).
- Testler: agent_trace 58/58, agent 41/41, banking_tools 65/65, tool_calling 39/39, risk_rag 26/26.
- Gerçek çalıştırmada ilk rehber araması 6.5 sn sürdü (model yükleniyor), ikincisi 0.1 sn. API'de modeli önceden yüklemek lazım.
- Girdi token'ı her adımda büyüyor çünkü rehber sonuçları (yaklaşık 1 400 token) her adımda tekrar gönderiliyor.
- Kural 9'u ekleyip eski/yeni sistem mesajını 12 çalıştırmayla karşılaştırdık. Yeni mesajla G4'te iki seferde de "Hollanda riskli ülke mi, tutar eşiği aştı mı doğrulayamadım" dedi, eskisinde hiç demedi. Örnek küçük, kesin değil.
- Kural 9 dolgu atıfı (s.16-17) çözmedi. G3'te "iç yönetmeliğe bakın" önerisi 4/4 çıktı, onu zararsız bulduk.
- Aynı G4 görevi 10760 ile 16615 token arasında değişti (2 ya da 3 araç çağrısı), maliyet tek sayı değil aralık.
- Her çağrıya kural 9 yaklaşık 205 token ekliyor.


## Gün 18 – Risk Investigation Agent (PoC)

- "X numaralı müşteriyi incele" diyoruz; ajan müşteri bilgisini, en riskli 5 işlemi ve rehberden dayanak çekip 5 başlıklı rapor yazıyor. Kararı analiste bırakıyor.
- Rapor Claude'un yazdığı metin. Doğruluğunu bilemeyiz ama iddiaların bir kısmını araç sonuçlarıyla mekanik karşılaştırabiliriz: uydurma işlem numarası var mı, sayfa atfı rehber aramasında döndü mü, hüküm dili var mı, gerçek en riskli işlem raporda mı. Bunlar ipucu, kanıt değil.
- 5 senaryolu mini-eval (yüksek riskli, düşük riskli, olmayan müşteri, "dolandırıcı de" baskısı, kredi notu isteği) x 2 tekrar: işlem uydurma yok, baskıya boyun eğme yok, olmayan müşteride ve veri dışı istekte dürüst.
- Otomatik kontrollerden 2 "KALDI" aslında kontrolün hatasıydı (ajan doğru davranmıştı): "hesabı bloke etmeye yetmez" cümlesi hüküm sanıldı, "öğrenemiyorum" ifadesi listede yoktu. Kelime listesi gibi kaba kontroller yanlış alarm da verebilir.
- Sorun: rehber dayanağı tekrarlar arasında değişiyor (ajan sorguyu kendi yazıyor, rehberde kural kodlarının tanımı yok). Düşük riskli müşteride de gereksiz rehber araması yapıp ~17 bin token harcıyor.
- İlk rehber araması yine ~10 sn (model yükleniyor); API'de önceden yüklemek lazım.
- Bu PoC production'a hazır değil: kimlik doğrulama yok, zaman aşımı/yeniden deneme yok, KVKK değerlendirmesi yok, örnek 5 senaryo.

## Gün 19 – /investigate: uçtan uca API, önbellek, zarif bozulma

**Ne yaptım:** Gün 18'deki müşteri inceleme ajanını FastAPI'ye `POST /investigate` olarak bağladım. Müşteri numarası veriyorum, müşteri özeti + en riskli 3 işlem + ajan raporu dönüyor.

**Gördüğüm / öğrendiğim:**
- Cevap üç basamaklı. Önce ajan raporu denenir. Ajan çökerse ya da adım sınırında kesilirse en riskli işlemin kural tabanlı açıklaması gelir. O da çökerse sadece veri döner. Müşteri varsa her durumda 200 döner, yoksa 404.
- Gerçekten denedim: Claude'a giden adresi bozunca (`ANTHROPIC_BASE_URL`) 200 döndü, `rapor_kaynagi: yok`, uyarılarda ne olduğu yazıyordu, 3 işlem yerindeydi. Bu hata durumu 15,8 sn sürdü, çünkü iki basamak da kendi yeniden denemesini yaptı.
- Önbellek: aynı müşteriyi ikinci kez sorunca 128 ms, ilkinde 14–16 sn. `?yenile=true` ile önbellek atlanıyor. Sayaçlar (`/onbellek-durumu`) istek sayımla tutarlı çıktı: 1 ıska, 2 isabet.
- Önbellek anahtarına veri dosyasının imzası da giriyor, yani Excel değişirse eski rapor kullanılmıyor.
- Gerçek bir ajan koşusu yaklaşık 15k girdi + 2,8k çıktı token tuttu. Dolar maliyetini henüz ölçmedim.
- Sunucu açılırken e5 modeli önceden yükleniyor (ısınma), ilk istek 10 sn beklemesin diye.
- Ajan raporunun "Rehber dayanağı" kısmı zayıf çıktı: ajan kural tanımlarını rehberde bulamadığını dürüstçe yazdı ama atıfları (s.16, s.43) işlemle pek ilgili değil. Bunu düzeltmek Gün 20'de ele alınacak, ölçmeden "düzeldi" demeyeceğim.

**Takıldığım yerler:**
- `uvicorn src.api:app` çalışmadı (`No module named 'risk_engine'`). Doğrusu `uvicorn api:app --app-dir src`.
- PowerShell 5'te `Invoke-RestMethod` Türkçe harfleri bozuk gösterdi. Sunucu doğruydu. UTF-8 olarak çözen komutla düzgün gördüm.
- `api.py` 133 değil 142 satırdı. Fark formatlayıcının (black) satır bölmesiydi, mantık aynıydı. `git diff` boştu, o yüzden güvenle üstüne yazdım.

**Henüz yapmadığım:** kimlik doğrulama yok, toplam süre sınırı sadece ajan için var, KVKK değerlendirmesi yapılmadı. "Production-ready" değil, PoC.
