"""Utilities for scraping syllabus HTML pages into textbook CSV format.

This script parses one or more saved syllabus HTML pages and extracts
structured textbook information for downstream processing. The output
is a raw CSV that can be used as the input to `prepare_textbooks.py`.
"""
from __future__ import annotations

import argparse
import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Set


try:
    from bs4 import BeautifulSoup
except ImportError as error:  # pragma: no cover - dependency guard
    raise SystemExit(
        "Missing optional dependency 'beautifulsoup4'. "
        "Install it via 'pip install beautifulsoup4'."
    ) from error


@dataclass
class TextbookRecord:
    course_code: str
    course_title: str
    campus: str
    faculty_names: List[str]
    textbook_title: str
    textbook_title_reading: str = ""
    authors: str = ""
    publisher: str = ""
    publication_year: str = ""
    isbn: str = ""
    note: str = ""
    tag_names: str = ""
    course_category: str = ""
    instruction_language: str = ""
    academic_year: str = ""
    term: str = ""
    schedule: str = ""
    classroom: str = ""
    credits: str = ""
    instructors: Optional[List[str]] = None

    def to_csv_row(self) -> List[str]:
        return [
            self.textbook_title,
            self.textbook_title_reading,
            self.authors,
            self.publisher,
            self.publication_year,
            self.isbn,
            self.course_title,
            self.course_code,
            self.academic_year,
            self.term,
            self.schedule,
            self.classroom,
            self.credits,
            ",".join(self.instructors or []),
            ",".join(self.faculty_names),
            self.campus,
            self.tag_names,
            self.course_category,
            self.instruction_language,
            self.note,
        ]


@dataclass
class CourseMetadata:
    course_code: str
    course_title: str
    academic_year: str
    term: str
    schedule: str
    campus: str
    classroom: str
    faculties: List[str]
    instructors: List[str]
    credits: str
    instruction_language: str


CSV_HEADER = [
    "textbook_title",
    "textbook_title_reading",
    "authors",
    "publisher",
    "publication_year",
    "isbn",
    "course_title",
    "course_code",
    "academic_year",
    "term",
    "schedule",
    "classroom",
    "credits",
    "instructors",
    "faculty_names",
    "campus",
    "tag_names",
    "course_category",
    "instruction_language",
    "note",
]


GENERAL_FACULTY_KEYWORDS: tuple[str, ...] = (
    "共通教育",
    "教養教育",
    "全学共通",
    "基盤教育",
    "汎用教育",
    "General Education",
    "教養科目",
    "共通科目",
)

GENERAL_TITLE_KEYWORDS: tuple[str, ...] = (
    "教養",
    "共通科目",
    "General Education",
    "Liberal Arts",
)

INTERNATIONAL_TITLE_KEYWORDS: tuple[str, ...] = (
    "留学生",
    "International Students",
    "for International Students",
    "Non-Japanese",
    "外国人",
)


def normalize_textbook_header(label: str) -> Optional[str]:
    value = label.strip()
    if not value:
        return None
    lower = value.lower()
    if "書名" in value or "タイトル" in value or "name" in lower:
        return "title"
    if "読み" in value or "フリガナ" in value or "ふりがな" in value:
        return "reading"
    if "著者" in value or "編者" in value or "author" in lower:
        return "authors"
    if "出版社" in value or "publisher" in lower:
        return "publisher"
    if "isbn" in value.lower():
        return "isbn"
    if "備考" in value or "補足" in value or "メモ" in value or "使用頻度" in value or "note" in lower:
        return "note"
    return None


def determine_course_category(faculty_names: List[str], course_title: str) -> str:
    normalized_faculties = [name.strip() for name in faculty_names if name.strip()]
    if not normalized_faculties:
        return "general-education"

    for faculty in normalized_faculties:
        if any(keyword in faculty for keyword in GENERAL_FACULTY_KEYWORDS):
            return "general-education"

    if len(set(normalized_faculties)) >= 3:
        return "general-education"

    if any(keyword in course_title for keyword in GENERAL_TITLE_KEYWORDS):
        return "general-education"

    return "faculty-course"


def detect_international_course(course_title: str) -> bool:
    lowered = course_title.lower()
    for keyword in INTERNATIONAL_TITLE_KEYWORDS:
        if keyword.lower() in lowered:
            return True
    return False


def normalize_language_tag(language_value: str) -> Optional[str]:
    if not language_value:
        return None
    lowered = language_value.lower()
    if "english" in lowered or "英語" in language_value:
        return "english"
    if "japanese" in lowered or "日本語" in language_value:
        return "japanese"
    if "chinese" in lowered or "中国語" in language_value:
        return "chinese"
    if "korean" in lowered or "韓国語" in language_value:
        return "korean"
    if "french" in lowered or "フランス語" in language_value:
        return "french"
    if "german" in lowered or "ドイツ語" in language_value:
        return "german"
    return None


