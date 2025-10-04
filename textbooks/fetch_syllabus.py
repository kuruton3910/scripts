"""Download syllabus HTML pages in bulk for textbook scraping.

Usage example::

    python scripts/textbooks/fetch_syllabus.py --input scripts/textbooks/raw/syllabus_urls.csv

The input file should be a CSV with at least a `url` column. Optional
columns like `course_code` or `course_title` are used to generate stable
filenames under `raw/html/`.
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional
from urllib.parse import urlparse

import requests


try:
    from slugify import slugify  # type: ignore
except ImportError:  # pragma: no cover - fallback slugifier
    def slugify(value: str) -> str:
        return "-".join(
            segment for segment in "".join(
                ch if ch.isalnum() else " " for ch in value
            ).split()
        )


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_HTML_DIR = PROJECT_ROOT / "scripts" / "textbooks" / "raw" / "html"


@dataclass
class SyllabusTarget:
    url: str
    course_code: str = ""
    course_title: str = ""
    file_name: str = ""

    def resolve_filename(self, default_index: int) -> str:
        if self.file_name:
            return ensure_html_extension(self.file_name)
        if self.course_code:
            return ensure_html_extension(slugify(self.course_code))
        if self.course_title:
            return ensure_html_extension(slugify(self.course_title) or f"course-{default_index}")
        parsed = urlparse(self.url)
        last_segment = Path(parsed.path).name or f"page-{default_index}"
        return ensure_html_extension(slugify(last_segment) or f"page-{default_index}")


def ensure_html_extension(name: str) -> str:
    if name.lower().endswith(".html"):
        return name
    return f"{name}.html"


def load_plain_text_targets(input_path: Path) -> List[SyllabusTarget]:
    targets: List[SyllabusTarget] = []
    with input_path.open("r", encoding="utf-8") as fp:
        for line in fp:
            value = line.strip()
            if not value:
                continue
            if value.lower() == "url":
                continue
            targets.append(SyllabusTarget(url=value))
    return targets


def extract_url_from_row(row: dict[str, Optional[str]]) -> str:
    url_candidate = (row.get("url") or "").strip()
    if url_candidate:
        return url_candidate

    for value in row.values():
        if not value:
            continue
        text = value.strip()
        if text.lower().startswith("http://") or text.lower().startswith("https://"):
            return text
    return ""


def load_targets(input_path: Path) -> List[SyllabusTarget]:
    if not input_path.exists():
        raise FileNotFoundError(f"Input file not found: {input_path}")

    if input_path.suffix.lower() == ".csv":
        with input_path.open("r", encoding="utf-8-sig", newline="") as fp:
            reader = csv.DictReader(fp)

            fieldnames = reader.fieldnames or []
            if "url" not in fieldnames:
                # fallback: treat as simple text file with one URL per line
                return load_plain_text_targets(input_path)

            targets: List[SyllabusTarget] = []
            for row in reader:
                url_value = extract_url_from_row(row)
                if not url_value:
                    continue
                targets.append(
                    SyllabusTarget(
                        url=url_value,
                        course_code=(row.get("course_code") or "").strip(),
                        course_title=(row.get("course_title") or "").strip(),
                        file_name=(row.get("file_name") or "").strip(),
                    )
                )
    else:
        targets = load_plain_text_targets(input_path)

    if not targets:
        raise ValueError("No syllabus URLs found in input file")

    return targets


def build_session(auth_cookie: Optional[str]) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": "Mozilla/5.0 (compatible; textbook-scraper/1.0)",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        }
    )
    if auth_cookie:
        session.headers.update({"Cookie": auth_cookie})
    return session


def download_targets(
    targets: Iterable[SyllabusTarget],
    session: requests.Session,
    delay: float,
    output_dir: Path,
) -> List[Path]:
    saved_files: List[Path] = []
    output_dir.mkdir(parents=True, exist_ok=True)

    target_list = list(targets)
    total = len(target_list)

    for index, target in enumerate(target_list, start=1):
        file_name = target.resolve_filename(index)
        initial_destination = output_dir / file_name
        destination = ensure_unique_destination(initial_destination)
        if destination != initial_destination:
            print(
                f"[info] Renamed duplicate filename to {destination.name}",
                file=sys.stderr,
            )

        try:
            response = session.get(target.url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:  # pragma: no cover - IO bound
            print(f"[error] Failed to download {target.url}: {exc}", file=sys.stderr)
            continue

        destination.write_bytes(response.content)
        saved_files.append(destination)
        print(f"[ok] {target.url} -> {destination.relative_to(PROJECT_ROOT)}")

        if delay and index < total:
            time.sleep(delay)

    return saved_files


def ensure_unique_destination(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem}-{counter}{suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def main(argv: Optional[List[str]] = None) -> None:  # pragma: no cover - CLI glue
    parser = argparse.ArgumentParser(description="Fetch syllabus HTML files in bulk.")
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to CSV or TXT listing syllabus URLs.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=RAW_HTML_DIR,
        help="Directory to save HTML files (default: scripts/textbooks/raw/html)",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Optional delay in seconds between requests.",
    )
    parser.add_argument(
        "--auth-cookie",
        type=str,
        default=None,
        help="Value for the Cookie header (e.g. sessionid=...). Useful for authenticated portals.",
    )

    args = parser.parse_args(argv)
    targets = load_targets(args.input)
    session = build_session(args.auth_cookie)
    saved_files = download_targets(targets, session, args.delay, args.output)

    if not saved_files:
        raise SystemExit("No files were downloaded. Check errors above.")

    print(f"Saved {len(saved_files)} syllabus pages to {args.output}")


if __name__ == "__main__":  # pragma: no cover - CLI entrypoint
    main()
