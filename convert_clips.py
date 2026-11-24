#!/usr/bin/env python3
"""Convert per-clip metadata JSON files into the repo's YouTube upload CSV.

Reads ``clip*.json`` files from a clips directory, copies the matching MP4s
into a ``videos/`` directory, and writes a ``video_metadata.csv`` in the exact
format ``app.py`` expects:

    File_name,title,description,tags

Configuration is driven by an optional JSON config file (see
``convert_clips.config.json`` for an example). CLI arguments override any value
set in the config file, so the script is generic and reusable across different
clip batches and JSON schemas.

Usage:
    python convert_clips.py [--config config.json] [--clips-dir DIR] ...
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import sys
from pathlib import Path

DEFAULT_CONFIG_NAME = "convert_clips.config.json"


def load_config(config_path: Path | None) -> dict:
    """Load configuration from a JSON file, returning {} if none/missing."""
    if config_path is None:
        # Look for a config file next to this script by default name.
        default_cfg = Path(__file__).resolve().parent / DEFAULT_CONFIG_NAME
        if default_cfg.is_file():
            config_path = default_cfg
        else:
            return {}
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)


def find_clip_jsons(clips_dir: Path, glob_pattern: str = "clip*.json") -> list[Path]:
    """Return sorted clip JSON paths matching the glob pattern."""
    return sorted(clips_dir.glob(glob_pattern))


def load_clip_metadata(json_path: Path) -> dict:
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


def resolve_value(meta: dict, mapping: str | None, default: str = "") -> str:
    """Resolve a value from clip metadata using a dotted key path.

    Supports simple key lookup (e.g. ``title``) and list-joining via
    ``<key>:join:<sep>`` (e.g. ``hashtags:join:,\"``).
    """
    if mapping is None:
        return default
    if ":join:" in mapping:
        key, sep = mapping.split(":join:", 1)
        value = meta.get(key, [])
        if not isinstance(value, list):
            value = [value]
        return sep.join(str(v).strip() for v in value if str(v).strip())
    return str(meta.get(mapping, default))


def build_file_name(json_path: Path, pattern: str, video_ext: str) -> str:
    """Build the MP4 file name from the JSON stem using a pattern.

    Available placeholders: {stem}, {ext}
    """
    stem = json_path.stem
    return pattern.format(stem=stem, ext=json_path.suffix) + video_ext


def convert(
    clips_dir: Path,
    repo_dir: Path,
    videos_dir_name: str = "videos",
    csv_out_name: str = "video_metadata.csv",
    *,
    glob_pattern: str = "clip*.json",
    video_ext: str = ".mp4",
    file_name_pattern: str = "{stem}",
    field_mapping: dict | None = None,
) -> int:
    clips_dir = clips_dir.resolve()
    repo_dir = repo_dir.resolve()
    videos_dir = repo_dir / videos_dir_name
    videos_dir.mkdir(parents=True, exist_ok=True)

    csv_path = repo_dir / csv_out_name

    clip_files = find_clip_jsons(clips_dir, glob_pattern)
    if not clip_files:
        print(f"⚠️  No {glob_pattern} files found in {clips_dir}", file=sys.stderr)
        return 0

    field_mapping = field_mapping or {}
    fieldnames = list(
        field_mapping.get(
            "csv_columns",
            ["File_name", "title", "description", "tags", "state", "video_id"],
        )
    )

    rows: list[dict[str, str]] = []

    for json_path in clip_files:
        meta = load_clip_metadata(json_path)

        mp4_name = build_file_name(json_path, file_name_pattern, video_ext)
        mp4_src = clips_dir / mp4_name
        mp4_dst = videos_dir / mp4_name

        if mp4_src.exists():
            shutil.copy2(mp4_src, mp4_dst)
            print(f"📼 Copied {mp4_name} -> {videos_dir_name}/")
        else:
            print(f"⚠️  {mp4_name} not found; row will still be written", file=sys.stderr)

        row: dict[str, str] = {}
        for col in fieldnames:
            if col == "File_name":
                row[col] = mp4_name
            elif col == "state":
                # New rows always start as unprocessed unless the mapping says otherwise.
                mapping = field_mapping.get(col)
                row[col] = resolve_value(meta, mapping, default="unprocessed")
            elif col == "video_id":
                row[col] = resolve_value(meta, field_mapping.get(col), default="")
            else:
                mapping = field_mapping.get(col)
                row[col] = resolve_value(meta, mapping)

        rows.append(row)

    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print(f"✅ Wrote {len(rows)} rows to {csv_path}")
    print(f"📁 Videos staged in {videos_dir}")
    return len(rows)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert clip JSON metadata to YouTube upload CSV + staged videos."
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Path to JSON config file (defaults to convert_clips.config.json "
        "next to this script if present)",
    )
    parser.add_argument(
        "--clips-dir",
        type=Path,
        default=None,
        help="Directory containing clip JSON + MP4 files",
    )
    parser.add_argument(
        "--repo-dir",
        type=Path,
        default=None,
        help="Target repo directory (contains app.py)",
    )
    parser.add_argument(
        "--videos-dir",
        default=None,
        help="Subdirectory name under repo-dir for staged MP4s",
    )
    parser.add_argument(
        "--csv-out",
        default=None,
        help="Output CSV filename under repo-dir",
    )
    args = parser.parse_args()

    config = load_config(args.config)

    def cfg(key, default=None):
        return config.get(key, default)

    clips_dir = args.clips_dir if args.clips_dir is not None else Path(cfg("clips_dir", ""))
    repo_dir = args.repo_dir if args.repo_dir is not None else Path(cfg("repo_dir", ""))
    if str(repo_dir) == "":
        repo_dir = Path(__file__).resolve().parent
    videos_dir = args.videos_dir if args.videos_dir is not None else cfg("videos_dir", "videos")
    csv_out = args.csv_out if args.csv_out is not None else cfg("csv_out", "video_metadata.csv")

    glob_pattern = cfg("glob_pattern", "clip*.json")
    video_ext = cfg("video_ext", ".mp4")
    file_name_pattern = cfg("file_name_pattern", "{stem}")
    field_mapping = cfg("field_mapping", None)

    if not clips_dir.is_dir():
        print(f"❌ Clips directory not found: {clips_dir}", file=sys.stderr)
        sys.exit(1)
    if not repo_dir.is_dir():
        print(f"❌ Repo directory not found: {repo_dir}", file=sys.stderr)
        sys.exit(1)

    convert(
        clips_dir,
        repo_dir,
        videos_dir_name=videos_dir,
        csv_out_name=csv_out,
        glob_pattern=glob_pattern,
        video_ext=video_ext,
        file_name_pattern=file_name_pattern,
        field_mapping=field_mapping,
    )


if __name__ == "__main__":
    main()
