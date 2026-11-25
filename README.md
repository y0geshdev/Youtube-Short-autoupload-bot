# YouTube Short Auto-Upload Bot

A config-driven Python bot that converts clip metadata (JSON + MP4) into a YouTube-ready CSV and uploads scheduled Shorts to YouTube using the YouTube Data API v3.

**Multi-channel support:** Each YouTube channel gets its own directory under `channels/` containing its own config, CSV, staged videos, and OAuth token. This keeps multiple channels completely isolated.

---

## What It Does

1. **`convert_clips.py`** — Reads per-clip JSON metadata files (`clipNN.json`) and matching MP4s from a clips directory, copies the MP4s into a channel's `videos/` staging folder, and writes `video_metadata.csv` in the exact format `app.py` expects.
2. **`app.py`** — Reads `video_metadata.csv` via `csv.DictReader`, stages MP4s from `videos/`, authenticates with Google OAuth, lists available channels (asks for confirmation if multiple), and uploads each video with title, description, tags, category, privacy status, and a scheduled publish time.

---

## Repository Layout

```
Youtube-Short-autoupload-bot/
├── app.py                      # Main uploader (config-driven, OAuth + upload)
├── convert_clips.py            # Generic clip JSON → CSV converter (config-driven)
├── config.json                 # Root-level settings (global defaults for upload + converter)
├── yt_upload.json              # Google OAuth 2.0 client secrets (YouTube Data API v3)
├── token.json                  # Auto-generated OAuth token (created on first run)
├── catogory.txt                # YouTube video category ID reference
├── README.md                   # This file
├── .gitignore                  # Ignores env/, __pycache__, channel video dirs
└── channels/                   # One directory per YouTube channel
    ├── <channel-name>/         # Per-channel directory (auto-created on first run)
    │   ├── config.json         # Channel-specific settings (overrides root config.json)
    │   ├── yt_upload.json      # Channel-specific OAuth client secrets (optional)
    │   ├── token.json          # Channel-specific OAuth token (auto-created)
    │   ├── videos/             # Staged MP4s ready for upload (clip01.mp4 … clipNN.mp4)
    │   └── video_metadata.csv  # Generated CSV consumed by app.py (for this channel)
    └── <channel-name-2>/
        ├── config.json
        ├── yt_upload.json
        ├── token.json
        ├── videos/
        └── video_metadata.csv
```

> **Key rule:** Every channel gets its own subdirectory under `channels/`. All channel-specific artifacts — config, OAuth token, staged videos, generated CSV — live inside that channel's directory. The root-level files are global defaults/templates only.

---

## Configuration Files to Update or Edit

You need to edit these files before running:

| File | Location | What to Edit |
|------|----------|--------------|
| `yt_upload.json` | Repo root | **Required** — Replace placeholder client_id/client_secret with your real Google OAuth 2.0 credentials |
| `config.json` | Repo root | **Root defaults** — Review global defaults (category, privacy, schedule timings, clips_dir, etc.) for upload + converter |
| `channels/<channel-name>/config.json` | Per-channel | **Per-channel** — Override any root `config.json` setting for this specific channel (clips_dir, video_directory, csv_file, schedule, etc.) |
| `channels/<channel-name>/yt_upload.json` | Per-channel | Optional — Use different OAuth credentials for this channel |

