#!/usr/bin/env python3
"""Audience report for The Healthcare Paradox (all platforms, since launch).

Two steps:

  1. collect  - pulls everything that is public or has an API: OP3 feed downloads
                (all rows since launch), YouTube public counters (subscribers, views
                per video), Apple Podcasts reviews. Writes a data JSON.
  2. render   - builds the branded HTML report (and a PDF) from that data JSON plus an
                optional "extra" JSON with the numbers that need a logged-in read
                (Spotify for Creators, YouTube Analytics, comments). See
                scripts/audience_report/README.md for the extra JSON schema.

Examples:
  python3 scripts/audience_report.py collect --out build/audience/data.json
  python3 scripts/audience_report.py render --data build/audience/data.json \
      --extra build/audience/extra.json --out build/audience/report.html \
      --pdf "build/audience/The-Healthcare-Paradox-Audience-Report-2026-09-27.pdf"

Requirements: python3, curl. For the PDF: pip install playwright (Chromium at
$PLAYWRIGHT_CHROMIUM, /opt/pw-browsers/chromium, or Playwright's own install).
"""
import argparse
import base64
import collections
import datetime as dt
import glob
import html
import json
import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HERE = os.path.join(ROOT, "scripts", "audience_report")

OP3_TOKEN = "preview07ce"
OP3_SHOW = "0184f9251a7b4e98b1ad0815e2b569b8"
YT_HANDLE = "thehealthcareparadox"
APPLE_ID = "6806405453"
SPOTIFY_SHOW = "7K7Ub2NPG2Km4aGw0C25eN"
LAUNCH = "2026-08-26"          # episode 1 publication date
OP3_START = "2026-08-01"

LINKS = [
    ("Website", "https://thehealthcareparadox.com"),
    ("Email", "mailto:info@thehealthcareparadox.com", "info@thehealthcareparadox.com"),
    ("Spotify", f"https://open.spotify.com/show/{SPOTIFY_SHOW}"),
    ("Apple Podcasts", f"https://podcasts.apple.com/us/podcast/the-healthcare-paradox/id{APPLE_ID}"),
    ("YouTube", f"https://www.youtube.com/@{YT_HANDLE}"),
    ("Amazon Music", "https://music.amazon.com/podcasts/b04ac0eb-1742-4710-b1f9-e9ab3c585f79"),
    ("iHeartRadio", "https://www.iheart.com/podcast/343036242/"),
    ("Pandora", "https://www.pandora.com/podcast/the-healthcare-paradox/PC:1001121395"),
]
PLATFORM_CHIPS = ["YouTube", "Spotify", "Apple Podcasts", "Amazon Music", "iHeartRadio", "Pandora"]
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/128.0 Safari/537.36")
BOT_COUNTRIES = {"CN", "ID", "PL", "SE", "GB", "DE", "FR", "RU", "SG", "NL", "IE", "IN", "HK", "JP", "KR", "BR", "UA"}
COUNTRY_NAMES = {"PR": "Puerto Rico", "US": "United States", "CN": "China", "ID": "Indonesia", "PL": "Poland",
                 "SE": "Sweden", "GB": "United Kingdom", "DE": "Germany", "FR": "France", "ES": "Spain",
                 "MX": "Mexico", "DO": "Dominican Republic", "CA": "Canada", "CO": "Colombia"}


# ----------------------------------------------------------------------------- helpers
def log(*a):
    print(*a, file=sys.stderr, flush=True)


def fetch(url, timeout=60, extra=None):
    cmd = ["curl", "-sS", "-L", "--max-time", str(timeout), "-A", UA,
           "-H", "Accept-Language: en-US,en;q=0.9", "-b", "CONSENT=YES+1"] + (extra or []) + [url]
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout + 15)
    if r.returncode != 0:
        raise RuntimeError(f"curl failed for {url}: {r.stderr.strip()[:200]}")
    return r.stdout


def fetch_json(url, timeout=60):
    return json.loads(fetch(url, timeout))


def esc(s):
    return html.escape(str(s), quote=True)


def fmt(n):
    if isinstance(n, float) and not n.is_integer():
        return f"{n:,.1f}"
    return f"{int(n):,}"


def parse_date(s):
    return dt.date.fromisoformat(s[:10])


def long_date(d):
    return d.strftime("%B %-d, %Y")


def short_date(d):
    return d.strftime("%b %-d")


# ----------------------------------------------------------------------------- episodes
def load_episodes():
    """dirname -> {number, title, type, pubdate, label}."""
    eps = {}
    for f in sorted(glob.glob(os.path.join(ROOT, "episodes", "*", "metadata.json"))):
        m = json.load(open(f, encoding="utf-8"))
        d = os.path.basename(os.path.dirname(f))
        m["dirname"] = d
        m["label"] = episode_label(m, d)
        eps[d] = m
    return eps


LABEL_OVERRIDES = {"006": "Elena PR vs Rosa USA", "002": "The Medicare Funding Paradox"}


def episode_label(meta, dirname=""):
    t = meta.get("title", "")
    if meta.get("episode_type") == "trailer" or "Official Trailer" in t:
        m = re.search(r"Trailer:\s*(.*)", t)
        core = m.group(1).strip().rstrip(".") if m else "Official Trailer"
        return "Trailer · " + core
    core = LABEL_OVERRIDES.get(dirname[:3]) or re.split(r":| - | — ", t)[0].strip()
    try:
        n = int(meta.get("number") or 0)
    except ValueError:
        n = 0
    return f"Ep {n} · {core}" if n else core


