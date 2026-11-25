#!/usr/bin/env python3
"""YouTube Short auto-upload bot.

Reads configuration from ``config.json`` (all upload constants, paths,
schedule timings, etc.). CLI arguments override any config value, so nothing
is hardcoded.

Usage:
    python app.py [--config config.json] [--csv-file video_metadata.csv] ...
"""

from __future__ import annotations

import argparse
import csv
import datetime
import json
import os
import random
import sys
import time
from pathlib import Path

import google.auth.transport.requests
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError, ResumableUploadError
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

DEFAULT_CONFIG_NAME = "config.json"


def load_config(config_path: Path | None = None) -> dict:
    """Load configuration from a JSON file.

    Falls back to built-in defaults if no config file is found. Unknown keys
    in the file (e.g. ``_comment`` documentation) are ignored.
    """
    defaults = {
        "client_secrets_file": "yt_upload.json",
        "token_file": "token.json",
        "youtube_upload_scope": ["https://www.googleapis.com/auth/youtube.upload"],
        "youtube_readonly_scope": ["https://www.googleapis.com/auth/youtube.readonly"],
        "youtube_api_service_name": "youtube",
        "youtube_api_version": "v3",
        "video_category": "15",
        "privacy_status": "private",
        "video_directory": "videos",
        "csv_file": "video_metadata.csv",
        "set_size": 5,
        "start_date": "2025-04-26",
        "schedule_timings": [
            [23, 0], [23, 30], [0, 0], [0, 30], [1, 0],
            [1, 30], [2, 0], [2, 30], [3, 0], [3, 30],
        ],
        "oauth_port": 0,
        "auth_method": "local_server",
    }

    if config_path is None:
        default_cfg = Path(__file__).resolve().parent / DEFAULT_CONFIG_NAME
        config_path = default_cfg if default_cfg.is_file() else None

    if config_path:
        with open(config_path, "r", encoding="utf-8") as f:
            file_cfg = json.load(f)
        # Only override known keys; ignore documentation keys like _comment.
        for key in defaults:
            if key in file_cfg:
                defaults[key] = file_cfg[key]

    return defaults


def resolve_config(
    config: dict,
    *,
    client_secrets_file: str | None = None,
    token_file: str | None = None,
    youtube_upload_scope: list | None = None,
    youtube_readonly_scope: list | None = None,
    youtube_api_service_name: str | None = None,
    youtube_api_version: str | None = None,
    video_category: str | None = None,
    privacy_status: str | None = None,
    video_directory: str | None = None,
    csv_file: str | None = None,
    set_size: int | None = None,
    start_date: str | None = None,
    schedule_timings: list | None = None,
    oauth_port: int | None = None,
    auth_method: str | None = None,
) -> dict:
    """Merge config with CLI overrides (non-None CLI args win)."""
    merged = dict(config)
    overrides = {
        "client_secrets_file": client_secrets_file,
        "token_file": token_file,
        "youtube_upload_scope": youtube_upload_scope,
        "youtube_readonly_scope": youtube_readonly_scope,
        "youtube_api_service_name": youtube_api_service_name,
        "youtube_api_version": youtube_api_version,
        "video_category": video_category,
        "privacy_status": privacy_status,
        "video_directory": video_directory,
        "csv_file": csv_file,
        "set_size": set_size,
        "start_date": start_date,
        "schedule_timings": schedule_timings,
        "oauth_port": oauth_port,
        "auth_method": auth_method,
    }
    for key, value in overrides.items():
        if value is not None:
            merged[key] = value
    return merged


# ---------------------------------------------------------------------------
# Module-level configuration (loaded once; overridable via CLI in main()).
# ---------------------------------------------------------------------------
CONFIG = load_config()

CLIENT_SECRETS_FILE = CONFIG["client_secrets_file"]
TOKEN_FILE = CONFIG["token_file"]
YOUTUBE_UPLOAD_SCOPE = CONFIG["youtube_upload_scope"]
YOUTUBE_READONLY_SCOPE = CONFIG["youtube_readonly_scope"]
YOUTUBE_API_SERVICE_NAME = CONFIG["youtube_api_service_name"]
YOUTUBE_API_VERSION = CONFIG["youtube_api_version"]
VIDEO_CATEGORY = CONFIG["video_category"]
PRIVACY_STATUS = CONFIG["privacy_status"]
VIDEO_DIRECTORY = CONFIG["video_directory"]
CSV_FILE = CONFIG["csv_file"]
SET_SIZE = CONFIG["set_size"]
START_DATE = CONFIG["start_date"]
SCHEDULE_TIMINGS = [tuple(t) for t in CONFIG["schedule_timings"]]
OAUTH_PORT = CONFIG["oauth_port"]
AUTH_METHOD = CONFIG["auth_method"]


