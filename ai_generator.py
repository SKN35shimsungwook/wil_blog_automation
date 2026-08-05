"""Gemini API를 호출해서 공부 메모를 주간회고(WIL) 마크다운으로 변환한다."""
import json
import re

from google import genai
from google.genai import types

SYSTEM_PROMPT = """너는 개발 부트캠프생의 주간회고(WIL, Weekly I Learned)를 대신 작성해주는 전문 테크 블로그 에디터다.
아래 두 가지 기준을 반드시 지켜서 글을 써야 한다.

[플레이데이터 주간회고 가이드]
- 목적: 지난 일주일을 되돌아보며 현재 상태를 파악하고, 다음 주를 더 잘 보내기 위한 도구로 쓴다.
- Four Fs(FACTS/FEELINGS/FINDINGS/FUTURE)와 KPT(Keep/Problem/Try)를 함께 담는다.
- 일기가 아니라 트러블슈팅 중심으로 쓴다: 문제 -> 원인 -> 해결 -> 배운 점 흐름을 구체적으로.
- 수려한 문장보다 솔직하고 담백한 글이 낫다.
- 글의 마지막은 스스로를 응원하는 한마디로 마무리한다.

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

[출력 형식]
반드시 아래 JSON 스키마 하나만 출력한다. 코드펜스나 설명 문구 없이 순수 JSON 텍스트만 출력할 것.
{
  "title_suggestions": ["제목 후보 5개, 예: [플레이데이터] 로 시작하거나 구체적 키워드+숫자 포함"],
  "tags": ["기술 태그들, 5~10개, 예: Python, Selenium"],
  "one_line_summary": "이번 주를 한 문장으로 요약",
  "markdown_body": "아래 구조를 그대로 따르는 마크다운 문자열. 최상위 제목(H1)은 포함하지 말고 '## 한 줄 요약' 부터 시작한다.\\n\\n## 한 줄 요약\\n...\\n\\n## 이번 주 학습\\n(기술 스택별 경험 서술, 목록+짧은 문단)\\n\\n## 가장 어려웠던 문제 (트러블슈팅)\\n### 문제 1: ...\\n**문제**\\n**원인**\\n**해결**\\n**배운 점**\\n(메모에 에러/문제가 여러 개면 문제 2, 3 반복)\\n\\n## 이번 주 깨달음\\n(Findings, 실무/앞으로에 어떤 의미인지)\\n\\n## KPT\\n### Keep\\n### Problem\\n### Try\\n\\n## 성장 인사이트\\n(과거 회고 요약이 주어졌다면 그것과 비교, 없으면 이번 주 학습 습관에 대한 짧은 관찰)\\n\\n## 다음 주 목표\\n(3개, 체크리스트 형태)\\n\\n## 나에게 하는 응원\\n(진심이 담긴 응원 한두 문장)"
}
"""

USER_PROMPT_TEMPLATE = """다음은 이번 주 공부 메모다. 이 내용만 근거로 주간회고를 작성해라.

[이번 주 공부 메모]
{notes}

[참고: 이번 주 커리큘럼상 예정된 주제 (참고용, 메모에 없는 내용을 지어내지 말 것)]
{curriculum_topic}

[성찰 질문 답변 (없으면 "(작성 안 함)")]
{reflection_answers}

[과거 회고 요약 (최근 순, 없으면 빈 목록)]
{history_summary}
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


def build_history_summary(history: list, max_weeks: int = 4) -> str:
    if not history:
        return "(과거 회고 없음, 이번이 첫 회고)"
    lines = []
    for entry in history[-max_weeks:]:
        tags = ", ".join(entry.get("tags", []))
        lines.append(
            f"- {entry.get('date', '?')}: {entry.get('one_line_summary', '')} (태그: {tags})"
        )
    return "\n".join(lines)


def generate_wil(
    api_key: str,
    model: str,
    notes: str,
    history: list,
    regenerate: bool = False,
    curriculum_topic: str = "",
    reflection_answers: str = "",
) -> dict:
    if not api_key:
        raise ValueError("Gemini API 키가 설정되지 않았습니다. 설정 메뉴에서 입력해주세요.")
    if not notes.strip():
        raise ValueError("공부 메모가 비어있습니다.")

    client = genai.Client(api_key=api_key)
    history_summary = build_history_summary(history)
    extra_instruction = (
        "\n[지시] 이전 생성 결과와는 다른 표현과 구성으로, 새로운 관점에서 다시 작성해줘."
        if regenerate
        else ""
    )
    user_prompt = USER_PROMPT_TEMPLATE.format(
        notes=notes.strip(),
        history_summary=history_summary,
        extra_instruction=extra_instruction,
        curriculum_topic=curriculum_topic or "(정보 없음)",
        reflection_answers=reflection_answers.strip() or "(작성 안 함)",
    )

    response = client.models.generate_content(
        model=model,
        contents=user_prompt,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            response_mime_type="application/json",
            max_output_tokens=4000,
        ),
    )

    raw_text = response.text or ""

    try:
        data = _extract_json(raw_text)
    except (json.JSONDecodeError, AttributeError) as exc:
        raise ValueError(f"AI 응답을 JSON으로 해석하지 못했습니다: {exc}\n\n원본 응답:\n{raw_text}") from exc

    for key in ("title_suggestions", "tags", "one_line_summary", "markdown_body"):
        if key not in data:
            raise ValueError(f"AI 응답에 '{key}' 항목이 없습니다.\n\n원본 응답:\n{raw_text}")

    return data
