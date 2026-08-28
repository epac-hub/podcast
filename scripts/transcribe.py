#!/usr/bin/env python3
"""Transcribe an episode's audio with Whisper (faster-whisper).

Writes into the episode directory:
  - transcript.txt   (plain text)
  - transcript.vtt   (WebVTT with timestamps; linked from the RSS feed)

Usage:
  python3 scripts/transcribe.py episodes/001-my-episode [--model small] [--language en]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def fmt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("episode_dir", type=Path)
    p.add_argument("--model", default="small", help="Whisper model size (default: small)")
    p.add_argument("--language", default=None, help="Force language code, e.g. en")
    args = p.parse_args()

    ep_dir = args.episode_dir if args.episode_dir.is_absolute() else ROOT / args.episode_dir
    audio = ep_dir / "episode.mp3"
    if not audio.exists():
        sys.exit(f"error: {audio} not found")

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("error: faster-whisper not installed (pip install faster-whisper)")

    print(f"loading whisper model '{args.model}'...")
    model = WhisperModel(args.model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(audio), language=args.language, vad_filter=True)

    txt_lines, vtt_lines = [], ["WEBVTT", ""]
    for seg in segments:
        text = seg.text.strip()
        if not text:
            continue
        txt_lines.append(text)
        vtt_lines += [f"{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}", text, ""]
        print(f"  [{fmt_ts(seg.start)}] {text}")

    (ep_dir / "transcript.txt").write_text("\n".join(txt_lines) + "\n")
    (ep_dir / "transcript.vtt").write_text("\n".join(vtt_lines) + "\n")

    meta_path = ep_dir / "metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["transcript"] = "transcript.vtt"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n")

    print(f"wrote transcript.txt and transcript.vtt (language: {info.language})")


if __name__ == "__main__":
    main()
