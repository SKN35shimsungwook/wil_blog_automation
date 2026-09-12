"""Gemini API를 호출해서 공부 메모를 주간회고(WIL) 마크다운으로 변환한다."""
import json
import re

from google import genai
from google.genai import types

WIL_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "title_suggestions": types.Schema(
            type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
        ),
        "tags": types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        "one_line_summary": types.Schema(type=types.Type.STRING),
        "markdown_body": types.Schema(type=types.Type.STRING),
    },
    required=["title_suggestions", "tags", "one_line_summary", "markdown_body"],
)

COMPREHENSION_RESPONSE_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "questions": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "type": types.Schema(type=types.Type.STRING),
                    "question": types.Schema(type=types.Type.STRING),
                    "options": types.Schema(
                        type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)
                    ),
                },
                required=["type", "question"],
            ),
        ),
        "reflection_options": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        ),
    },
    required=["questions", "reflection_options"],
)

SYSTEM_PROMPT = """너는 개발 부트캠프생의 주간회고(WIL, Weekly I Learned)를 대신 작성해주는 전문 테크 블로그 에디터다.
아래 두 가지 기준을 반드시 지켜서 글을 써야 한다.

[플레이데이터 주간회고 가이드]
- 목적: 지난 일주일을 되돌아보며 현재 상태를 파악하고, 다음 주를 더 잘 보내기 위한 도구로 쓴다.
- Four Fs(FACTS/FEELINGS/FINDINGS/FUTURE)와 KPT(Keep/Problem/Try)를 함께 담는다.
- 내용 구성은 일기가 아니라 트러블슈팅 중심으로: 문제 -> 원인 -> 해결 -> 배운 점 흐름을 구체적으로.
- 수려한 문장보다 솔직하고 담백한 글이 낫다.
- 글의 마지막은 스스로를 응원하는 한마디로 마무리한다.

[문체 — 반드시 지킬 것]
"~습니다/~했습니다" 같은 정중체를 절대 쓰지 않는다. 개인 일기/블로그처럼 "~했다/~였다/~한다/~배웠다" 같은
평서형 종결어미(다나까체 아님, 일반 반말 서술체)로 통일한다. 예: "익혔다", "이해했다", "헷갈렸다", "깨달았다".

[우수 회고 2편을 분석해서 뽑아낸 공통 원칙 — 반드시 반영할 것]
1. 단순 "무엇을 배웠다" 나열이 아니라 "배운 것 -> 어려웠던 점 -> 어떻게 해결했는가 -> 무엇을 깨달았는가"의 흐름으로 이어지게 쓴다.
2. 기술 설명과 감정/생각을 함께 녹인다. ("처음엔 ~라고 생각했는데, 실제로 해보니 ~였다" 같은 문장을 자연스럽게 섞는다.)
3. API/라이브러리 이름만 나열하지 말고, 그것을 사용하며 겪은 경험을 서술한다. (예: "select()와 find()의 차이를 직접 크롤링하며 이해했다")
4. 분량 배분: 트러블슈팅 섹션이 가장 길고 구체적이어야 한다. (왜 안됐는지 -> 무슨 에러였는지 -> 원인 -> 해결 -> 다음엔 어떻게 할지)
5. 메모에 에러 메시지나 키워드만 짧게 적혀 있어도, 흔히 발생하는 원인과 해결 흐름을 합리적으로 추론해서 "문제/원인/해결/배운 점" 형태로 자연스럽게 재구성한다. 단, 지어낸 사실을 단정적으로 서술하지 말고 메모에 있는 내용에 근거해서만 작성한다.

[성찰 질문 답변 활용 규칙]
사용자 메시지에 "성찰 질문 답변"이 포함되어 있으면, 그건 사용자가 직접 답한 5개의 고정 질문(인상 깊은 배움 / 어려움 / 깨달음·감정 / 현재 상태 / 다음 주 계획)이다.
- 감정/생각/느낀 점에 해당하는 부분(Feelings, "이번 주 깨달음"의 정서적 측면, "나에게 하는 응원")은 반드시 이 답변을 우선 근거로 삼아 작성한다. 답변이 없으면 공부 메모 톤에서 조심스럽게 유추한다.
- "다음 주 목표"는 성찰 질문 답변의 "다음 주 계획" 항목이 있으면 그것을 우선 반영하고, 부족하면 공부 메모 기반으로 보충한다.
- 기술적 사실(Facts, 트러블슈팅)은 어디까지나 공부 메모 기반으로 작성하고, 성찰 답변의 감정적 표현을 기술 설명에 섞지 않는다.

[첨부된 코드 파일 활용 규칙]
사용자 메시지에 "첨부된 코드 파일"이 포함되어 있으면(.py/.ipynb에서 추출한 실제 코드):
- "이번 주 학습"이나 "트러블슈팅" 섹션에서 관련 있는 부분은 반드시 파일에 있는 코드를 그대로 발췌해서 마크다운 코드펜스(```python ... ```)로 인용한다. 코드를 요약하지 말고, 짧고 핵심적인 부분만 골라 그대로 옮긴다.
- 코드를 지어내거나 변형하지 말 것. 첨부된 코드에 없는 내용은 인용하지 않는다.
- 어느 파일의 어떤 부분인지 알 수 있게 코드 앞에 짧게 맥락을 설명하는 문장을 붙인다.

[출력 형식]
반드시 아래 JSON 스키마 하나만 출력한다. 코드펜스나 설명 문구 없이 순수 JSON 텍스트만 출력할 것.
{
  "title_suggestions": ["제목 후보 5개, 예: [플레이데이터] 로 시작하거나 구체적 키워드+숫자 포함"],
  "tags": ["기술 태그들, 5~10개, 예: Python, Selenium"],
  "one_line_summary": "이번 주를 한 문장으로 요약",
  "markdown_body": "아래 구조를 그대로 따르는 마크다운 문자열. 최상위 제목(H1)은 포함하지 말고 '## 한 줄 요약' 부터 시작한다.\\n\\n## 한 줄 요약\\n...\\n\\n## 이번 주 학습\\n(기술 스택별 경험 서술, 목록+짧은 문단)\\n\\n## 가장 어려웠던 문제 (트러블슈팅)\\n### 문제 1: ...\\n**문제**\\n**원인**\\n**해결**\\n**배운 점**\\n(메모에 에러/문제가 여러 개면 문제 2, 3 반복)\\n\\n## 이번 주 깨달음\\n(Findings, 실무/앞으로에 어떤 의미인지)\\n\\n## KPT\\n### Keep\\n### Problem\\n### Try\\n\\n## 성장 인사이트\\n(과거 회고 요약이 주어졌다면 그것과 비교, 없으면 이번 주 학습 습관에 대한 짧은 관찰)\\n\\n## 다음 주 목표\\n(3개, 체크리스트 형태)\\n\\n## 나에게 하는 응원\\n(진심이 담긴 응원 한두 문장)"
}
"""