**Minimum edits to get started:**
1. Replace `yt_upload.json` with your real Google OAuth credentials
2. Set `clips_dir` in `config.json` (or a channel's `config.json`) to point to your clips directory

---

## Per-Channel Directory Structure (What Gets Created)

When you run the scripts for a channel, the following is created under `channels/<channel-name>/`:

| Path | Purpose |
|------|---------|
| `config.json` | Channel-specific settings (created by you or auto-generated from root `config.json`) |
| `token.json` | Auto-generated OAuth token (created on first successful auth) |
| `videos/` | Staged MP4s copied from your clips directory |
| `video_metadata.csv` | Generated CSV with `File_name,title,description,tags` columns |

---

## Prerequisites

- Python 3.10+ (tested on Python 3.14)
- A Google Cloud project with the **YouTube Data API v3** enabled
- OAuth 2.0 client credentials (download from Google Cloud Console → APIs & Services → Credentials)

### Install dependencies

```bash
pip install google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client
```

> On some Linux systems you may need `--break-system-packages`:
> `pip install --break-system-packages google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client`

---

## Google Cloud Console Setup (one-time)

1. Go to [console.cloud.google.com](https://console.cloud.google.com/)
2. Create or select your project (e.g. `clipping-project-515400`)
3. **Enable the API:** APIs & Services → Library → search "YouTube Data API v3" → Enable
4. **Configure OAuth consent screen:** APIs & Services → OAuth consent screen → set app name, add your email as a test user (if app is in "Testing" status), publish
5. **Create credentials:** APIs & Services → Credentials → Create Credentials → OAuth client ID → Application type: "Desktop app" → download the JSON
6. Save the downloaded JSON as `yt_upload.json` in the repo root (it already exists with placeholder credentials — replace with yours if needed)

---

## Quick Start (End-to-End)

### Step 1: Create channel config

Create a channel directory and copy the root config as a starting point:

```bash
# Create channel directory
mkdir -p channels/my-channel/videos

# Copy root config and customize per-channel values
cp config.json channels/my-channel/config.json
```

Edit `channels/my-channel/config.json` to set channel-specific values (e.g., `video_directory`, `csv_file`, `start_date`, `schedule_timings`, `privacy_status`, `clips_dir`).

### Step 2: Prepare clip data for the channel

Before running the converter, set `clips_dir` in `channels/my-channel/config.json` to point to your clip batch (it varies per batch):

```json
"clips_dir": "/home/yogesh/Documents/.../data/users/u_local/creators/chaoscratetv/videos/20261123-033506-ad05eed369/clips"
```

Then run the converter using your channel config:

```bash
python3 convert_clips.py --config channels/my-channel/config.json
```

This reads clip JSON + MP4 files from `clips_dir`, copies MP4s into `channels/my-channel/videos/`, and writes `channels/my-channel/video_metadata.csv` — all paths taken from `channels/my-channel/config.json`.

> Tip: You can still override individual values with `--clips-dir DIR`, `--repo-dir DIR`, `--video-directory DIR`, or `--csv-file PATH` flags if needed for a one-off run.

### Step 3: Authenticate and upload

```bash
rm -f token.json          # Force fresh OAuth
python3 app.py --list-channels
```

This prints an authorization URL. Visit it in your browser, sign in with your Google account, copy the authorization code, paste it back. The script then lists all YouTube channels under your account with their IDs and titles.

**If you have multiple channels:** Make note of which channel you want to upload to. During the OAuth authorization screen, select the specific channel you want before granting access.

Then run the uploader:

```bash
python3 app.py --config channels/my-channel/config.json
```

1. OAuth authenticates (uses both `youtube.upload` and `youtube.readonly` scopes)
2. Lists available channels and asks: `Proceed with upload? (y/n):`
3. Type `y` to confirm
4. Each video is uploaded and scheduled at its configured time

---

## Configuration Reference

### `config.json` (root defaults + per-channel overrides)

Both `app.py` and `convert_clips.py` read from `config.json`. Each script uses only the keys relevant to it and ignores the rest. Unknown keys (e.g. `_comment` documentation) are ignored.

| Key | Type | Default | Used by | Description |
|-----|------|---------|---------|-------------|
| `client_secrets_file` | string | `"yt_upload.json"` | app.py | Path to Google OAuth 2.0 client secrets JSON |
| `token_file` | string | `"token.json"` | app.py | Path to stored OAuth token (auto-created on first auth) |
| `youtube_upload_scope` | array | `["https://www.googleapis.com/auth/youtube.upload"]` | app.py | OAuth scope for upload access |
| `youtube_readonly_scope` | array | `["https://www.googleapis.com/auth/youtube.readonly"]` | app.py | Read-only scope (needed to list channels) |
| `youtube_api_service_name` | string | `"youtube"` | app.py | Google API service name |
| `youtube_api_version` | string | `"v3"` | app.py | YouTube Data API version |
| `video_category` | string | `"15"` | app.py | YouTube category ID (15 = Pets & Animals; see `catogory.txt`) |
| `privacy_status` | string | `"private"` | app.py | `private` / `public` / `unlisted` |
| `video_directory` | string | `"videos"` | app.py | Directory containing MP4 files to upload |
| `csv_file` | string | `"video_metadata.csv"` | app.py | CSV with video metadata (consumed via `csv.DictReader`) |
| `set_size` | int | `5` | app.py | Number of videos per batch (one batch per day) |
| `start_date` | string | `"2025-04-26"` | app.py | Start date for scheduling (YYYY-MM-DD) |
| `schedule_timings` | array | `[[23,0],[23,30],[0,0],...]` | app.py | List of `[hour, minute]` UTC times per video within a batch |
| `oauth_port` | int | `0` | app.py | Local server port for OAuth callback (0 = random available port) |
| `auth_method` | string | `"console"` | app.py | `console` (no redirect URI needed) or `local_server` (needs registered redirect URI) |
| `clips_dir` | string | (required) | convert_clips.py | Directory containing clip JSON + MP4 files |
| `repo_dir` | string | (script dir) | convert_clips.py | Target repo directory (contains `app.py`) |
| `video_directory` | string | `"videos"` | convert_clips.py | Subdirectory under `repo_dir` for staged MP4s |
| `csv_file` | string | `"video_metadata.csv"` | convert_clips.py | Output CSV filename under `repo_dir` |
| `glob_pattern` | string | `"clip*.json"` | convert_clips.py | Glob pattern to find clip metadata JSON files |
| `video_ext` | string | `".mp4"` | convert_clips.py | Extension of video files to copy alongside each JSON |
| `file_name_pattern` | string | `"{stem}"` | convert_clips.py | Pattern to build video file name from JSON stem (`{stem}`, `{ext}`) |
| `field_mapping` | object | (see below) | convert_clips.py | Maps CSV columns to source JSON keys |

`field_mapping` example:

```json
{
  "csv_columns": ["File_name", "title", "description", "tags", "is_processed", "video_id"],
  "title": "title",
  "description": "description",
  "tags": "hashtags:join:,"
}
```

The `:join:` syntax joins list values (e.g. `hashtags` array joined with `,`). `File_name` is auto-populated from the MP4 filename. `is_processed` always defaults to `0` and `video_id` to empty — `app.py` manages both after uploads.

---

## CSV Format (`video_metadata.csv`)

`app.py` reads via `csv.DictReader` and expects these columns:

| Column | Description |
|--------|-------------|
| `File_name` | MP4 filename (must exist in `video_directory`) |
| `title` | Video title |
| `description` | Video description |
| `tags` | Comma-separated tags (split on `,`, then stripped) |
| `is_processed` | `0` or `1` bit — **re-run safety**: `app.py` skips rows where `is_processed=1`. `convert_clips.py` writes `0` for every new row; `app.py` flips it to `1` (and fills `video_id`) only after a successful upload. |
| `video_id` | YouTube video ID, written by `app.py` after successful upload (empty until then). |

Example:

```
File_name,title,description,tags,is_processed,video_id
clip01.mp4,My Video Title,"Video description here.\n\n#Tag1 #Tag2","Tag1,Tag2",1,Q1nRJ4fXcws
clip02.mp4,Another Title,"Desc","Tag1",0,
```

> **Re-running `app.py` is safe:** already-uploaded videos (`is_processed=1`) are skipped automatically, so only new/unprocessed rows get uploaded. Old CSVs without `is_processed`/`video_id` columns still work — every row is treated as `0` (unprocessed), and the columns are added on the first successful upload.

---

## CLI Arguments (`app.py`)

| Argument | Description |
|----------|-------------|
| `--config` | Path to JSON config file (default: `config.json`) |
| `--client-secrets-file` | Override `client_secrets_file` |
| `--token-file` | Override `token_file` |
| `--video-category` | Override `video_category` |
| `--privacy-status` | Override `privacy_status` |
| `--video-directory` | Override `video_directory` |
| `--csv-file` | Override `csv_file` |
| `--set-size` | Override `set_size` (int) |
| `--start-date` | Override `start_date` (YYYY-MM-DD) |
| `--oauth-port` | Override `oauth_port` (int) |
| `--auth-method` | `local_server` or `console` |
| `--list-channels` | List all channels and exit (no upload) |

## CLI Arguments (`convert_clips.py`)

| Argument | Description |
|----------|-------------|
| `--config` | Path to JSON config file |
| `--clips-dir` | Directory containing clip JSON + MP4 files |
| `--repo-dir` | Target repo directory |
| `--video-directory` | Subdirectory under repo-dir for staged MP4s |
| `--csv-file` | Output CSV filename under repo-dir |

---

## OAuth Flow Details

Two methods are supported:

- **`console`** (default): Prints an authorization URL. You visit it, sign in, copy the code, paste it back. No redirect URI registration needed in Google Cloud Console. Recommended for local/dev use.
- **`local_server`**: Opens a local browser callback server. Requires `http://localhost:<port>` registered as a redirect URI in Google Cloud Console. If it fails with `redirect_uri_mismatch`, it automatically falls back to console flow.

**Multi-channel accounts:** During the Google authorization screen, select the specific channel you want to upload to before granting access. Uploads always go to the channel authorized in that OAuth session — there is no `channelId` parameter in the YouTube API `videos.insert` method. Each channel's OAuth token is stored in that channel's `token.json`.

---

## Troubleshooting

| Error | Cause | Fix |
|-------|-------|-----|
| `403 insufficientPermissions` (on `channels.list`) | Token lacks `youtube.readonly` scope | Delete `token.json` and re-run (scopes now combined) |
| `400 redirect_uri_mismatch` | Local server port not registered in GCP Console | Use `auth_method: "console"` or register `http://localhost:<port>` in GCP |
| `400 missing required parameter: redirect_uri` | Console flow missing OOB redirect URI | Already fixed — set `flow.redirect_uri = "urn:ietf:wg:oauth:2.0:oob"` |
| `AttributeError: 'InstalledAppFlow' object has no attribute 'run_console'` | `run_console()` doesn't exist in installed library version | Already fixed — uses `authorization_url()` + `fetch_token()` manually |
| `400 invalidCategoryId` | Category ID not valid for your region/account | Change `video_category` in channel's `config.json` (see `catogory.txt`) |
| `429 Quota exceeded` | Daily YouTube upload quota reached | Request quota increase in GCP Console or wait for daily reset |
| `EOFError: EOF when reading a line` | Running in non-interactive environment | Run in a real terminal with stdin available |

---

## Example Workflow (New Clip Batch, New Channel)

```bash
# 1. Create channel directory + copy root config as starting point
mkdir -p channels/my-new-channel/videos
cp config.json channels/my-new-channel/config.json

# 2. Edit channels/my-new-channel/config.json as needed
#    (set clips_dir, video_directory, csv_file, start_date, schedule_timings, etc.)

# 3. Convert clips to CSV + stage MP4s using channel config
#    (set clips_dir in channels/my-new-channel/config.json first)
python3 convert_clips.py --config channels/my-new-channel/config.json

# 4. Verify the generated CSV
cat channels/my-new-channel/video_metadata.csv

# 5. Authenticate and list channels
rm -f token.json
python3 app.py --list-channels

# 6. Upload (select correct channel during OAuth if multiple)
python3 app.py --config channels/my-new-channel/config.json
```

---

## Notes

- `token.json` is created automatically on first successful OAuth and reused on subsequent runs (no re-auth needed unless expired). Each channel has its own `token.json` under its directory.
- Uploads are scheduled (not immediate) — each video gets a `publishAt` time based on `start_date` + batch index × `schedule_timings`.
- The CSV tracks upload state: `convert_clips.py` marks every row `is_processed=0`; `app.py` only uploads rows where `is_processed=0` and flips it to `1` (with the YouTube `video_id`) after each successful upload. Re-running `app.py` is safe — processed videos are skipped.
- Privacy status defaults to `private`; change to `public` or `unlisted` in the channel's `config.json` as needed.
- The `.gitignore` excludes `env/`, `__pycache__`, and channel `videos/` directories.
- All channel-specific artifacts live under `channels/<channel-name>/` — root-level files are global defaults/templates only.
