#!/usr/bin/env python3
"""Publish an episode end to end in one run.

New episode (everything):
  python3 scripts/publish_episode.py inbox/episode.m4a \
      --title "Episode title" --date 2026-09-30 --number 14 \
      [--short-title "Title for YouTube (<=100 chars)"] [--description "..."] \
      [--pubtime 07:30] [--model small|medium] [--language en] \
      [--cover assets/cover.jpg] [--tags "tag one,tag two"] [--no-transcribe] [--no-video]

Existing episode (redo selected steps, e.g. after editing notes.md):
  python3 scripts/publish_episode.py --episode episodes/014-... --steps yt-meta,build
  python3 scripts/publish_episode.py --episode episodes/014-... --steps transcribe,video,yt-meta,build

Steps:
  audio       convert + loudness-normalize the recording, splice the show intro and
              outro bumpers around it -> episodes/NNN-slug/episode.mp3
  metadata    metadata.json (number, title, short_title, pubdate, pubtime, duration,
              bytes, ...) and a notes.md skeleton if none exists
  transcribe  faster-whisper with scripts/glossary.json -> transcript.txt / transcript.vtt
  video       promo/epNN-full.mp4 (intro clip + cover art + outro clip, 1920x1080 30 fps)
              and promo/epNN-thumb.jpg (1280x720)
  yt-meta     promo/epNN-youtube.json: YouTube title (<=100 chars), description built
              from notes.md (<=5000 bytes), tags, thumbnail URL, playlist
  build       python3 scripts/build.py (site + feed)

After the run: edit notes.md, re-run `--steps yt-meta,build`, commit, open the PR,
then upload promo/epNN-full.mp4 with promo/epNN-youtube.json (see CLAUDE.md).
"""
import argparse
import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from new_episode import (audio_duration_seconds, convert_audio, load_config,  # noqa: E402
                         next_number, slugify)
import transcribe as tr  # noqa: E402

EPISODES = ROOT / "episodes"
PROMO = ROOT / "promo"
INTRO = PROMO / "bumpers" / "intro_thp.ts"
OUTRO = PROMO / "bumpers" / "outro_jessica.ts"
DEFAULT_COVER = ROOT / "assets" / "cover.jpg"
ALL_STEPS = ["audio", "metadata", "transcribe", "video", "yt-meta", "build"]

YT_TITLE_MAX = 100
YT_DESC_MAX_BYTES = 5000
YT_TAGS_MAX_CHARS = 500
YT_CATEGORY = "25"  # News & Politics
DEFAULT_TAGS = ["The Healthcare Paradox", "Puerto Rico", "healthcare policy", "Medicare",
                "Medicaid", "podcast"]


# ---------------------------------------------------------------- helpers
def run(cmd: list, **kw) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, check=True, **kw)


def ffprobe_duration(path: Path, stream: str | None = None) -> float:
    cmd = ["ffprobe", "-v", "error"]
    if stream:
        cmd += ["-select_streams", stream, "-show_entries", "stream=duration"]
    else:
        cmd += ["-show_entries", "format=duration"]
    cmd += ["-of", "default=noprint_wrappers=1:nokey=1", str(path)]
    out = subprocess.run(cmd, capture_output=True, text=True, check=True).stdout.strip().split("\n")[0]
    return float(out)


def need(path: Path, what: str) -> None:
    if not path.exists():
        sys.exit(f"error: {what} not found: {path}")


def log(msg: str) -> None:
    print(f"[publish] {msg}", flush=True)