PROJECT_WEEK_ADDENDUM = """
[중요 — 이번 주는 프로젝트 주간이다]
사용자 메시지에 "이번 주는 프로젝트 주간입니다"라고 표시되어 있으면, 일반 수업 회고보다 더 비중 있게 다뤄야 한다.
단순히 그 주에 배운 기술을 나열하는 게 아니라, 실제로 무언가를 만든 과정을 회고하는 글이어야 한다.
markdown_body는 위에서 설명한 구조 대신 아래 구조를 따른다 (역시 '## 한 줄 요약'부터 시작, 최상위 제목 없음):

## 한 줄 요약
...

## 프로젝트 개요
(무엇을 만들었는지, 목표가 무엇이었는지 — 메모에 있는 내용 기반)

## 내가 맡은 역할과 기여
사용자 메시지에 "내 역할"이 주어지면 반드시 그 내용을 그대로 근거로 삼아 구체적으로 서술한다(지어내거나
과장하지 않는다). 주어지지 않았으면 메모 내용에서 합리적으로 유추해서 작성한다.
(팀 프로젝트면 담당 파트, 개인 프로젝트면 무엇을 직접 설계/구현했는지)

## 기술적 도전과 해결 과정 (트러블슈팅)
### 문제 1: ...
**문제** / **원인** / **해결** / **배운 점**
(프로젝트는 난이도가 높은 만큼, 이 섹션이 평소 회고보다 더 길고 구체적이어야 한다. 문제가 여러 개면 다 담아라.)

## 협업/과정에서 배운 점
(있다면 협업 경험, 없으면 프로젝트를 진행하며 스스로 배운 작업 방식/태도)

## 🚀 프로젝트 산출물 소개
사용자 메시지에 "프로젝트 산출물 정보"가 주어지면 이걸 근거로, 마치 포트폴리오에 프로젝트를 소개하듯
자신감 있고 매력적으로 써라 (과장 금지, 있는 사실을 잘 보여주는 톤). 다음을 포함한다:
- 무엇을 만들었는지 한 줄 소개(엘리베이터 피치처럼)
- 주요 기능/특징 (README 내용이 주어졌으면 그걸 근거로 정리)
- GitHub 저장소 링크가 주어졌으면 마크다운 링크로 반드시 포함: [GitHub 저장소](주소)
- 산출물 정보가 없으면 이 섹션은 짧게 "이번 프로젝트는 아직 공개 저장소가 없다" 정도로만 적고 넘어간다.
(첨부된 이미지가 있다면 별도로 본문에 자동 삽입되니, 이 섹션에 이미지 캡션처럼 "아래는 실행 화면입니다" 같은 짧은 안내 문장만 자연스럽게 넣어도 좋다.)

## 아쉬운 점과 개선하고 싶은 부분
(시간이 더 있었다면 무엇을 더 하고 싶었는지)

## 이번 프로젝트를 통한 성장
(이 프로젝트 전후로 나의 실력/자신감이 어떻게 달라졌는지 — 성찰 질문 답변을 우선 근거로)

## 다음 주 목표
(3개, 체크리스트 형태)

## 나에게 하는 응원
(프로젝트를 마친 스스로에게, 조금 더 힘주어 응원)
"""

