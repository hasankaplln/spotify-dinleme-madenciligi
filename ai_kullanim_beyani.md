# Yapay Zekâ Araçları Kullanım Beyanı (Ek B)

**Ders:** Veri Madenciliği ve Veri Görselleştirme Dönem Projesi (2026–2027 Güz)  
**Ad Soyad:** Hasan Kaplan  
**Öğrenci No.:** 256066007  
**Proje Başlığı:** Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve Sonraki Şarkı Önerisi

## 1. Kullanılan Araçlar

| Araç | Sürüm / Model | Hangi Amaçla |
| :--- | :--- | :--- |
| Gemini | Gemini (Task Mode) | Hafta 1 konu seçimi ve ilk prototip (`collect_spotify.py`); Hafta 2 periyodik veri toplama/arşivleme (`periodic_collector.py`) ve veri sözlüğü taslağının (`DATA_DICTIONARY.md`) oluşturulması |

## 2. Kullanım Kaydı

| Tarih | Araç | Amaç | İlgili Dosya / Bölüm | Çıktıyı Nasıl Doğruladım |
| :--- | :--- | :--- | :--- | :--- |
| 20.10.2026 | Gemini | Fikir üretme ve yöntem planlama | `Ek-A_Konu_Oneri_Formu_Hasan_Kaplan.pdf` | Şartnamedeki asgari veri büyüklüğü (en az 5.000 satır), iki klasik yöntem ailesi ve CPU üzerinde çalışabilir derin öğrenme kriterleriyle karşılaştırarak doğruladım. |
| 20.10.2026 | Gemini | Kod yazma (Hafta 1 veri toplama prototipi) | `src/collect/collect_spotify.py` | Örnek Spotify `StreamingHistory` JSON şeması üzerinde betiği çalıştırıp oturum bölme (30 dk eşiği), önbellekleme ve Parquet çıktısını test ettim. |
| 02.11.2026 | Gemini | Kod yazma ve belgeleme (Hafta 2 arşivleme ve veri sözlüğü taslağı) | `src/collect/periodic_collector.py`, `DATA_DICTIONARY.md` | Zaman damgalı JSON anlık görüntü (`snapshot_*.json`) arşivlemesini, SHA-256 özetli `collection_manifest.csv` kaydını ve sütun veri tiplerini kontrol ederek doğruladım. |

## 3. En Etkili 3 İstem

### İstem 1
* **Dosya:** `prompts/01_hafta1_konu_ve_planlama.md`
* **Ne İşe Yaradı:** Harici ekran kartı (GPU) olmayan bir bilgisayarda Spotify dinleme geçmişi üzerinde hem klasik veri madenciliği (K-Means/HDBSCAN oturum kümeleme ve FP-Growth birliktelik kuralları) hem de hafif bir sıralı derin öğrenme modeli (PyTorch Embedding + GRU/MLP) kurgulayarak 10 haftalık yol haritasını oluşturdu.
* **Neyi Değiştirmek Zorunda Kaldım:** Veri dışa aktarımının gecikmesi riskine karşı Last.fm API (`artist.getTopTags`, `user.getRecentTracks`) ve yerel SQLite önbellekleme adımlarını B planına ekledim.

### İstem 2
* **Dosya:** `prompts/02_hafta2_periyodik_toplama_ve_veri_sozlugu.md`
* **Ne İşe Yaradı:** Her veri çekiminde ham JSON verisini zaman damgası ve SHA-256 özetiyle `data/raw/archive/` klasörüne yedekleyen, `collection_manifest.csv` kayıt defterini güncelleyen ve Hafta 2 veri sözlüğü taslağını hazırlayan yapıyı kurdu.
* **Neyi Değiştirmek Zorunda Kaldım:** Arşiv klasörünün gereksiz büyümesini önlemek için anlık görüntü paketlemeyi ve Last.fm API hız sınırını (`0.35 sn`) sabitledim.

### İstem 3
* **Dosya:** *(İlerleyen haftalarda eklenecektir)*
* **Ne İşe Yaradı:** *(İlerleyen haftalarda doldurulacaktır)*
* **Neyi Değiştirmek Zorunda Kaldım:** *(İlerleyen haftalarda doldurulacaktır)*

## 4. Kendi Katkım

* **Yapay Zekânın Yapamadığı veya Yanlış Yaptığı ve Benim Çözdüğüm Noktalar:**
  * Kişisel Spotify hesap verimin mahremiyet kontrolünü, kişisel tanımlayıcı alanların (IP adresi, cihaz kimliği vb.) temizlenmesini ve kendi dinleme alışkanlıklarıma özgü oturum tanımlama kurallarını (30 dakikalık sessizlik eşiği ve 30 saniye altı atlama/skip filtresi) bizzat doğruladım ve yapılandırdım.

## 5. Beyan

Bu projede yapay zekâ araçlarıyla üretilen tüm içerikleri inceledim, test ettim ve savunabilirim. Yukarıdaki kayıt, kullanımımı eksiksiz ve doğru biçimde yansıtır.

* **Ad Soyad:** Hasan Kaplan
* **Tarih:** 02.11.2026