# Podcast

A self-contained podcast: audio, RSS feed, and website all live in this repository
and are published with GitHub Pages. Submitting `feed.xml` once to Apple Podcasts,
Spotify, and other directories is all it takes to distribute the show.

## How it works

```
podcast.config.json        show-level metadata (title, description, author, ...)
assets/cover.jpg           cover art (2048x2048 JPEG, kept under 512 KB for Apple)
episodes/NNN-slug/         one folder per episode
  episode.mp3              normalized audio
  metadata.json            title, date, duration, ...
  notes.md                 show notes (markdown)
  transcript.txt|.vtt      transcript (optional)
scripts/                   the pipeline
templates/                 Jinja2 site templates + CSS
docs/                      build output (generated; deployed to GitHub Pages)
```

On every push to `main`, the GitHub Actions workflow
(`.github/workflows/deploy.yml`) rebuilds `docs/` and deploys it to GitHub Pages:

- Site: https://thehealthcareparadox.com
- Feed: https://thehealthcareparadox.com/feed.xml (the same feed is served at https://epac-hub.github.io/podcast/feed.xml, the URL registered with the directories)
- Data: https://healthconsole.org (CMS Console) and https://insurancepr.org (Puerto Rico Insurance Observatory)

## Adding an episode

One command does the whole pipeline (normalize, intro/outro bumpers, transcript with the
glossary, metadata, YouTube video + thumbnail, YouTube metadata, site build):

```
python3 scripts/publish_episode.py inbox/recording.m4a \
    --title "Episode title" --date 2026-09-30 --number 14 \
    [--short-title "YouTube title (<=100 chars)"] [--description "Feed description"]
```

Then write `episodes/NNN-slug/notes.md`, regenerate the YouTube metadata and the site
with `python3 scripts/publish_episode.py --episode episodes/NNN-slug --steps yt-meta,build`,
commit, and merge to `main`. Upload `promo/epNN-full.mp4` with `promo/epNN-youtube.json`
(`scripts/youtube_upload.py upload promo/epNN-youtube.json` with the show's own Google
OAuth client; see `CLAUDE.md` for the fallback paths).

The individual steps still exist: `scripts/new_episode.py` (ingest only),
`scripts/transcribe.py` (Whisper with `scripts/glossary.json`; `--fix-only` re-applies the
glossary to an existing transcript), `scripts/build.py` (site + feed).

## Configuring the show

Edit `podcast.config.json` (title, description, author, category, language,
explicit flag, owner contact for directories). Regenerate placeholder cover art
with `python3 scripts/make_cover.py`, or drop your own square 1400-3000px JPG
at `assets/cover.jpg` — keep the file under 512 KB or Apple Podcasts will
reject the feed's artwork.

## Submitting to directories

1. Make sure the site is live and `feed.xml` validates (https://podba.se/validate/
   or https://castfeedvalidator.com/).
2. Apple Podcasts: https://podcastsconnect.apple.com → add show via RSS URL.
3. Spotify: https://podcasters.spotify.com → add existing show via RSS URL.
4. Most other apps (Overcast, Pocket Casts, ...) pick the show up automatically
   from Apple's directory.

Note: Apple requires an owner email in the feed (`owner_email` in the config).
