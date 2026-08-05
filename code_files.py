"""첨부한 .py / .ipynb 파일에서 AI 프롬프트에 넣을 코드 컨텍스트를 뽑아낸다."""
import json
from pathlib import Path

MAX_CHARS_PER_FILE = 6000
MAX_TOTAL_CHARS = 24000


def _read_py(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="ignore")
    if len(text) > MAX_CHARS_PER_FILE:
        text = text[:MAX_CHARS_PER_FILE] + "\n... (내용이 길어 이하 생략)"
    return f"### {path.name}\n```python\n{text}\n```"


def _read_ipynb(path: Path) -> str:
    data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
    parts = []
    for i, cell in enumerate(data.get("cells", []), start=1):
        source = "".join(cell.get("source", []))
        if not source.strip():
            continue
        cell_type = cell.get("cell_type", "code")
        if cell_type == "markdown":
            parts.append(f"[셀 {i} - 설명]\n{source}")
        else:
            parts.append(f"[셀 {i} - 코드]\n```python\n{source}\n```")
    body = "\n\n".join(parts)
    if len(body) > MAX_CHARS_PER_FILE:
        body = body[:MAX_CHARS_PER_FILE] + "\n... (내용이 길어 이하 생략)"
    return f"### {path.name}\n{body}"


def extract_code_context(file_paths: list) -> str:
    """여러 파일을 읽어 AI 프롬프트에 넣을 하나의 텍스트로 합친다."""
    if not file_paths:
        return ""

    blocks = []
    total = 0
    for p in file_paths:
        path = Path(p)
        try:
            if path.suffix == ".ipynb":
                block = _read_ipynb(path)
            elif path.suffix == ".py":
                block = _read_py(path)
            else:
                continue
        except Exception as exc:  # noqa: BLE001
            block = f"### {path.name}\n(파일을 읽지 못했습니다: {exc})"

        if total + len(block) > MAX_TOTAL_CHARS:
            blocks.append(f"... (총 길이 제한으로 이후 파일 생략)")
            break
        blocks.append(block)
        total += len(block)

    return "\n\n".join(blocks)
