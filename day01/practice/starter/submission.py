"""Day 1 — 운영 알람 트리아지 체인.

알람 하나를 넣으면 구조화된 분류 결과와 담당팀 안내 초안을 동시에 만듭니다.

[중요] 이 파일의 규칙
  1. 함수 이름과 인자를 바꾸지 마세요. 채점기가 이 이름으로 찾습니다.
  2. 모델은 반드시 함수 **안에서** 만듭니다. 모듈 최상단에서 만들면
     채점기가 가짜 모델을 넣을 수 없어 채점이 실패합니다.
  3. `llm` 인자가 들어오면 그것을 쓰고, None이면 직접 만듭니다.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field

# 과정 전체에서 고정으로 쓰는 값입니다. 바꾸지 마세요.
MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = "us-east-1"

# 알람 본문이 지나치게 길면 프롬프트에 넣기 전에 잘라냅니다.
MAX_ALERT_CHARS = 2000


def _default_llm():
    """기본 모델을 만듭니다. 채점기는 이 함수를 부르지 않습니다.

    import를 함수 안에 둔 이유: 모듈을 불러오는 것만으로 AWS 자격증명을
    요구하지 않게 하기 위해서입니다.
    """
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model=MODEL_ID, region_name=REGION, temperature=0)


def get_text(message: Any) -> str:
    """ChatBedrockConverse는 content를 블록 리스트로 주기도 하므로 텍스트만 모아 반환합니다."""
    content = message.content if hasattr(message, "content") else message
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content)


def _alert_text(alert: Any) -> str:
    """알람 dict를 프롬프트에 넣을 문자열로 만듭니다.

    키가 빠져 있거나, 값에 중첩 dict·이모지·특수문자가 섞여 있거나,
    본문이 수천 자로 길어도 여기서 한 번 정리하고 넘깁니다.
    """
    if not isinstance(alert, dict):
        text = str(alert)
    else:
        try:
            text = json.dumps(alert, ensure_ascii=False, default=str, indent=2)
        except (TypeError, ValueError):
            text = str(alert)
    if len(text) > MAX_ALERT_CHARS:
        text = text[:MAX_ALERT_CHARS] + "\n... (이하 생략)"
    return text


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════

class TriageResult(BaseModel):
    """운영 알람 분류 결과입니다."""

    severity: Literal["P1", "P2", "P3", "P4"] = Field(
        ...,
        description=(
            "장애 등급. "
            "P1=결제·인증처럼 매출과 직결된 기능이 이미 실패하고 있음(즉시 소집). "
            "P2=핵심 서비스가 성능 저하·부분 실패 상태이며 곧 P1로 번질 수 있음(당직자 즉시 착수). "
            "P3=단일 인스턴스나 비핵심 배치 문제로 고객 영향이 아직 없음(업무시간 내 처리). "
            "P4=정보성 알람이거나 이미 자동 복구된 건(기록만 남김)."
        ),
    )
    service: str = Field(
        ...,
        description="영향을 받은 서비스 이름. 알람의 service 값을 그대로 쓰고, 값이 없으면 unknown 으로 적습니다.",
    )
    category: Literal[
        "availability",
        "performance",
        "error_rate",
        "capacity",
        "security",
        "data",
        "unknown",
    ] = Field(
        ...,
        description=(
            "증상 분류. availability=요청 자체가 실패하거나 무응답, performance=지연·타임아웃, "
            "error_rate=5xx 등 오류 비율 상승, capacity=CPU·메모리·디스크·커넥션 고갈, "
            "security=인증 실패 폭증이나 비정상 접근, data=정합성·유실 의심. "
            "판단 근거가 부족하면 unknown 을 씁니다."
        ),
    )
    owner_team: str = Field(
        ...,
        description=(
            "1차로 확인해야 할 담당팀. 서비스 이름에서 추정합니다. "
            "예를 들어 payment-api 는 결제플랫폼팀, auth 계열은 인증팀, "
            "자원 고갈로 보이면 인프라운영팀입니다. 모르겠으면 운영센터 당직으로 둡니다."
        ),
    )
    first_check: str = Field(
        ...,
        description="당직자가 가장 먼저 확인할 항목 한 가지를 명령형 한 문장으로 적습니다. 예: 최근 30분 내 배포 이력을 확인한다.",
    )
    summary: str = Field(
        ...,
        description="무슨 일이 일어났는지 한 문장으로 요약합니다. 알람 원문을 그대로 옮기지 말고 사람이 읽을 문장으로 씁니다.",
    )


TRIAGE_SCHEMA = TriageResult

# severity 등급의 높낮이 비교용입니다. 숫자가 작을수록 급합니다.
SEVERITY_ORDER = {"P1": 1, "P2": 2, "P3": 3, "P4": 4}

# 분류에 실패했을 때 돌려줄 안전한 기본값입니다.
# 모델 출력을 못 읽었다는 것은 판단이 없다는 뜻이므로 사람이 반드시 보도록 P1로 둡니다.
_FALLBACK_TRIAGE: dict[str, Any] = {
    "severity": "P1",
    "service": "unknown",
    "category": "unknown",
    "owner_team": "운영센터 당직",
    "first_check": "모델 응답을 읽지 못했습니다. 알람 원문을 사람이 직접 확인한다.",
    "summary": "자동 분류에 실패한 알람입니다. 수동 확인이 필요합니다.",
}

TRIAGE_PROMPT = """당신은 24시간 운영센터의 당직 리드입니다.
아래 모니터링 알람 하나를 읽고, 티켓 시스템에 그대로 적재할 분류 결과를 만드세요.