USER_PROMPT_TEMPLATE = """다음은 이번 주 공부 메모다. 이 내용만 근거로 주간회고를 작성해라.

[이번 주 공부 메모]
{notes}

[참고: 이번 주 커리큘럼상 예정된 주제 (참고용, 메모에 없는 내용을 지어내지 말 것)]
{curriculum_topic}

[성찰 질문 답변 (없으면 "(작성 안 함)")]
{reflection_answers}

[첨부된 코드 파일 (없으면 "(첨부 없음)")]
{code_context}

[프로젝트 산출물 정보 (프로젝트 주간에만 의미 있음, 없으면 "(정보 없음)")]
{project_info}

[과거 회고 요약 (최근 순, 없으면 빈 목록)]
{history_summary}
{project_marker}
{extra_instruction}
"""


def _extract_json(text: str) -> dict:
    text = text.strip()
    fence_match = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fence_match:
        text = fence_match.group(1)
    else:
        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            text = brace_match.group(0)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # LLM이 문자열 안에 이스케이프 없이 개행을 넣는 경우가 있어 완화 모드로 재시도.
        return json.loads(text, strict=False)


def _raise_if_truncated(response):
    """max_output_tokens에 걸려 응답이 중간에 잘리면 JSON 파싱 에러 대신
    명확한 이유를 알려준다."""
    finish_reason = None
    if response.candidates:
        finish_reason = getattr(response.candidates[0], "finish_reason", None)
    if finish_reason is not None and str(finish_reason).endswith("MAX_TOKENS"):
        raise ValueError(
            "AI 응답이 출력 길이 제한에 걸려 중간에 잘렸습니다. 다시 시도해주세요."
        )


def build_history_summary(history: list, max_weeks: int = 4, current_week: int = None) -> str:
    """과거 회고 요약을 만든다. current_week가 주어지면 그보다 주차 번호가 작은
    회고만(시간상 진짜 '과거'인 것만) 사용한다. 이게 없으면, 같은 주차를 재생성했거나
    나중 주차를 먼저 테스트로 만든 경우까지 '지난주'로 착각해서 없는 이야기를 지어낼 수 있다."""
    relevant = history
    if current_week is not None:
        relevant = [
            h for h in history if isinstance(h.get("week"), int) and h["week"] < current_week
        ]
        relevant = sorted(relevant, key=lambda h: h["week"])
    if not relevant:
        return "(과거 회고 없음, 이번이 첫 회고)"
    lines = []
    for entry in relevant[-max_weeks:]:
        tags = ", ".join(entry.get("tags", []))
        label = f"{entry['week']}주차" if isinstance(entry.get("week"), int) else entry.get("date", "?")
        lines.append(f"- {label}: {entry.get('one_line_summary', '')} (태그: {tags})")
    return "\n".join(lines)


