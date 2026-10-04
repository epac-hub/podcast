#!/usr/bin/env python3
"""Upload an episode video to YouTube with the show's OWN Google OAuth client.

Why: the shared connector quota ("Video Uploads per day" on a third-party Google
project) blocks uploads for hours. A project owned by the show has its own quota
(10,000 units/day; an upload costs about 1,600, a thumbnail 50, a playlist insert 50).

One-time setup (about ten minutes, in the Google account that owns the channel):
  1. console.cloud.google.com -> new project (e.g. "thp-podcast").
  2. APIs & Services -> Library -> enable "YouTube Data API v3".
  3. OAuth consent screen -> External -> add the channel's Google account as a test user.
  4. Credentials -> Create credentials -> OAuth client ID -> "TVs and Limited Input devices".
  5. Give the client id and secret to the environment as THP_YT_CLIENT_ID and
     THP_YT_CLIENT_SECRET (or write ~/.config/thp/youtube_client.json with those two keys).
  6. python3 scripts/youtube_upload.py auth   -> prints a URL and a code; approve it in a
     browser. The refresh token is saved to ~/.config/thp/youtube_token.json; copy its
     "refresh_token" into THP_YT_REFRESH_TOKEN so cloud sessions survive container resets.

Then, per episode:
  python3 scripts/youtube_upload.py upload promo/ep14-youtube.json [--privacy public]
  python3 scripts/youtube_upload.py status VIDEO_ID
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("THP_CONFIG_DIR", Path.home() / ".config" / "thp"))
TOKEN_FILE = Path(os.environ.get("THP_YT_TOKEN_FILE", CONFIG_DIR / "youtube_token.json"))
CLIENT_FILE = CONFIG_DIR / "youtube_client.json"
SCOPE = "https://www.googleapis.com/auth/youtube"
API = "https://www.googleapis.com/youtube/v3"
UPLOAD = "https://www.googleapis.com/upload/youtube/v3"
CHUNK = 8 * 1024 * 1024


def client_credentials() -> tuple[str, str]:
    cid, sec = os.environ.get("THP_YT_CLIENT_ID"), os.environ.get("THP_YT_CLIENT_SECRET")
    if not (cid and sec) and CLIENT_FILE.exists():
        c = json.loads(CLIENT_FILE.read_text())
        cid, sec = c.get("client_id"), c.get("client_secret")
    if not (cid and sec):
        sys.exit("error: set THP_YT_CLIENT_ID and THP_YT_CLIENT_SECRET (see the docstring)")
    return cid, sec


def save_token(tok: dict) -> None:
    TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_FILE.write_text(json.dumps(tok, indent=2))
    os.chmod(TOKEN_FILE, 0o600)


def cmd_auth(_args) -> None:
    cid, sec = client_credentials()
    r = requests.post("https://oauth2.googleapis.com/device/code",
                      data={"client_id": cid, "scope": SCOPE}, timeout=30)
    r.raise_for_status()
    d = r.json()
    print(f"\nOpen {d['verification_url']} and enter the code: {d['user_code']}\n"
          f"(waiting up to {d['expires_in'] // 60} minutes)")
    interval = d.get("interval", 5)
    deadline = time.time() + d["expires_in"]
    while time.time() < deadline:
        time.sleep(interval)
        t = requests.post("https://oauth2.googleapis.com/token", data={
            "client_id": cid, "client_secret": sec, "device_code": d["device_code"],
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code"}, timeout=30).json()
        if "access_token" in t:
            t["expires_at"] = time.time() + t.get("expires_in", 3600) - 60
            save_token(t)
            print(f"authorized. token saved to {TOKEN_FILE}\n"
                  f"THP_YT_REFRESH_TOKEN={t['refresh_token']}")
            return
        err = t.get("error")
        if err == "slow_down":
            interval += 5
        elif err not in ("authorization_pending", None):
            sys.exit(f"error: {err}: {t.get('error_description', '')}")
    sys.exit("error: the code expired before it was approved")


def access_token() -> str:
    cid, sec = client_credentials()
    tok = json.loads(TOKEN_FILE.read_text()) if TOKEN_FILE.exists() else {}
    refresh = os.environ.get("THP_YT_REFRESH_TOKEN") or tok.get("refresh_token")
    if not refresh:
        sys.exit("error: not authorized yet; run `youtube_upload.py auth`")
    if tok.get("access_token") and tok.get("expires_at", 0) > time.time() and tok.get("refresh_token") == refresh:
        return tok["access_token"]
    r = requests.post("https://oauth2.googleapis.com/token", data={
        "client_id": cid, "client_secret": sec, "refresh_token": refresh,
        "grant_type": "refresh_token"}, timeout=30)
    if r.status_code != 200:
        sys.exit(f"error: token refresh failed: {r.text}")
    t = r.json()
    tok.update({"access_token": t["access_token"], "refresh_token": refresh,
                "expires_at": time.time() + t.get("expires_in", 3600) - 60})
    save_token(tok)
    return tok["access_token"]


def api(method: str, url: str, token: str, **kw) -> requests.Response:
    headers = kw.pop("headers", {})
    headers["Authorization"] = f"Bearer {token}"
    r = requests.request(method, url, headers=headers, timeout=kw.pop("timeout", 120), **kw)
    if r.status_code >= 400:
        sys.exit(f"error: {method} {url} -> {r.status_code}: {r.text[:800]}")
    return r


def cmd_upload(args) -> None:
    meta_path = Path(args.meta)
    meta = json.loads(meta_path.read_text())
    video = (ROOT / meta["video"]) if not Path(meta["video"]).is_absolute() else Path(meta["video"])
    if not video.exists():
        sys.exit(f"error: video not found: {video}")
    token = access_token()
    size = video.stat().st_size
    body = {
        "snippet": {"title": meta["title"], "description": meta["description"],
                    "tags": meta.get("tags", []), "categoryId": meta.get("categoryId", "25"),
                    "defaultLanguage": meta.get("defaultLanguage", "en"),
                    "defaultAudioLanguage": meta.get("defaultAudioLanguage", "en-US")},
        "status": {"privacyStatus": args.privacy or meta.get("privacyStatus", "public"),
                   "selfDeclaredMadeForKids": False},
    }
    print(f"starting resumable upload of {video.name} ({size / 1e6:.1f} MB)")
    r = api("POST", f"{UPLOAD}/videos?uploadType=resumable&part=snippet,status", token,
            headers={"Content-Type": "application/json; charset=UTF-8",
                     "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(size)},
            data=json.dumps(body))
    session = r.headers["Location"]
    sent = 0
    with open(video, "rb") as f:
        while sent < size:
            f.seek(sent)
            chunk = f.read(CHUNK)
            end = sent + len(chunk) - 1
            rr = requests.put(session, data=chunk, timeout=600, headers={
                "Content-Length": str(len(chunk)), "Content-Type": "video/mp4",
                "Content-Range": f"bytes {sent}-{end}/{size}"})
            if rr.status_code in (200, 201):
                vid = rr.json()["id"]
                break
            if rr.status_code == 308:
                rng = rr.headers.get("Range")
                sent = int(rng.split("-")[1]) + 1 if rng else end + 1
                print(f"  {sent / size:6.1%}", flush=True)
                continue
            sys.exit(f"error: upload chunk failed {rr.status_code}: {rr.text[:500]}")
    print(f"uploaded: https://www.youtube.com/watch?v={vid}")

    thumb = meta.get("thumbnail")
    if thumb and (ROOT / thumb).exists():
        api("POST", f"{UPLOAD}/thumbnails/set?videoId={vid}", token,
            headers={"Content-Type": "image/jpeg"}, data=(ROOT / thumb).read_bytes())
        print("thumbnail set")
    pl = meta.get("playlist_id")
    if pl:
        api("POST", f"{API}/playlistItems?part=snippet", token,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"snippet": {"playlistId": pl,
                                         "resourceId": {"kind": "youtube#video", "videoId": vid}}}))
        print(f"added to playlist {pl}")
    print(json.dumps({"video_id": vid, "url": f"https://www.youtube.com/watch?v={vid}"}))


def cmd_status(args) -> None:
    token = access_token()
    r = api("GET", f"{API}/videos?part=status,contentDetails,snippet&id={args.video_id}", token)
    items = r.json().get("items", [])
    if not items:
        sys.exit("error: video not found")
    it = items[0]
    print(json.dumps({"title": it["snippet"]["title"], "privacy": it["status"]["privacyStatus"],
                      "upload": it["status"]["uploadStatus"],
                      "duration": it["contentDetails"]["duration"]}, indent=2))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("auth", help="one-time device-code authorization").set_defaults(fn=cmd_auth)
    u = sub.add_parser("upload", help="upload promo/epNN-youtube.json's video, thumbnail, playlist")
    u.add_argument("meta")
    u.add_argument("--privacy", choices=["public", "unlisted", "private"], default=None)
    u.set_defaults(fn=cmd_upload)
    s = sub.add_parser("status", help="show a video's processing status")
    s.add_argument("video_id")
    s.set_defaults(fn=cmd_status)
    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