판단 원칙
- 알람에 없는 사실을 지어내지 않습니다. 근거가 부족하면 unknown 계열 값을 씁니다.
- 고객이 지금 실패를 겪고 있는지를 등급 판단의 첫 기준으로 둡니다.
- 키가 비어 있거나 형식이 깨진 알람도 되묻지 말고 그대로 분류합니다.

[알람]
{alert}

{format_instructions}

인사말이나 설명 문장 없이 JSON 객체 하나만 출력하세요."""

NOTICE_SYSTEM = """당신은 24시간 운영센터의 당직 리드입니다. 방금 받은 알람을 담당팀 채널에 공유할 안내 초안을 씁니다.
읽는 사람은 새벽에 호출된 담당 엔지니어입니다. 3~5문장으로 짧게, 존댓말로, 과장 없이 사실만 씁니다.
무엇이 언제부터 어떻게 되고 있는지 먼저 적고, 지금 요청하는 조치 한 가지로 끝냅니다.
확인되지 않은 원인은 단정하지 않고, 알람 값이 비어 있거나 깨져 있으면 그 사실을 그대로 적습니다."""

NOTICE_HUMAN = """다음 알람에 대한 담당팀 안내 초안을 작성하세요.

[알람]
{alert}"""


def _normalize_triage(parsed: Any) -> dict:
    """파서가 돌려준 값을 항상 같은 모양의 dict로 맞춥니다."""
    if isinstance(parsed, list):
        parsed = next((item for item in parsed if isinstance(item, dict)), None)
    if not isinstance(parsed, dict):
        return {**_FALLBACK_TRIAGE, "parse_failed": True}

    result = {**_FALLBACK_TRIAGE, "parse_failed": False}
    result.update({k: v for k, v in parsed.items() if v is not None})
    if str(result.get("severity")) not in SEVERITY_ORDER:
        # 등급 값이 깨졌으면 사람이 보도록 최고 등급으로 올립니다.
        result["severity"] = "P1"
        result["parse_failed"] = True
    return result


def _recover_triage(text: str) -> dict:
    """모델이 JSON이 아닌 것을 뱉었을 때 쓰는 복구 경로입니다."""
    return {
        **_FALLBACK_TRIAGE,
        "parse_failed": True,
        "raw_output": str(text)[:300],
    }


def build_triage_chain(llm=None):
    """알람 dict를 받아 TRIAGE_SCHEMA 형태의 dict를 반환하는 체인을 만듭니다.

    반드시 지킬 것:
      - 프롬프트에 파서의 format_instructions를 실제로 주입해야 합니다.
        스키마만 정의하고 프롬프트에 넣지 않으면 모델은 형식을 모릅니다.
    """
    from langchain_core.output_parsers import JsonOutputParser, StrOutputParser
    from langchain_core.prompts import PromptTemplate
    from langchain_core.runnables import RunnableLambda

    llm = llm or _default_llm()

    parser = JsonOutputParser(pydantic_object=TRIAGE_SCHEMA)
    prompt = PromptTemplate(
        template=TRIAGE_PROMPT,
        input_variables=["alert"],
        partial_variables={"format_instructions": parser.get_format_instructions()},
    )

    to_prompt_input = {"alert": RunnableLambda(_alert_text)}

    # 정상 경로: 프롬프트 -> 모델 -> JSON 파서
    primary = to_prompt_input | prompt | llm | parser | RunnableLambda(_normalize_triage)
    # 복구 경로: 모델이 JSON을 깨뜨리면 텍스트로 받아 안전한 기본값으로 되돌립니다.
    recovery = (
        to_prompt_input | prompt | llm | StrOutputParser() | RunnableLambda(_recover_triage)
    )

    return primary.with_fallbacks([recovery])


def build_notice_chain(llm=None):
    """알람 dict를 받아 담당팀 안내 초안 문자열을 반환하는 체인을 만듭니다.

    반드시 지킬 것:
      - system 메시지로 역할을 지정합니다 (30자 이상).
      - 기본 예시 문구를 그대로 두지 말고 본인 조직의 맥락으로 바꾸세요.
    """
    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_core.runnables import RunnableLambda

    llm = llm or _default_llm()

    prompt = ChatPromptTemplate.from_messages(
        [("system", NOTICE_SYSTEM), ("human", NOTICE_HUMAN)]
    )

    return {"alert": RunnableLambda(_alert_text)} | prompt | llm | StrOutputParser()


def build_full_chain(llm=None):
    """두 체인을 병렬로 묶어 {"triage": dict, "notice": str} 를 반환합니다.

    심화 파트를 구현했다면, triage 결과는 apply_severity_rules를 거친 값이어야 합니다.
    """
    from langchain_core.runnables import (
        RunnableLambda,
        RunnableParallel,
        RunnablePassthrough,
    )

    llm = llm or _default_llm()

    branches = RunnableParallel(
        triage=build_triage_chain(llm),
        notice=build_notice_chain(llm),
        alert=RunnablePassthrough(),
    )

    def _finalize(payload: dict) -> dict:
        # LLM 판단 위에 결정적 규칙을 한 번 더 덮어씁니다.
        triage = apply_severity_rules(payload.get("triage"), payload.get("alert"))
        notice = payload.get("notice")
        return {"triage": triage, "notice": "" if notice is None else str(notice)}

    return branches | RunnableLambda(_finalize)


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

# 죽으면 매출과 고객 신뢰가 바로 깎이는 서비스입니다. 모델 판단과 무관하게 등급을 올립니다.
CRITICAL_SERVICES: set[str] = {
    "payment-api",
    "auth-api",
    "order-api",
    "checkout-web",
    "settlement-batch",
}

# message 안에 이 낱말이 보이면 이미 고객 요청이 실패하고 있다고 봅니다.
OUTAGE_KEYWORDS = ("5xx", "outage")


def apply_severity_rules(triage: dict, alert: dict) -> dict:
    """모델이 매긴 severity 위에 결정적 규칙을 얹습니다.

    이 함수는 LLM을 호출하지 않습니다. 같은 입력에 항상 같은 출력을 내야 합니다.

    규칙:
      - alert["service"]가 CRITICAL_SERVICES에 있으면 최소 P2
      - alert["message"]에 "5xx" 또는 "outage"가 있으면 최소 P1
      - 둘 다면 더 높은 쪽(숫자가 작은 쪽)을 적용
      - 아무것도 해당 없으면 모델 판단을 그대로 둠
      - 규칙이 적용됐으면 그 사실을 결과에 남길 것 (예: rule_applied 키)

    Returns:
        규칙이 반영된 새 dict. 원본을 그대로 바꾸지 말고 복사해서 쓰는 편이 안전합니다.
    """
    if isinstance(triage, dict):
        result = dict(triage)
    else:
        result = {**_FALLBACK_TRIAGE, "parse_failed": True}
    alert = alert if isinstance(alert, dict) else {}

    current = str(result.get("severity", "")).upper()
    floor: str | None = None
    applied: list[str] = []

    service = str(alert.get("service") or "").strip()
    if service in CRITICAL_SERVICES:
        floor = "P2"
        applied.append("critical_service")

    message = str(alert.get("message") or "").lower()
    if any(keyword in message for keyword in OUTAGE_KEYWORDS):
        # 둘 다 걸리면 더 높은 쪽(숫자가 작은 쪽)인 P1이 이깁니다.
        floor = "P1"
        applied.append("outage_keyword")

    final = current if current in SEVERITY_ORDER else "P1"
    if floor is not None and SEVERITY_ORDER[floor] < SEVERITY_ORDER[final]:
        final = floor
    elif floor is not None:
        # 모델이 이미 더 높게 매겼으면 낮추지 않고, 규칙이 걸렸다는 사실만 남깁니다.
        applied.append("kept_model_severity")

    result["severity"] = final
    result["rule_applied"] = applied
    return result