def _run_console_flow(flow: InstalledAppFlow) -> None:
    """Run an OAuth flow without a local server (no redirect URI needed).

    Prints the authorization URL, waits for the user to paste the code,
    and exchanges it for credentials on the provided flow object.
    """
    # Use the standard out-of-band (OOB) redirect URI so Google can return
    # the authorization code without needing a registered redirect endpoint.
    oob_redirect_uri = "urn:ietf:wg:oauth:2.0:oob"
    flow.redirect_uri = oob_redirect_uri
    auth_url, _ = flow.authorization_url(
        access_type="offline",
        prompt="consent",
    )
    print("\n📋 Please go to this URL and authorize the app:")
    print(f"   {auth_url}\n")
    code = input("🔑 Enter the authorization code: ").strip()
    flow.fetch_token(code=code)


def get_authenticated_service():
    creds = None
    # Combine upload + readonly scopes so we can both list channels and upload.
    all_scopes = list(dict.fromkeys(YOUTUBE_UPLOAD_SCOPE + YOUTUBE_READONLY_SCOPE))
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, all_scopes)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                CLIENT_SECRETS_FILE, all_scopes
            )
            if AUTH_METHOD == "console":
                # Console flow: no local server, no redirect URI needed.
                # User visits the printed URL, authorizes, and pastes the code back.
                print("🔐 Starting OAuth console flow (no redirect URI needed)...")
                _run_console_flow(flow)
                creds = flow.credentials
            else:
                # Local server flow: requires a matching redirect URI registered
                # in Google Cloud Console (e.g. http://localhost:8080).
                # Matches get_token.py: port=0, access_type="offline", prompt="consent".
                try:
                    creds = flow.run_local_server(
                        port=0, access_type="offline", prompt="consent"
                    )
                except Exception as exc:  # noqa: BLE001
                    msg = str(exc).lower()
                    if "redirect_uri_mismatch" in msg or "redirect" in msg:
                        print(
                            f"⚠️  Local server OAuth failed ({exc}).\n"
                            "   Falling back to console flow (no redirect URI needed)..."
                        )
                        _run_console_flow(flow)
                        creds = flow.credentials
                    else:
                        raise
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
    return build(
        YOUTUBE_API_SERVICE_NAME,
        YOUTUBE_API_VERSION,
        credentials=creds,
    )


def list_channels(youtube):
    """List all YouTube channels the authenticated user owns or manages.

    Returns a list of (channel_id, channel_title) tuples.
    Useful when the Google account has multiple channels — run this first
    to see which channels are available, then re-run OAuth selecting the
    desired channel during the Google authorization screen.
    """
    request = youtube.channels().list(mine=True, part="id,snippet")
    response = request.execute()
    channels = []
    for item in response.get("items", []):
        cid = item["id"]
        title = item["snippet"].get("title", "Untitled")
        channels.append((cid, title))
    return channels


def confirm_upload(channels):
    """Show available channels and ask user to confirm upload target.

    Returns True if user confirms, False if they decline.
    """
    print("\n📺 Channels available for this account:")
    for idx, (cid, title) in enumerate(channels, 1):
        print(f"   {idx}. {title}  (ID: {cid})")

    print(f"\n   ⚠️  Videos will be uploaded to the channel selected during OAuth.")
    print(f"   If you want a different channel, cancel (Ctrl+C), delete token.json,")
    print(f"   and re-run python3 app.py selecting the correct channel.")

    answer = input("\n   Proceed with upload? (y/n): ").strip().lower()
    return answer in ("y", "yes")


def schedule_upload(youtube, file_path, title, description, tags, publish_time):
    """Upload one video. Returns the YouTube video ID on success, else None."""
    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": VIDEO_CATEGORY,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": PRIVACY_STATUS,
            "publishAt": publish_time.isoformat() + "Z",
        },
    }
    media = MediaFileUpload(file_path, chunksize=-1, resumable=True)
    request = youtube.videos().insert(part="snippet,status", body=body, media_body=media)
    return resumable_upload(request)


class QuotaExceededError(Exception):
    """Raised when the YouTube API daily quota or rate limit is exhausted."""