def generate_wil(
    api_key: str,
    model: str,
    notes: str,
    history: list,
    regenerate: bool = False,
    curriculum_topic: str = "",
    reflection_answers: str = "",
    code_context: str = "",
    current_week: int = None,
    is_project_week: bool = False,
    github_url: str = "",
    deliverable_notes: str = "",
    my_role: str = "",
) -> dict:
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다. 설정 메뉴에서 입력해주세요.")
    if not notes.strip():
        raise ValueError("공부 메모가 비어있습니다.")

    client = genai.Client(api_key=api_key)
    history_summary = build_history_summary(history, current_week=current_week)
    extra_instruction = (
        "\n[지시] 이전 생성 결과와는 다른 표현과 구성으로, 새로운 관점에서 다시 작성해줘."
        if regenerate
        else ""
    )
    project_info_parts = []
    if my_role.strip():
        project_info_parts.append(f"내 역할: {my_role.strip()}")
    if github_url.strip():
        project_info_parts.append(f"GitHub 저장소: {github_url.strip()}")
    if deliverable_notes.strip():
        project_info_parts.append(f"산출물 소개/README:\n{deliverable_notes.strip()}")
    project_info = "\n\n".join(project_info_parts) or "(정보 없음)"

    user_prompt = USER_PROMPT_TEMPLATE.format(
        notes=notes.strip(),
        history_summary=history_summary,
        extra_instruction=extra_instruction,
        curriculum_topic=curriculum_topic or "(정보 없음)",
        reflection_answers=reflection_answers.strip() or "(작성 안 함)",
        code_context=code_context.strip() or "(첨부 없음)",
        project_marker="[이번 주는 프로젝트 주간입니다]" if is_project_week else "",
        project_info=project_info,
    )
    system_instruction = SYSTEM_PROMPT + (PROJECT_WEEK_ADDENDUM if is_project_week else "")

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=system_instruction,
            response_mime_type="application/json",
            response_schema=WIL_RESPONSE_SCHEMA,
            max_output_tokens=8192,
        ),
    )

    raw_text = response.text or ""
    _raise_if_truncated(response)

    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"AI 응답을 JSON으로 해석하지 못했습니다: {exc}\n\n원본 응답:\n{raw_text}") from exc

    for key in ("title_suggestions", "tags", "one_line_summary", "markdown_body"):
        if key not in data:
            raise ValueError(f"AI 응답에 '{key}' 항목이 없습니다.\n\n원본 응답:\n{raw_text}")

    return data


MERGE_SYSTEM_PROMPT = """너는 개발 부트캠프생의 주간회고(WIL)를 편집하는 전문 테크 블로그 에디터다.
같은 주에 대해 따로 작성된 초안 두 개가 주어진다:
1. 프로젝트 회고 초안 (그 주에 진행한 프로젝트에 대한 회고)
2. 수업 내용 회고 초안 (같은 주에 별도로 진행된 일반 수업 내용에 대한 회고)

이 둘을 절대 단순히 이어붙이거나 "프로젝트는 이랬고, 수업은 이랬다" 식으로 나열하지 마라.
프로젝트 회고 초안의 구조(개요/역할/트러블슈팅/협업/산출물 소개/아쉬운 점/성장/다음 주 목표/응원)를
전체 글의 기본 뼈대로 삼되, 수업 내용 회고 초안에 있는 학습/트러블슈팅을 흐름이 자연스러운 위치에
녹여 넣어서 "이 주에 실제로 있었던 일"이 하나의 이야기로 읽히게 재구성해라.
예를 들어 수업에서 배운 개념이 프로젝트에 실제로 도움이 됐다면 그 연결을 짚어주고, 관련 없으면
"이번 주 학습" 같은 섹션을 하나 추가해서 자연스럽게 포함시켜라(단, 뼈대 자체가 산산조각 나지 않게).

[반드시 지킬 것]
- 두 초안에 이미 쓰여 있는 사실만 사용한다. 새로운 사실을 지어내지 않는다.
- "~습니다" 금지. "~했다/~였다/~한다/~배웠다" 같은 평서형 서술체를 유지한다.
- 두 초안에서 겹치거나 비슷한 내용은 한 번만 자연스럽게 정리해서 쓰고, 중복해서 나열하지 않는다.
- 최상위 제목(H1)은 포함하지 말고 '## 한 줄 요약'부터 시작한다.
- 코드 인용이 두 초안에 각각 있다면 그대로 유지해도 되지만, 같은 코드를 두 번 반복해서 인용하지 않는다.

[출력 형식]
반드시 아래 JSON 스키마 하나만 출력한다. 코드펜스나 설명 문구 없이 순수 JSON만.
{
  "title_suggestions": ["제목 후보 5개"],
  "tags": ["기술 태그들, 프로젝트+수업 내용을 합쳐 5~10개"],
  "one_line_summary": "이번 주(프로젝트+수업)를 한 문장으로 요약",
  "markdown_body": "위에서 설명한 대로 하나로 자연스럽게 합쳐진 최종 마크다운 본문"
}
"""

