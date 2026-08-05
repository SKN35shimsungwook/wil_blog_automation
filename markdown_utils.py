"""마크다운 조립, HTML 변환, 파일 저장 유틸."""
from datetime import date
from pathlib import Path

import markdown as md_lib

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "output"


def assemble_markdown(title: str, markdown_body: str) -> str:
    return f"# {title}\n\n{markdown_body.strip()}\n"


def markdown_to_html(markdown_text: str) -> str:
    return md_lib.markdown(
        markdown_text,
        extensions=["fenced_code", "tables", "toc", "codehilite"],
    )


def default_filename(prefix: str = "WIL", ext: str = "md") -> str:
    return f"{date.today().isoformat()}-{prefix}.{ext}"


def save_text_file(content: str, filename: str) -> Path:
    OUTPUT_DIR.mkdir(exist_ok=True)
    path = OUTPUT_DIR / filename
    path.write_text(content, encoding="utf-8")
    return path
