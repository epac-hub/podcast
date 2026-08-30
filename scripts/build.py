#!/usr/bin/env python3
"""Build the podcast site and RSS feed into docs/.

Reads podcast.config.json and every episodes/*/metadata.json, then writes:
  docs/index.html                     episode list + players
  docs/episodes/<dir>/index.html      per-episode page (notes + transcript)
  docs/audio/<dir>.mp3                episode audio
  docs/transcripts/<dir>.vtt|.txt     transcripts, when present
  docs/feed.xml                       RSS 2.0 with iTunes + Podcasting 2.0 tags

Usage: python3 scripts/build.py
"""
import datetime
import email.utils
import html
import json
import shutil
import xml.etree.ElementTree as ET
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parent.parent
EPISODES = ROOT / "episodes"
TEMPLATES = ROOT / "templates"
OUT = ROOT / "docs"

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
PODCAST = "https://podcastindex.org/namespace/1.0"
CONTENT = "http://purl.org/rss/1.0/modules/content/"


def load_config() -> dict:
    with open(ROOT / "podcast.config.json") as f:
        return json.load(f)


def load_episodes() -> list[dict]:
    episodes = []
    if not EPISODES.exists():
        return episodes
    for ep_dir in sorted(EPISODES.iterdir()):
        meta_path = ep_dir / "metadata.json"
        if not meta_path.exists():
            continue
        meta = json.loads(meta_path.read_text())
        if meta.get("draft"):
            continue
        meta["dir"] = ep_dir
        meta["dirname"] = ep_dir.name
        notes = ep_dir / "notes.md"
        meta["notes_md"] = notes.read_text() if notes.exists() else ""
        txt = ep_dir / "transcript.txt"
        meta["transcript_text"] = txt.read_text() if txt.exists() else ""
        episodes.append(meta)
    episodes.sort(key=lambda m: (m.get("pubdate", ""), m.get("number", 0)))
    return episodes


def md_to_html(text: str) -> str:
    if not text.strip():
        return ""
    try:
        import markdown

        return markdown.markdown(text, extensions=["extra"])
    except ImportError:
        return "<pre>" + html.escape(text) + "</pre>"


def fmt_duration(seconds: int) -> str:
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def pub_datetime(meta: dict) -> datetime.datetime:
    d = datetime.date.fromisoformat(meta["pubdate"])
    return datetime.datetime(d.year, d.month, d.day, 12, 0, 0,
                             tzinfo=datetime.timezone.utc)


def build_feed(config: dict, episodes: list[dict]) -> bytes:
    for prefix, uri in [("itunes", ITUNES), ("atom", ATOM),
                        ("podcast", PODCAST), ("content", CONTENT)]:
        ET.register_namespace(prefix, uri)

    site = config["site_url"].rstrip("/")
    rss = ET.Element("rss", version="2.0")
    ch = ET.SubElement(rss, "channel")

    def el(parent, tag, text=None, **attrs):
        e = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
        if text is not None:
            e.text = str(text)
        return e

    el(ch, "title", config["title"])
    el(ch, "link", site + "/")
    el(ch, "description", config["description"])
    el(ch, "language", config.get("language", "en-US"))
    el(ch, "generator", "build.py")
    if config.get("copyright"):
        el(ch, "copyright", config["copyright"])
    el(ch, f"{{{ATOM}}}link", href=f"{site}/feed.xml", rel="self",
       type="application/rss+xml")
    el(ch, f"{{{ITUNES}}}author", config.get("author") or config["title"])
    el(ch, f"{{{ITUNES}}}summary", config["description"])
    el(ch, f"{{{ITUNES}}}explicit", "true" if config.get("explicit") else "false")
    el(ch, f"{{{ITUNES}}}type", "episodic")
    el(ch, f"{{{ITUNES}}}image", href=f"{site}/{config.get('cover_image', 'assets/cover.jpg')}")
    el(ch, "image")
    img = ch.find("image")
    el(img, "url", f"{site}/{config.get('cover_image', 'assets/cover.jpg')}")
    el(img, "title", config["title"])
    el(img, "link", site + "/")
    cat = el(ch, f"{{{ITUNES}}}category", text=config.get("category", "Society & Culture"))
    cat.set("text", config.get("category", "Society & Culture"))
    cat.text = None
    if config.get("subcategory"):
        sub = ET.SubElement(cat, f"{{{ITUNES}}}category")
        sub.set("text", config["subcategory"])
    if config.get("owner_name") or config.get("owner_email"):
        owner = el(ch, f"{{{ITUNES}}}owner")
        if config.get("owner_name"):
            el(owner, f"{{{ITUNES}}}name", config["owner_name"])
        if config.get("owner_email"):
            el(owner, f"{{{ITUNES}}}email", config["owner_email"])
    if episodes:
        el(ch, "lastBuildDate",
           email.utils.format_datetime(pub_datetime(episodes[-1])))

    for meta in reversed(episodes):  # newest first
        item = el(ch, "item")
        el(item, "title", meta["title"])
        page = f"{site}/episodes/{meta['dirname']}/"
        el(item, "link", page)
        el(item, "guid", page, isPermaLink="true")
        el(item, "description", meta.get("description") or meta["title"])
        el(item, "pubDate", email.utils.format_datetime(pub_datetime(meta)))
        el(item, "enclosure", url=f"{site}/audio/{meta['dirname']}.mp3",
           length=meta["bytes"], type="audio/mpeg")
        el(item, f"{{{ITUNES}}}duration", int(meta["duration_seconds"]))
        el(item, f"{{{ITUNES}}}episode", meta["number"])
        el(item, f"{{{ITUNES}}}episodeType", meta.get("episode_type", "full"))
        el(item, f"{{{ITUNES}}}explicit",
           "true" if meta.get("explicit") else "false")
        if meta.get("season"):
            el(item, f"{{{ITUNES}}}season", meta["season"])
        if meta.get("transcript"):
            el(item, f"{{{PODCAST}}}transcript",
               url=f"{site}/transcripts/{meta['dirname']}.vtt", type="text/vtt")
        notes_html = md_to_html(meta["notes_md"])
        if notes_html:
            enc = el(item, f"{{{CONTENT}}}encoded")
            enc.text = notes_html

    ET.indent(rss)
    return ET.tostring(rss, encoding="utf-8", xml_declaration=True)