MERGE_USER_PROMPT_TEMPLATE = """다음 두 초안을 하나의 자연스러운 주간회고로 합쳐라.

[프로젝트 회고 초안]
{project_markdown}

[수업 내용 회고 초안]
{class_markdown}
"""


def merge_project_and_class_reviews(
    api_key: str, model: str, project_markdown: str, class_markdown: str
) -> dict:
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    user_prompt = MERGE_USER_PROMPT_TEMPLATE.format(
        project_markdown=project_markdown.strip(),
        class_markdown=class_markdown.strip(),
    )
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=MERGE_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=WIL_RESPONSE_SCHEMA,
            max_output_tokens=8192,
        ),
    )
    raw_text = response.text or ""
    _raise_if_truncated(response)
    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"합치기 응답을 JSON으로 해석하지 못했습니다: {exc}\n\n원본 응답:\n{raw_text}") from exc

    for key in ("title_suggestions", "tags", "one_line_summary", "markdown_body"):
        if key not in data:
            raise ValueError(f"합치기 응답에 '{key}' 항목이 없습니다.\n\n원본 응답:\n{raw_text}")

    return data


COMPREHENSION_SYSTEM_PROMPT = """너는 개발 부트캠프 튜터다. 학생이 첨부한 코드 파일(.py/.ipynb에서 추출)을 보고 두 가지를 만든다.

[1. 이해도 확인 질문]
- 질문은 총 5~6개: 객관식(4지선다) 위주로 4~5개, 짧은 서술형 1~2개를 섞는다.
- 코드에 실제로 등장하는 구체적인 함수/라이브러리/문법/패턴을 근거로 질문을 만들어라. 일반적이고 뻔한 질문 금지.
- 객관식의 오답도 그럴듯하게(헷갈릴 만하게) 만들어라. 정답은 명시하지 않는다(채점 목적이 아니라 회고 작성용 자료 수집이 목적).

[2. 성찰 질문 빠른 선택지]
사용자 메시지에 고정된 성찰 질문 5개가 주어진다. 각 질문마다, 이 코드/주차 내용을 참고했을 때
있을 법한 답변 3개를 추측해서 만들어라(사용자가 타이핑 없이 빠르게 고를 수 있도록 하는 용도).
- 코드에서 유추할 수 있는 구체적인 내용으로 만들어라(막연한 뻔한 답 금지).
- 5개 질문 순서와 정확히 같은 순서로, 질문당 3개씩 담는다.

반드시 아래 JSON 스키마 하나만 출력한다. 코드펜스나 설명 문구 없이 순수 JSON만.
{
  "questions": [
    {"type": "mc", "question": "...", "options": ["...", "...", "...", "..."]},
    {"type": "short", "question": "..."}
  ],
  "reflection_options": [
    ["...", "...", "..."],
    ["...", "...", "..."],
    ["...", "...", "..."],
    ["...", "...", "..."],
    ["...", "...", "..."]
  ]
}
"""


