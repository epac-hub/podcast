# The Healthcare Paradox — operating rules for Claude

This repository publishes the podcast (audio, feed, site) and its YouTube videos.
Follow these rules in every session.

## Publishing an episode (one command)

```
python3 scripts/publish_episode.py <recording.m4a> --title "<title>" --date YYYY-MM-DD --number N \
    [--short-title "<YouTube title, <=100 chars>"] [--description "<feed description>"]
```

It normalizes the audio, splices the intro and outro bumpers (`promo/bumpers/`),
writes `metadata.json` (pubtime 07:30 UTC by default), transcribes with the glossary
(`scripts/glossary.json`), renders `promo/epNN-full.mp4` (intro clip + cover + outro
clip) and `promo/epNN-thumb.jpg`, writes `promo/epNN-youtube.json`, and rebuilds the site.

Then:
1. Write `notes.md` from the transcript in the house format: one intro paragraph with
   bold figures, `In this episode:`, bold-led bullets, `The closing question: ...`,
   then the standard footer (Listen on..., CMS Console line, music credit). Put the
   one-paragraph feed description in `metadata.json` (`description`).
2. `python3 scripts/publish_episode.py --episode episodes/NNN-... --steps yt-meta,build`
3. Commit on the session branch, push, open a draft PR against `main`, mark it ready,
   squash-merge it, then reset the branch onto `origin/main`.
4. Upload the YouTube video (next section) and verify the live feed shows the episode.

## YouTube uploads

Use `promo/epNN-youtube.json` (title, description, tags, thumbnail URL, playlist) and
`promo/epNN-full.mp4`. Try the paths in this order:

1. **Own Google project (own quota):** `python3 scripts/youtube_upload.py upload promo/epNN-youtube.json`
   once `THP_YT_CLIENT_ID`, `THP_YT_CLIENT_SECRET` and `THP_YT_REFRESH_TOKEN` exist in
   the environment (setup steps are in that script's docstring).
2. **Zapier YouTube connection (separate quota pool):** action `youtube_upload_video`
   (title, description, tags, video = raw GitHub URL of the mp4, thumbnail = raw URL of
   the jpg, privacy_status public, category_id 25, default_language en). Then
   `youtube_add_video_to_playlist` for `PLcYq_st79K6M`.
3. **Composio** `YOUTUBE_MULTIPART_UPLOAD_VIDEO` (account `youtube_wis-foody`, workbench
   session "mile": stage the mp4 with `upload_local_file` from `/tmp`). Its Google
   project is shared and its "Video Uploads per day" quota resets at **07:00 UTC**.
   If it answers `rateLimitExceeded` / `quotaExceeded`, do not retry in a loop: schedule
   one `send_later` retry for 07:05 UTC and tell the user. When an episode is ready
   before 07:00 UTC, prefer scheduling the upload for 07:05 UTC over trying earlier.

After any upload: set the thumbnail, add the video to playlist `PLcYq_st79K6M` without a
position (the playlist is not manually sorted), verify with `videos.list`, and give the
user the `https://www.youtube.com/watch?v=...` link. YouTube titles are at most 100
characters; the full title stays on the site and in the feed.

## Standing rules

- Canonical feed: `https://epac-hub.github.io/podcast/feed.xml` (never accept feed redirects);
  the site is `https://thehealthcareparadox.com`. Give users the site links.
- Contact email: `info@thehealthcareparadox.com`.
- Never include the sentence about our own test downloads in any report or email.
- Never commit `build/` or `docs/`; CI builds `docs/` on every merge to `main`.
- `guid_base` in `podcast.config.json` never changes. Renaming an episode changes only
  `title`; the folder, slug and GUID stay.
- Apple truncates titles at 255 characters; YouTube at 100 (`short_title` in metadata).
- Shorts are review-before-publish; episodes are publish-on-request.
- Never mix YouTube counters (public views vs Analytics views) in reports.
- Routines bound to this session: daily YouTube RSS-duplicate sweep at 07:10 UTC
  (cron), weekly audience report on Sundays at 21:00 UTC (`scripts/audience_report.py`).

## Environment notes

- Cloud containers restart: `apt-get install -y ffmpeg` and
  `pip install faster-whisper mutagen jinja2 markdown pillow requests playwright pymupdf`
  bring the pipeline back. Keep large temporary files out of `/mnt/files` in the
  Composio sandbox (use `/tmp` there).
- The Composio YouTube proxy returns tuples; search the result recursively for `items`.
