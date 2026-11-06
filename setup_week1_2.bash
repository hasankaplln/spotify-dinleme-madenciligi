#!/usr/bin/env bash
# ==============================================================================
# Hafta 1 ve Hafta 2 — Yerel Bilgisayar ve GitHub Depo Kurulum Betiği
# Proje: Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve Sonraki Şarkı Önerisi
# Öğrenci: Hasan Kaplan (256066007)
# ==============================================================================

set -e

echo "[1/5] Şartnamedeki standart proje klasör yapısı oluşturuluyor..."
mkdir -p data/raw/archive \
         data/processed \
         src/collect \
         src/features \
         src/mining \
         src/models \
         notebooks \
         outputs/findings \
         outputs/figures \
         outputs/models \
         app \
         web \
         reports \
         prompts

# Boş klasörlerin Git tarafından takip edilmesi için .gitkeep dosyaları (ham veri hariç)
touch data/processed/.gitkeep \
      src/features/.gitkeep \
      src/mining/.gitkeep \
      src/models/.gitkeep \
      notebooks/.gitkeep \
      outputs/findings/.gitkeep \
      outputs/figures/.gitkeep \
      outputs/models/.gitkeep \
      app/.gitkeep \
      web/.gitkeep \
      reports/.gitkeep

# Eğer betikler ana dizine indirildiyse otomatik olarak src/collect/ içine taşı veya kopyala
if [ -f "collect_spotify.py" ] && [ ! -f "src/collect/collect_spotify.py" ]; then
    cp collect_spotify.py src/collect/collect_spotify.py
    echo "  -> collect_spotify.py dosyası src/collect/ içine kopyalandı."
fi

if [ -f "periodic_collector.py" ] && [ ! -f "src/collect/periodic_collector.py" ]; then
    cp periodic_collector.py src/collect/periodic_collector.py
    echo "  -> periodic_collector.py dosyası src/collect/ içine kopyalandı."
fi

echo "[2/5] .gitignore, pyproject.toml ve Makefile oluşturuluyor..."

cat << 'EOF' > .gitignore
# Ham kişisel veriler (Şartname kuralı: ham veri git dışında tutulur, yalnızca örnek ve manifest eklenir)
data/raw/*.json
data/raw/archive/*.json
data/processed/*.parquet
data/processed/*.sqlite

# Python ve sanal ortam
.venv/
venv/
__pycache__/
*.py[cod]
.pytest_cache/
.ruff_cache/

# İşletim sistemi ve editör dosyaları
.DS_Store
Thumbs.db
.vscode/
.idea/
EOF

cat << 'EOF' > pyproject.toml
[project]
name = "spotify-dinleme-madenciligi"
version = "0.2.0"
description = "Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve Sonraki Şarkı Önerisi (Hasan Kaplan - 256066007)"
readme = "README.md"
requires-python = ">=3.10"
dependencies = [
    "numpy>=1.26.0",
    "pandas>=2.1.0",
    "pyarrow>=14.0.0",
    "matplotlib>=3.8.0",
    "seaborn>=0.13.0",
    "scikit-learn>=1.4.0",
    "mlxtend>=0.23.0",
    "lightgbm>=4.3.0",
    "torch>=2.2.0",
    "shap>=0.45.0",
    "streamlit>=1.32.0",
]

[tool.ruff]
line-length = 100
EOF

cat << 'EOF' > Makefile
PYTHON ?= .venv/bin/python

.PHONY: setup data week1 week2 all clean

setup:
	python3 -m venv .venv
	$(PYTHON) -m pip install --upgrade pip
	$(PYTHON) -m pip install numpy pandas pyarrow

week1:
	$(PYTHON) src/collect/collect_spotify.py --demo

week2:
	$(PYTHON) src/collect/periodic_collector.py --demo

data: week1 week2

all: data

clean:
	rm -rf data/processed/*.parquet data/processed/*.csv
EOF

echo "[3/5] prompts/ klasörüne Hafta 1 ve Hafta 2 istem özetleri yazılıyor..."
cat << 'EOF' > prompts/01_hafta1_konu_ve_planlama.md
# İstem 1 — Hafta 1 Konu Seçimi ve CPU Dostu Mimari Planlama

* **Tarih:** 20.10.2026
* **Amaç:** Ekran kartı (GPU) olmayan kişisel bilgisayarda Spotify kişisel dinleme verisiyle çalışacak Aşama 1 (2 klasik yöntem + 1 derin öğrenme modeli + baseline) ve Aşama 2 (etkileşimli dashboard + D3.js) mimarisini kurgulamak ve ilk veri toplama betiğini (`src/collect/collect_spotify.py`) oluşturmak.
EOF

cat << 'EOF' > prompts/02_hafta2_periyodik_toplama_ve_veri_sozlugu.md
# İstem 2 — Hafta 2 Periyodik Veri Toplama, Arşivleme ve Veri Sözlüğü Taslağı

* **Tarih:** 02.11.2026
* **Amaç:** Her veri çekiminde ham JSON verisini zaman damgalı ve SHA-256 özetli olarak `data/raw/archive/` altına yedekleyen, `collection_manifest.csv` kayıt defterini güncelleyen `src/collect/periodic_collector.py` betiğini ve `DATA_DICTIONARY.md` taslağını oluşturmak.
EOF

echo "[4/5] Python sanal ortamı (.venv) kuruluyor ve temel paketler yükleniyor..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
fi
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet numpy pandas pyarrow

echo "[5/5] Hafta 1 ve Hafta 2 veri toplama betikleri test ediliyor..."
if [ -f "src/collect/collect_spotify.py" ]; then
    .venv/bin/python src/collect/collect_spotify.py --demo
fi
if [ -f "src/collect/periodic_collector.py" ]; then
    .venv/bin/python src/collect/periodic_collector.py --demo
fi

echo ""
echo "=============================================================================="
echo "[TAMAMLANDI] Klasör yapısı, sanal ortam ve Hafta 1-2 testleri başarıyla kuruldu!"
echo "Şimdi Git ve GitHub adımlarını çalıştırabilirsiniz."
echo "=============================================================================="