# ---------------------------------------------------------------- steps
def step_audio(src: Path, ep_dir: Path, config: dict) -> Path:
    """Normalize the recording and splice intro + content + outro into episode.mp3."""
    need(src, "audio file")
    need(INTRO, "intro bumper")
    need(OUTRO, "outro bumper")
    ep_dir.mkdir(parents=True, exist_ok=True)
    dest = ep_dir / "episode.mp3"
    with tempfile.TemporaryDirectory() as tmp:
        content = Path(tmp) / "content.mp3"
        log(f"normalizing {src.name} (loudnorm, {config.get('audio_bitrate', '128k')})")
        convert_audio(src, content, config.get("audio_bitrate", "128k"),
                      config.get("loudness_normalize", True))
        log("splicing intro + content + outro")
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-i", str(INTRO), "-i", str(content), "-i", str(OUTRO),
             "-filter_complex", "[0:a][1:a][2:a]concat=n=3:v=0:a=1[a]", "-map", "[a]",
             "-ar", "44100", "-ac", "2", "-c:a", "libmp3lame",
             "-b:a", config.get("audio_bitrate", "128k"), str(dest)])
    log(f"episode.mp3: {ffprobe_duration(dest):.1f} s, {dest.stat().st_size:,} bytes")
    return dest


def step_metadata(ep_dir: Path, args, number: int, slug: str, config: dict) -> dict:
    meta_path = ep_dir / "metadata.json"
    meta = json.loads(meta_path.read_text()) if meta_path.exists() else {}
    audio = ep_dir / "episode.mp3"
    need(audio, "episode.mp3")
    meta.update({
        "number": number,
        "slug": slug,
        "title": args.title or meta.get("title", ""),
        "description": args.description or meta.get("description", ""),
        "pubdate": args.date or meta.get("pubdate") or datetime.date.today().isoformat(),
        "pubtime": args.pubtime or meta.get("pubtime") or "07:30",
        "audio": "episode.mp3",
        "duration_seconds": audio_duration_seconds(audio),
        "bytes": audio.stat().st_size,
        "explicit": bool(args.explicit or meta.get("explicit", False)),
        "season": args.season if args.season is not None else meta.get("season"),
        "episode_type": meta.get("episode_type", "full"),
        "transcript": meta.get("transcript"),
        "draft": meta.get("draft", False),
    })
    if args.short_title:
        meta["short_title"] = args.short_title
    meta_path.write_text(json.dumps(meta, indent=2, ensure_ascii=False) + "\n")

    notes = ep_dir / "notes.md"
    if not notes.exists() or not notes.read_text().strip():
        skeleton = (meta["description"] + "\n\n" if meta["description"] else "") + (
            "In this episode:\n\n"
            "- **Point one.** ...\n"
            "- **Point two.** ...\n\n"
            "The closing question: ...\n\n"
            "Listen to The Healthcare Paradox on Spotify, Apple Podcasts, Amazon Music,\n"
            "iHeartRadio, Pandora, and YouTube.\n\n"
            f"The federal data behind this show is browsable in the [{config.get('console_label', 'CMS Console')}]"
            f"({config.get('console_url', 'https://healthconsole.org')}).\n\n"
            f"{config.get('music_credit', '')}\n")
        notes.write_text(skeleton)
        log("notes.md skeleton written (edit it, then re-run --steps yt-meta,build)")
    log(f"metadata.json: #{number}, {meta['pubdate']} {meta['pubtime']}, "
        f"{meta['duration_seconds']} s, {meta['bytes']:,} bytes")
    return meta


def step_transcribe(ep_dir: Path, model: str, language: str) -> None:
    log(f"transcribing with faster-whisper '{model}' (this takes a few minutes)")
    info = tr.transcribe_episode(ep_dir, model, language, verbose=False)
    log(f"transcript: {info['lines']} lines ({info['language']})")


