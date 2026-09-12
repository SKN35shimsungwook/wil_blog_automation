"""마크다운 조립, HTML 변환, 파일 저장 유틸."""
import sys
from datetime import date
from pathlib import Path

import markdown as md_lib

# PyInstaller로 exe를 빌드하면 __file__이 임시 압축해제 폴더를 가리켜서(특히 --onefile),
# 저장 폴더가 실행할 때마다 바뀌거나 사라진다. exe로 실행 중이면 exe가 있는 폴더를 기준으로 한다.
BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
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
