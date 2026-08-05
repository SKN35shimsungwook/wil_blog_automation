"""로컬 설정/이력 저장소. config.json에는 API 키 등 민감정보가 들어가므로 git에 커밋하지 않는다."""
import json
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
HISTORY_PATH = BASE_DIR / "history.json"

DEFAULT_CONFIG = {
    "gemini_api_key": "",
    "gemini_model": "gemini-flash-latest",
    "tistory_blog_name": "",
    "camp_name": "SK 네트웍스 Family AI 캠프",
    "camp_gisu": "35",
    "camp_start_date": "2026-07-07",
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
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
    return json.loads(HISTORY_PATH.read_text(encoding="utf-8"))


def save_history(history: list) -> None:
    HISTORY_PATH.write_text(
        json.dumps(history, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def append_history_entry(entry: dict, keep_last: int = 26) -> None:
    history = load_history()
    history.append(entry)
    save_history(history[-keep_last:])