def step_video(ep_dir: Path, number: int, cover: Path) -> tuple[Path, Path]:
    """Render the YouTube video (intro clip, still cover, outro clip) and the thumbnail."""
    from PIL import Image

    need(cover, "cover image")
    audio = ep_dir / "episode.mp3"
    need(audio, "episode.mp3")
    PROMO.mkdir(exist_ok=True)
    out_mp4 = PROMO / f"ep{number:02d}-full.mp4"
    out_jpg = PROMO / f"ep{number:02d}-thumb.jpg"

    img = Image.open(cover).convert("RGB")
    thumb = Image.new("RGB", (1280, 720), (0, 0, 0))
    thumb.paste(img.resize((720, 720), Image.LANCZOS), (280, 0))
    thumb.save(out_jpg, quality=92)

    total = ffprobe_duration(audio)
    intro_v = ffprobe_duration(INTRO, "v:0")
    outro_v = ffprobe_duration(OUTRO, "v:0")
    body = max(1.0, total - ffprobe_duration(INTRO) - ffprobe_duration(OUTRO))
    with tempfile.TemporaryDirectory() as tmp:
        frame = Path(tmp) / "frame1080.png"
        canvas = Image.new("RGB", (1920, 1080), (0, 0, 0))
        canvas.paste(img.resize((1080, 1080), Image.LANCZOS), (420, 0))
        canvas.save(frame)
        log(f"rendering video: intro {intro_v:.1f} s + cover {body:.1f} s + outro {outro_v:.1f} s "
            "(1920x1080, 30 fps; several minutes)")
        run(["ffmpeg", "-y", "-loglevel", "error",
             "-i", str(INTRO),
             "-loop", "1", "-framerate", "30", "-t", f"{body:.3f}", "-i", str(frame),
             "-i", str(OUTRO),
             "-i", str(audio),
             "-filter_complex",
             "[0:v]fps=30,scale=1920:1080,setsar=1,format=yuv420p[v0];"
             "[1:v]fps=30,setsar=1,format=yuv420p[v1];"
             "[2:v]fps=30,scale=1920:1080,setsar=1,format=yuv420p[v2];"
             "[v0][v1][v2]concat=n=3:v=1:a=0[v]",
             "-map", "[v]", "-map", "3:a",
             "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "23",
             "-r", "30", "-pix_fmt", "yuv420p",
             "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
             "-shortest", "-movflags", "+faststart", str(out_mp4)])
    log(f"video: {out_mp4.relative_to(ROOT)} ({ffprobe_duration(out_mp4):.1f} s, "
        f"{out_mp4.stat().st_size / 1e6:.1f} MB); thumbnail: {out_jpg.relative_to(ROOT)}")
    return out_mp4, out_jpg


def youtube_title(meta: dict) -> tuple[str, bool]:
    """Return (title, auto_shortened)."""
    t = (meta.get("short_title") or meta["title"]).strip()
    if len(t) <= YT_TITLE_MAX:
        return t, False
    best = -1
    for sep in (" — ", " – ", ": ", ". ", "; ", ", ", " "):
        i = t.rfind(sep, 0, YT_TITLE_MAX - 1)
        if i > best and i >= 40:
            best = i
    short = t[:best].rstrip(" ,;:—–-") if best > 0 else t[:YT_TITLE_MAX - 1]
    if not short.endswith((".", "!", "?")):
        short += "."
    return short[:YT_TITLE_MAX], True


def notes_to_plain(notes_md: str) -> list[str]:
    """Markdown show notes -> list of plain-text paragraphs (bullets become '• ' lines)."""
    paras = re.split(r"\n\s*\n", notes_md.strip())
    out = []
    for para in paras:
        lines = para.split("\n")
        if re.match(r"^\s*[-*] ", lines[0]):
            bullets = []
            for ln in lines:
                if re.match(r"^\s*[-*] ", ln):
                    bullets.append(re.sub(r"^\s*[-*] ", "", ln).strip())
                elif bullets:
                    bullets[-1] += " " + ln.strip()
            out += ["• " + b for b in bullets]
        else:
            out.append(" ".join(ln.strip() for ln in lines))
    text = "\n\n".join(out)
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"(?<!\w)\*(.+?)\*(?!\w)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1 (\2)", text)
    text = text.replace("<", "(").replace(">", ")")
    return [p for p in text.split("\n\n") if p.strip()]


