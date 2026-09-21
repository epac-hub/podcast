# Audience report

Weekly, all-platform audience report for The Healthcare Paradox: one branded PDF (English) with
everything since launch plus a "this week" strip. Sent every Sunday at 5:00 p.m. Puerto Rico time
(21:00 UTC) by the "Weekly audience report" routine.

```
python3 scripts/audience_report.py collect --out build/audience/data.json
python3 scripts/audience_report.py render --data build/audience/data.json \
    --extra build/audience/extra.json --out build/audience/report.html \
    --pdf build/audience/The-Healthcare-Paradox-Audience-Report-YYYY-MM-DD.pdf
```

`collect` needs only `curl` and pulls what is public or has an API:

- OP3 (feed downloads on the canonical feed, every row since 2026-08-01, plus the 30-day and
  per-episode summaries and the top apps).
- YouTube public pages (`/videos`, `/shorts`, `/about`): subscribers, channel views, views per video.
- Apple Podcasts customer reviews RSS (US and PR storefronts).

`render` needs `playwright` for the PDF (`pip install playwright`; Chromium is taken from
`$PLAYWRIGHT_CHROMIUM`, `/opt/pw-browsers/chromium`, or Playwright's own install). The HTML alone
needs nothing.

## extra.json

Numbers that need a logged-in read go in a small JSON. Every key is optional; the report says
"not read this time" for anything missing.

```json
{
  "asof": "2026-09-27",
  "spotify": {
    "followers": 4, "plays_all": 40, "plays_7d": 1, "hours": "5 h 5 min", "listeners": 12,
    "new_followers_7d": 0,
    "country": {"Puerto Rico": 94.9, "United States": 5.1},
    "gender": "Men 70% · Women 22.5% · Not specified 7.5%",
    "episodes": [["Ep 1 · The Island That Broke the Spreadsheet", 15, "3 listeners"], ["Ep 4 · Roadmap to the Republican Letter", 11]],
    "comments": [{"who": "name · date", "text": "...", "ctx": "on which episode"}],
    "note": "episodes 9 and 10 still at 0"
  },
  "youtube": {
    "subscribers": 6, "views_all": 733, "minutes_all": 255, "views_7d": 40, "new_subscribers_7d": 1,
    "by_country": [["United States", 401, 78], ["Puerto Rico", 332, 177]],
    "by_video": [["j33KAE5IF0Q", 167, 14], ["G06mxFWUvBE", 64, 17]],
    "traffic": [["Shorts feed", 643], ["Channel page", 129]],
    "demographics": [["Men 45 to 54", 33.1], ["Women 65+", 30.8]],
    "likes": 8, "likes_note": "the grandmother Short 2, the rest 1 each",
    "comments": [{"who": "@sirgalaga6577 · YouTube · Sep 8, 2026", "text": "THANK YOU", "ctx": "On the oncologist Short"}]
  },
  "notes": ["Anything worth flagging this week."]
}
```

`by_video` rows are `[videoId, views, minutes, label]`; the label is optional (it is derived from the
public title when omitted). Spotify `episodes` rows are `[label, plays, note]`.

Where the logged-in numbers come from:

- Spotify for Creators (`https://creators.spotify.com/dash/show/7K7Ub2NPG2Km4aGw0C25eN/overview`,
  `/episodes`, `/analytics/show/<id>/audience`, `/interactivity/show/<id>/comments`). Login is
  passwordless: the 6-digit code arrives at the owner's Gmail from no-reply@alerts.spotify.com.
- YouTube Analytics API (`youtubeanalytics.googleapis.com/v2/reports`, `ids=channel==MINE`) and the
  Data API comment threads for channel `UCJX4WAViwqzsNivDlBu_IQQ`. The Data API quota resets at
  07:00 UTC.

Do not put the owner's test downloads in the report, and keep the contact email as
info@thehealthcareparadox.com.
