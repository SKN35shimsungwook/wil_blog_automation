"""로컬 설정/이력 저장소. config.json에는 API 키 등 민감정보가 들어가므로 git에 커밋하지 않는다."""
import json
import sys
from pathlib import Path

# PyInstaller로 exe를 빌드하면 __file__이 임시 압축해제 폴더를 가리켜서(특히 --onefile),
# 설정/이력이 실행할 때마다 초기화되거나 사라진다. exe로 실행 중이면 exe가 있는 폴더를 기준으로 한다.
BASE_DIR = (
    Path(sys.executable).resolve().parent
    if getattr(sys, "frozen", False)
    else Path(__file__).resolve().parent
)
CONFIG_PATH = BASE_DIR / "config.json"
HISTORY_PATH = BASE_DIR / "history.json"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "gemini_model": "gemini-flash-lite-latest",
    "tistory_blog_name": "",
    "camp_name": "SK 네트웍스 Family AI 캠프",
    "camp_gisu": "35",
    "camp_start_date": "2026-07-07",
    "thumbnail_path": "",
    "tistory_category": "SKN35회고록",
}


def _backup_corrupted(path: Path) -> None:
    backup = path.with_suffix(path.suffix + ".corrupted")
    try:
        backup.write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    except OSError:
        pass


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _backup_corrupted(CONFIG_PATH)
        return dict(DEFAULT_CONFIG)
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def save_config(config: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load_history() -> list:
    if not HISTORY_PATH.exists():
        return []
    try:
        return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        _backup_corrupted(HISTORY_PATH)
        return []


def save_history(history: list) -> None:
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_history_entry(entry: dict, keep_last: int = 26) -> None:
    """같은 주차(week)로 이미 저장된 항목이 있으면 새로 덮어쓴다 (다시 생성 시
    같은 주차가 중복으로 쌓여서 나중에 '지난주'로 잘못 인식되는 것을 방지)."""
    history = load_history()
    week = entry.get("week")
    if isinstance(week, int):
        history = [h for h in history if h.get("week") != week]
    history.append(entry)
    history.sort(key=lambda h: h.get("week") if isinstance(h.get("week"), int) else 0)
    save_history(history[-keep_last:])


def set_history_url(week: int, url: str) -> None:
    """티스토리 업로드 성공 후, 해당 주차 이력 항목에 실제 게시 URL을 기록한다.
    월간 종합 회고에서 그 달의 글 링크들을 모을 때 쓴다."""
    history = load_history()
    for entry in history:
        if entry.get("week") == week:
            entry["url"] = url
            break
    save_history(history)
