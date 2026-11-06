#!/usr/bin/env python3
"""Hafta 1 — İlk Veri Toplama ve Birleştirme Betiği (src/collect/collect_spotify.py)

Proje: Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve
Sonraki Şarkı Önerisi
Öğrenci: Hasan Kaplan (256066007)

Bu betik:
1. Spotify Kişisel Veri Dışa Aktarımı (`StreamingHistory_music_*.json` veya
`endsong_*.json`)
   dosyalarını `data/raw/` klasöründen okur ve kişisel/hassas cihaz bilgilerini
   temizler.
2. İsteğe bağlı olarak Last.fm API (`artist.getTopTags`) üzerinden hız sınırına
(rate-limit)
   uygun biçimde sanatçı tür/etiket zenginleştirmesi yapar (SQLite önbellekli).
3. Ardışık dinlemeler arasındaki 30 dakikalık boşluklara göre dinleme oturumu
(`session_id`)
   atar ve `data/processed/listening_history.parquet` + `.csv` olarak kaydeder.
4. Henüz Spotify arşivi gelmediyse `--demo` parametresiyle boru hattını test
etmek için
   gerçekçi şemada örnek veri üretir.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
from pathlib import Path
import random
import sqlite3
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

SEED = 42
SESSION_GAP_MINUTES = 30
MIN_VALID_PLAY_MS = (
    30_000  # 30 saniyeden kısa dinlemeler "skip" (atlama) sayılır
)


def init_tag_cache(db_path: Path) -> sqlite3.Connection:
  """Last.fm API yanıtlarını önbelleklemek için yerel SQLite tablosu oluşturur."""
  db_path.parent.mkdir(parents=True, exist_ok=True)
  conn = sqlite3.connect(db_path)
  conn.execute("""
        CREATE TABLE IF NOT EXISTS artist_tags (
            artist_name TEXT PRIMARY KEY,
            primary_genre TEXT,
            tags_json TEXT,
            updated_at TEXT
        )
        """)
  conn.commit()
  return conn


def fetch_artist_genre_lastfm(
    artist_name: str,
    api_key: str | None,
    conn: sqlite3.Connection,
    rate_limit_sec: float = 0.35,
) -> str:
  """Sanatçının en popüler tür etiketini önce SQLite önbellekten, yoksa Last.fm API'den çeker.

  Hız sınırı (saniyede <= 3 istek) kurallarına uyar.
  """
  cur = conn.execute(
      "SELECT primary_genre FROM artist_tags WHERE artist_name = ?",
      (artist_name,),
  )
  row = cur.fetchone()
  if row is not None:
    return row[0]

  if not api_key:
    return "unknown"

  params = urlencode({
      "method": "artist.gettoptags",
      "artist": artist_name,
      "api_key": api_key,
      "format": "json",
  })
  url = f"https://ws.audioscrobbler.com/2.0/?{params}"
  req = Request(
      url,
      headers={
          "User-Agent": "SpotifyMiningProject/1.0 (Student Research Project)"
      },
  )

  try:
    time.sleep(rate_limit_sec)
    with urlopen(req, timeout=10) as resp:
      payload = json.loads(resp.read().decode("utf-8"))
    toptags = payload.get("toptags", {}).get("tag", [])
    if isinstance(toptags, list) and len(toptags) > 0:
      tags = [t.get("name", "").lower() for t in toptags[:5] if t.get("name")]
      primary = tags[0] if tags else "unknown"
    else:
      tags = []
      primary = "unknown"
  except Exception:
    tags = []
    primary = "unknown"

  conn.execute(
      "INSERT OR REPLACE INTO artist_tags (artist_name, primary_genre,"
      " tags_json, updated_at) VALUES (?, ?, ?, ?)",
      (
          artist_name,
          primary,
          json.dumps(tags, ensure_ascii=False),
          datetime.utcnow().isoformat(),
      ),
  )
  conn.commit()
  return primary


def load_spotify_raw_json(raw_dir: Path) -> pd.DataFrame:
  """Spotify Hesap Verisi (`StreamingHistory_music_*.json`) veya

  Genişletilmiş Geçmiş (`Streaming_History_Audio_*.json`) dosyalarını okur ve
  standart şemaya dönüştürür.
  """
  json_files = sorted(raw_dir.glob("*Streaming*History*.json")) + sorted(
      raw_dir.glob("endsong_*.json")
  )
  if not json_files:
    raise FileNotFoundError(
        f"'{raw_dir}' içinde Spotify JSON dosyası bulunamadı. "
        "Test için '--demo' bayrağını kullanabilir veya Spotify JSON"
        " dosyalarınızı data/raw/ klasörüne koyabilirsiniz."
    )

  records: list[dict[str, Any]] = []
  for fpath in json_files:
    with open(fpath, "r", encoding="utf-8") as f:
      items = json.load(f)
    for item in items:
      # Standart StreamingHistory şeması vs Extended Streaming History şeması
      if "endTime" in item:
        ts_str = item.get("endTime")
        artist = item.get("artistName")
        track = item.get("trackName")
        ms_played = int(item.get("msPlayed", 0))
        reason_end = "completed" if ms_played >= MIN_VALID_PLAY_MS else "fwdbtn"
      else:
        ts_str = item.get("ts")
        artist = item.get("master_metadata_album_artist_name")
        track = item.get("master_metadata_track_name")
        ms_played = int(item.get("ms_played", 0))
        reason_end = item.get("reason_end", "unknown")

      if not ts_str or not artist or not track:
        continue

      records.append({
          "played_at": ts_str,
          "artist_name": str(artist).strip(),
          "track_name": str(track).strip(),
          "ms_played": ms_played,
          "reason_end": str(reason_end),
      })

  df = pd.DataFrame(records)
  df["played_at"] = pd.to_datetime(df["played_at"], utc=True, errors="coerce")
  df = (
      df.dropna(subset=["played_at"])
      .sort_values("played_at")
      .reset_index(drop=True)
  )
  return df


def generate_demo_dataset(n_rows: int = 5500, seed: int = SEED) -> pd.DataFrame:
  """Spotify dışa aktarım arşivi beklenirken boru hattını uçtan uca test etmek için

  5.500 satırlık gerçekçi oturum ve geçiş yapısına sahip örnek veri üretir.
  """
  rng = random.Random(seed)
  np_rng = np.random.default_rng(seed)

  catalog = [
      (
          "Duman",
          "Türkçe Rock",
          ["Senden Daha Güzel", "Kufi", "Her Şeyi Yak", "Öyle Dertli"],
      ),
      (
          "Mor ve Ötesi",
          "Türkçe Rock",
          ["Bir Derdim Var", "Cambaz", "Deli", "Oyunbozan"],
      ),
      (
          "Şebnem Ferah",
          "Türkçe Rock",
          ["Sil Baştan", "Bu Aşk Fazla Sana", "Mayın Tarlası"],
      ),
      (
          "Mabel Matiz",
          "Türkçe Pop",
          ["Antidepresan", "Fırtınadayım", "Öyle Kolaysa", "Numaracı"],
      ),
      ("Sezen Aksu", "Türkçe Pop", ["Firuze", "Tükeneceğiz", "Gülümse"]),
      (
          "Tame Impala",
          "Indie / Psychedelic",
          ["The Less I Know The Better", "Let It Happen", "Borderline"],
      ),
      (
          "Arctic Monkeys",
          "Indie Rock",
          ["Do I Wanna Know?", "505", "R U Mine?", "Snap Out of It"],
      ),
      ("Radiohead", "Alternative Rock", ["Creep", "Karma Police", "No Surprises"]),
      (
          "The Weeknd",
          "Synthpop / R&B",
          ["Blinding Lights", "Starboy", "Save Your Tears"],
      ),
      ("Daft Punk", "Electronic", ["Instant Crush", "Get Lucky", "Veridis Quo"]),
      ("Ezhel", "Türkçe Rap", ["Geceler", "Felaket", "Margiela"]),
      ("Ceza", "Türkçe Rap", ["Yerli Plaka", "Suspus", "Holocaust"]),
      (
          "Ludovico Einaudi",
          "Instrumental / Focus",
          ["Experience", "Nuvole Bianche", "Una Mattina"],
      ),
      (
          "Ólafur Arnalds",
          "Instrumental / Focus",
          ["Saman", "Near Light", "Brot"],
      ),
  ]

  rows: list[dict[str, Any]] = []
  current_time = datetime(2026, 4, 1, 9, 15, 0)

  while len(rows) < n_rows:
    # Oturum bağlamı seç (ders çalışma/odaklanma, yolculuk, akşam dinlenmesi)
    hour = current_time.hour
    if 9 <= hour < 17:
      weights = [1, 1, 1, 1, 1, 2, 2, 2, 1, 2, 1, 1, 4, 4]
    elif 17 <= hour < 22:
      weights = [4, 4, 3, 3, 2, 3, 3, 2, 3, 2, 3, 2, 1, 1]
    else:
      weights = [2, 2, 2, 2, 3, 3, 2, 3, 2, 2, 1, 1, 3, 3]

    session_len = int(np_rng.integers(4, 18))
    for _ in range(session_len):
      if len(rows) >= n_rows:
        break
      artist, genre, tracks = rng.choices(catalog, weights=weights, k=1)[0]
      track = rng.choice(tracks)
      is_skipped = rng.random() < 0.16
      if is_skipped:
        ms_played = int(np_rng.integers(4_000, 28_000))
        reason_end = "fwdbtn"
      else:
        ms_played = int(np_rng.integers(140_000, 260_000))
        reason_end = "trackdone"

      current_time += timedelta(milliseconds=ms_played + int(np_rng.integers(1_000, 8_000)))
      rows.append({
          "played_at": pd.Timestamp(current_time, tz="UTC"),
          "artist_name": artist,
          "track_name": track,
          "primary_genre": genre,
          "ms_played": ms_played,
          "reason_end": reason_end,
      })

    # Oturumlar arası boşluk (45 dk ile 14 saat arası)
    gap_minutes = int(np_rng.integers(45, 720))
    current_time += timedelta(minutes=gap_minutes)

  return pd.DataFrame(rows)


def enrich_and_segment_sessions(df: pd.DataFrame) -> pd.DataFrame:
  """Zaman serisi ve oturum (session) özniteliklerini çıkarır."""
  df = df.sort_values("played_at").reset_index(drop=True)
  df["minutes_played"] = (df["ms_played"] / 60_000.0).round(3)
  df["is_skipped"] = df["ms_played"] < MIN_VALID_PLAY_MS

  # Ardışık parçalar arası süre farkı (dakika)
  time_diff_min = df["played_at"].diff().dt.total_seconds().div(60.0).fillna(0.0)
  df["gap_minutes"] = time_diff_min.round(2)
  df["is_new_session"] = (time_diff_min > SESSION_GAP_MINUTES) | (df.index == 0)
  df["session_id"] = df["is_new_session"].cumsum()

  # Takvim ve saat dilimi öznitelikleri
  local_dt = df["played_at"].dt.tz_convert("Europe/Istanbul")
  df["hour"] = local_dt.dt.hour
  df["day_of_week"] = local_dt.dt.day_name()
  df["is_weekend"] = local_dt.dt.dayofweek >= 5

  return df


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Spotify Kişisel Dinleme Verisi Toplama ve Hazırlama"
  )
  parser.add_argument(
      "--raw-dir",
      type=Path,
      default=Path("data/raw"),
      help="Ham Spotify JSON klasörü",
  )
  parser.add_argument(
      "--out-dir",
      type=Path,
      default=Path("data/processed"),
      help="İşlenmiş veri çıktı klasörü",
  )
  parser.add_argument(
      "--lastfm-api-key",
      type=str,
      default=None,
      help="İsteğe bağlı Last.fm API anahtarı",
  )
  parser.add_argument(
      "--demo",
      action="store_true",
      help="Örnek 5.500 satırlık veriyle boru hattını test et",
  )
  args = parser.parse_args()

  args.out_dir.mkdir(parents=True, exist_ok=True)

  if args.demo:
    print(
        "[INFO] Demo modu: 5.500 satırlık örnek dinleme geçmişi üretiliyor..."
    )
    df = generate_demo_dataset(n_rows=5500, seed=SEED)
  else:
    print(
        f"[INFO] '{args.raw_dir}' klasöründeki Spotify JSON dosyaları"
        " okunuyor..."
    )
    df = load_spotify_raw_json(args.raw_dir)
    conn = init_tag_cache(args.out_dir / "artist_tags_cache.sqlite")
    unique_artists = df["artist_name"].unique()
    print(
        f"[INFO] {len(unique_artists)} tekil sanatçı için tür/etiket"
        " önbelleği kontrol ediliyor..."
    )
    genre_map = {
        artist: fetch_artist_genre_lastfm(artist, args.lastfm_api_key, conn)
        for artist in unique_artists
    }
    df["primary_genre"] = df["artist_name"].map(genre_map)
    conn.close()

  df = enrich_and_segment_sessions(df)

  parquet_path = args.out_dir / "listening_history.parquet"
  csv_path = args.out_dir / "listening_history_sample.csv"
  df.to_parquet(parquet_path, index=False)
  df.head(200).to_csv(csv_path, index=False)

  print(f"[OK] Toplam dinleme kaydı: {len(df):,} satır")
  print(f"[OK] Tekil sanatçı sayısı: {df['artist_name'].nunique():,}")
  print(f"[OK] Tekil şarkı sayısı  : {df['track_name'].nunique():,}")
  print(f"[OK] Tespit edilen oturum: {df['session_id'].nunique():,}")
  print(f"[OK] Kaydedilen dosya    : {parquet_path}")


if __name__ == "__main__":
  main()