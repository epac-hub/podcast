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

- Site: https://epac-hub.github.io/podcast/
- Feed: https://epac-hub.github.io/podcast/feed.xml

## Adding an episode

```bash
pip install jinja2 markdown mutagen faster-whisper   # once
# ffmpeg must be installed

# 1. Ingest the audio (converts to normalized MP3, creates the episode folder)
python3 scripts/new_episode.py recording.m4a --title "My episode title" \
    --description "One-paragraph episode description."

# 2. Transcribe (optional but recommended)
python3 scripts/transcribe.py episodes/001-my-episode-title

# 3. Edit episodes/001-.../notes.md with the show notes

# 4. Rebuild the site and feed
python3 scripts/build.py

# 5. Commit and push — GitHub Pages redeploys automatically
```

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
