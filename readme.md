# Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve Sonraki Şarkı Önerisi

**Ders:** Veri Madenciliği ve Veri Görselleştirme Dönem Projesi (2026–2027 Güz)  
**Öğrenci:** Hasan Kaplan (`256066007`)  
**Alan:** 13 — Müzik ve Medya  
**Mevcut Evre:** Hafta 2 (Otomatik ve Periyodik Veri Toplama, Ham Veri Arşivleme ve Veri Sözlüğü Taslağı)

## 1. Problem Tanımı ve Araştırma Soruları

Bu proje, kişisel Spotify dinleme geçmişi (`StreamingHistory` / `Extended Streaming History`) ve Last.fm API tür/etiket zenginleştirmesi üzerinden dinleme oturumlarını (sessions) modellemeyi, sanatçı/tür birliktelik kurallarını keşfetmeyi ve ekran kartı (GPU) gerektirmeyen hafif bir sıralı derin öğrenme modeliyle bir sonraki şarkı/sanatçı tahminini gerçekleştirmeyi amaçlar.

1. **Oturum Kümelemesi (RQ1):** Dinleme zaman damgaları ve parça geçişlerinden anlamlı oturum (session) ve bağlam kümeleri çıkarılabilir mi?
2. **Birliktelik Kuralları (RQ2):** Hangi sanatçı ve müzik türü ikilileri aynı oturumlarda istatistiksel olarak güçlü birliktelik kuralları (yüksek *lift*) oluşturur?
3. **Sıralı Öneri ve Derin Öğrenme (RQ3):** CPU üzerinde eğitilen sıralı derin öğrenme modeli (`PyTorch Embedding + GRU / MLP`), sonraki şarkı/sanatçı tahmininde Markov ve `LightGBM` temel modellerini ne ölçüde geçer?

## 2. Depo Yapısı (Hafta 1–2 Durumu)

```text
spotify-dinleme-madenciligi/
├── README.md                        # Problem, kurulum ve Hafta 1-2 çalıştırma kılavuzu
├── DATA_DICTIONARY.md               # Hafta 2: Veri sözlüğü taslağı ve ham arşiv şeması
├── data/
│   ├── raw/                         # Git dışında; Spotify JSON dosyaları ve archive/ klasörü
│   │   ├── archive/                 # Zaman damgalı ham veri yedekleri (snapshot_*.json)
│   │   └── collection_manifest.csv  # Periyodik veri toplama kayıt defteri (log)
│   └── processed/                   # raw_combined_history.parquet, listening_history.parquet, SQLite önbellek
├── src/
│   ├── collect/
│   │   ├── collect_spotify.py       # Hafta 1: İlk veri okuma ve oturum bölme prototipi
│   │   └── periodic_collector.py    # Hafta 2: Otomatik/periyodik çekim ve ham veri arşivleme
│   ├── features/                    # (Hafta 3'te eklenecek: Temizleme ve EDA)
│   ├── mining/                      # (Hafta 4-5'te eklenecek: Kümeleme ve Birliktelik Kuralları)
│   └── models/                      # (Hafta 5-6'da eklenecek: Baseline ve Derin Öğrenme)
├── outputs/
│   ├── findings/                    # Aşama 2 Dashboard veri sözleşmesi klasörü
│   ├── figures/                     # Analiz grafikleri klasörü
│   └── models/                      # Model çıktıları klasörü
└── AI_KULLANIM_BEYANI.md            # Ek B: Güncel yapay zekâ araçları kullanım beyanı
```

## 3. Hafta 1 ve Hafta 2 Komutlarını Çalıştırma

### Ortam Kurulumu

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install pandas pyarrow numpy
```

### Hafta 2: Periyodik Veri Toplama ve Ham Veri Arşivleme

1. Spotify'dan gelen JSON dosyalarınızı `data/raw/` klasörüne kopyalayın (henüz gelmediyse `--demo` bayrağını kullanın).
2. Ham veriyi zaman damgalı olarak `data/raw/archive/` altına arşivlemek, `collection_manifest.csv` kaydını oluşturmak ve birleştirilmiş tabloyu üretmek için:

```bash
# Demo verisiyle Hafta 2 arşivleme ve toplama testi:
python3 src/collect/periodic_collector.py --demo

# Gerçek Spotify JSON + isteğe bağlı Last.fm API periyodik çekimiyle çalıştırma:
python3 src/collect/periodic_collector.py --lastfm-user KULLANICI_ADINIZ --lastfm-api-key API_ANAHTARINIZ
```

### Günlük Otomatik Çalıştırma (`cron` örneği)

Periyodik toplayıcıyı her gün saat 23:00'te otomatik çalıştırmak için (`crontab -e`):

```cron
0 23 * * * cd /proje/yolu && .venv/bin/python src/collect/periodic_collector.py --lastfm-user KULLANICI_ADINIZ --lastfm-api-key API_ANAHTARINIZ >> data/raw/cron_collect.log 2>&1
```