def label_for_title(title, episodes):
    """Short label for a YouTube video title (long-form videos share the episode title)."""
    norm = lambda s: re.sub(r"[^a-z0-9]+", " ", s.lower()).strip()
    nt = norm(title)
    for e in episodes.values():
        ne = norm(e["title"])
        if nt == ne or (len(nt) > 30 and (nt.startswith(ne[:40]) or ne.startswith(nt[:40]))):
            return e["label"]
    if "|" in title:
        return "Short · " + title.split("|")[0].strip().rstrip(".")
    if "Official Trailer" in title:
        m = re.search(r"Trailer:\s*(.*)", title)
        return "Trailer · " + (m.group(1).strip().rstrip(".") if m else "Official Trailer")
    return re.split(r":| - | — ", title)[0].strip()


# ----------------------------------------------------------------------------- collect
def collect_op3():
    base = "https://op3.dev/api/1"
    rows, token, guard = [], None, 0
    while True:
        url = (f"{base}/downloads/show/{OP3_SHOW}?token={OP3_TOKEN}&format=json&limit=20000"
               f"&start={OP3_START}" + (f"&continuationToken={token}" if token else ""))
        d = fetch_json(url, 120)
        rows += d.get("rows", [])
        token = d.get("continuationToken")
        guard += 1
        if not token or guard > 20:
            break
    slim = []
    for r in rows:
        m = re.search(r"/audio/([^/]+?)\.mp3", r.get("url", ""))
        slim.append({"t": r.get("time", "")[:19], "ep": m.group(1) if m else "", "cc": r.get("countryCode", ""),
                     "region": r.get("regionName", ""), "atype": r.get("agentType", ""),
                     "agent": r.get("agentName", ""), "device": r.get("deviceName", "")})
    out = {"rows": slim}
    for name in ("show-download-counts", "episode-download-counts", "top-apps-for-show"):
        try:
            out[name.replace("-", "_")] = fetch_json(f"{base}/queries/{name}?token={OP3_TOKEN}&showUuid={OP3_SHOW}", 90)
        except Exception as e:  # noqa: BLE001
            log("OP3", name, "failed:", e)
    log(f"OP3: {len(slim)} downloads since {OP3_START}")
    return out


def _yt_initial_data(page):
    m = re.search(r"var ytInitialData = (\{.*?\});</script>", page, re.S)
    return json.loads(m.group(1)) if m else {}


def _views_from_text(s):
    m = re.search(r"([\d.,]+)\s*([KM]?)\s*views?", s or "")
    if not m:
        return 0
    return int(float(m.group(1).replace(",", "")) * {"K": 1000, "M": 1_000_000}.get(m.group(2), 1))


def collect_youtube_public():
    out = {"videos": [], "subscribers": None, "channel_views": None, "video_count": None}
    base = f"https://www.youtube.com/@{YT_HANDLE}"
    seen = {}

    def walk(o, kind):
        if isinstance(o, dict):
            if kind == "video" and "lockupViewModel" in o:
                v = o["lockupViewModel"]
                md = v.get("metadata", {}).get("lockupMetadataViewModel", {})
                parts = [p.get("text", {}).get("content", "") for r in md.get("metadata", {})
                         .get("contentMetadataViewModel", {}).get("metadataRows", []) for p in r.get("metadataParts", [])]
                vid = v.get("contentId")
                if vid and vid not in seen:
                    seen[vid] = {"id": vid, "kind": "video", "title": md.get("title", {}).get("content", ""),
                                 "views": _views_from_text(" ".join(parts)),
                                 "published": next((p for p in parts if "ago" in p), "")}
            if kind == "short" and "shortsLockupViewModel" in o:
                v = o["shortsLockupViewModel"]
                vid = (v.get("onTap", {}).get("innertubeCommand", {}).get("reelWatchEndpoint", {}).get("videoId")
                       or v.get("entityId", ""))
                om = v.get("overlayMetadata", {})
                if vid and vid not in seen:
                    seen[vid] = {"id": vid, "kind": "short", "title": om.get("primaryText", {}).get("content", ""),
                                 "views": _views_from_text(om.get("secondaryText", {}).get("content", "")), "published": ""}
            for k in o.values():
                walk(k, kind)
        elif isinstance(o, list):
            for k in o:
                walk(k, kind)

    for path, kind in (("/videos", "video"), ("/shorts", "short")):
        try:
            walk(_yt_initial_data(fetch(base + path, 60)), kind)
        except Exception as e:  # noqa: BLE001
            log("YouTube", path, "failed:", e)
    try:
        about = fetch(base + "/about", 60)
        m = re.search(r'"subscriberCountText":"([\d.,]+[KM]?) subscribers?"', about)
        out["subscribers"] = _views_from_text((m.group(1) + " views") if m else "") if m else None
        m = re.search(r'"viewCountText":"([\d,]+) views?"', about)
        out["channel_views"] = int(m.group(1).replace(",", "")) if m else None
        m = re.search(r'"videoCountText":"([\d,]+) videos?"', about)
        out["video_count"] = int(m.group(1).replace(",", "")) if m else None
    except Exception as e:  # noqa: BLE001
        log("YouTube about failed:", e)
    out["videos"] = sorted(seen.values(), key=lambda v: -v["views"])
    log(f"YouTube public: {len(out['videos'])} videos, {out['subscribers']} subscribers")
    return out


