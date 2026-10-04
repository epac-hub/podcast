#!/usr/bin/env python3
"""Transcribe an episode's audio with Whisper (faster-whisper).

Writes into the episode directory:
  - transcript.txt   (plain text)
  - transcript.vtt   (WebVTT with timestamps; linked from the RSS feed)

The glossary in scripts/glossary.json is passed to Whisper as the initial
prompt (so proper nouns such as Triple-S, Vieques or ASES are spelled right)
and its replacement rules are applied to every line afterwards.

Usage:
  python3 scripts/transcribe.py episodes/001-my-episode [--model small] [--language en]
  python3 scripts/transcribe.py episodes/001-my-episode --fix-only   # re-apply the
      glossary replacements to an existing transcript without running Whisper
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GLOSSARY = ROOT / "scripts" / "glossary.json"


def fmt_ts(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    h, rem = divmod(ms, 3_600_000)
    m, rem = divmod(rem, 60_000)
    s, ms = divmod(rem, 1000)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"


def load_glossary(path: Path = GLOSSARY) -> dict:
    if not path.exists():
        return {"prompt": "", "replacements": []}
    g = json.loads(path.read_text())
    rules = []
    for pattern, repl, flags in g.get("replacements", []):
        f = re.IGNORECASE if "i" in flags else 0
        rules.append((re.compile(pattern, f), repl))
    return {"prompt": g.get("prompt", ""), "rules": rules}


def fix_text(text: str, glossary: dict) -> str:
    for rx, repl in glossary.get("rules", []):
        text = rx.sub(repl, text)
    return text


def fix_transcript_files(ep_dir: Path, glossary: dict) -> int:
    """Apply the glossary rules to transcript.txt and transcript.vtt in place.
    Returns the number of lines changed."""
    changed = 0
    for name in ("transcript.txt", "transcript.vtt"):
        f = ep_dir / name
        if not f.exists():
            continue
        lines = f.read_text().split("\n")
        out = []
        for ln in lines:
            if name.endswith(".vtt") and ("-->" in ln or ln == "WEBVTT"):
                out.append(ln)
                continue
            new = fix_text(ln, glossary)
            if new != ln:
                changed += 1
            out.append(new)
        f.write_text("\n".join(out))
    return changed


def transcribe_episode(ep_dir: Path, model_size: str = "small", language: str | None = "en",
                       glossary: dict | None = None, verbose: bool = True) -> dict:
    audio = ep_dir / "episode.mp3"
    if not audio.exists():
        sys.exit(f"error: {audio} not found")
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        sys.exit("error: faster-whisper not installed (pip install faster-whisper)")

    glossary = glossary or load_glossary()
    if verbose:
        print(f"loading whisper model '{model_size}'...")
    model = WhisperModel(model_size, device="cpu", compute_type="int8")
    segments, info = model.transcribe(
        str(audio), language=language, vad_filter=True,
        initial_prompt=glossary.get("prompt") or None,
    )

    txt_lines, vtt_lines = [], ["WEBVTT", ""]
    for seg in segments:
        text = fix_text(seg.text.strip(), glossary)
        if not text:
            continue
        txt_lines.append(text)
        vtt_lines += [f"{fmt_ts(seg.start)} --> {fmt_ts(seg.end)}", text, ""]
        if verbose:
            print(f"  [{fmt_ts(seg.start)}] {text}")

    (ep_dir / "transcript.txt").write_text("\n".join(txt_lines) + "\n")
    (ep_dir / "transcript.vtt").write_text("\n".join(vtt_lines) + "\n")

    meta_path = ep_dir / "metadata.json"
    meta = json.loads(meta_path.read_text())
    meta["transcript"] = "transcript.vtt"
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")
    if verbose:
        print(f"wrote transcript.txt and transcript.vtt (language: {info.language})")
    return {"language": info.language, "lines": len(txt_lines)}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("episode_dir", type=Path)
    p.add_argument("--model", default="small", help="Whisper model size: small (default) or medium (slower, more accurate)")
    p.add_argument("--language", default=None, help="Force language code, e.g. en")
    p.add_argument("--glossary", type=Path, default=GLOSSARY)
    p.add_argument("--fix-only", action="store_true", help="only re-apply glossary replacements to the existing transcript")
    args = p.parse_args()

    ep_dir = args.episode_dir if args.episode_dir.is_absolute() else ROOT / args.episode_dir
    glossary = load_glossary(args.glossary)
    if args.fix_only:
        n = fix_transcript_files(ep_dir, glossary)
        print(f"{ep_dir.name}: {n} line(s) fixed")
        return
    transcribe_episode(ep_dir, args.model, args.language, glossary)


if __name__ == "__main__":
    main()