def derive_tags(
    category: str,
    faculty_names: List[str],
    course_title: str,
    instruction_language: str,
) -> List[str]:
    tags: Set[str] = {category}

    unique_faculties = {name for name in faculty_names if name}
    if len(unique_faculties) > 1 and category != "general-education":
        tags.add("multi-faculty")

    if detect_international_course(course_title):
        tags.add("international-student")

    language_tag = normalize_language_tag(instruction_language)
    if language_tag:
        tags.add(f"lang:{language_tag}")

    return sorted(tags)


def append_note(record: TextbookRecord, addition: str) -> None:
    if not addition:
        return
    if addition in record.note:
        return
    if record.note:
        record.note = f"{record.note} / {addition}"
    else:
        record.note = addition


def annotate_aliases(records: List[TextbookRecord]) -> None:
    titles_by_code: Dict[str, Set[str]] = {}
    for record in records:
        if record.course_code:
            titles_by_code.setdefault(record.course_code, set()).add(record.course_title)

    for record in records:
        if not record.course_code:
            continue
        alias_titles = titles_by_code.get(record.course_code, {record.course_title})
        if len(alias_titles) <= 1:
            continue
        other_titles = sorted(title for title in alias_titles if title != record.course_title)
        if other_titles:
            append_note(record, f"別名称: {' / '.join(other_titles)}")


def annotate_faculty_scope(records: List[TextbookRecord]) -> None:
    for record in records:
        unique_faculties = sorted(set(record.faculty_names))
        if len(unique_faculties) > 1:
            append_note(record, f"複数学部向け: {', '.join(unique_faculties)}")
        if record.course_category == "general-education":
            append_note(record, "教養・共通科目 (自動判定)")


def iter_html_files(target: Path) -> Iterable[Path]:
    if target.is_dir():
        yield from sorted(target.glob("*.html"))
    else:
        yield target


def extract_course_metadata(soup: "BeautifulSoup") -> CourseMetadata:
    course_table = soup.select_one("#table-syllabusitems table.stdlist")
    if not course_table:
        raise ValueError("Could not locate course metadata table in HTML page")

    rows = course_table.find_all("tr")
    if len(rows) < 2:
        raise ValueError("Course metadata table does not contain expected rows")

    cells = [cell.get_text(strip=True) for cell in rows[1].find_all("td")]
    if len(cells) < 1:
        raise ValueError("Course metadata row missing expected columns")

    def get_cell(index: int) -> str:
        if index < len(cells):
            return cells[index]
        return ""

    course_identifier = get_cell(0)
    course_code, course_title = parse_course_identifier(course_identifier)
    academic_year = get_cell(1)
    term = get_cell(2)
    schedule = get_cell(3)
    faculties = normalize_name_list(get_cell(4))
    instructors = normalize_instructor_list(get_cell(5))
    credits = get_cell(6) if len(cells) > 6 else ""

    campus = extract_section_text(soup, "キャンパス")
    classroom = extract_section_text(soup, "授業施設|教室|教場|教室名")
    instruction_language = extract_section_text(
        soup,
        "使用言語|Language of instruction|使用言語等|使用される言語",
    )

    return CourseMetadata(
        course_code=course_code,
        course_title=course_title,
        academic_year=academic_year,
        term=term,
        schedule=schedule,
        campus=campus,
        classroom=classroom,
        faculties=faculties,
        instructors=instructors,
        credits=credits,
        instruction_language=instruction_language,
    )


def parse_course_identifier(value: str) -> tuple[str, str]:
    match = re.match(r"(?P<code>[^\s：:]+)[：:](?P<title>.+)", value)
    if match:
        return match.group("code"), match.group("title").strip()

    parts = value.split(maxsplit=1)
    if len(parts) == 2:
        return parts[0].strip(), parts[1].strip()

    return value.strip(), ""


def extract_section_text(soup: "BeautifulSoup", section_name: str) -> str:
    header_candidates = soup.find_all(["h3", "th"], string=re.compile(section_name))
    for header in header_candidates:
        sibling = header.find_next(lambda tag: getattr(tag, "get_text", None))
        if not sibling:
            continue
        text = sibling.get_text(strip=True)
        if text:
            return text
    return ""


def normalize_name_list(value: str) -> List[str]:
    if not value:
        return []
    raw_items = re.split(r"[、,\s]+", value.strip())
    return [item for item in raw_items if item]


def normalize_instructor_list(value: str) -> List[str]:
    if not value:
        return []
    raw_items = re.split(r"[、,\/／]+", value.strip())
    return [item.strip() for item in raw_items if item.strip()]