def build_site(config: dict, episodes: list[dict]) -> None:
    env = Environment(loader=FileSystemLoader(TEMPLATES),
                      autoescape=select_autoescape(["html"]))
    env.filters["duration"] = fmt_duration
    env.filters["markdown"] = md_to_html

    view = []
    for meta in reversed(episodes):  # newest first
        v = dict(meta)
        v["audio_url"] = f"audio/{meta['dirname']}.mp3"
        v["page_url"] = f"episodes/{meta['dirname']}/"
        v["notes_html"] = md_to_html(meta["notes_md"])
        v["date_display"] = datetime.date.fromisoformat(meta["pubdate"]).strftime("%B %-d, %Y")
        view.append(v)

    ctx = {"config": config, "episodes": view,
           "year": datetime.date.today().year}

    (OUT / "index.html").write_text(
        env.get_template("index.html").render(**ctx, root=""))

    for v in view:
        page_dir = OUT / "episodes" / v["dirname"]
        page_dir.mkdir(parents=True, exist_ok=True)
        (page_dir / "index.html").write_text(
            env.get_template("episode.html").render(**ctx, ep=v, root="../../"))


def main() -> None:
    config = load_config()
    episodes = load_episodes()

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    (OUT / ".nojekyll").write_text("")

    (OUT / "audio").mkdir()
    (OUT / "transcripts").mkdir()
    for meta in episodes:
        shutil.copy2(meta["dir"] / meta["audio"],
                     OUT / "audio" / f"{meta['dirname']}.mp3")
        for ext in ("vtt", "txt"):
            src = meta["dir"] / f"transcript.{ext}"
            if src.exists():
                shutil.copy2(src, OUT / "transcripts" / f"{meta['dirname']}.{ext}")

    assets_out = OUT / "assets"
    assets_out.mkdir()
    assets_src = ROOT / "assets"
    if assets_src.exists():
        for f in assets_src.iterdir():
            if f.is_file():
                shutil.copy2(f, assets_out / f.name)
    static = TEMPLATES / "static"
    if static.exists():
        for f in static.iterdir():
            if f.is_file():
                shutil.copy2(f, assets_out / f.name)

    (OUT / "feed.xml").write_bytes(build_feed(config, episodes))
    build_site(config, episodes)

    print(f"built {len(episodes)} episode(s) -> {OUT.relative_to(ROOT)}/")
    print(f"feed: {config['site_url'].rstrip('/')}/feed.xml")


if __name__ == "__main__":
    main()