def youtube_description(ep_dir: Path, meta: dict, config: dict) -> tuple[str, bool]:
    """Build the YouTube description from notes.md (fallback: metadata description).
    Returns (description, compacted)."""
    notes = ep_dir / "notes.md"
    paras = notes_to_plain(notes.read_text()) if notes.exists() else []
    drop_prefixes = ("Listen to The Healthcare Paradox", "Music:", "The federal data behind")
    body = [p for p in paras if not p.startswith(drop_prefixes) and not p.startswith("• Point one")]
    if not body:
        body = [meta.get("description") or meta["title"]]

    links = [("Site", config.get("site_url")), ("Spotify", config.get("spotify_url")),
             ("Apple Podcasts", config.get("apple_url")), ("Amazon Music", config.get("amazon_url")),
             ("iHeartRadio", config.get("iheart_url")), ("Pandora", config.get("pandora_url"))]
    footer = [f"{config['title']} — new episodes every week.\n" +
              "\n".join(f"• {name}: {url}" for name, url in links if url)]
    if config.get("console_url"):
        footer.append(f"The federal data behind this show is browsable in the "
                      f"{config.get('console_label', 'CMS Console')} ({config['console_url']}).")
    if config.get("music_credit"):
        footer.append(config["music_credit"])

    def assemble(parts):
        return "\n\n".join(parts + footer)

    def n_sent(t):
        return len(re.split(r"(?<=[.!?])\s+", t))

    compacted = False
    desc = assemble(body)
    while len(desc.encode("utf-8")) > YT_DESC_MAX_BYTES:
        compacted = True
        bullets = [i for i, p in enumerate(body) if p.startswith("• ")]
        # 1) trim the bullet with the most sentences by one sentence (keep at least two)
        cands = [i for i in bullets if n_sent(body[i]) > 2]
        if cands:
            i = max(cands, key=lambda k: (n_sent(body[k]), len(body[k])))
            body[i] = " ".join(re.split(r"(?<=[.!?])\s+", body[i])[:-1])
        # 2) then drop trailing non-bullet paragraphs (closing question), keeping the intro
        elif len(body) > 1 and not body[-1].startswith("• "):
            body = body[:-1]
        # 3) then drop bullets from the end
        elif bullets:
            body.pop(bullets[-1])
        else:
            body = [body[0].encode("utf-8")[:YT_DESC_MAX_BYTES - 1200].decode("utf-8", "ignore")]
        desc = assemble(body)
    return desc, compacted


def step_yt_meta(ep_dir: Path, meta: dict, number: int, config: dict, extra_tags: list[str]) -> Path:
    title, shortened = youtube_title(meta)
    desc, compacted = youtube_description(ep_dir, meta, config)
    tags, seen, total = [], set(), 0
    for t in list(config.get("youtube_tags", DEFAULT_TAGS)) + extra_tags:
        t = t.strip()
        if not t or t.lower() in seen:
            continue
        cost = len(t) + (2 if " " in t else 0) + 1
        if total + cost > YT_TAGS_MAX_CHARS:
            break
        seen.add(t.lower()); tags.append(t); total += cost
    raw_base = config.get("github_raw_base", "https://raw.githubusercontent.com/epac-hub/podcast/main").rstrip("/")
    out = {
        "episode": ep_dir.name,
        "video": f"promo/ep{number:02d}-full.mp4",
        "thumbnail": f"promo/ep{number:02d}-thumb.jpg",
        "thumbnail_url": f"{raw_base}/promo/ep{number:02d}-thumb.jpg",
        "title": title,
        "description": desc,
        "tags": tags,
        "categoryId": YT_CATEGORY,
        "privacyStatus": "public",
        "defaultLanguage": "en",
        "defaultAudioLanguage": config.get("language", "en-US"),
        "playlist_id": config.get("youtube_playlist"),
    }
    path = PROMO / f"ep{number:02d}-youtube.json"
    path.write_text(json.dumps(out, indent=2, ensure_ascii=False) + "\n")
    log(f"youtube meta: {path.relative_to(ROOT)} (title {len(title)} chars"
        f"{', auto-shortened; set --short-title to control it' if shortened else ''}; "
        f"description {len(desc.encode('utf-8'))} bytes{', compacted to fit 5000' if compacted else ''}; "
        f"{len(tags)} tags)")
    return path


def step_build() -> None:
    log("building site + feed")
    out = subprocess.run([sys.executable, str(ROOT / "scripts" / "build.py")],
                         capture_output=True, text=True, cwd=ROOT)
    if out.returncode != 0:
        sys.exit(f"error: build failed\n{out.stdout}\n{out.stderr}")
    print("  " + out.stdout.strip().replace("\n", "\n  "))