def extract_textbooks(soup: "BeautifulSoup") -> List[dict[str, str]]:
    textbooks_section = soup.find("h3", string=re.compile("教科書"))
    if not textbooks_section:
        return []

    table = textbooks_section.find_next("table")
    if not table:
        return []

    rows = table.find_all("tr")
    if not rows:
        return []

    header_map: List[Optional[str]] = []
    first_row_cells = rows[0].find_all(["th", "td"])
    has_header = any(cell.name == "th" for cell in first_row_cells)

    if has_header:
        header_map = [normalize_textbook_header(cell.get_text(strip=True)) for cell in first_row_cells]
        data_rows = rows[1:]
    else:
        data_rows = rows

    textbooks = []
    for row in data_rows:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue
        values: dict[str, str] = {}
        for index, cell in enumerate(cells):
            key: Optional[str]
            if header_map and index < len(header_map):
                key = header_map[index]
            else:
                key = None
            text = cell.get_text(strip=True)
            if key:
                values[key] = text
            else:
                # fallback positional mapping when header is unknown
                if index == 0:
                    values.setdefault("title", text)
                elif index == 1:
                    values.setdefault("authors", text)
                elif index == 2:
                    values.setdefault("publisher", text)
                elif index == 3:
                    values.setdefault("isbn", text)
                elif index == 4:
                    values.setdefault("note", text)

        title = values.get("title", "").strip()
        if not title:
            continue
        textbooks.append(
            {
                "title": title,
                "reading": values.get("reading", ""),
                "authors": values.get("authors", ""),
                "publisher": values.get("publisher", ""),
                "isbn": values.get("isbn", ""),
                "note": values.get("note", ""),
            }
        )
    return textbooks


def build_records(soup: "BeautifulSoup") -> List[TextbookRecord]:
    metadata = extract_course_metadata(soup)
    textbooks = extract_textbooks(soup)

    resolved_course_title = metadata.course_title or (
        metadata.course_code if metadata.course_code else ""
    )
    if not resolved_course_title:
        resolved_course_title = "Untitled Course"

    course_category = determine_course_category(metadata.faculties, resolved_course_title)
    base_tags = derive_tags(
        course_category,
        metadata.faculties,
        resolved_course_title,
        metadata.instruction_language,
    )

    records: List[TextbookRecord] = []
    for textbook in textbooks:
        note = textbook.get("note", "")
        record_tags = set(base_tags)
        if detect_international_course(note):
            record_tags.add("international-student")
        records.append(
            TextbookRecord(
                course_code=metadata.course_code,
                course_title=resolved_course_title,
                campus=metadata.campus,
                faculty_names=metadata.faculties,
                textbook_title=textbook["title"],
                textbook_title_reading=textbook.get("reading", ""),
                authors=textbook.get("authors", ""),
                publisher=textbook.get("publisher", ""),
                note=note,
                tag_names=",".join(sorted(record_tags)),
                course_category=course_category,
                instruction_language=metadata.instruction_language,
                academic_year=metadata.academic_year,
                term=metadata.term,
                schedule=metadata.schedule,
                classroom=metadata.classroom,
                credits=metadata.credits,
                instructors=metadata.instructors,
            )
        )
    return records


def scrape_file(path: Path) -> List[TextbookRecord]:
    with path.open("r", encoding="utf-8") as fp:
        soup = BeautifulSoup(fp, "html.parser")
    return build_records(soup)


def write_csv(records: Iterable[TextbookRecord], output_path: Path) -> None:
    records = list(records)
    if not records:
        raise SystemExit("No textbook records found. Ensure the input HTML contains textbook tables.")

    with output_path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(CSV_HEADER)
        for record in records:
            writer.writerow(record.to_csv_row())


def main(args: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="Scrape syllabus HTML files into a raw textbook CSV.")
    parser.add_argument(
        "--input",
        type=Path,
        default=Path(__file__).parent / "raw" / "html",
        help="Path to an HTML file or directory containing syllabus pages (default: scripts/textbooks/raw/html)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(__file__).parent / "raw" / "textbooks_raw.csv",
        help="Destination CSV file for scraped textbook data.",
    )
    parsed = parser.parse_args(args=args)

    all_records: List[TextbookRecord] = []
    for html_file in iter_html_files(parsed.input):
        if not html_file.exists():
            raise SystemExit(f"Input file not found: {html_file}")
        records = scrape_file(html_file)
        if not records:
            continue
        all_records.extend(records)

    if not all_records:
        raise SystemExit("Finished scanning HTML files but found no textbook entries. Double-check the input pages.")

    annotate_aliases(all_records)
    annotate_faculty_scope(all_records)

    parsed.output.parent.mkdir(parents=True, exist_ok=True)
    write_csv(all_records, parsed.output)
    print(f"Wrote {len(all_records)} textbook rows to {parsed.output}")


if __name__ == "__main__":
    main()
