#!/usr/bin/env python3
"""Hafta 2 — Otomatik / Periyodik Veri Toplama ve Ham Veri Arşivleme Betiği

(src/collect/periodic_collector.py)

Proje: Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve
Sonraki Şarkı Önerisi
Öğrenci: Hasan Kaplan (256066007)

Hafta 2 Gereksinimleri (Şartname Bölüm 07):
- "Otomatik ve periyodik toplama başlar, ham veri arşivlenir, veri sözlüğü
taslağı yazılır."

Bu betik:
1. Spotify Kişisel Veri Dışa Aktarımı (`data/raw/StreamingHistory_music_*.json`)
dosyalarını ve/veya
   Last.fm API (`user.getRecentTracks`) üzerinden son dinlenen şarkıları
   periyodik olarak çeker.
2. Her çekim çalışmasında ham yanıtı zaman damgalı olarak
`data/raw/archive/snapshot_YYYYMMDD_HHMMSS.json`
   altında arşivler ve `data/raw/collection_manifest.csv` kayıt defterine
   (log) işler.
3. Sanatçıların müzik türü etiketlerini hız sınırına (<= 3 istek/sn) uyarak
Last.fm API'den
   (`artist.getTopTags`) çeker ve yerel SQLite önbelleğine
   (`data/processed/artist_tags_cache.sqlite`) yazar.
4. Tüm ham kayıtları birleştirip henüz temizleme/EDA uygulanmamış ham birleşik
tablo olarak
   `data/processed/raw_combined_history.parquet` dosyasına kaydeder.
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

# Hafta 1'deki temel toplama modülünden yardımcı fonksiyonları içe aktarır
try:
  from collect_spotify import (
      SEED,
      fetch_artist_genre_lastfm,
      generate_demo_dataset,
      init_tag_cache,
      load_spotify_raw_json,
  )
except ImportError:
  import sys

  sys.path.append(str(Path(__file__).resolve().parent))
  from collect_spotify import (
      SEED,
      fetch_artist_genre_lastfm,
      generate_demo_dataset,
      init_tag_cache,
      load_spotify_raw_json,
  )


def fetch_recent_tracks_lastfm(
    username: str,
    api_key: str,
    limit: int = 200,
    from_unix: int | None = None,
) -> list[dict[str, Any]]:
  """Last.fm API (user.getRecentTracks) üzerinden kullanıcının son dinlediği parçaları çeker."""
  params: dict[str, Any] = {
      "method": "user.getrecenttracks",
      "user": username,
      "api_key": api_key,
      "limit": min(limit, 200),
      "format": "json",
  }
  if from_unix is not None:
    params["from"] = from_unix

  url = f"https://ws.audioscrobbler.com/2.0/?{urlencode(params)}"
  req = Request(
      url,
      headers={
          "User-Agent": "SpotifyMiningProject/1.0 (Student Research Project)"
      },
  )

  time.sleep(0.35)  # Hız sınırı: saniyede en fazla 3 istek
  with urlopen(req, timeout=15) as resp:
    payload = json.loads(resp.read().decode("utf-8"))

  tracks = payload.get("recenttracks", {}).get("track", [])
  if isinstance(tracks, dict):
    tracks = [tracks]

  parsed: list[dict[str, Any]] = []
  for item in tracks:
    # Şu an çalmakta olan ("nowplaying") parçanın bitiş zamanı henüz yoktur, atla
    if item.get("@attr", {}).get("nowplaying") == "true":
      continue
    date_info = item.get("date", {})
    uts = date_info.get("uts")
    if not uts:
      continue
    played_at = datetime.fromtimestamp(int(uts), tz=timezone.utc).strftime(
        "%Y-%m-%d %H:%M"
    )
    artist = item.get("artist", {}).get("#text", "").strip()
    track = item.get("name", "").strip()
    if artist and track:
      parsed.append({
          "endTime": played_at,
          "artistName": artist,
          "trackName": track,
          "msPlayed": 180_000,  # Last.fm skroplama varsayılan süresi (~3 dk)
          "source": "lastfm_recent_api",
      })
  return parsed


def archive_raw_snapshot(
    records: list[dict[str, Any]],
    archive_dir: Path,
    source_label: str,
) -> tuple[Path, str]:
  """Çekilen ham veriyi zaman damgalı JSON olarak arşivler ve SHA-256 özeti üretir."""
  archive_dir.mkdir(parents=True, exist_ok=True)
  ts_label = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
  snapshot_path = archive_dir / f"snapshot_{source_label}_{ts_label}.json"

  raw_bytes = json.dumps(records, ensure_ascii=False, indent=2).encode("utf-8")
  sha256_hash = hashlib.sha256(raw_bytes).hexdigest()[:16]

  with open(snapshot_path, "wb") as f:
    f.write(raw_bytes)

  return snapshot_path, sha256_hash


def append_collection_manifest(
    manifest_path: Path,
    snapshot_path: Path,
    source_label: str,
    row_count: int,
    unique_artists: int,
    sha256_short: str,
) -> None:
  """Her veri toplama çalışmasını `data/raw/collection_manifest.csv` dosyasına kayıt düşer."""
  manifest_path.parent.mkdir(parents=True, exist_ok=True)
  file_exists = manifest_path.exists()

  with open(manifest_path, "a", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    if not file_exists:
      writer.writerow([
          "collected_at_utc",
          "source",
          "snapshot_file",
          "row_count",
          "unique_artists",
          "sha256_prefix",
      ])
    writer.writerow([
        datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        source_label,
        snapshot_path.name,
        row_count,
        unique_artists,
        sha256_short,
    ])


def main() -> None:
  parser = argparse.ArgumentParser(
      description=(
          "Hafta 2: Otomatik ve Periyodik Veri Toplama ve Ham Veri Arşivleme"
      )
  )
  parser.add_argument(
      "--raw-dir",
      type=Path,
      default=Path("data/raw"),
      help="Ham veri ve arşiv klasörü",
  )
  parser.add_argument(
      "--out-dir",
      type=Path,
      default=Path("data/processed"),
      help="Birleştirilmiş veri klasörü",
  )
  parser.add_argument(
      "--lastfm-user",
      type=str,
      default=None,
      help="Periyodik çekim için Last.fm kullanıcı adı",
  )
  parser.add_argument(
      "--lastfm-api-key",
      type=str,
      default=None,
      help="Last.fm API anahtarı",
  )
  parser.add_argument(
      "--demo",
      action="store_true",
      help="Gerçekçi örnek veriyle Hafta 2 arşivleme akışını test et",
  )
  args = parser.parse_args()

  archive_dir = args.raw_dir / "archive"
  manifest_path = args.raw_dir / "collection_manifest.csv"
  args.out_dir.mkdir(parents=True, exist_ok=True)

  if args.demo:
    print("[INFO] Hafta 2 Demo Modu: Periyodik veri çekimi ve ham arşivleme simüle ediliyor...")
    df = generate_demo_dataset(n_rows=5500, seed=SEED)
    raw_records = (
        df.assign(played_at=df["played_at"].astype(str))
        .to_dict(orient="records")
    )
    source_label = "spotify_export_and_api_demo"
  else:
    records_list: list[dict[str, Any]] = []
    source_label = "spotify_local_json"

    # 1. Yerel Spotify JSON dışa aktarım dosyalarını oku
    try:
      df_local = load_spotify_raw_json(args.raw_dir)
      records_list.extend(
          df_local.assign(played_at=df_local["played_at"].astype(str)).to_dict(
              orient="records"
          )
      )
    except FileNotFoundError:
      print("[WARN] Yerel Spotify JSON bulunamadı, yalnızca API kontrol edilecek.")

    # 2. Varsa Last.fm API üzerinden son dinlenenleri periyodik olarak ekle
    if args.lastfm_user and args.lastfm_api_key:
      print(f"[INFO] Last.fm kullanıcısı '{args.lastfm_user}' için son dinlenenler çekiliyor...")
      recent_api = fetch_recent_tracks_lastfm(
          args.lastfm_user, args.lastfm_api_key, limit=200
      )
      for item in recent_api:
        records_list.append({
            "played_at": item["endTime"],
            "artist_name": item["artistName"],
            "track_name": item["trackName"],
            "ms_played": item["msPlayed"],
            "reason_end": "trackdone",
        })
      source_label = "spotify_plus_lastfm_periodic"

    if not records_list:
      raise RuntimeError(
          "Hiçbir veri kaynağı bulunamadı! Lütfen 'data/raw/' içine Spotify JSON"
          " dosyalarını koyun veya '--demo' parametresiyle çalıştırın."
      )

    raw_records = records_list
    df = pd.DataFrame(raw_records)
    df["played_at"] = pd.to_datetime(df["played_at"], utc=True, errors="coerce")

    # Sanatçı türlerini SQLite önbellekli olarak zenginleştir
    conn = init_tag_cache(args.out_dir / "artist_tags_cache.sqlite")
    unique_artists = df["artist_name"].dropna().unique()
    genre_map = {
        artist: fetch_artist_genre_lastfm(artist, args.lastfm_api_key, conn)
        for artist in unique_artists
    }
    df["primary_genre"] = df["artist_name"].map(genre_map)
    conn.close()

  # Ham anlık görüntüyü (snapshot) arşivle ve manifest'e kaydet
  snapshot_path, sha_short = archive_raw_snapshot(
      raw_records[:500],  # Arşiv şişmesini önlemek için anlık örnek paket kaydı
      archive_dir=archive_dir,
      source_label=source_label,
  )
  append_collection_manifest(
      manifest_path=manifest_path,
      snapshot_path=snapshot_path,
      source_label=source_label,
      row_count=len(df),
      unique_artists=int(df["artist_name"].nunique()),
      sha256_short=sha_short,
  )

  # Hafta 2 birleştirilmiş ham veri tablosunu Parquet olarak kaydet (Temizleme Hafta 3'te yapılacak)
  combined_parquet = args.out_dir / "raw_combined_history.parquet"
  df.to_parquet(combined_parquet, index=False)

  print(f"[OK] Ham veri anlık görüntüsü arşivlendi : {snapshot_path}")
  print(f"[OK] Veri toplama kayıt defteri (log)    : {manifest_path}")
  print(f"[OK] Birleştirilmiş ham tablo (Parquet)  : {combined_parquet} ({len(df):,} satır)")


if __name__ == "__main__":
  main()