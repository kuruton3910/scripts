"""Utilities for inspecting and archiving syllabus HTML snapshots.

Usage examples:

    # Show how many HTML files are stored
    python scripts/textbooks/manage_html.py stats

    # Archive everything except the latest 100 files into a zip and delete originals
    python scripts/textbooks/manage_html.py archive --keep-latest 100 --delete-after
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys
from pathlib import Path
from typing import Iterable, List
from zipfile import ZIP_DEFLATED, ZipFile


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_HTML_DIR = PROJECT_ROOT / "scripts" / "textbooks" / "raw" / "html"
DEFAULT_ARCHIVE_DIR = PROJECT_ROOT / "scripts" / "textbooks" / "raw" / "html_archive"


def gather_html_files(target: Path) -> List[Path]:
    if not target.exists() or not target.is_dir():
        return []
    return sorted(target.glob("*.html"), key=lambda path: path.stat().st_mtime)


def human_size(num_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if num_bytes < 1024 or unit == "TB":
            return f"{num_bytes:.1f}{unit}"
        num_bytes /= 1024
    return f"{num_bytes:.1f}TB"


def command_stats(target: Path) -> int:
    files = gather_html_files(target)
    if not files:
        print(f"No HTML files found in {target}.")
        return 0

    total_size = sum(path.stat().st_size for path in files)
    oldest = files[0].stat().st_mtime
    newest = files[-1].stat().st_mtime

    print(f"Directory: {target}")
    print(f"Files: {len(files)}")
    print(f"Total size: {human_size(total_size)}")
    print(
        "Oldest: ",
        dt.datetime.fromtimestamp(oldest).strftime("%Y-%m-%d %H:%M:%S"),
        files[0].name,
    )
    print(
        "Newest: ",
        dt.datetime.fromtimestamp(newest).strftime("%Y-%m-%d %H:%M:%S"),
        files[-1].name,
    )
    return 0


def command_archive(
    target: Path,
    archive_dir: Path,
    keep_latest: int,
    delete_after: bool,
    dry_run: bool,
) -> int:
    files = gather_html_files(target)
    if not files:
        print(f"No HTML files found in {target}. Nothing to archive.")
        return 0

    if keep_latest < 0:
        raise ValueError("--keep-latest must be zero or positive")

    if keep_latest >= len(files):
        print(
            "keep_latest is greater than or equal to the number of files. "
            "Nothing will be archived."
        )
        return 0

    archive_candidates = files[: len(files) - keep_latest]
    kept = files[len(files) - keep_latest :] if keep_latest else []

    timestamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"syllabus-html-{timestamp}.zip"

    print(f"Preparing to archive {len(archive_candidates)} file(s) to {archive_path}")
    if keep_latest:
        print(f"Keeping latest {len(kept)} file(s) untouched.")
    if dry_run:
        print("Dry run enabled. No files will be written or deleted.")
        return 0

    with ZipFile(archive_path, "w", compression=ZIP_DEFLATED, compresslevel=6) as zf:
        for path in archive_candidates:
            relative = path.relative_to(target)
            zf.write(path, arcname=relative)
    print(f"Archive created: {archive_path}")

    if delete_after:
        for path in archive_candidates:
            path.unlink(missing_ok=True)
        print(f"Deleted {len(archive_candidates)} original file(s).")
    else:
        print("Original files retained. Use --delete-after to remove them after archiving.")

    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage local syllabus HTML snapshots.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    stats = subparsers.add_parser("stats", help="Show the number of HTML files and their total size.")
    stats.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_HTML_DIR,
        help="Directory containing HTML files (default: scripts/textbooks/raw/html)",
    )

    archive = subparsers.add_parser("archive", help="Archive old HTML files into a zip.")
    archive.add_argument(
        "--target",
        type=Path,
        default=DEFAULT_HTML_DIR,
        help="Directory containing HTML files (default: scripts/textbooks/raw/html)",
    )
    archive.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_ARCHIVE_DIR,
        help="Directory where the archive zip will be stored (default: scripts/textbooks/raw/html_archive)",
    )
    archive.add_argument(
        "--keep-latest",
        type=int,
        default=0,
        help="Number of most-recent HTML files to keep without archiving.",
    )
    archive.add_argument(
        "--delete-after",
        action="store_true",
        help="Delete original HTML files after creating the archive.",
    )
    archive.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview the archive operation without writing or deleting files.",
    )

    return parser


def main(argv: Iterable[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "stats":
        return command_stats(args.target)
    if args.command == "archive":
        return command_archive(
            target=args.target,
            archive_dir=args.output_dir,
            keep_latest=args.keep_latest,
            delete_after=args.delete_after,
            dry_run=args.dry_run,
        )

    parser.print_help()
    return 1


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    sys.exit(main())