def resumable_upload(request):
    response = None
    error = None
    retry = 0
    while response is None:
        try:
            print("Uploading file...")
            status, response = request.next_chunk()
            if response:
                if "id" in response:
                    print(f"✅ Video uploaded successfully! Video ID: {response['id']}")
                    return response["id"]
                else:
                    print(f"❌ Upload failed: {response}")
                    return None
        except (HttpError, ResumableUploadError) as e:
            # YouTube quota exhausted (403 quotaExceeded), rate limited (429),
            # or upload limit exceeded (400 uploadLimitExceeded).
            # These are not retriable within the same run — stop gracefully so the
            # current video stays unprocessed and can be retried next day.
            try:
                body = json.loads(e.content.decode() or "{}")
                reason = (
                    body.get("error", {})
                    .get("errors", [{}])[0]
                    .get("reason", "")
                )
            except (ValueError, AttributeError):
                reason = ""

            quota_reasons = ("quotaExceeded", "rateLimitExceeded", "uploadLimitExceeded")
            is_quota_error = (
                e.resp.status in (403, 429) or
                (e.resp.status == 400 and (reason in quota_reasons or "exceeded" in reason.lower()))
            )
            if is_quota_error:
                print(f"⛔ YouTube API quota/rate limit reached (HTTP {e.resp.status}, reason: {reason}).")
                print("   Stopping upload run. Unprocessed videos will be retried on the next run.")
                raise QuotaExceededError(
                    f"YouTube API quota/rate limit reached (HTTP {e.resp.status}, reason: {reason})"
                )
            if e.resp.status in [500, 502, 503, 504]:
                error = f"A retriable HTTP error {e.resp.status} occurred: {e.content}"
            else:
                raise
        except Exception as e:
            error = f"A retriable error occurred: {e}"

        if error:
            print(error)
            retry += 1
            if retry > 10:
                print("❌ Max retries reached. Upload failed.")
                return None
            sleep_time = random.uniform(1, min(60, 2 ** retry))
            print(f"🔄 Retrying in {sleep_time:.2f} seconds...")
            time.sleep(sleep_time)
    return None


