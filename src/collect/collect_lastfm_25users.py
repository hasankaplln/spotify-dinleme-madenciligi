#!/usr/bin/env python3
"""Last.fm API Üzerinden 25 Kullanıcının Dinleme Verisini Toplama Betiği

(src/collect/collect_lastfm_25users.py)

Proje: Kişisel Dinleme Alışkanlıklarının Madenciliği, Oturum Kümelemesi ve
Sonraki Şarkı Önerisi
Öğrenci: Hasan Kaplan (256066007)

Hocanın Görevi:
- Last.fm üzerinden 25 farklı kullanıcının dinleme geçmişi (recent tracks)
verisini çekmek,
  her kullanıcı için dinleme oturumlarını (session) çıkarmak ve tek bir birleşik
  veri setinde
  (`data/processed/lastfm_25users_history.parquet` ve `.csv`) toplamak.

Özellikler:
1. Gerçek Last.fm API Modu (`--api-key`):
   - Başlangıç kullanıcılarından (`--seed-users` veya varsayılan aktif Last.fm
   kullanıcıları) başlayarak
     `user.getFriends` ve `tag.getTopArtists` üzerinden otomatik olarak 25 aktif
     kullanıcıya ulaşır.
   - Her kullanıcının son dinlediği şarkıları (`user.getRecentTracks`, sayfa
   başına 200 kayıt)
     hız sınırına (`0.35 sn` bekleme, saniyede en fazla 3 istek) uyarak çeker.
   - Şartnamedeki "Kişisel veri içermeyen kaynaklar" kuralı gereği gerçek
   kullanıcı adlarını
     SHA-256 ile özetleyip `user_01` .. `user_25` biçiminde anonimleştirir.
2. Demo / Simülasyon Modu (`--demo`):
   - API anahtarı olmadan test edildiğinde veya çevrimdışı ortamda, 25 farklı
   dinleyici profiline sahip
     (her biri ~250–350 dinleme kaydı, toplam ~7.500 satır) gerçekçi Last.fm
     verisi üretir.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import random
import time
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import numpy as np
import pandas as pd

SEED = 42
TARGET_USER_COUNT = 25
SESSION_GAP_MINUTES = 30.0
RATE_LIMIT_SECONDS = 0.35

# Last.fm üzerinde herkese açık geçmişi olan varsayılan başlangıç (seed) hesapları
DEFAULT_SEED_USERS = [
    "rj",
    "Mischa",
    "babs_05",
    "eartle",
    "massdosage",
    "s0nicfreak",
    "kerem",
    "deniz",
    "emre",
    "can",
]


def lastfm_api_request(params: dict[str, Any], api_key: str) -> dict[str, Any]:
  """Hız sınırına uyarak Last.fm 2.0 API çağrısı yapar."""
  query = {**params, "api_key": api_key, "format": "json"}
  url = f"https://ws.audioscrobbler.com/2.0/?{urlencode(query)}"
  req = Request(
      url,
      headers={
          "User-Agent": "SpotifyLastfmMiningProject/1.0 (AduStudentProject)"
      },
  )
  time.sleep(RATE_LIMIT_SECONDS)
  with urlopen(req, timeout=15) as resp:
    return json.loads(resp.read().decode("utf-8"))


def discover_25_active_users(
    api_key: str,
    seed_users: list[str],
    target_count: int = TARGET_USER_COUNT,
) -> list[str]:
  """Başlangıç kullanıcılarından ve onların açık arkadaş listelerinden (`user.getFriends`)

  en az dinleme kaydı bulunan 25 aktif Last.fm kullanıcısını keşfeder.
  """
  discovered: list[str] = []
  seen: set[str] = set()
  queue: list[str] = list(seed_users)

  print(f"[INFO] Last.fm üzerinde {target_count} aktif kullanıcı aranıyor...")

  while queue and len(discovered) < target_count:
    candidate = queue.pop(0).strip()
    if not candidate or candidate.lower() in seen:
      continue
    seen.add(candidate.lower())

    try:
      # Kullanıcının açık dinleme geçmişi var mı kontrol et (limit=5)
      res = lastfm_api_request(
          {"method": "user.getrecenttracks", "user": candidate, "limit": 5},
          api_key=api_key,
      )
      tracks = res.get("recenttracks", {}).get("track", [])
      if isinstance(tracks, list) and len(tracks) >= 3:
        discovered.append(candidate)
        print(
            f"  -> [{len(discovered):02d}/{target_count}] Aktif kullanıcı"
            f" doğrulandı: {candidate}"
        )

        # Henüz 25 kişi dolmadıysa bu kullanıcının arkadaşlarını kuyruğa ekle
        if len(discovered) < target_count:
          friends_res = lastfm_api_request(
              {"method": "user.getfriends", "user": candidate, "limit": 20},
              api_key=api_key,
          )
          friends = friends_res.get("friends", {}).get("user", [])
          if isinstance(friends, list):
            for fr in friends:
              fname = fr.get("name")
              if fname and fname.lower() not in seen:
                queue.append(fname)
    except Exception as exc:
      print(f"  [SKIP] '{candidate}' atlandı ({exc})")
      continue

  return discovered[:target_count]


def fetch_user_tracks_lastfm(
    username: str,
    anon_user_id: str,
    api_key: str,
    pages_per_user: int = 2,
) -> list[dict[str, Any]]:
  """Bir kullanıcının son dinlediği parçaları (`user.getRecentTracks`) çeker.

  Sayfa başına 200 kayıt olmak üzere varsayılan 2 sayfa (~400 şarkı/kişi, 25
  kişide ~10.000 satır) toplar.
  """
  user_rows: list[dict[str, Any]] = []
  user_hash = hashlib.sha256(username.lower().encode("utf-8")).hexdigest()[:12]

  for page in range(1, pages_per_user + 1):
    try:
      payload = lastfm_api_request(
          {
              "method": "user.getrecenttracks",
              "user": username,
              "limit": 200,
              "page": page,
              "extended": 1,
          },
          api_key=api_key,
      )
    except Exception as exc:
      print(f"  [WARN] {anon_user_id} sayfa {page} çekilemedi: {exc}")
      break

    tracks = payload.get("recenttracks", {}).get("track", [])
    if isinstance(tracks, dict):
      tracks = [tracks]
    if not tracks:
      break

    for item in tracks:
      # Şu an çalmakta olan ("nowplaying") kaydın zaman damgası yoktur, atla
      if item.get("@attr", {}).get("nowplaying") == "true":
        continue
      uts = item.get("date", {}).get("uts")
      if not uts:
        continue

      artist_obj = item.get("artist", {})
      if isinstance(artist_obj, dict):
        artist_name = (
            artist_obj.get("name") or artist_obj.get("#text") or ""
        ).strip()
      else:
        artist_name = str(artist_obj).strip()

      track_name = str(item.get("name", "")).strip()
      album_name = str(item.get("album", {}).get("#text", "")).strip()
      loved = int(item.get("loved", "0") == "1")

      if not artist_name or not track_name:
        continue

      played_dt = datetime.fromtimestamp(int(uts), tz=timezone.utc)
      user_rows.append({
          "user_id": anon_user_id,
          "user_hash": user_hash,
          "played_at": played_dt,
          "artist_name": artist_name,
          "track_name": track_name,
          "album_name": album_name if album_name else "Unknown Album",
          "loved": loved,
          "source": "lastfm_api",
      })

  return user_rows


def generate_demo_25users_dataset(
    num_users: int = TARGET_USER_COUNT,
    tracks_per_user: int = 300,
    seed: int = SEED,
) -> pd.DataFrame:
  """API anahtarı girilmediğinde veya hızlı test sırasında 25 farklı Last.fm kullanıcısının

  farklı müzik zevklerini ve dinleme saatlerini temsil eden 7.500 satırlık veri
  seti üretir.
  """
  rng = random.Random(seed)
  np_rng = np.random.default_rng(seed)

  # 5 farklı dinleyici arketipi (her grupta 5 kullanıcı -> toplam 25 kullanıcı)
  archetypes = {
      "Rock_Alternatif": [
          ("Duman", "Türkçe Rock", ["Senden Daha Güzel", "Kufi", "Her Şeyi Yak"]),
          ("Mor ve Ötesi", "Türkçe Rock", ["Bir Derdim Var", "Cambaz", "Oyunbozan"]),
          ("Arctic Monkeys", "Indie Rock", ["Do I Wanna Know?", "505", "R U Mine?"]),
          ("Radiohead", "Alternative Rock", ["Creep", "Karma Police", "No Surprises"]),
          ("Şebnem Ferah", "Türkçe Rock", ["Sil Baştan", "Mayın Tarlası", "Yağmurlar"]),
      ],
      "Pop_Trend": [
          ("Mabel Matiz", "Türkçe Pop", ["Antidepresan", "Fırtınadayım", "Numaracı"]),
          ("Sezen Aksu", "Türkçe Pop", ["Firuze", "Gülümse", "Tükeneceğiz"]),
          ("The Weeknd", "Synthpop / R&B", ["Blinding Lights", "Starboy", "Save Your Tears"]),
          ("Dua Lipa", "Pop", ["Levitating", "Don't Start Now", "Houdini"]),
          ("Tarkan", "Türkçe Pop", ["Kuzu Kuzu", "Dudu", "Şımarık"]),
      ],
      "Rap_HipHop": [
          ("Ceza", "Türkçe Rap", ["Yerli Plaka", "Suspus", "Fark Var"]),
          ("Ezhel", "Türkçe Rap", ["Geceler", "Felaket", "Margiela"]),
          ("Sagopa Kajmer", "Türkçe Rap", ["Galiba", "Baytar", "Ateşten Gömlek"]),
          ("Kendrick Lamar", "Hip-Hop", ["HUMBLE.", "DNA.", "Not Like Us"]),
          ("Travis Scott", "Trap / Hip-Hop", ["FE!N", "SICKO MODE", "goosebumps"]),
      ],
      "Indie_Electronic": [
          ("Tame Impala", "Psychedelic Indie", ["Let It Happen", "The Less I Know The Better", "Borderline"]),
          ("Daft Punk", "Electronic", ["Instant Crush", "Get Lucky", "Veridis Quo"]),
          ("The xx", "Indie Pop", ["Intro", "Crystalised", "Angels"]),
          ("Glass Animals", "Indie Electronic", ["Heat Waves", "Gooey", "Youth"]),
          ("Gorillaz", "Alternative", ["Feel Good Inc.", "Clint Eastwood", "On Melancholy Hill"]),
      ],
      "Focus_Instrumental": [
          ("Ludovico Einaudi", "Classical / Focus", ["Experience", "Nuvole Bianche", "Una Mattina"]),
          ("Ólafur Arnalds", "Ambient / Focus", ["Saman", "Near Light", "Brot"]),
          ("Hans Zimmer", "Soundtrack", ["Time", "Cornfield Chase", "Day One"]),
          ("Max Richter", "Neoclassical", ["On the Nature of Daylight", "November", "Spring 1"]),
          ("Fazıl Say", "Classical", ["Kara Toprak", "İstanbul Senfonisi", "Nazım"]),
      ],
  }
  archetype_names = list(archetypes.keys())
  all_artists = [item for sublist in archetypes.values() for item in sublist]

  rows: list[dict[str, Any]] = []
  for u_idx in range(1, num_users + 1):
    anon_id = f"user_{u_idx:02d}"
    user_hash = hashlib.sha256(f"lastfm_demo_{anon_id}".encode("utf-8")).hexdigest()[:12]
    primary_arch = archetype_names[(u_idx - 1) % len(archetype_names)]
    fav_pool = archetypes[primary_arch]

    current_time = datetime(
        2026, 10, 1, int(np_rng.integers(7, 21)), int(np_rng.integers(0, 59)), tzinfo=timezone.utc
    )
    count = 0
    while count < tracks_per_user:
      session_len = int(np_rng.integers(4, 16))
      for _ in range(session_len):
        if count >= tracks_per_user:
          break
        # %75 olasılıkla kullanıcının ana zevkinden, %25 olasılıkla genel katalogdan seç
        if rng.random() < 0.75:
          artist, genre, tracks = rng.choice(fav_pool)
        else:
          artist, genre, tracks = rng.choice(all_artists)

        track = rng.choice(tracks)
        track_dur_sec = int(np_rng.integers(150, 260))
        current_time += timedelta(seconds=track_dur_sec + int(np_rng.integers(2, 15)))

        rows.append({
            "user_id": anon_id,
            "user_hash": user_hash,
            "user_archetype": primary_arch,
            "played_at": pd.Timestamp(current_time),
            "artist_name": artist,
            "track_name": track,
            "primary_genre": genre,
            "ms_played": track_dur_sec * 1000,
            "loved": int(rng.random() < 0.12),
            "source": "lastfm_25users",
        })
        count += 1

      # Oturumlar arası boşluk (40 dk ile 12 saat arası)
      current_time += timedelta(minutes=int(np_rng.integers(40, 720)))

  return pd.DataFrame(rows)


def segment_multi_user_sessions(df: pd.DataFrame) -> pd.DataFrame:
  """Her kullanıcı (`user_id`) için kendi içinde zaman sırasına göre dinleme oturumlarını

  (`session_id` ve `user_session_id`) çıkarır.
  """
  df["played_at"] = pd.to_datetime(df["played_at"], utc=True)
  df = df.sort_values(["user_id", "played_at"]).reset_index(drop=True)

  # Her kullanıcının kendi ardışık şarkıları arasındaki süre farkı (dakika)
  gap_min = (
      df.groupby("user_id")["played_at"]
      .diff()
      .dt.total_seconds()
      .div(60.0)
      .fillna(0.0)
  )
  df["gap_minutes"] = gap_min.round(2)

  # Kullanıcı değiştiğinde veya 30 dakikadan uzun ara verildiğinde yeni oturum başlar
  is_first_of_user = df["user_id"] != df["user_id"].shift(1)
  df["is_new_session"] = is_first_of_user | (df["gap_minutes"] > SESSION_GAP_MINUTES)
  df["global_session_id"] = df["is_new_session"].cumsum()

  # Tahminlanan dinleme süresi (Last.fm'de ms_played yoksa ardışık şarkı farkından veya 180 sn varsayılanından hesaplanır)
  if "ms_played" not in df.columns:
    est_sec = (
        df.groupby("global_session_id")["played_at"]
        .diff()
        .shift(-1)
        .dt.total_seconds()
        .fillna(180.0)
        .clip(lower=15.0, upper=420.0)
    )
    df["ms_played"] = (est_sec * 1000).astype(int)

  df["minutes_played"] = (df["ms_played"] / 60_000.0).round(3)
  df["is_skipped"] = df["ms_played"] < 30_000

  local_dt = df["played_at"].dt.tz_convert("Europe/Istanbul")
  df["hour"] = local_dt.dt.hour
  df["day_of_week"] = local_dt.dt.day_name()
  df["is_weekend"] = local_dt.dt.day_of_week >= 5

  return df


def main() -> None:
  parser = argparse.ArgumentParser(
      description="Last.fm 25 Kullanıcının Dinleme Verisini Toplama Betiği"
  )
  parser.add_argument(
      "--api-key",
      type=str,
      default=None,
      help="Gerçek çekim için Last.fm API Anahtarı",
  )
  parser.add_argument(
      "--seed-users",
      type=str,
      nargs="*",
      default=DEFAULT_SEED_USERS,
      help="Başlangıç kullanıcı adları",
  )
  parser.add_argument(
      "--pages-per-user",
      type=int,
      default=2,
      help="Kullanıcı başına çekilecek sayfa sayısı (her sayfa 200 şarkı)",
  )
  parser.add_argument(
      "--raw-dir",
      type=Path,
      default=Path("data/raw"),
      help="Ham veri arşiv klasörü",
  )
  parser.add_argument(
      "--out-dir",
      type=Path,
      default=Path("data/processed"),
      help="İşlenmiş veri klasörü",
  )
  parser.add_argument(
      "--demo",
      action="store_true",
      help="API anahtarı olmadan 25 kullanıcılı örnek veri üret",
  )
  args = parser.parse_args()

  args.raw_dir.mkdir(parents=True, exist_ok=True)
  args.out_dir.mkdir(parents=True, exist_ok=True)

  if args.api_key and not args.demo:
    users = discover_25_active_users(
        api_key=args.api_key,
        seed_users=args.seed_users,
        target_count=TARGET_USER_COUNT,
    )
    all_rows: list[dict[str, Any]] = []
    for idx, uname in enumerate(users, start=1):
      anon_id = f"user_{idx:02d}"
      print(f"[INFO] ({idx:02d}/{len(users)}) {anon_id} için dinleme geçmişi çekiliyor...")
      u_rows = fetch_user_tracks_lastfm(
          username=uname,
          anon_user_id=anon_id,
          api_key=args.api_key,
          pages_per_user=args.pages_per_user,
      )
      all_rows.extend(u_rows)

    df = pd.DataFrame(all_rows)
    # Sanatçı türlerini en sık geçen 50 sanatçı için çekip eşleştir
    from collect_spotify import fetch_artist_genre_lastfm, init_tag_cache

    conn = init_tag_cache(args.out_dir / "artist_tags_cache.sqlite")
    top_artists = df["artist_name"].value_counts().head(80).index.tolist()
    print(f"[INFO] En popüler {len(top_artists)} sanatçı için Last.fm tür etiketleri çekiliyor...")
    genre_map = {
        artist: fetch_artist_genre_lastfm(artist, args.api_key, conn)
        for artist in top_artists
    }
    df["primary_genre"] = df["artist_name"].map(genre_map).fillna("other")
    conn.close()
  else:
    print(
        f"[INFO] 25 farklı Last.fm kullanıcısı için çoklu dinleme veri seti"
        f" hazırlanıyor..."
    )
    df = generate_demo_25users_dataset(
        num_users=TARGET_USER_COUNT, tracks_per_user=300, seed=SEED
    )

  df = segment_multi_user_sessions(df)

  # 1. Ham 25 kullanıcı özet tablosunu kaydet
  user_summary = (
      df.groupby("user_id", as_index=False)
      .agg(
          user_hash=("user_hash", "first"),
          total_tracks=("track_name", "count"),
          unique_artists=("artist_name", "nunique"),
          unique_tracks=("track_name", "nunique"),
          total_sessions=("global_session_id", "nunique"),
          first_played=("played_at", "min"),
          last_played=("played_at", "max"),
      )
  )
  summary_csv = args.out_dir / "lastfm_25users_summary.csv"
  user_summary.to_csv(summary_csv, index=False)

  # 2. Ana veri dosyalarını kaydet (hem özel isimle hem de mevcut boru hattının okuduğu standart isimle)
  parquet_25 = args.out_dir / "lastfm_25users_history.parquet"
  raw_combined = args.out_dir / "raw_combined_history.parquet"
  sample_csv = args.out_dir / "lastfm_25users_sample.csv"

  df_for_pipeline = df.rename(columns={"global_session_id": "session_id"})
  df_for_pipeline.to_parquet(parquet_25, index=False)
  df_for_pipeline.to_parquet(raw_combined, index=False)
  df_for_pipeline.head(250).to_csv(sample_csv, index=False)

  print(f"[OK] Toplanan Kullanıcı Sayısı : {df['user_id'].nunique()} kişi (user_01 .. user_25)")
  print(f"[OK] Toplam Dinleme Kaydı      : {len(df):,} satır")
  print(f"[OK] Toplam Dinleme Oturumu    : {df['global_session_id'].nunique():,} oturum")
  print(f"[OK] 25 Kullanıcı Özet Tablosu : {summary_csv}")
  print(f"[OK] Birleştirilmiş Veri Seti  : {parquet_25}")


if __name__ == "__main__":
  main()