def generate_comprehension_questions(
    api_key: str, model: str, code_context: str, reflection_questions: list
) -> dict:
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")
    if not code_context.strip():
        raise ValueError("첨부된 코드 파일이 없습니다. 먼저 '코드 파일' 탭에서 파일을 첨부해주세요.")

    reflection_list = "\n".join(f"{i+1}. {q}" for i, q in enumerate(reflection_questions))
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=(
            f"[첨부된 코드 파일]\n{code_context}\n\n"
            f"[고정 성찰 질문 5개 (이 순서대로 reflection_options를 만들 것)]\n{reflection_list}"
        ),
        config=types.GenerateContentConfig(
            system_instruction=COMPREHENSION_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=COMPREHENSION_RESPONSE_SCHEMA,
            max_output_tokens=8192,
        ),
    )
    raw_text = response.text or ""
    _raise_if_truncated(response)
    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"질문 생성 응답을 해석하지 못했습니다: {exc}\n\n원본 응답:\n{raw_text}") from exc

    questions = data.get("questions", [])
    if not questions:
        raise ValueError(f"AI가 질문을 만들지 못했습니다.\n\n원본 응답:\n{raw_text}")
    return {
        "questions": questions,
        "reflection_options": data.get("reflection_options", []),
    }


NOTES_DRAFT_SYSTEM_PROMPT = """너는 개발 부트캠프생을 대신해 '이번 주 공부 메모' 초안을 작성하는 도우미다.
첨부된 코드 파일과, 학생이 이해도 확인 질문에 답한 내용을 근거로 자유 형식의 공부 메모를 작성한다.

- 실제로 다룬 기술/함수/코드를 구체적으로 언급한다. 코드에 없는 내용을 지어내지 않는다.
- 답변에서 학생이 헷갈려했거나 확신 없어 보이는 부분이 있으면, 트러블슈팅 후보로 짧게 남긴다.
  (예: "- WebDriverWait와 sleep의 차이가 헷갈림" 처럼)
- 문체는 개조식(짧은 메모체, 줄글 아님). 이 메모는 나중에 다른 AI가 읽고 정식 회고를 작성하는 데 쓰인다.
- 순수 텍스트만 출력한다. JSON도, 마크다운 코드펜스도 쓰지 않는다.
"""


def draft_study_notes(api_key: str, model: str, code_context: str, qa_pairs: list) -> str:
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")

    client = genai.Client(api_key=api_key)
    qa_text = "\n\n".join(
        f"Q: {q}\nA: {a}" for q, a in qa_pairs if a and a.strip()
    ) or "(답변 없음)"
    prompt = f"[첨부된 코드 파일]\n{code_context or '(첨부 없음)'}\n\n[이해도 확인 질문과 답변]\n{qa_text}"

    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=types.GenerateContentConfig(
            system_instruction=NOTES_DRAFT_SYSTEM_PROMPT,
            max_output_tokens=4096,
        ),
    )
    _raise_if_truncated(response)
    return (response.text or "").strip()


MONTHLY_OPTIONS_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "reflection_options": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.ARRAY, items=types.Schema(type=types.Type.STRING)),
        ),
    },
    required=["reflection_options"],
)

MONTHLY_OPTIONS_SYSTEM_PROMPT = """너는 개발 부트캠프 튜터다. 학생의 한 달치 주간회고 요약 목록을 보고,
월간 종합회고를 위한 고정 질문들에 대해 있을 법한 빠른 선택지를 만든다.
- 질문 순서와 정확히 같은 순서로, 질문당 3개씩 담는다.
- 한 달 동안의 태그/요약에서 실제로 드러나는 경향(자주 나온 기술, 반복된 어려움 등)을 근거로 구체적으로 만들어라.
- 반드시 JSON만 출력: {"reflection_options": [["...","...","..."], ...]}
"""


def generate_monthly_reflection_options(
    api_key: str, model: str, week_summaries: str, monthly_questions: list
) -> list:
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")
    if not week_summaries.strip():
        raise ValueError("이번 달에 저장된 회고가 없습니다.")

    question_list = "\n".join(f"{i+1}. {q}" for i, q in enumerate(monthly_questions))
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=f"[이번 달 주간회고 요약]\n{week_summaries}\n\n[고정 질문]\n{question_list}",
        config=types.GenerateContentConfig(
            system_instruction=MONTHLY_OPTIONS_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=MONTHLY_OPTIONS_SCHEMA,
            max_output_tokens=4096,
        ),
    )
    raw_text = response.text or ""
    _raise_if_truncated(response)
    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"선택지 생성 응답을 해석하지 못했습니다: {exc}") from exc
    return data.get("reflection_options", [])


