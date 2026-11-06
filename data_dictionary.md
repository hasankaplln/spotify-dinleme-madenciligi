# Veri Sözlüğü (Data Dictionary) — Hafta 3 Güncellemesi

**Proje:** Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve Sonraki Şarkı Önerisi  
**Öğrenci:** Hasan Kaplan (`256066007`)  
**Teslim Evresi:** Hafta 3 (Temizleme, Eksik Veri / Aykırı Değer Analizi ve EDA)

Bu belge, Hafta 2'de oluşturulan veri sözlüğü taslağının Hafta 3 temizleme, aykırı değer analizi ve oturum öznitelik çıkarımı adımlarından sonraki güncellenmiş hâlidir.

## 1. Parça Bazlı Temizlenmiş Dinleme Tablosu (`data/processed/listening_history.parquet`)

Her satır, kalite kontrollerinden geçmiş tek bir şarkı dinleme olayını temsil eder.

| Sütun Adı | Veri Tipi | Birim / Biçim | Açıklama | Uygulanan Temizleme ve Aykırı Değer Kuralı |
| :--- | :--- | :--- | :--- | :--- |
| `played_at` | `datetime64[ns, UTC]` | ISO-8601 (UTC) | Şarkı dinleme işleminin bittiği zaman damgası | Boş (`null`) ve mükerrer kayıtlar çıkarıldı; kronolojik sıralandı. |
| `artist_name` | `string` | Metin | Şarkıyı seslendiren sanatçı veya grup adı | Baş/son boşluklar (`strip()`) temizlendi. |
| `track_name` | `string` | Metin | Dinlenen parçanın adı | Baş/son boşluklar temizlendi. |
| `primary_genre` | `string` | Kategori | Last.fm API (`artist.getTopTags`) ana müzik türü | Eksik tür etiketleri `"unknown"` kategorisine atandı. |
| `ms_played` | `int64` | Milisaniye (`ms`) | Parçanın çalındığı süre | `< 1.000 ms` (1 sn altı tıklama hatası) ve `> 3.600.000 ms` (60 dk üstü açık kalma anomalisi) elendi. |
| `minutes_played` | `float64` | Dakika (`dk`) | `ms_played / 60000.0` ile hesaplanan dinleme süresi | `[0.017, 60.0]` dk aralığında doğrulandı; IQR üst sınırı `eda_summary.json` içinde raporlandı. |
| `reason_end` | `string` | Kategori | Parçanın bitiş nedeni (`trackdone`, `fwdbtn` vb.) | `< 30 sn` dinlemeler `fwdbtn` (ileri sarma/atlama) olarak standartlaştırıldı. |
| `is_skipped` | `bool` | Mantıksal (`True`/`False`) | Şarkının 30 saniyeden kısa dinlenip atlanıp atlanmadığı | `ms_played < 30.000 ms` koşuluyla türetildi. |
| `gap_minutes` | `float64` | Dakika (`dk`) | Bir önceki şarkı ile mevcut şarkı arasındaki boşluk süresi | İlk kayıtta `0.0`; negatif değer bulunmadığı doğrulandı. |
| `is_new_session` | `bool` | Mantıksal (`True`/`False`) | `gap_minutes > 30.0` koşuluna göre yeni oturum başlangıcı | 30 dakikalık sessizlik eşiğiyle hesaplandı. |
| `session_id` | `int64` | Tam sayı (`1..N`) | Tekil dinleme oturumu kimliği | Temizleme sonrası kesintisiz `1..N` olarak yeniden numaralandırıldı. |
| `hour` | `int32` | Saat (`0..23`) | Türkiye yerel saatine (`Europe/Istanbul`) göre dinleme saati | Zaman dilimi dönüşümü sonrasında çıkarıldı. |
| `day_of_week` | `string` | Gün adı (`Monday..Sunday`) | Dinlemenin gerçekleştiği haftanın günü | Haftalık takvim ısı haritası için üretildi. |
| `is_weekend` | `bool` | Mantıksal (`True`/`False`) | Cumartesi veya Pazar günü dinlemesi olup olmadığı | `local_dt.dt.day_of_week >= 5` kuralıyla üretildi. |
| `day_period` | `string` | Kategori | `Sabah (06-11)`, `Gündüz (12-17)`, `Akşam (18-23)`, `Gece (00-05)` | Günün zaman dilimi bazlı tür dağılımı analizi için eklendi. |

## 2. Oturum Bazlı Öznitelik Tablosu (`data/processed/sessions_features.parquet`)

Hafta 3'te türetilen bu tablo, her dinleme oturumunu tek bir satırda özetler ve Hafta 4'teki kümeleme modellerinin (`K-Means`, `HDBSCAN`) girdisini oluşturur.

| Sütun Adı | Veri Tipi | Birim / Biçim | Açıklama |
| :--- | :--- | :--- | :--- |
| `session_id` | `int64` | Tam sayı (`1..N`) | Tekil dinleme oturumu kimliği (Birincil Anahtar). |
| `session_start` | `datetime64[ns, Europe/Istanbul]` | Yerel Zaman | Oturumdaki ilk parçanın başlangıç zamanı. |
| `session_end` | `datetime64[ns, Europe/Istanbul]` | Yerel Zaman | Oturumdaki son parçanın bitiş zamanı. |
| `track_count` | `int64` | Adet | Oturum boyunca dinlenen toplam şarkı sayısı. |
| `unique_artists` | `int64` | Adet | Oturumda dinlenen tekil sanatçı sayısı. |
| `unique_genres` | `int64` | Adet | Oturumda dinlenen tekil müzik türü sayısı. |
| `total_minutes` | `float64` | Dakika (`dk`) | Oturumun toplam müzik dinleme süresi. |
| `mean_track_minutes` | `float64` | Dakika (`dk`) | Oturumdaki ortalama şarkı dinleme süresi. |
| `skip_rate` | `float64` | Oran (`0.0..1.0`) | Oturum içinde atlanan (`is_skipped == True`) şarkıların oranı. |
| `artist_diversity` | `float64` | Oran (`0.0..1.0`) | `unique_artists / track_count` ile hesaplanan sanatçı çeşitlilik skoru. |
| `start_hour` | `int32` | Saat (`0..23`) | Oturumun başladığı günün saati. |
| `sin_hour`, `cos_hour` | `float64` | Oran (`-1.0..1.0`) | Gece yarısı sürekliliğini koruyan döngüsel (cyclical) saat bileşenleri. |
| `dominant_genre` | `string` | Kategori | Oturumda en çok tekrar eden baskın müzik türü. |
| `dominant_artist` | `string` | Metin | Oturumda en çok dinlenen baskın sanatçı. |
