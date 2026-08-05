"""Playwright로 티스토리 글쓰기 화면을 직접 조작해 글을 작성한다.

티스토리 Open API는 2024년 2월 서비스가 종료되었고, 로그인도 카카오계정 전용이라
아이디/비밀번호를 코드에서 대신 입력할 방법이 없다. 그래서 이 모듈은:

1. 로그인이 안 되어 있으면 화면이 보이는(headless=False) 브라우저 창을 띄우고,
   사용자가 직접 카카오 로그인을 완료할 때까지 기다린다. (자동입력/CAPTCHA 우회 없음)
   브라우저는 Playwright 번들 Chromium 대신 시스템에 이미 설치된 Microsoft Edge
   (channel="msedge")를 사용한다. Windows에 기본 내장되어 있어 별도 설치가 필요 없고,
   압축 해제된 번들 바이너리의 side-by-side 매니페스트 문제를 피할 수 있다.
2. 로그인 세션(쿠키)은 tistory_session.json에 저장해 두었다가 다음부터는 재사용한다.
3. 제목/본문(HTML)/태그는 자동으로 입력한다.
4. 최종 '완료 -> 공개범위 선택 -> 발행' 클릭까지는 자동으로 시도하되, 티스토리 에디터
   구조가 바뀌어 실패하면 예외를 던지지 않고 사용자가 브라우저에서 직접 완료 버튼을
   누르도록 안내하고 그 결과를 기다린다.
"""
import re
import time
from pathlib import Path

from playwright.sync_api import TimeoutError as PwTimeoutError
from playwright.sync_api import sync_playwright

BASE_DIR = Path(__file__).resolve().parent
SESSION_PATH = BASE_DIR / "tistory_session.json"

LOGIN_WAIT_TIMEOUT_MS = 5 * 60 * 1000  # 카카오 로그인(2단계 인증 포함) 대기, 최대 5분
MANUAL_PUBLISH_WAIT_SEC = 10 * 60  # 자동 발행 실패 시 사용자가 직접 완료할 때까지 대기, 최대 10분

PUBLISH_BUTTON_PATTERN = re.compile("공개\\s*발행|저장")


def _editor_url(blog_name: str) -> str:
    return f"https://{blog_name}.tistory.com/manage/newpost/?type=post"


def _is_editor_open(page) -> bool:
    return "/manage/newpost" in page.url


def _goto_with_retry(page, url: str, attempts: int = 3, delay_sec: float = 2.0):
    """브라우저를 막 띄운 직후 첫 네비게이션에서 가끔 발생하는 일시적인
    net::ERR_INTERNET_DISCONNECTED 오류를 자동으로 재시도해서 넘긴다."""
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url)
            return
        except PwTimeoutError:
            raise
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < attempts:
                time.sleep(delay_sec)
    raise last_error


def ensure_login(blog_name: str, on_status=None) -> bool:
    """로그인 세션을 확인하고, 없으면 사용자가 직접 로그인할 때까지 기다린 뒤 세션을 저장한다."""
    status = on_status or (lambda msg: None)
    storage_state = str(SESSION_PATH) if SESSION_PATH.exists() else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="msedge")
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()
        _goto_with_retry(page, _editor_url(blog_name))

        if not _is_editor_open(page):
            status("브라우저 창에서 카카오 계정으로 로그인해주세요...")
            try:
                page.wait_for_url(lambda url: "/manage/newpost" in url, timeout=LOGIN_WAIT_TIMEOUT_MS)
            except PwTimeoutError:
                browser.close()
                return False

        context.storage_state(path=str(SESSION_PATH))
        status("로그인 세션을 저장했습니다.")
        browser.close()
        return True


