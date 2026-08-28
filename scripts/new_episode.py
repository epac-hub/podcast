#!/usr/bin/env python3
"""Ingest an audio file as a new podcast episode.

Creates episodes/NNN-slug/ containing:
  - episode.mp3      (converted, loudness-normalized audio)
  - metadata.json    (episode metadata used by build.py)
  - notes.md         (show notes, markdown — edit freely)

Usage:
  python3 scripts/new_episode.py path/to/audio.m4a --title "My first episode" \
      [--description "..."] [--date 2026-08-28] [--number 3] [--slug my-slug]
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "episodes"


def slugify(text: str) -> str:
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-zA-Z0-9]+", "-", text).strip("-").lower()
    return text or "episode"


def next_number() -> int:
    numbers = []
    if EPISODES.exists():
        for d in EPISODES.iterdir():
            m = re.match(r"^(\d+)-", d.name)
            if m:
                numbers.append(int(m.group(1)))
    return max(numbers, default=0) + 1


def load_config() -> dict:
    with open(ROOT / "podcast.config.json") as f:
        return json.load(f)


def convert_audio(src: Path, dest: Path, bitrate: str, normalize: bool) -> None:
    """Convert to MP3 (CBR, 44.1 kHz). Falls back to a copy if src is already mp3
    and ffmpeg is unavailable."""
    if shutil.which("ffmpeg") is None:
        if src.suffix.lower() == ".mp3":
            print("warning: ffmpeg not found; copying mp3 without normalization")
            shutil.copy2(src, dest)
            return
        sys.exit("error: ffmpeg is required to convert non-mp3 audio")
    cmd = ["ffmpeg", "-y", "-i", str(src), "-vn", "-ar", "44100", "-ac", "2"]
    if normalize:
        # Apple Podcasts recommends about -16 LUFS for stereo.
        cmd += ["-af", "loudnorm=I=-16:TP=-1.5:LRA=11"]
    cmd += ["-c:a", "libmp3lame", "-b:a", bitrate, str(dest)]
    subprocess.run(cmd, check=True)


def audio_duration_seconds(path: Path) -> int:
    try:
        from mutagen.mp3 import MP3

        return int(round(MP3(str(path)).info.length))
    except Exception:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
            capture_output=True, text=True, check=True,
        )
        return int(round(float(out.stdout.strip())))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("audio", type=Path)
    p.add_argument("--title", required=True)
    p.add_argument("--description", default="")
    p.add_argument("--date", default=None, help="Publish date YYYY-MM-DD (default: today)")
    p.add_argument("--number", type=int, default=None)
    p.add_argument("--slug", default=None)
    p.add_argument("--season", type=int, default=None)
    p.add_argument("--explicit", action="store_true")
    args = p.parse_args()

    if not args.audio.exists():
        sys.exit(f"error: {args.audio} not found")

    config = load_config()
    number = args.number or next_number()
    slug = args.slug or slugify(args.title)
    ep_dir = EPISODES / f"{number:03d}-{slug}"
    ep_dir.mkdir(parents=True, exist_ok=True)

    dest = ep_dir / "episode.mp3"
    convert_audio(args.audio, dest, config.get("audio_bitrate", "128k"),
                  config.get("loudness_normalize", True))

    date = args.date or datetime.date.today().isoformat()
    meta = {
        "number": number,
        "slug": slug,
        "title": args.title,
        "description": args.description,
        "pubdate": date,
        "audio": "episode.mp3",
        "duration_seconds": audio_duration_seconds(dest),
        "bytes": dest.stat().st_size,
        "explicit": args.explicit,
        "season": args.season,
        "episode_type": "full",
        "transcript": None,
        "draft": False
    }
    with open(ep_dir / "metadata.json", "w") as f:
        json.dump(meta, f, indent=2)

    notes = ep_dir / "notes.md"
    if not notes.exists():
        notes.write_text(f"{args.description}\n" if args.description else "")

    print(f"created {ep_dir.relative_to(ROOT)}")
    print(f"  duration: {meta['duration_seconds']}s  size: {meta['bytes']} bytes")
    print("next: python3 scripts/transcribe.py " + str(ep_dir.relative_to(ROOT)))


if __name__ == "__main__":
    main()