MONTHLY_SYSTEM_PROMPT = """너는 개발 부트캠프생의 월간 종합회고를 대신 작성해주는 전문 테크 블로그 에디터다.
이건 매주 쓰는 주간회고(WIL)와 다르다 — 이미 발행된 그 달의 주간회고 여러 개를 하나로 묶어서
"이번 달 전체를 돌아보는" 요약/종합 글을 쓰는 것이다.

[반드시 지킬 것]
- "~습니다" 금지. "~했다/~였다/~한다/~배웠다" 같은 평서형 서술체로 통일한다.
- 각 주차 글의 링크를 반드시 마크다운 링크로 포함한다 (예: [1회차 - 제목](url)). 링크 목록을 빠뜨리지 마라.
- 단순히 각 주의 요약을 나열하지 말고, 한 달 전체를 관통하는 성장 흐름/변화를 짚어라
  (예: "1회차엔 환경설정도 헤맸는데, 4회차 프로젝트에선 스스로 에러를 해결해냈다" 같은 비교).
- 이번 달 가장 많이 나온 기술/키워드, 가장 기억에 남는 트러블슈팅 하나를 짧게 하이라이트한다.
- 성찰(월간 질문 답변)이 있으면 감정/평가 부분에 그걸 우선 반영한다.

[출력 형식]
반드시 아래 JSON 스키마 하나만 출력한다. 코드펜스나 설명 문구 없이 순수 JSON만.
{
  "title_suggestions": ["제목 후보 5개, 예: [캠프명] N월 종합회고"],
  "tags": ["기술 태그들, 5~10개"],
  "one_line_summary": "이번 달을 한 문장으로 요약",
  "markdown_body": "'## 한 줄 요약'부터 시작(최상위 제목 없음).\\n\\n## 한 줄 요약\\n...\\n\\n## 이번 달 회고 목록\\n(각 주차 링크를 마크다운 목록으로)\\n\\n## 이번 달 배운 것 종합\\n(주차별 나열이 아니라 흐름으로 묶어서)\\n\\n## 가장 기억에 남는 트러블슈팅\\n(그 달 전체에서 하나 골라 문제/원인/해결/배운점)\\n\\n## 성장 곡선\\n(월초 대비 월말에 달라진 점, 있으면 성찰 답변 근거)\\n\\n## 이번 달 KPT\\n### Keep\\n### Problem\\n### Try\\n\\n## 다음 달 목표\\n(3개, 체크리스트)\\n\\n## 나에게 하는 응원\\n"
}
"""

MONTHLY_USER_PROMPT_TEMPLATE = """다음은 이번 달에 발행된 주간회고들의 요약이다. 이 내용을 근거로 월간 종합회고를 써라.

[이번 달 주간회고 목록 (회차/제목/링크/태그/요약)]
{week_summaries}

[월간 성찰 질문 답변 (없으면 "(작성 안 함)")]
{reflection_answers}
"""


def generate_monthly_review(
    api_key: str,
    model: str,
    week_summaries: str,
    reflection_answers: str = "",
) -> dict:
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다.")
    if not week_summaries.strip():
        raise ValueError("이번 달에 저장된 회고가 없습니다.")

    client = genai.Client(api_key=api_key)
    user_prompt = MONTHLY_USER_PROMPT_TEMPLATE.format(
        week_summaries=week_summaries.strip(),
        reflection_answers=reflection_answers.strip() or "(작성 안 함)",
    )
    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=MONTHLY_SYSTEM_PROMPT,
            response_mime_type="application/json",
            response_schema=WIL_RESPONSE_SCHEMA,
            max_output_tokens=8192,
        ),
    )
    raw_text = response.text or ""
    _raise_if_truncated(response)
    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"AI 응답을 JSON으로 해석하지 못했습니다: {exc}\n\n원본 응답:\n{raw_text}") from exc

    for key in ("title_suggestions", "tags", "one_line_summary", "markdown_body"):
        if key not in data:
            raise ValueError(f"AI 응답에 '{key}' 항목이 없습니다.\n\n원본 응답:\n{raw_text}")
    return data
