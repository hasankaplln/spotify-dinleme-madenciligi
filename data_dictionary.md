# Veri Sözlüğü Taslağı (Data Dictionary Draft) — Hafta 2

**Proje:** Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve Sonraki Şarkı Önerisi  
**Öğrenci:** Hasan Kaplan (`256066007`)  
**Teslim Evresi:** Hafta 2 (Otomatik ve Periyodik Toplama, Ham Veri Arşivleme ve Veri Sözlüğü Taslağı)

Bu belge, **Hafta 2** itibarıyla toplanan ve `data/raw/` altında arşivlenip `data/processed/raw_combined_history.parquet` ile `data/processed/listening_history.parquet` dosyalarına dönüştürülen birincil veri kaynaklarının şemasını tanımlar. *(Not: Eksik veri/aykırı değer temizliği ve nihai oturum öznitelik çıkarımı Hafta 3'te gerçekleştirilecek ve bu sözlük güncellenecektir.)*

## 1. Ham Veri Kaynakları ve Arşivleme Yapısı (`data/raw/`)

Hafta 2'de kurulan toplama boru hattı üç tamamlayıcı kaynağı birleştirir ve her çalışmayı `data/raw/collection_manifest.csv` dosyasında kayıt altına alır:

| Kaynak Dosya / Tablo | Biçim | Kaynak Türü | Açıklama |
| :--- | :--- | :--- | :--- |
| `StreamingHistory_music_*.json` | JSON | Birincil Veri (Spotify Dışa Aktarımı) | Kullanıcının son 1 yıldaki şarkı dinleme kayıtları (`endTime`, `artistName`, `trackName`, `msPlayed`). |
| `archive/snapshot_*.json` | JSON | Periyodik Ham Arşiv | `periodic_collector.py` her çalıştığında alınan zaman damgalı ve SHA-256 özetli ham veri yedeği. |
| `collection_manifest.csv` | CSV | Toplama Kayıt Defteri (Log) | Her periyodik çekimin UTC zamanını, satır sayısını, tekil sanatçı sayısını ve dosya özetini (`sha256_prefix`) tutar. |
| `artist_tags_cache.sqlite` | SQLite | API Zenginleştirme Önbelleği | Last.fm API (`artist.getTopTags`) üzerinden çekilen sanatçı–tür eşleşmelerini önbellekler. |

## 2. Birleştirilmiş Dinleme Geçmişi Tablosu Taslak Şeması (`listening_history.parquet`)

Her satır, zaman sırasına göre gerçekleşmiş tek bir şarkı dinleme kaydını temsil eder.

| Sütun Adı | Veri Tipi | Birim / Biçim | Kaynak | Açıklama ve Hafta 3 İçin Planlanan Kalite Kuralı |
| :--- | :--- | :--- | :--- | :--- |
| `played_at` | `datetime64[ns, UTC]` | ISO-8601 (UTC) | Spotify / Last.fm | Şarkı dinleme işleminin bittiği zaman damgası. Hafta 3'te mükerrer zaman damgaları kontrol edilecektir. |
| `artist_name` | `string` | Metin | Spotify / Last.fm | Şarkıyı seslendiren sanatçı veya grup adı. Boşlukları temizlenmiş (`strip()`) metin. |
| `track_name` | `string` | Metin | Spotify / Last.fm | Dinlenen şarkının adı. Podcast ve sesli kitap kayıtları Hafta 3'te filtrelenecektir. |
| `primary_genre` | `string` | Kategori | Last.fm API | Sanatçının en popüler müzik türü etiketi (ör. `Türkçe Rock`, `Indie Rock`). Etiketi bulunmayanlar `"unknown"` alır. |
| `ms_played` | `int64` | Milisaniye (`ms`) | Spotify JSON | Şarkının çalındığı süre. Hafta 3'te `< 1.000 ms` tıklama hataları ve `> 3.600.000 ms` açık kalma anomalileri temizlenecektir. |
| `minutes_played` | `float64` | Dakika (`dk`) | Türetilmiş | `ms_played / 60000.0` formülüyle hesaplanan dakika cinsinden dinleme süresi. |
| `reason_end` | `string` | Kategori | Spotify JSON | Şarkının bitiş şekli (`trackdone` / `completed` veya `fwdbtn` — ileri sarma/atlama). |
| `is_skipped` | `bool` | Mantıksal (`True`/`False`) | Türetilmiş | Şarkının 30 saniyeden (`30.000 ms`) kısa dinlenip atlanıp atlanmadığını belirten bayrak. |
| `gap_minutes` | `float64` | Dakika (`dk`) | Türetilmiş | Bir önceki şarkı ile mevcut şarkı arasındaki bekleme süresi. |
| `is_new_session` | `bool` | Mantıksal (`True`/`False`) | Türetilmiş | `gap_minutes > 30.0` olduğunda yeni bir dinleme oturumunun başladığını gösterir. |
| `session_id` | `int64` | Tam sayı (`1..N`) | Türetilmiş | `is_new_session` üzerinden atanan tekil dinleme oturumu numarası. |
| `hour` | `int32` | Saat (`0..23`) | Türetilmiş | Türkiye yerel saatine (`Europe/Istanbul`) göre dinlemenin gerçekleştiği saat dilimi. |
| `day_of_week` | `string` | Gün adı (`Monday..Sunday`) | Türetilmiş | Dinlemenin gerçekleştiği haftanın günü. |
| `is_weekend` | `bool` | Mantıksal (`True`/`False`) | Türetilmiş | Dinlemenin Cumartesi veya Pazar günü gerçekleşip gerçekleşmediği. |

## 3. Hafta 2 Veri Büyüklüğü ve Hız Sınırı Notları

* **Hedeflenen Asgari Veri Büyüklüğü:** Şartnamedeki tablo verisi asgari sınırı olan **5.000 satırın** üzerinde (en az 5.500 – 10.000+ dinleme satırı) veri toplanmaktadır.
* **API Hız Sınırı (Rate Limiting):** Last.fm API kullanım koşullarına uygun olarak istekler arasında `0.35 saniye` bekleme süresi uygulanmakta ve her sanatçı SQLite önbellekten yalnızca bir kez sorgulanmaktadır.
