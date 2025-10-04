#!/usr/bin/env python3
"""教科書マスタ用の CSV を整形して Supabase へ投入できる形式に変換するスクリプト.

想定する入力ファイル:
    scripts/textbooks/raw/textbooks_raw.csv
        - ヘッダーに必須列: textbook_title, course_title, campus
        - 任意列: textbook_title_reading, course_title_reading,
                  faculty_names, department_names, tag_names
          (カンマ区切りで複数値を表現する)

出力ファイル:
    scripts/textbooks/processed/textbooks_for_import.csv
        - Supabase の `copy` コマンドで取り込める最小構成
    scripts/textbooks/processed/textbook_relations.json
        - 学部/学科/タグの関連を保持 (API 経由で別途投入)

使用方法:
    $ python scripts/textbooks/prepare_textbooks.py

追加の整形ロジックを足したい場合は `normalize_row` を編集してください。
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Dict

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "scripts" / "textbooks" / "raw"
PROCESSED_DIR = PROJECT_ROOT / "scripts" / "textbooks" / "processed"

RAW_CSV = RAW_DIR / "textbooks_raw.csv"
OUTPUT_CSV = PROCESSED_DIR / "textbooks_for_import.csv"
RELATIONS_JSON = PROCESSED_DIR / "textbook_relations.json"
MINIMAL_OUTPUT_CSV = PROCESSED_DIR / "textbooks_for_import_minimal.csv"

REQUIRED_COLUMNS = {"textbook_title", "course_title", "campus"}
OPTIONAL_COLUMNS = {
    "textbook_title_reading",
    "course_title_reading",
    "faculty_names",
    "department_names",
    "tag_names",
    "course_code",
    "course_category",
    "instruction_language",
    "note",
    "authors",
    "publisher",
    "publication_year",
    "isbn",
}


@dataclass
class TextbookRow:
    textbook_title: str
    course_title: str
    campus: str
    textbook_title_reading: str = ""
    course_title_reading: str = ""
    course_code: str = ""
    course_category: str = ""
    instruction_language: str = ""
    note: str = ""
    authors: str = ""
    publisher: str = ""
    publication_year: str = ""
    isbn: str = ""
    faculties: List[str] = None
    departments: List[str] = None
    tags: List[str] = None

    def to_csv_row(self) -> Dict[str, str]:
        return {
            "textbook_title": self.textbook_title,
            "textbook_title_reading": self.textbook_title_reading,
            "course_title": self.course_title,
            "course_title_reading": self.course_title_reading,
            "campus": self.campus,
            "faculty_names": ",".join(self.faculties or []),
            "department_names": ",".join(self.departments or []),
            "tag_names": ",".join(self.tags or []),
            "course_code": self.course_code,
            "course_category": self.course_category,
            "instruction_language": self.instruction_language,
            "note": self.note,
            "authors": self.authors,
            "publisher": self.publisher,
            "publication_year": self.publication_year,
            "isbn": self.isbn,
        }

    def to_relations(self) -> Dict[str, Any]:
        return {
            "textbook_title": self.textbook_title,
            "course_title": self.course_title,
            "course_code": self.course_code,
            "course_category": self.course_category,
            "instruction_language": self.instruction_language,
            "note": self.note,
            "faculties": self.faculties or [],
            "departments": self.departments or [],
            "tags": self.tags or [],
            "authors": self.authors,
            "publisher": self.publisher,
            "publication_year": self.publication_year,
            "isbn": self.isbn,
        }


def normalize_value(value: str | None) -> str:
    if value is None:
        return ""
    return value.strip()


def split_multi_value(value: str | None) -> List[str]:
    if not value:
        return []
    return [normalize_value(part) for part in value.split(",") if part.strip()]


def normalize_row(raw: Dict[str, str]) -> TextbookRow:
    return TextbookRow(
        textbook_title=normalize_value(raw["textbook_title"]),
        textbook_title_reading=normalize_value(
            raw.get("textbook_title_reading", "")
        ),
        course_title=normalize_value(raw["course_title"]),
        course_title_reading=normalize_value(raw.get("course_title_reading", "")),
        campus=normalize_value(raw["campus"]),
        course_code=normalize_value(raw.get("course_code", "")),
        course_category=normalize_value(raw.get("course_category", "")),
        instruction_language=normalize_value(raw.get("instruction_language", "")),
        note=normalize_value(raw.get("note", "")),
        authors=normalize_value(raw.get("authors", "")),
        publisher=normalize_value(raw.get("publisher", "")),
        publication_year=normalize_value(raw.get("publication_year", "")),
        isbn=normalize_value(raw.get("isbn", "")),
        faculties=split_multi_value(raw.get("faculty_names")),
        departments=split_multi_value(raw.get("department_names")),
        tags=split_multi_value(raw.get("tag_names")),
    )


def ensure_directories() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)


def load_raw_rows() -> List[Dict[str, str]]:
    if not RAW_CSV.exists():
        raise FileNotFoundError(
            f"入力ファイルが見つかりません: {RAW_CSV}\n"
            "raw/ フォルダに textbooks_raw.csv を配置してください。"
        )

    with RAW_CSV.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        header = set(reader.fieldnames or [])

        missing = REQUIRED_COLUMNS - header
        if missing:
            raise ValueError(
                "必須カラムが不足しています: " + ", ".join(sorted(missing))
            )

        unexpected = header - (REQUIRED_COLUMNS | OPTIONAL_COLUMNS)
        if unexpected:
            print(
                "[warn] 未知のカラムを検出しました (処理には使用しません):",
                ", ".join(sorted(unexpected)),
            )

        return list(reader)


def write_full_output(rows: List[TextbookRow]) -> None:
    # CSV 出力
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        fieldnames = [
            "textbook_title",
            "textbook_title_reading",
            "course_title",
            "course_title_reading",
            "campus",
            "faculty_names",
            "department_names",
            "tag_names",
            "course_code",
            "course_category",
            "instruction_language",
            "note",
            "authors",
            "publisher",
            "publication_year",
            "isbn",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row.to_csv_row())

    # JSON 出力（学部・学科・タグの関連情報）
    relations = [row.to_relations() for row in rows]
    with RELATIONS_JSON.open("w", encoding="utf-8") as f:
        json.dump(relations, f, ensure_ascii=False, indent=2)

    print(f"書き出し完了: {OUTPUT_CSV}")
    print(f"関連ファイル: {RELATIONS_JSON}")


SECTION_SUFFIX_RE = re.compile(r"[\s\u3000]*[\(（][A-Za-z0-9Ａ-Ｚ０-９]{1,4}[\)）]$")


def canonical_course_title(title: str) -> str:
    if not title:
        return ""
    return SECTION_SUFFIX_RE.sub("", title).strip()


def write_minimal_output(rows: List[TextbookRow]) -> None:
    seen_keys = set()
    minimal_rows: List[Dict[str, str]] = []

    for row in rows:
        base_course = canonical_course_title(row.course_title)
        key = (
            row.textbook_title,
            base_course,
            row.campus,
            tuple(sorted(row.faculties or [])),
        )

        if key in seen_keys:
            continue

        seen_keys.add(key)
        minimal_rows.append(
            {
                "course_title": base_course or row.course_title,
                "textbook_title": row.textbook_title,
                "campus": row.campus,
                "faculty_names": ",".join(row.faculties or []),
            }
        )

    with MINIMAL_OUTPUT_CSV.open("w", encoding="utf-8", newline="") as f:
        fieldnames = ["course_title", "textbook_title", "campus", "faculty_names"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in minimal_rows:
            writer.writerow(row)

    print(
        "書き出し完了 (簡易版): "
        f"{MINIMAL_OUTPUT_CSV} (重複削除後 {len(minimal_rows)} 行)"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--minimal-only",
        action="store_true",
        help="簡易版 CSV のみを書き出す",
    )
    args = parser.parse_args()

    ensure_directories()
    raw_rows = load_raw_rows()
    processed_rows = [normalize_row(raw) for raw in raw_rows]

    if not args.minimal_only:
        write_full_output(processed_rows)

    write_minimal_output(processed_rows)


if __name__ == "__main__":
    main()
