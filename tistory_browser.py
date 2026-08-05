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


# 최종 버튼 문구는 공개범위에 따라 "공개 발행" / "공개(보호) 발행" / "비공개 저장"으로
# 달라진다. "공개(보호)"처럼 괄호 안에 다른 글자가 끼는 경우가 있어 "공개" 바로 뒤에
# 공백만 오는 패턴으로는 놓친다 -> "발행" 또는 "저장"으로 끝나는지만 넉넉하게 확인한다.
PUBLISH_BUTTON_PATTERN = re.compile("발행|저장")


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
    thumbnail_path: str = "",
    category: str = "",
    body_image_paths: list = None,
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
        if category:
            _set_category(page, category)
        if body_image_paths:
            status(f"본문에 이미지 {len(body_image_paths)}개를 삽입하는 중...")
            _insert_body_images(page, body_image_paths)

        status("입력을 완료했습니다. 자동 게시를 시도합니다...")
        try:
            _attempt_auto_publish(page, visibility_label, thumbnail_path)
            status("게시 여부를 실제 글 목록에서 확인하는 중...")
            real_url = _find_published_url(page, blog_name, title)
            if not real_url:
                raise RuntimeError(
                    "발행 버튼 클릭까지는 진행됐지만, 글 목록에서 실제 게시물을 확인하지 못했습니다."
                )
            browser.close()
            return {"url": real_url, "auto_published": True}
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


def _set_category(page, category_name: str):
    """상단 '카테고리' 버튼(id=category-btn)을 눌러 목록(id=category-list)에서
    이름이 일치하는 항목을 고른다. 카테고리가 없거나 이름이 안 맞으면 조용히 넘어간다."""
    try:
        page.locator("#category-btn").click(timeout=5_000)
        option = page.locator("#category-list [role='option']", has_text=category_name)
        option.first.wait_for(state="visible", timeout=3_000)
        option.first.click()
    except Exception:  # noqa: BLE001
        pass


def _insert_body_images(page, image_paths: list):
    """본문 툴바의 '이미지 ▾ -> 사진' 메뉴로 실제 티스토리 CDN에 이미지를 업로드해서
    본문 커서 위치에 순서대로 삽입한다 (대표이미지와는 별개의, 본문 안에 보이는 이미지).
    커서를 본문 맨 끝으로 옮겨두고 하나씩 순서대로 넣는다. 실패한 이미지는 건너뛴다."""
    try:
        frame = page.frame(name="editor-tistory_ifr")
        body = frame.locator("body#tinymce")
        body.click()
        page.keyboard.press("Control+End")
    except Exception:  # noqa: BLE001
        pass

    for path in image_paths:
        try:
            img_btn = page.locator("button:has(i.mce-i-image)").locator("visible=true").first
            img_btn.click(timeout=5_000)
            photo_option = page.get_by_text("사진", exact=True).locator("visible=true").first
            photo_option.click(timeout=3_000)
            file_input = page.locator("#openFile")
            file_input.wait_for(state="attached", timeout=5_000)
            file_input.set_input_files(path)
            page.wait_for_timeout(2_500)
        except Exception:  # noqa: BLE001
            continue


def _set_thumbnail(page, thumbnail_path: str):
    """'완료' 클릭 후 뜨는 발행 모달의 대표이미지 파일 입력에 직접 파일을 넣는다.
    실패해도(파일 없음, 요소 못 찾음 등) 전체 게시를 막지 않고 조용히 넘어간다."""
    try:
        file_input = page.locator("input[type='file'][accept='image/*']").first
        file_input.wait_for(state="attached", timeout=5_000)
        file_input.set_input_files(thumbnail_path)
        page.wait_for_timeout(1_000)
    except Exception:  # noqa: BLE001
        pass


def _attempt_auto_publish(page, visibility_label: str, thumbnail_path: str = "") -> str:
    complete_btn = page.get_by_role("button", name="완료")
    complete_btn.wait_for(state="visible", timeout=10_000)
    complete_btn.click()

    if thumbnail_path:
        _set_thumbnail(page, thumbnail_path)

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


def _find_published_url(page, blog_name: str, title: str, timeout_sec: float = 15.0):
    """발행 버튼을 눌렀다고 해서 실제로 저장됐다는 보장이 없어서(관찰됨: 클릭은 성공했지만
    글 목록엔 아무것도 안 생긴 경우), 반드시 '글 관리' 목록에서 방금 쓴 제목이 실제로
    보이는지 확인한다. 또한 발행 직후 page.url은 새 글쓰기 화면으로 리셋되는 경우가 많아
    실제 게시글 주소가 아니므로, 목록의 제목 링크 자체의 href 속성에서 진짜 URL을 읽는다
    (클릭해서 새 탭이 뜨길 기다리는 방식은 타이밍에 따라 실패할 수 있어 더 안정적인
    이 방식으로 바꿨다). 못 찾으면 None."""
    posts_url = f"https://{blog_name}.tistory.com/manage/posts/"
    needle = title[:20]
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            page.goto(posts_url)
            page.wait_for_load_state("networkidle", timeout=10_000)
            link = page.get_by_role("link", name=needle, exact=False).first
            if link.is_visible(timeout=2_000):
                href = link.get_attribute("href")
                if href:
                    return href
        except Exception:  # noqa: BLE001
            pass
        time.sleep(2)
    return None


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