# ---------------------------------------------------------------- main
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("audio", nargs="?", type=Path, help="recording to ingest (m4a/mp3/wav)")
    p.add_argument("--episode", type=Path, help="existing episode dir: run --steps on it instead of ingesting")
    p.add_argument("--steps", default="", help="comma list for --episode (default: yt-meta,build); "
                                               "any of " + ",".join(ALL_STEPS))
    p.add_argument("--title")
    p.add_argument("--short-title", help="YouTube title (<=100 chars); stored in metadata.json")
    p.add_argument("--description", default="")
    p.add_argument("--date", help="publish date YYYY-MM-DD (default: today)")
    p.add_argument("--pubtime", default=None, help="publish time HH:MM UTC (default 07:30)")
    p.add_argument("--number", type=int)
    p.add_argument("--slug")
    p.add_argument("--season", type=int, default=None)
    p.add_argument("--explicit", action="store_true")
    p.add_argument("--model", default="small", help="whisper model: small (default) or medium")
    p.add_argument("--language", default="en")
    p.add_argument("--cover", type=Path, default=DEFAULT_COVER)
    p.add_argument("--tags", default="", help="extra YouTube tags, comma separated")
    p.add_argument("--no-transcribe", action="store_true")
    p.add_argument("--no-video", action="store_true")
    p.add_argument("--no-build", action="store_true")
    p.add_argument("--force", action="store_true", help="overwrite an existing episode.mp3")
    args = p.parse_args()

    for tool in ("ffmpeg", "ffprobe"):
        if shutil.which(tool) is None:
            sys.exit(f"error: {tool} is required")
    config = load_config()
    extra_tags = [t for t in args.tags.split(",") if t.strip()]

    if args.episode:
        ep_dir = args.episode if args.episode.is_absolute() else ROOT / args.episode
        need(ep_dir / "metadata.json", "metadata.json")
        meta = json.loads((ep_dir / "metadata.json").read_text())
        number, slug = meta["number"], meta["slug"]
        steps = [s.strip() for s in (args.steps or "yt-meta,build").split(",") if s.strip()]
        bad = [s for s in steps if s not in ALL_STEPS]
        if bad:
            sys.exit(f"error: unknown step(s) {bad}; choose from {ALL_STEPS}")
        if "audio" in steps:
            if not args.audio:
                sys.exit("error: the audio step needs the recording as the positional argument")
            step_audio(args.audio, ep_dir, config)
        if "metadata" in steps or "audio" in steps or args.short_title or args.title:
            meta = step_metadata(ep_dir, args, number, slug, config)
        if "transcribe" in steps:
            step_transcribe(ep_dir, args.model, args.language)
        if "video" in steps:
            step_video(ep_dir, number, args.cover)
        if "yt-meta" in steps:
            step_yt_meta(ep_dir, meta, number, config, extra_tags)
        if "build" in steps:
            step_build()
        log("done")
        return

    if not args.audio or not args.title:
        sys.exit("error: a new episode needs the recording and --title (or use --episode DIR)")
    number = args.number or next_number()
    slug = args.slug or slugify(args.title)
    ep_dir = EPISODES / f"{number:03d}-{slug}"
    if (ep_dir / "episode.mp3").exists() and not args.force:
        sys.exit(f"error: {ep_dir.relative_to(ROOT)} already has episode.mp3 (use --force or --episode)")

    log(f"episode {number}: {ep_dir.relative_to(ROOT)}")
    step_audio(args.audio, ep_dir, config)
    meta = step_metadata(ep_dir, args, number, slug, config)
    if not args.no_transcribe:
        step_transcribe(ep_dir, args.model, args.language)
    if not args.no_video:
        step_video(ep_dir, number, args.cover)
    step_yt_meta(ep_dir, meta, number, config, extra_tags)
    if not args.no_build:
        step_build()
    log("done. Next: edit notes.md, run `--episode "
        f"{ep_dir.relative_to(ROOT)} --steps yt-meta,build`, commit, open the PR, "
        f"then upload promo/ep{number:02d}-full.mp4 with promo/ep{number:02d}-youtube.json.")


if __name__ == "__main__":
    main()
