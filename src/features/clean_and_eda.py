#!/usr/bin/env python3
"""Hafta 3 — Veri Temizleme, Eksik/Aykırı Değer Analizi, Oturum Öznitelik Çıkarımı ve EDA Betiği

(src/features/clean_and_eda.py)

Proje: Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve
Sonraki Şarkı Önerisi
Öğrenci: Hasan Kaplan (256066007)

Hafta 3 Gereksinimleri (Şartname Bölüm 07):
- "Temizleme, eksik veri ve aykırı değer analizi, EDA. Araştırma soruları
gerekirse güncellenir."

Bu betik:
1. `data/processed/raw_combined_history.parquet` (veya
`listening_history.parquet`) dosyasını okur.
2. Veri kalitesi, eksik veri ve aykırı değer (outlier) analizini yapar:
   - Eksik (`null`) zaman damgası, sanatçı veya şarkı kayıtlarını raporlar ve
   temizler.
   - Mükerrer (`played_at` + `artist_name` + `track_name`) kayıtları eler.
   - `< 1.000 ms` (1 sn altı) hatalı tıklama gürültüsünü ve `> 3.600.000 ms` (60
   dk üstü) açık kalma anomalilerini filtreler; IQR yöntemiyle oturum süresi
   dağılımını inceler.
3. Dinleme oturumlarını (`session_id`) 30 dakikalık boşluk eşiğine göre yeniden
numaralandırır ve
   oturum bazlı öznitelik tablosunu (`data/processed/sessions_features.parquet`)
   üretir.
4. Aşama 1 ara raporunda kullanılacak 4 temel EDA grafiğini (`outputs/figures/`)
ve kalite/EDA
   özet raporunu (`outputs/findings/eda_summary.json`) üretir.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns

SEED = 42
MIN_MS_THRESHOLD = 1_000        # 1 saniye altı sistem/tıklama gürültüsü
MAX_MS_THRESHOLD = 3_600_000    # 60 dakika üstü açık kalma / podcast anomalisi
SKIP_MS_THRESHOLD = 30_000      # 30 saniye altı atlama (skip)
SESSION_GAP_MINUTES = 30.0


def assign_day_period(hour: int) -> str:
  if 0 <= hour < 6:
    return "Gece (00-05)"
  if 6 <= hour < 12:
    return "Sabah (06-11)"
  if 12 <= hour < 18:
    return "Gündüz (12-17)"
  return "Akşam (18-23)"


def clean_listening_records(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
  """Eksik değerleri, mükerrer kayıtları ve süre aykırı değerlerini temizler."""
  initial_count = len(df)

  # 1. Eksik temel alanların kontrolü ve temizlenmesi
  required_cols = ["played_at", "artist_name", "track_name", "ms_played"]
  missing_before = {col: int(df[col].isna().sum()) for col in required_cols if col in df.columns}
  df = df.dropna(subset=required_cols).copy()

  if "primary_genre" not in df.columns:
    df["primary_genre"] = "unknown"
  else:
    df["primary_genre"] = df["primary_genre"].fillna("unknown").astype(str)

  # 2. Mükerrer kayıt kontrolü
  dup_count = int(df.duplicated(subset=["played_at", "artist_name", "track_name"]).sum())
  df = df.drop_duplicates(subset=["played_at", "artist_name", "track_name"]).copy()

  # 3. Aykırı süre filtresi (< 1 sn veya > 60 dk)
  too_short_count = int((df["ms_played"] < MIN_MS_THRESHOLD).sum())
  too_long_count = int((df["ms_played"] > MAX_MS_THRESHOLD).sum())
  df = df[(df["ms_played"] >= MIN_MS_THRESHOLD) & (df["ms_played"] <= MAX_MS_THRESHOLD)].copy()

  # 4. Kronolojik sıralama ve oturum (session) yeniden hesaplama
  df["played_at"] = pd.to_datetime(df["played_at"], utc=True)
  df = df.sort_values("played_at").reset_index(drop=True)

  df["minutes_played"] = (df["ms_played"] / 60_000.0).round(3)
  df["is_skipped"] = df["ms_played"] < SKIP_MS_THRESHOLD

  gap_min = df["played_at"].diff().dt.total_seconds().div(60.0).fillna(0.0)
  df["gap_minutes"] = gap_min.round(2)
  df["is_new_session"] = (gap_min > SESSION_GAP_MINUTES) | (df.index == 0)
  df["session_id"] = df["is_new_session"].cumsum()

  # Pandas 3.x / 4.x tam uyumlu tarih/saat özellikleri (dt.day_of_week)
  local_dt = df["played_at"].dt.tz_convert("Europe/Istanbul")
  df["hour"] = local_dt.dt.hour
  df["day_of_week"] = local_dt.dt.day_name()
  df["is_weekend"] = local_dt.dt.day_of_week >= 5
  df["day_period"] = df["hour"].map(assign_day_period)

  # IQR tabanlı parça süresi aykırı değer istatistiği
  q25, q75 = np.percentile(df["minutes_played"], [25, 75])
  iqr = q75 - q25
  iqr_upper = float(q75 + 1.5 * iqr)
  iqr_outlier_tracks = int((df["minutes_played"] > iqr_upper).sum())

  quality_report = {
      "initial_rows": int(initial_count),
      "cleaned_rows": int(len(df)),
      "missing_values_before": missing_before,
      "duplicates_removed": dup_count,
      "outliers_too_short_removed": too_short_count,
      "outliers_too_long_removed": too_long_count,
      "iqr_upper_bound_minutes": round(iqr_upper, 2),
      "iqr_long_track_count": iqr_outlier_tracks,
      "unique_artists": int(df["artist_name"].nunique()),
      "unique_tracks": int(df["track_name"].nunique()),
      "unique_genres": int(df["primary_genre"].nunique()),
      "total_sessions": int(df["session_id"].nunique()),
      "overall_skip_rate": round(float(df["is_skipped"].mean()), 4),
      "total_hours_played": round(float(df["minutes_played"].sum() / 60.0), 2),
  }
  return df, quality_report


def build_session_features(df: pd.DataFrame) -> pd.DataFrame:
  """Her dinleme oturumu (session_id) için öznitelik tablosunu üretir."""
  local_dt = df["played_at"].dt.tz_convert("Europe/Istanbul")
  df_temp = df.assign(local_played_at=local_dt)

  def dominant_val(series: pd.Series) -> str:
    mode = series.mode()
    return str(mode.iloc[0]) if not mode.empty else "unknown"

  sessions = (
      df_temp.groupby("session_id", as_index=False)
      .agg(
          session_start=("local_played_at", "min"),
          session_end=("local_played_at", "max"),
          track_count=("track_name", "count"),
          unique_artists=("artist_name", "nunique"),
          unique_genres=("primary_genre", "nunique"),
          total_minutes=("minutes_played", "sum"),
          mean_track_minutes=("minutes_played", "mean"),
          skip_rate=("is_skipped", "mean"),
          start_hour=("hour", "first"),
          is_weekend=("is_weekend", "first"),
          day_period=("day_period", "first"),
          dominant_genre=("primary_genre", dominant_val),
          dominant_artist=("artist_name", dominant_val),
      )
  )

  sessions["total_minutes"] = sessions["total_minutes"].round(2)
  sessions["mean_track_minutes"] = sessions["mean_track_minutes"].round(2)
  sessions["skip_rate"] = sessions["skip_rate"].round(4)
  sessions["artist_diversity"] = (
      sessions["unique_artists"] / sessions["track_count"].clip(lower=1)
  ).round(4)

  # Döngüsel (cyclical) saat kodlaması
  sessions["sin_hour"] = np.sin(2 * np.pi * sessions["start_hour"] / 24.0).round(4)
  sessions["cos_hour"] = np.cos(2 * np.pi * sessions["start_hour"] / 24.0).round(4)

  return sessions


def generate_eda_figures(
    df: pd.DataFrame, sessions: pd.DataFrame, fig_dir: Path
) -> list[str]:
  """Hafta 3 Keşifsel Veri Analizi (EDA) için 4 temel grafik üretir."""
  fig_dir.mkdir(parents=True, exist_ok=True)
  sns.set_theme(style="whitegrid", palette="deep")
  saved_files: list[str] = []

  # 1. Gün × Saat Dinleme Yoğunluğu Isı Haritası
  day_order = [
      "Monday",
      "Tuesday",
      "Wednesday",
      "Thursday",
      "Friday",
      "Saturday",
      "Sunday",
  ]
  day_tr = {
      "Monday": "Pazartesi",
      "Tuesday": "Salı",
      "Wednesday": "Çarşamba",
      "Thursday": "Perşembe",
      "Friday": "Cuma",
      "Saturday": "Cumartesi",
      "Sunday": "Pazar",
  }
  pivot = (
      df.pivot_table(
          index="day_of_week",
          columns="hour",
          values="minutes_played",
          aggfunc="sum",
          fill_value=0,
      )
      .reindex(day_order)
      .rename(index=day_tr)
  )
  for h in range(24):
    if h not in pivot.columns:
      pivot[h] = 0.0
  pivot = pivot[sorted(pivot.columns)]

  fig, ax = plt.subplots(figsize=(11, 4.5), dpi=180)
  sns.heatmap(
      pivot,
      cmap="YlGnBu",
      linewidths=0.4,
      ax=ax,
      cbar_kws={"label": "Toplam Dinleme (Dakika)"},
  )
  ax.set_title(
      "Haftanın Günleri ve Saatlere Göre Dinleme Yoğunluğu (Isı Haritası)",
      fontsize=12,
      fontweight="bold",
  )
  ax.set_xlabel("Saat (00:00 – 23:00)")
  ax.set_ylabel("Gün")
  fig.tight_layout()
  f1 = fig_dir / "eda_01_hourly_weekday_heatmap.png"
  fig.savefig(f1)
  plt.close(fig)
  saved_files.append(str(f1))

  # 2. En Çok Dinlenen İlk 12 Sanatçı ve Atlama (Skip) Oranları
  top_artists = (
      df.groupby("artist_name", as_index=False)
      .agg(
          total_hours=("minutes_played", lambda s: s.sum() / 60.0),
          play_count=("track_name", "count"),
          skip_rate=("is_skipped", "mean"),
      )
      .sort_values("total_hours", ascending=False)
      .head(12)
  )

  fig, ax = plt.subplots(figsize=(9.5, 5.0), dpi=180)
  bars = ax.barh(
      top_artists["artist_name"][::-1],
      top_artists["total_hours"][::-1],
      color="#1DB954",
      edgecolor="#0F3D5E",
  )
  for bar, skip in zip(bars, top_artists["skip_rate"][::-1]):
    ax.text(
        bar.get_width() + 0.15,
        bar.get_y() + bar.get_height() / 2,
        f"Skip: %{skip * 100:.1f}",
        va="center",
        fontsize=8.5,
        color="#1F2937",
    )
  ax.set_title(
      "En Çok Dinlenen Sanatçılar (Saat) ve Atlama (Skip) Oranları",
      fontsize=12,
      fontweight="bold",
  )
  ax.set_xlabel("Toplam Dinleme Süresi (Saat)")
  ax.set_ylabel("Sanatçı")
  ax.set_xlim(0, top_artists["total_hours"].max() * 1.22)
  fig.tight_layout()
  f2 = fig_dir / "eda_02_top_artists_and_skip.png"
  fig.savefig(f2)
  plt.close(fig)
  saved_files.append(str(f2))

  # 3. Oturum Uzunluğu (Dakika) ve Oturum Başına Şarkı Sayısı Dağılımı
  fig, axes = plt.subplots(1, 2, figsize=(10.5, 4.2), dpi=180)
  sns.histplot(
      sessions["total_minutes"], bins=25, kde=True, color="#2563EB", ax=axes[0]
  )
  axes[0].set_title(
      "Oturum Süresi Dağılımı (Dakika)", fontsize=11, fontweight="bold"
  )
  axes[0].set_xlabel("Oturum Süresi (dk)")
  axes[0].set_ylabel("Oturum Sayısı")

  sns.histplot(
      sessions["track_count"], bins=20, kde=False, color="#0D9488", ax=axes[1]
  )
  axes[1].set_title(
      "Oturum Başına Şarkı Sayısı Dağılımı", fontsize=11, fontweight="bold"
  )
  axes[1].set_xlabel("Oturumdaki Şarkı Sayısı")
  axes[1].set_ylabel("Oturum Sayısı")
  fig.tight_layout()
  f3 = fig_dir / "eda_03_session_distributions.png"
  fig.savefig(f3)
  plt.close(fig)
  saved_files.append(str(f3))

  # 4. Günün Zaman Dilimlerine Göre Müzik Türü Dağılımı
  period_order = [
      "Sabah (06-11)",
      "Gündüz (12-17)",
      "Akşam (18-23)",
      "Gece (00-05)",
  ]
  genre_period = (
      df.groupby(["day_period", "primary_genre"])["minutes_played"]
      .sum()
      .unstack(fill_value=0)
      .reindex(period_order)
  )
  genre_period_pct = genre_period.div(genre_period.sum(axis=1), axis=0) * 100.0

  fig, ax = plt.subplots(figsize=(10.0, 4.8), dpi=180)
  genre_period_pct.plot(kind="bar", stacked=True, colormap="tab20", ax=ax)
  ax.set_title(
      "Günün Zaman Dilimlerine Göre Dinlenen Müzik Türü Payları (%)",
      fontsize=12,
      fontweight="bold",
  )
  ax.set_xlabel("Zaman Dilimi")
  ax.set_ylabel("Dinleme Süresi Payı (%)")
  ax.legend(
      title="Müzik Türü", bbox_to_anchor=(1.02, 1), loc="upper left", fontsize=8
  )
  plt.xticks(rotation=0)
  fig.tight_layout()
  f4 = fig_dir / "eda_04_genre_by_day_period.png"
  fig.savefig(f4)
  plt.close(fig)
  saved_files.append(str(f4))

  return saved_files


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Hafta 3: Veri Temizleme, Aykırı Değer Analizi ve EDA"
  )
  parser.add_argument(
      "--input",
      type=Path,
      default=Path("data/processed/raw_combined_history.parquet"),
      help="Girdi Parquet dosyası",
  )
  parser.add_argument(
      "--processed-dir",
      type=Path,
      default=Path("data/processed"),
      help="İşlenmiş veri klasörü",
  )
  parser.add_argument(
      "--findings-dir",
      type=Path,
      default=Path("outputs/findings"),
      help="Bulgular ve özet JSON klasörü",
  )
  parser.add_argument(
      "--figures-dir",
      type=Path,
      default=Path("outputs/figures"),
      help="EDA grafikleri klasörü",
  )
  args = parser.parse_args()

  args.processed_dir.mkdir(parents=True, exist_ok=True)
  args.findings_dir.mkdir(parents=True, exist_ok=True)
  args.figures_dir.mkdir(parents=True, exist_ok=True)

  input_path = args.input
  if not input_path.exists():
    fallback = args.processed_dir / "listening_history.parquet"
    if fallback.exists():
      input_path = fallback
    else:
      raise FileNotFoundError(
          f"Girdi dosyası bulunamadı: {args.input}. Önce Hafta 2 betiğini"
          " çalıştırın."
      )

  df_raw = pd.read_parquet(input_path)
  df_clean, quality_report = clean_listening_records(df_raw)
  sessions_df = build_session_features(df_clean)

  clean_path = args.processed_dir / "listening_history.parquet"
  sessions_path = args.processed_dir / "sessions_features.parquet"
  sessions_sample_csv = args.processed_dir / "sessions_features_sample.csv"

  df_clean.to_parquet(clean_path, index=False)
  sessions_df.to_parquet(sessions_path, index=False)
  sessions_df.head(100).to_csv(sessions_sample_csv, index=False)

  saved_figs = generate_eda_figures(df_clean, sessions_df, args.figures_dir)
  quality_report["session_summary"] = {
      "median_session_minutes": round(
          float(sessions_df["total_minutes"].median()), 2
      ),
      "iqr_session_minutes": round(
          float(
              sessions_df["total_minutes"].quantile(0.75)
              - sessions_df["total_minutes"].quantile(0.25)
          ),
          2,
      ),
      "mean_session_tracks": round(
          float(sessions_df["track_count"].mean()), 2
      ),
      "mean_session_skip_rate": round(
          float(sessions_df["skip_rate"].mean()), 4
      ),
  }
  quality_report["generated_figures"] = saved_figs

  summary_json_path = args.findings_dir / "eda_summary.json"
  with open(summary_json_path, "w", encoding="utf-8") as f:
    json.dump(quality_report, f, ensure_ascii=False, indent=2)

  print(f"[OK] Temizlenen dinleme verisi : {len(df_clean):,} satır -> {clean_path}")
  print(f"[OK] Oturum öznitelik tablosu  : {len(sessions_df):,} oturum -> {sessions_path}")
  print(f"[OK] EDA kalite ve özet raporu : {summary_json_path}")
  print(f"[OK] Üretilen EDA grafikleri   : {len(saved_figs)} adet ({args.figures_dir})")


if __name__ == "__main__":
  main()