"""Gün 13: TAZE soru seti. Bu sorular hiçbir prompt/chunk/arama ayarında kullanılmadı.
KURAL: sonuçlara bakarak bu soruları, chunklamayı veya promptu DEĞİŞTİRME. Değiştirirsen set artık taze değildir.

Dürüst not: sorular Claude tarafından yazıldı (sistemin zayıf noktalarını bilerek). Bu yüzden beklenen ifadelerin
PDF'te gerçekten yazdığı SENİN tarafından elle doğrulanmalı (her soru için sayfa numarası yanında).
Kapsam: kod/tablo sorusu değil, düzyazı paragrafı sorusu ağırlıklı (önceki setler çoğunlukla kod soruları).

Biçim (held_out_testi ile aynı):
  CEVAPLI : (soru, kaynakta geçmesi gereken ifade, cevapta geçmesi gereken ifadelerden BİRİ)
  CEVAPSIZ: rehberde olmayan soru. Doğrusu sadece 'bulamadım' demek.
Eşleştirme boşluk ve büyük/küçük harf yok sayılarak yapılır.
"""

# (soru, kaynakta ifade, cevapta ifade(ler))  # PDF sayfası
CEVAPLI = [
    ("MASAK.Online sistemine giriş yetkisi almak için yükümlü kurum hangi belgeyi, hangi imza türüyle MASAK'a göndermek zorundadır?",
     "ıslak imzalı olarak Başkanlığa iletilecektir", ("ıslak",)),  # s.7, 3.2.1
    ("Bir bankanın uyum görevlisi değişirse MASAK.Online için ne yapılması gerekir?",
     "yeniden düzenlenerek", ("yeniden", "tekrar")),  # s.7, 3.2.1
    ("Rehbere göre hangi tarihten sonra şüpheli işlem bildirimleri yalnızca bu rehberdeki usullere göre gönderilebilir?",
     "09.05.2024 tarihinden sonra", ("09.05.2024", "9.05.2024", "9 Mayıs 2024")),  # s.5, 1.4
    ("Elde tutulan (stok) mal varlıkları için yapılan bildirimlerde erteleme talebi işaretlenebilir mi?",
     "gönderilmemesi", ("gönderilmem", "hayır", "işaretlenmem", "işaretlenemez")),  # s.7, 3.3
    ("Bu rehber bankalar dışında hangi kuruluş için de geçerlidir?",
     "Posta ve Telgraf Teşkilatı", ("posta",)),  # s.5, 1.1
    ("Hazine ve Maliye Bakanlığı'na şüpheli işlem bildirim formlarının düzenlenmesine ilişkin usul ve esasları belirleme yetkisini veren hüküm hangisidir?",
     "dördüncü fıkrasında", ("28",)),  # s.5, 2. Genel Açıklama (Tedbirler Yönetmeliği md. 28/4)
    ("MASAK'ın yayımladığı bildirim rehberleri nerede duyurulur?",
     "resmî internet sitesi", ("internet sitesi", "masak.online")),  # s.5, 2. Genel Açıklama
    ("Erteleme talebiyle bildirim yapmak için yalnızca şüphe yeterli midir?",
     "ciddi emare", ("ciddi emare",)),  # s.7, 3.3
]

# Rehberde bu konular geçmiyor (PDF'te 'geri bildirim', 'kişisel veri', 'KVKK' aratıldı: 0 sonuç;
# 'saklama' ve 'harç' sadece alakasız bağlamlarda (vergi defteri, gümrük harcı) geçiyor, tuzak olarak seçildi)
CEVAPSIZ = [
    "MASAK, bildirimi gönderen bankaya geri bildirimi kaç gün içinde verir?",
    "Rehbere göre bildirim verileri kişisel verilerin korunması mevzuatı kapsamında nasıl saklanmalıdır?",
    "Bildirimlerin gönderilmesi için MASAK'a ödenen ücret ve harç ne kadardır?",
]