def save_csv(csv_path, rows, fieldnames):
    """Rewrite the CSV, adding is_processed/video_id columns if they were missing."""
    fieldnames = list(fieldnames)
    for extra in ("is_processed", "video_id"):
        if extra not in fieldnames:
            fieldnames.append(extra)
    for row in rows:
        row.setdefault("is_processed", "0")
        row.setdefault("video_id", "")
    tmp_path = str(csv_path) + ".tmp"
    with open(tmp_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    os.replace(tmp_path, csv_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="YouTube Short auto-upload bot (config-driven)."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to JSON config file (defaults to config.json next to this script).",
    )
    parser.add_argument(
        "--client-secrets-file",
        default=None,
        help="Override client_secrets_file from config.",
    )
    parser.add_argument(
        "--token-file",
        default=None,
        help="Override token_file from config.",
    )
    parser.add_argument(
        "--video-category",
        default=None,
        help="Override video_category from config.",
    )
    parser.add_argument(
        "--privacy-status",
        default=None,
        help="Override privacy_status from config.",
    )
    parser.add_argument(
        "--video-directory",
        default=None,
        help="Override video_directory from config.",
    )
    parser.add_argument(
        "--csv-file",
        default=None,
        help="Override csv_file from config.",
    )
    parser.add_argument(
        "--set-size",
        type=int,
        default=None,
        help="Override set_size from config.",
    )
    parser.add_argument(
        "--start-date",
        default=None,
        help="Override start_date from config (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--oauth-port",
        type=int,
        default=None,
        help="Override oauth_port from config (0 = random available port).",
    )
    parser.add_argument(
        "--auth-method",
        choices=["local_server", "console"],
        default=None,
        help="Override auth_method from config (local_server or console).",
    )
    parser.add_argument(
        "--force-auth",
        action="store_true",
        default=None,
        help="Delete the stored OAuth token before authenticating, forcing a fresh login so you can choose a different channel.",
    )
    parser.add_argument(
        "--list-channels",
        action="store_true",
        default=None,
        help="List all channels the authenticated user owns/manages, then exit.",
    )
    args = parser.parse_args()

    # Re-load config (honors --config) and apply CLI overrides.
    global CONFIG, CLIENT_SECRETS_FILE, TOKEN_FILE, YOUTUBE_UPLOAD_SCOPE
    global YOUTUBE_READONLY_SCOPE, YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION
    global VIDEO_CATEGORY, PRIVACY_STATUS, VIDEO_DIRECTORY, CSV_FILE, SET_SIZE
    global START_DATE, SCHEDULE_TIMINGS, OAUTH_PORT, AUTH_METHOD

    base_config = load_config(args.config)
    merged = resolve_config(
        base_config,
        client_secrets_file=args.client_secrets_file,
        token_file=args.token_file,
        video_category=args.video_category,
        privacy_status=args.privacy_status,
        video_directory=args.video_directory,
        csv_file=args.csv_file,
        set_size=args.set_size,
        start_date=args.start_date,
        oauth_port=args.oauth_port,
        auth_method=args.auth_method,
    )

    CONFIG = merged
    CLIENT_SECRETS_FILE = merged["client_secrets_file"]
    TOKEN_FILE = merged["token_file"]
    YOUTUBE_UPLOAD_SCOPE = merged["youtube_upload_scope"]
    YOUTUBE_READONLY_SCOPE = merged["youtube_readonly_scope"]
    YOUTUBE_API_SERVICE_NAME = merged["youtube_api_service_name"]
    YOUTUBE_API_VERSION = merged["youtube_api_version"]
    VIDEO_CATEGORY = merged["video_category"]
    PRIVACY_STATUS = merged["privacy_status"]
    VIDEO_DIRECTORY = merged["video_directory"]
    CSV_FILE = merged["csv_file"]
    SET_SIZE = merged["set_size"]
    START_DATE = merged["start_date"]
    SCHEDULE_TIMINGS = [tuple(t) for t in merged["schedule_timings"]]
    OAUTH_PORT = merged["oauth_port"]
    AUTH_METHOD = merged["auth_method"]

    # Force fresh OAuth: delete stored token so the user can choose a different channel.
    if args.force_auth:
        token_path = Path(TOKEN_FILE)
        if token_path.exists():
            token_path.unlink()
            print(f"🗑️  Cleared stored token: {TOKEN_FILE}")

    youtube = get_authenticated_service()

    # List channels and confirm upload target before proceeding.
    channels = list_channels(youtube)
    if not channels:
        print("❌ No channels found for this account.")
        return

    if args.list_channels:
        print("\n📺 Channels available for this account:")
        for idx, (cid, title) in enumerate(channels, 1):
            print(f"   {idx}. {title}  (ID: {cid})")
        print(
            "\n   To upload to a specific channel, delete token.json and re-run "
            "python3 app.py. During the Google authorization screen, select "
            "the desired channel before granting access."
        )
        return

    if not confirm_upload(channels):
        print("❌ Upload cancelled by user.")
        return

    csv_path = Path(CSV_FILE)
    if not csv_path.exists():
        print(f"❌ CSV file '{CSV_FILE}' not found. Exiting.")
        return

    with open(csv_path, mode="r", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        fieldnames = list(reader.fieldnames or [])
        videos = list(reader)

    if not videos:
        print("❌ No videos found in CSV file. Exiting.")
        return

    pending = [
        row for row in videos
        if row.get("is_processed", "0").strip() != "1"
    ]
    skipped = len(videos) - len(pending)
    if skipped:
        print(f"⏭️  Skipping {skipped} already-processed video(s).")
    if not pending:
        print("✅ All videos already processed. Nothing to do.")
        return

    start_date = datetime.datetime.strptime(START_DATE, "%Y-%m-%d")
    for i in range(0, len(pending), SET_SIZE):
        publish_date = start_date + datetime.timedelta(days=i // SET_SIZE)

        batch = pending[i : i + SET_SIZE]
        print(f"📅 Scheduling batch {i // SET_SIZE + 1} for {publish_date.strftime('%Y-%m-%d')} UTC")

        for idx, row in enumerate(batch):
            file_name = row["File_name"].strip()
            title = row["title"].strip()
            description = row["description"].strip()
            tags = [tag.strip() for tag in row["tags"].split(",")]
            file_path = os.path.join(VIDEO_DIRECTORY, file_name)

            schedule_time = SCHEDULE_TIMINGS[idx % len(SCHEDULE_TIMINGS)]
            publish_time = publish_date.replace(
                hour=schedule_time[0], minute=schedule_time[1], second=0
            )

            if not os.path.exists(file_path):
                print(f"⚠️ File '{file_name}' not found in '{VIDEO_DIRECTORY}'. Skipping.")
                continue

            print(
                f"🚀 Scheduling {file_name} for "
                f"{publish_time.strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
            try:
                video_id = schedule_upload(youtube, file_path, title, description, tags, publish_time)
            except QuotaExceededError as exc:
                print(f"⛔ {exc}")
                print("   Stopping upload run. Remaining unprocessed videos will be retried on the next run.")
                return
            if video_id:
                row["is_processed"] = "1"
                row["video_id"] = video_id
                save_csv(csv_path, videos, fieldnames)
                print(f"💾 Marked {file_name} as processed in {CSV_FILE}")


if __name__ == "__main__":
    main()