def post_to_tistory(
    blog_name: str,
    title: str,
    html_content: str,
    tags: list,
    visibility_label: str,
    on_status=None,
    should_cancel=None,
) -> dict:
    status = on_status or (lambda msg: None)
    cancel = should_cancel or (lambda: False)
    storage_state = str(SESSION_PATH) if SESSION_PATH.exists() else None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False, channel="msedge")
        context = browser.new_context(storage_state=storage_state)
        page = context.new_page()
        _goto_with_retry(page, _editor_url(blog_name))

        if not _is_editor_open(page):
            status("브라우저 창에서 카카오 계정으로 로그인해주세요...")
            try:
                page.wait_for_url(lambda url: "/manage/newpost" in url, timeout=LOGIN_WAIT_TIMEOUT_MS)
            except PwTimeoutError as exc:
                browser.close()
                raise TimeoutError("로그인 대기 시간이 초과되었습니다. 다시 시도해주세요.") from exc

        context.storage_state(path=str(SESSION_PATH))
        status("에디터에 제목/본문/태그를 입력하는 중...")
        page.wait_for_load_state("networkidle", timeout=30_000)

        _fill_title(page, title)
        _fill_body(page, html_content)
        _fill_tags(page, tags)

        status("입력을 완료했습니다. 자동 게시를 시도합니다...")
        try:
            result_url = _attempt_auto_publish(page, visibility_label)
            browser.close()
            return {"url": result_url, "auto_published": True}
        except Exception:
            pass

        status(
            "자동 게시에 실패했습니다. 열려있는 브라우저 창에서 직접 "
            "'완료' 버튼을 눌러 공개범위를 선택하고 게시해주세요. "
            "(게시를 마치면 자동으로 감지해서 창을 닫습니다)"
        )
        result_url = _wait_for_manual_publish(page, cancel)
        browser.close()
        return {"url": result_url, "auto_published": False}


def _fill_title(page, title: str):
    title_field = page.get_by_placeholder("제목을 입력하세요")
    title_field.wait_for(state="visible", timeout=20_000)
    title_field.click()
    title_field.fill(title)


def _fill_body(page, html_content: str):
    """티스토리 에디터는 TinyMCE 기반이라, 툴바의 'HTML 모드' 버튼을 찾아 누르는 대신
    TinyMCE의 자체 JS API(setContent)로 직접 본문 HTML을 채운다. 이렇게 하면 툴바
    버튼 위치/문구가 바뀌어도 안 깨지고, 제목 입력칸을 잘못 덮어쓰는 문제도 없다.

    setContent()만으로는 에디터 화면에는 반영되지만 실제 발행 시 티스토리가 읽어가는
    숨은 textarea(#editor-tistory)에는 동기화되지 않는다 (직접 확인함: setContent
    직후엔 textarea.value가 빈 문자열). editor.save()를 호출해야 그 textarea에
    내용이 실제로 반영되므로, 반드시 save()까지 호출한다."""
    page.wait_for_function("() => !!window.tinymce && window.tinymce.editors.length > 0", timeout=20_000)
    page.evaluate(
        """(html) => {
            const ed = window.tinymce.editors[0];
            ed.setContent(html);
            ed.save();
        }""",
        html_content,
    )


def _fill_tags(page, tags: list):
    if not tags:
        return
    try:
        tag_input = page.get_by_placeholder("태그입력")
        tag_input.wait_for(state="visible", timeout=5_000)
    except PwTimeoutError:
        return
    for tag in tags:
        tag_input.click()
        tag_input.fill(tag)
        tag_input.press("Enter")


def _attempt_auto_publish(page, visibility_label: str) -> str:
    complete_btn = page.get_by_role("button", name="완료")
    complete_btn.wait_for(state="visible", timeout=10_000)
    complete_btn.click()

    # 공개범위 라디오 라벨은 "비공개" 안에 "공개"가 부분 문자열로 들어있어
    # exact=False(부분일치)로 찾으면 여러 라디오가 동시에 매치된다. exact=True로 정확히 매치.
    visibility_option = page.get_by_text(visibility_label, exact=True)
    visibility_option.wait_for(state="visible", timeout=10_000)
    visibility_option.click()

    # 모달을 연 원래 '완료' 버튼이 화면 뒤에 그대로 DOM에 남아있어서,
    # 패턴에 '완료'가 섞여 있으면 버튼이 2개 이상 매칭되어 strict-mode 에러가 난다.
    # 모달에서 새로 나타난 버튼은 DOM 순서상 나중에 추가되므로 .last로 명확히 지정.
    publish_btn = page.get_by_role("button", name=PUBLISH_BUTTON_PATTERN).last
    publish_btn.wait_for(state="visible", timeout=10_000)
    publish_btn.click()

    page.wait_for_load_state("networkidle", timeout=20_000)
    return page.url


def _wait_for_manual_publish(page, should_cancel):
    start_url = page.url
    deadline = time.time() + MANUAL_PUBLISH_WAIT_SEC
    while time.time() < deadline:
        if should_cancel():
            return None
        if page.is_closed():
            return None
        if page.url != start_url:
            return page.url
        time.sleep(1)
    return None