def collect_apple_reviews():
    out = {}
    for store in ("us", "pr"):
        try:
            d = fetch_json(f"https://itunes.apple.com/{store}/rss/customerreviews/id={APPLE_ID}/sortBy=mostRecent/json", 60)
            entries = d.get("feed", {}).get("entry", [])
            if isinstance(entries, dict):
                entries = [entries]
            out[store] = [{"author": e.get("author", {}).get("name", {}).get("label", ""),
                           "rating": e.get("im:rating", {}).get("label", ""),
                           "title": e.get("title", {}).get("label", ""),
                           "text": e.get("content", {}).get("label", ""),
                           "date": e.get("updated", {}).get("label", "")[:10]} for e in entries if e.get("im:rating")]
        except Exception as e:  # noqa: BLE001
            log("Apple reviews", store, "failed:", e)
            out[store] = []
    log(f"Apple reviews: us={len(out.get('us', []))} pr={len(out.get('pr', []))}")
    return out


def cmd_collect(args):
    data = {"asof": args.asof, "collected_at": dt.datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "episodes": {k: {kk: v[kk] for kk in ("number", "title", "pubdate", "episode_type", "label")}
                         for k, v in load_episodes().items()},
            "op3": collect_op3(), "youtube_public": collect_youtube_public(), "apple_reviews": collect_apple_reviews()}
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    json.dump(data, open(args.out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("wrote", args.out)


# ----------------------------------------------------------------------------- analysis
def analyze_feed(rows, asof, episodes):
    a = {}
    a["total"] = len(rows)
    days = collections.Counter(r["t"][:10] for r in rows)
    first = min(days) if days else asof.isoformat()
    d0 = parse_date(first)
    series, cur = [], d0
    last_day = max(days) if days else asof.isoformat()
    while cur.isoformat() <= last_day:
        series.append([short_date(cur), days.get(cur.isoformat(), 0)])
        cur += dt.timedelta(days=1)
    a["daily"] = series
    a["last_day"] = last_day
    wk_end = parse_date(last_day)
    wk_start = wk_end - dt.timedelta(days=6)
    prev_start = wk_start - dt.timedelta(days=7)
    in_range = lambda r, s, e: s.isoformat() <= r["t"][:10] <= e.isoformat()
    a["week"] = sum(1 for r in rows if in_range(r, wk_start, wk_end))
    a["prev_week"] = sum(1 for r in rows if in_range(r, prev_start, wk_start - dt.timedelta(days=1)))
    a["week_label"] = f"{short_date(wk_start)} to {short_date(wk_end)}"
    by_ep = collections.defaultdict(collections.Counter)
    for r in rows:
        by_ep[r["ep"]][r["cc"] or "?"] += 1
    ep_rows = []
    for ep, c in sorted(by_ep.items(), key=lambda kv: -sum(kv[1].values())):
        meta = episodes.get(ep, {})
        sub = " · ".join(f"{cc} {n}" for cc, n in c.most_common() if cc in ("PR", "US"))
        ep_rows.append({"label": meta.get("label") or ep, "value": sum(c.values()), "sub": sub})
    for ep, meta in episodes.items():          # episodes with zero downloads still show up
        if ep not in by_ep:
            ep_rows.append({"label": meta["label"], "value": 0, "sub": f"published {meta.get('pubdate', '')}"})
    a["by_episode"] = ep_rows
    cc = collections.Counter(r["cc"] for r in rows)
    pr, us = cc.get("PR", 0), cc.get("US", 0)
    other = a["total"] - pr - us
    pct = lambda n: f"{round(100 * n / a['total'])}%" if a["total"] else "0%"
    a["pr_regions"] = collections.Counter(r["region"] for r in rows if r["cc"] == "PR" and r["region"]).most_common()
    a["us_regions"] = collections.Counter(r["region"] for r in rows if r["cc"] == "US" and r["region"]).most_common()
    a["by_country"] = [{"label": "Puerto Rico", "value": pr, "sub": f"{pct(pr)} · {len(a['pr_regions'])} municipalities"},
                       {"label": "United States", "value": us, "sub": f"{pct(us)} · {len(a['us_regions'])} states"},
                       {"label": "Other countries", "value": other, "sub": f"{pct(other)} · likely automated traffic"}]
    a["other_countries"] = [COUNTRY_NAMES.get(k, k) for k, _ in cc.most_common() if k not in ("PR", "US", "")]
    apps = collections.Counter(r["agent"] for r in rows if r["atype"] in ("app", "library"))
    browsers = collections.Counter(r["agent"] for r in rows if r["atype"] == "browser")
    a["apps"] = apps.most_common()
    a["app_total"] = sum(apps.values())
    a["browsers"] = browsers.most_common()
    a["web_total"] = sum(browsers.values())
    a["by_month"] = collections.Counter(r["t"][:7] for r in rows)
    return a


def month_label(ym):
    return dt.date(int(ym[:4]), int(ym[5:7]), 1).strftime("%B %Y")


def months_since_launch(asof):
    cur, out = dt.date(int(LAUNCH[:4]), int(LAUNCH[5:7]), 1), []
    while cur <= asof:
        out.append(cur.strftime("%Y-%m"))
        cur = (cur.replace(day=28) + dt.timedelta(days=4)).replace(day=1)
    return out


def load_snapshots(path):
    """Weekly totals saved by earlier reports: [{date, feed_total, yt_views, yt_subs, sp_plays, sp_followers}]."""
    snaps = []
    for f in sorted(glob.glob(os.path.join(path, "*.json"))):
        try:
            snaps.append(json.load(open(f, encoding="utf-8")))
        except Exception as e:  # noqa: BLE001
            log("snapshot", f, "unreadable:", e)
    return sorted(snaps, key=lambda s: s.get("date", ""))


def monthly_from_snapshots(snaps, key, months):
    """Per-month change of a cumulative counter, from the last snapshot of each month."""
    out = {}
    last_before = None
    for ym in months:
        in_month = [s for s in snaps if s.get("date", "")[:7] == ym and s.get(key) is not None]
        if not in_month:
            continue
        end = in_month[-1][key]
        out[ym] = (end - last_before[1], False) if last_before else (end, True)   # (value, cumulative_since_launch?)
        last_before = (ym, end)
    return out


def analyze_youtube_public(yp, episodes):
    vids = yp.get("videos", [])
    rows = []
    for v in vids:
        rows.append({"id": v["id"], "label": label_for_title(v["title"], episodes), "value": v["views"], "kind": v["kind"]})
    shorts = sum(v["views"] for v in vids if v["kind"] == "short")
    longs = sum(v["views"] for v in vids if v["kind"] == "video")
    return {"rows": rows, "shorts_views": shorts, "long_views": longs, "total": shorts + longs,
            "n_shorts": sum(1 for v in vids if v["kind"] == "short"), "n_long": sum(1 for v in vids if v["kind"] == "video"),
            "subscribers": yp.get("subscribers"), "channel_views": yp.get("channel_views")}


# ----------------------------------------------------------------------------- render
def pill(text, cls="live"):
    return f'<span class="pill {cls}">{esc(text)}</span>'


def card(title, note, body, extra=""):
    return (f'<div class="card chart"><h3>{esc(title)}</h3>' + (f'<p class="note">{note}</p>' if note else "")
            + body + extra + "</div>")


def build_html(data, extra, asof):
    episodes = data["episodes"]
    feed = analyze_feed(data["op3"]["rows"], asof, episodes)
    ytp = analyze_youtube_public(data.get("youtube_public", {}), episodes)
    sp = extra.get("spotify") or {}
    yta = extra.get("youtube") or {}
    apple = data.get("apple_reviews", {})
    reviews = [dict(r, store=s.upper()) for s in ("us", "pr") for r in apple.get(s, [])]
    launch = parse_date(LAUNCH)
    days_live = (asof - launch).days

    # ---- YouTube figures: analytics when available, public counters otherwise
    yt_subs = yta.get("subscribers") or ytp["subscribers"] or 0
    yt_views_all = yta.get("views_all")
    yt_minutes = yta.get("minutes_all")
    yt_comments = yta.get("comments") or []
    yt_likes = yta.get("likes")
    yt_video_rows = []
    if yta.get("by_video"):
        title_by_id = {v["id"]: v for v in data.get("youtube_public", {}).get("videos", [])}
        for item in yta["by_video"]:
            vid, views = item[0], item[1]
            mins = item[2] if len(item) > 2 else None
            lab = item[3] if len(item) > 3 else (label_for_title(title_by_id[vid]["title"], episodes) if vid in title_by_id else vid)
            yt_video_rows.append({"label": lab, "value": views, "sub": f"{fmt(mins)} min" if mins is not None else ""})
        yt_video_rows.sort(key=lambda r: -r["value"])
    else:
        yt_video_rows = [{"label": r["label"], "value": r["value"]} for r in ytp["rows"]]
    yt_views_line = (f"{fmt(yt_views_all)} views · {fmt(yt_minutes)} min watched" if yt_views_all is not None and yt_minutes is not None
                     else f"{fmt(yt_views_all)} views" if yt_views_all is not None
                     else f"{fmt(ytp['total'])} public views across {ytp['n_shorts'] + ytp['n_long']} videos")
    yt_small = (f"{fmt(ytp['total'])} on the public counters: {fmt(ytp['shorts_views'])} on {ytp['n_shorts']} Shorts, "
                f"{fmt(ytp['long_views'])} on {ytp['n_long']} episodes and trailers")
    yt_kpi = fmt(yt_views_all) if yt_views_all is not None else fmt(ytp["total"])
    yt_kpi_foot = ("YouTube Analytics since launch" if yt_views_all is not None else "public counters, since launch")
    if ytp["total"]:
        yt_kpi_foot += f" · {round(100 * ytp['shorts_views'] / ytp['total'])}% on Shorts"

    # ---- Spotify
    sp_plays = sp.get("plays_all")
    sp_line = (f"{fmt(sp_plays)} plays" + (f" · {sp['hours']} listened" if sp.get("hours") else "")) if sp_plays is not None else "n/d"
    sp_small = " · ".join(x for x in [f"{sp['listeners']} listeners in 30 days" if sp.get("listeners") is not None else "",
                                       sp.get("note", "")] if x)
    sp_comments = sp.get("comments") or []

    # ---- feed apps
    app_pct = lambda n: f"{round(100 * n / feed['app_total'])}% of app-attributed downloads" if feed["app_total"] else ""
    # OP3's own app attribution (rolling 30 days) is what Apple/iHeart/Amazon dashboards roughly match;
    # fall back to the raw user agents when the query is missing.
    top_apps = (data["op3"].get("top_apps_for_show") or {}).get("appDownloads") or {}
    if top_apps:
        feed["apps"] = sorted(top_apps.items(), key=lambda kv: -kv[1])
        feed["app_total"] = sum(top_apps.values())
    apps = dict(feed["apps"])
    apple_dl = apps.get("Apple Podcasts", 0) + apps.get("Unknown Apple App", 0) + apps.get("AppleCoreMedia", 0)

    last_day = parse_date(feed["last_day"])
    first_day = last_day - dt.timedelta(days=max(len(feed["daily"]) - 1, 0))

    def app_row(name, n, comments="—", cls="blue", small=""):
        return (f'<tr><td><span class="plat"><span class="dot {cls}"></span>{esc(name)}</span></td><td class="num">n/d</td>'
                f'<td class="num">{fmt(n)} downloads (30 days){f"<div class=small>{esc(small)}</div>" if small else ""}</td>'
                f'<td class="num">{comments}</td><td>{pill(short_date(last_day))}</td></tr>')
    other_apps = [(k, v) for k, v in feed["apps"] if k not in ("Apple Podcasts", "Unknown Apple App", "AppleCoreMedia")]
    table_rows = [
        f'<tr><td><span class="plat"><span class="dot rose"></span>YouTube</span></td><td class="num">{fmt(yt_subs)}</td>'
        f'<td class="num">{esc(yt_views_line)}<div class="small">{esc(yt_small)}</div></td>'
        f'<td class="num">{len(yt_comments)}</td><td>{pill("today")}</td></tr>',
        f'<tr><td><span class="plat"><span class="dot gold"></span>Spotify</span></td><td class="num">{fmt(sp["followers"]) if sp.get("followers") is not None else "n/d"}</td>'
        f'<td class="num">{esc(sp_line)}{f"<div class=small>{esc(sp_small)}</div>" if sp_small else ""}</td>'
        f'<td class="num">{len(sp_comments)}</td><td>{pill("today") if sp else pill("not read", "na")}</td></tr>',
        app_row("Apple Podcasts", apple_dl, f"{len(reviews)} reviews", small=app_pct(apple_dl)),
    ] + [app_row(k, v) for k, v in other_apps] + [
        f'<tr><td><span class="plat"><span class="dot blue"></span>Pandora</span></td><td class="num">n/d</td>'
        f'<td class="num">no download data<div class="small">Pandora does not report to the feed</div></td><td class="num">—</td><td>{pill("live", "na")}</td></tr>',
        f'<tr><td><span class="plat"><span class="dot mut"></span>Web (browser)</span></td><td class="num">—</td>'
        f'<td class="num">{fmt(feed["web_total"])} downloads<div class="small">{esc(" · ".join(f"{k} {v}" for k, v in feed["browsers"]))}</div></td>'
        f'<td class="num">—</td><td>{pill(short_date(last_day))}</td></tr>',
    ]

    total_followers = (yt_subs or 0) + (sp.get("followers") or 0)
    total_comments = len(yt_comments) + len(sp_comments) + len(reviews)

    # ---- this week
    wk_delta = feed["week"] - feed["prev_week"]
    week_items = [
        ("Feed downloads", fmt(feed["week"]), f"{feed['week_label']} · {'+' if wk_delta >= 0 else ''}{wk_delta} vs the week before"),
    ]
    if yta.get("views_7d") is not None:
        week_items.append(("YouTube views", fmt(yta["views_7d"]), "last 7 days, YouTube Analytics"))
    if sp.get("plays_7d") is not None:
        week_items.append(("Spotify plays", fmt(sp["plays_7d"]), "last 7 days, creator dashboard"))
    if yta.get("new_subscribers_7d") is not None or sp.get("new_followers_7d") is not None:
        week_items.append(("New followers", fmt((yta.get("new_subscribers_7d") or 0) + (sp.get("new_followers_7d") or 0)),
                           "YouTube + Spotify, last 7 days"))
    week_html = "".join(f'<div class="kpi"><div class="lab">{esc(l)}</div><div class="val">{v}</div><div class="foot">{esc(f)}</div></div>'
                        for l, v, f in week_items)

    # ---- month by month (feed from OP3 rows; YouTube and Spotify from Analytics/dashboard or weekly snapshots)
    months = months_since_launch(asof)
    snaps = extra.get("_snapshots") or []
    # snapshots mix Analytics and public counters; only compare like with like
    yt_key = "yt_views" if snaps and all(s.get("yt_views_source") == "analytics" for s in snaps if s.get("yt_views") is not None) else "yt_public_views"
    yt_month = {r[0]: (r[1], False) for r in (yta.get("by_month") or [])} or monthly_from_snapshots(snaps, yt_key, months)
    sp_month = {r[0]: (r[1], False) for r in (sp.get("by_month") or [])} or monthly_from_snapshots(snaps, "sp_plays", months)
    fol_month = monthly_from_snapshots(snaps, "followers", months)

    def mcell(d, ym):
        if ym not in d:
            return '<td class="num"><span class="small">n/d</span></td>'
        v, cum = d[ym]
        return f'<td class="num">{fmt(v)}{"<div class=small>since launch</div>" if cum else ""}</td>'

    month_rows = []
    for ym in months:
        lab = month_label(ym) + (" (to date)" if ym == asof.strftime("%Y-%m") else "")
        month_rows.append(f'<tr><td><b>{esc(lab)}</b></td><td class="num">{fmt(feed["by_month"].get(ym, 0))}</td>'
                          f'{mcell(yt_month, ym)}{mcell(sp_month, ym)}{mcell(fol_month, ym)}</tr>')
    month_table = ('<table><thead><tr><th>Month</th><th class="num">Feed downloads</th><th class="num">YouTube views</th>'
                   '<th class="num">Spotify plays</th><th class="num">New followers</th></tr></thead><tbody>'
                   + "".join(month_rows) + "</tbody></table>")
    month_note = ("YouTube and Spotify months come from " + ("YouTube Analytics and the creator dashboard." if yta.get("by_month") or sp.get("by_month") else
                  "the weekly snapshots saved with each report (the change between the last reading of one month and the next); the first tracked month shows the total since launch.")
                  + " Feed months are exact (OP3, one-day lag).")
    # ---- charts payload
    hb = [
        {"id": "c-feed", "rows": feed["by_episode"], "cls": "", "unit": "", "opts": {"aria": "Downloads per episode on the feed"}},
        {"id": "c-yt", "rows": yt_video_rows[:18], "cls": "rose", "unit": " views", "opts": {"aria": "Views per video on YouTube", "labW": 275}},
        {"id": "c-sp", "rows": [{"label": r[0], "value": r[1], "sub": r[2] if len(r) > 2 else ""} for r in sp.get("episodes", [])],
         "cls": "gold", "unit": " plays", "opts": {"aria": "Plays per episode on Spotify"}},
        {"id": "c-geo-feed", "rows": feed["by_country"], "cls": "", "unit": " downloads", "opts": {"aria": "Feed downloads by country", "labW": 150}},
    ]
    if sp.get("country"):
        hb.append({"id": "c-geo-sp", "rows": [{"label": k, "value": v} for k, v in sp["country"].items()], "cls": "gold", "unit": "%",
                   "opts": {"aria": "Spotify listeners by country", "labW": 150}})
    if yta.get("traffic"):
        hb.append({"id": "c-src", "rows": [{"label": r[0], "value": r[1]} for r in yta["traffic"]], "cls": "rose", "unit": " views",
                   "opts": {"aria": "YouTube traffic sources", "labW": 180}})
    if yta.get("demographics"):
        hb.append({"id": "c-demo", "rows": [{"label": r[0], "value": r[1]} for r in yta["demographics"]], "cls": "rose", "unit": "%",
                   "opts": {"aria": "Age and gender of YouTube viewers", "labW": 150}})
    report = {"hbars": hb, "daily": feed["daily"], "prchips": feed["pr_regions"][:12],
              "ytgeo": yta.get("by_country") or None}

    # ---- comments section
    said = []
    for c in yt_comments:
        said.append(f'<div class="comment"><div class="who">{esc(c.get("who", ""))}</div><div class="txt">“{esc(c.get("text", ""))}”</div>'
                    f'<div class="ctx">{esc(c.get("ctx", ""))}</div></div>')
    for c in sp_comments:
        said.append(f'<div class="comment"><div class="who">{esc(c.get("who", ""))} · Spotify</div><div class="txt">“{esc(c.get("text", ""))}”</div>'
                    f'<div class="ctx">{esc(c.get("ctx", ""))}</div></div>')
    for r in reviews:
        said.append(f'<div class="comment"><div class="who">{esc(r["author"])} · Apple Podcasts ({r["store"]}) · {esc(r["date"])} · {esc(r["rating"])} stars</div>'
                    f'<div class="txt">{esc(r["title"])}</div><div class="ctx">{esc(r["text"])}</div></div>')
    if not yt_comments:
        said.append('<div class="empty"><b>YouTube</b> No comments yet.</div>' if yta else
                    '<div class="empty"><b>YouTube</b> Comments not read this time (needs the API).</div>')
    if not reviews:
        said.append('<div class="empty"><b>Apple Podcasts</b> No reviews or ratings yet (US and Puerto Rico storefronts).</div>')
    if sp and not sp_comments:
        said.append('<div class="empty"><b>Spotify</b> 0 comments and 0 questions. Verified today in the Comments tab of the creator dashboard.</div>')
    if yt_likes is not None:
        said.append(f'<div class="empty"><b>YouTube likes</b> {fmt(yt_likes)} in total{esc(": " + yta["likes_note"]) if yta.get("likes_note") else "."}</div>')

    # ---- notes
    notes = list(extra.get("notes") or [])
    notes.insert(0, f"Feed downloads are measured by OP3 on the canonical feed since {short_date(parse_date(OP3_START if feed['daily'] else LAUNCH))} "
                    f"and arrive with a one-day lag: the last day included is {long_date(last_day)}. Pandora and the Spotify app do not pull from the feed.")
    if yt_views_all is None:
        notes.append("YouTube: public per-video counters read today. They exclude Shorts-feed plays, so YouTube Analytics reports more views.")
    else:
        notes.append(f"YouTube: Analytics views since launch, read today ({fmt(ytp['total'])} on the public counters, which exclude Shorts-feed plays).")
    if sp:
        notes.append("Spotify: read today from the Spotify for Creators dashboard (all-time plays, followers, listeners in the last 30 days).")
    else:
        notes.append("Spotify: not read this time (needs a login to the creator dashboard).")

    logo_b64 = base64.b64encode(open(os.path.join(ROOT, "assets", "logo-thp.png"), "rb").read()).decode()
    css = open(os.path.join(HERE, "report.css"), encoding="utf-8").read()
    js = open(os.path.join(HERE, "charts.js"), encoding="utf-8").read()
    chips = "".join(f'<a href="{esc(u)}">{esc(n)}</a>' for n, u, *_ in LINKS if n in PLATFORM_CHIPS)
    links = "".join(f'<div><b>{esc(n)}:</b> <a href="{esc(u)}">{esc(rest[0] if rest else u)}</a></div>' for n, u, *rest in LINKS)
    us_note = " · ".join(f"{k} {v}" for k, v in feed["us_regions"][:8]) or "none yet"
    other_note = ", ".join(feed["other_countries"][:8])

    return f"""<!doctype html><html lang="en" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>Audience Report {asof.isoformat()}</title>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,600;9..144,700&family=IBM+Plex+Sans:wght@400;500;600&display=swap">
<style>{css}</style></head><body>
<div class="wrap">
<div class="band">
  <img class="logo" src="data:image/png;base64,{logo_b64}" alt="thp. the healthcare paradox">
  <div class="bandtxt">
    <div class="bandeyebrow">The Healthcare Paradox · Audience report · week {asof.isocalendar()[1]}</div>
    <div class="bandtitle">Who listens, where, and what they've said</div>
    <div class="bandsub">As of {long_date(asof)} · everything since launch ({long_date(launch)}, {days_live} days) · YouTube, Spotify and the feed (OP3) read today</div>
    <div class="bandsub" style="margin-top:6px"><a href="https://thehealthcareparadox.com" style="color:#fff;font-weight:600;text-decoration:underline">thehealthcareparadox.com</a> · <a href="mailto:info@thehealthcareparadox.com" style="color:#fff;font-weight:600;text-decoration:underline">info@thehealthcareparadox.com</a></div>
    <div class="platrow">{chips}</div>
  </div>
</div>

<section>
  <h2>Summary by platform</h2>
  <div class="card tablewrap"><table>
    <thead><tr><th>Platform</th><th class="num">Followers</th><th class="num">Listens / views (since launch)</th><th class="num">Comments</th><th>As of</th></tr></thead>
    <tbody>{"".join(table_rows)}</tbody></table></div>
  <p class="sub">Feed downloads measured by OP3 (Apple Podcasts, iHeartRadio, Amazon Music, Podcast Addict and the website) from {short_date(first_day)} to {short_date(last_day)}: {fmt(feed['total'])} in total. Apple, Amazon, iHeart and Pandora do not publish follower counts.</p>
</section>

<section>
  <div class="kpis">
    <div class="kpi"><div class="lab">Total followers</div><div class="val">{fmt(total_followers)}</div><div class="foot">{fmt(yt_subs)} YouTube + {fmt(sp.get('followers') or 0)} Spotify</div></div>
    <div class="kpi"><div class="lab">Feed downloads</div><div class="val">{fmt(feed['total'])}</div><div class="foot">since launch · all apps and the web</div></div>
    <div class="kpi"><div class="lab">YouTube views</div><div class="val">{yt_kpi}</div><div class="foot">{esc(yt_kpi_foot)}</div></div>
    <div class="kpi"><div class="lab">Comments and reviews</div><div class="val">{total_comments}</div><div class="foot">{len(yt_comments)} YouTube · {len(sp_comments)} Spotify · {len(reviews)} Apple reviews</div></div>
  </div>
</section>

<section>
  <h2>This week</h2>
  <div class="kpis">{week_html}</div>
</section>

<section>
  <h2>Month by month</h2>
  <div class="card tablewrap">{month_table}<p class="note" style="margin-top:8px">{esc(month_note)}</p></div>
</section>

<section>
  <h2>Most listened episodes</h2>
  <div class="grid2">
    {card('On the feed (Apple, iHeart, Amazon, web)', 'Downloads per episode since launch. PR and US counts after the bar.', '<div id="c-feed"></div>')}
    {card('On YouTube', ('Views per video, YouTube Analytics since launch.' if yta.get('by_video') else 'Public view counters read today.') + ' Shorts dominate; full episodes add minutes, not views.', '<div id="c-yt"></div>')}
    {card('On Spotify', 'Plays per episode since publication, from the creator dashboard.' if sp.get('episodes') else 'Not read this time.', '<div id="c-sp"></div>')}
  </div>
</section>

<section>
  <h2>Download pace</h2>
  {card('Feed downloads per day', f'Every day since OP3 started counting. Last 7 days ({esc(feed["week_label"])}): {fmt(feed["week"])} downloads, the 7 days before: {fmt(feed["prev_week"])}.', '<div id="c-days"></div>')}
</section>

<section>
  <h2>Where they listen from</h2>
  <div class="grid2">
    {card('Feed: downloads by country', f'{fmt(feed["total"])} downloads. ' + (f'The other countries ({esc(other_note)}) are almost certainly bots and crawlers.' if other_note else ''), '<div id="c-geo-feed"></div><div class="chips" id="pr-chips"></div>', f'<p class="note">United States: {esc(us_note)}</p>')}
    {card('YouTube: views and minutes by country', 'YouTube Analytics since launch.' if yta.get('by_country') else 'Needs YouTube Analytics; not read this time.', '<div id="c-geo-yt"></div>', '<div class="legend"><span><span class="dot rose"></span>Views</span><span><span class="dot gold"></span>Minutes watched</span></div>' if yta.get('by_country') else '')}
    {card('Spotify: listeners by country', (f'{sp.get("listeners", "n/d")} listeners in the last 30 days, from the creator dashboard.'), '<div id="c-geo-sp"></div>', f'<p class="note">{esc(sp.get("gender", ""))}</p>' if sp.get('gender') else '') if sp.get('country') else ''}
  </div>
</section>

{('<section><h2>Who watches on YouTube</h2><div class="grid2">' + card('How they arrive', 'Views by traffic source, YouTube Analytics since launch', '<div id="c-src"></div>') + card('Age and gender', 'Share of viewers, YouTube Analytics', '<div id="c-demo"></div>') + '</div></section>') if yta.get('traffic') or yta.get('demographics') else ''}

<section>
  <h2>What people have said</h2>
  <div class="card" style="display:grid; gap:14px">{"".join(said)}</div>
</section>

<section>
  <h2>How to read these numbers</h2>
  <div class="card"><ul class="notes">{"".join(f'<li>{esc(n)}</li>' for n in notes)}</ul></div>
</section>

<section><h2>Listen and follow</h2><div class="card" style="display:grid;gap:6px">{links}</div></section>
</div>
<script>window.REPORT = {json.dumps(report, ensure_ascii=False)};</script>
<script>{js}</script>
</body></html>
"""


FOOTER = ("<div style='font-family:Helvetica,Arial,sans-serif;font-size:8px;color:#8a6b6e;width:100%;padding:0 12mm;display:flex;justify-content:space-between'>"
          "<span><b style='color:#9B1C24'>thp.</b> The Healthcare Paradox · YouTube · Spotify · Apple Podcasts · Amazon Music · iHeartRadio · Pandora · "
          "thehealthcareparadox.com · info@thehealthcareparadox.com</span><span>Page <span class='pageNumber'></span> of <span class='totalPages'></span></span></div>")


def render_pdf(html_path, pdf_path):
    from playwright.sync_api import sync_playwright  # noqa: PLC0415
    exe = os.environ.get("PLAYWRIGHT_CHROMIUM") or ("/opt/pw-browsers/chromium" if os.path.exists("/opt/pw-browsers/chromium") else None)
    kw = {"args": ["--no-sandbox"]}
    if exe:
        kw["executable_path"] = exe
    if os.environ.get("HTTPS_PROXY"):
        kw["proxy"] = {"server": os.environ["HTTPS_PROXY"]}
    with sync_playwright() as p:
        b = p.chromium.launch(**kw)
        pg = b.new_page(viewport={"width": 1100, "height": 1400})
        pg.goto("file://" + os.path.abspath(html_path), wait_until="load", timeout=90000)
        pg.wait_for_timeout(1500)
        pg.emulate_media(media="print")
        pg.pdf(path=pdf_path, format="Letter", print_background=True, display_header_footer=True, header_template="<span></span>",
               footer_template=FOOTER, margin={"top": "12mm", "bottom": "16mm", "left": "12mm", "right": "12mm"}, prefer_css_page_size=True)
        b.close()
    log("wrote", pdf_path, os.path.getsize(pdf_path), "bytes")


def snapshot_from(data, extra, asof):
    """Cumulative totals worth keeping week to week (drives the month-by-month table)."""
    feed_total = len(data["op3"]["rows"])
    ytp = data.get("youtube_public", {})
    yta = extra.get("youtube") or {}
    sp = extra.get("spotify") or {}
    yt_public = sum(v.get("views", 0) for v in ytp.get("videos", []))
    yt_subs = yta.get("subscribers") or ytp.get("subscribers") or 0
    snap = {"date": asof.isoformat(), "feed_total": feed_total,
            "yt_views": yta.get("views_all") if yta.get("views_all") is not None else yt_public,
            "yt_views_source": "analytics" if yta.get("views_all") is not None else "public",
            "yt_public_views": yt_public, "yt_subs": yt_subs,
            "sp_plays": sp.get("plays_all"), "sp_followers": sp.get("followers"),
            "followers": yt_subs + (sp.get("followers") or 0)}
    return snap


def cmd_render(args):
    data = json.load(open(args.data, encoding="utf-8"))
    extra = json.load(open(args.extra, encoding="utf-8")) if args.extra and os.path.exists(args.extra) else {}
    asof = parse_date(args.asof or extra.get("asof") or data.get("asof") or dt.date.today().isoformat())
    snap_dir = args.snapshots
    if snap_dir and not args.no_snapshot:
        os.makedirs(snap_dir, exist_ok=True)
        snap = snapshot_from(data, extra, asof)
        json.dump(snap, open(os.path.join(snap_dir, f"{asof.isoformat()}.json"), "w", encoding="utf-8"), indent=1)
        log("snapshot saved", snap)
    extra["_snapshots"] = load_snapshots(snap_dir) if snap_dir else []
    out = build_html(data, extra, asof)
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)
    open(args.out, "w", encoding="utf-8").write(out)
    log("wrote", args.out)
    if args.pdf:
        render_pdf(args.out, args.pdf)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="fetch OP3, YouTube public counters and Apple reviews")
    c.add_argument("--out", required=True)
    c.add_argument("--asof", default=dt.date.today().isoformat())
    c.set_defaults(fn=cmd_collect)
    r = sub.add_parser("render", help="build the HTML report (and PDF)")
    r.add_argument("--data", required=True)
    r.add_argument("--extra", default=None, help="JSON with Spotify / YouTube Analytics / comments (see README)")
    r.add_argument("--out", required=True, help="HTML output path")
    r.add_argument("--pdf", default=None, help="PDF output path (needs playwright)")
    r.add_argument("--asof", default=None)
    r.add_argument("--snapshots", default=os.path.join(ROOT, "reports", "audience", "snapshots"),
                   help="folder of weekly totals (read for the month-by-month table; today's is written unless --no-snapshot)")
    r.add_argument("--no-snapshot", action="store_true", help="do not write today's snapshot")
    r.set_defaults(fn=cmd_render)
    args = ap.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
