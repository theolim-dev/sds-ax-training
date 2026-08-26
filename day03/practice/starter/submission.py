"""Day 3 — 장애 원인 조사 Agent.

도구 세 개로 장애 원인을 좁혀 갑니다.

[중요]
  1. 함수·상수 이름을 바꾸지 마세요.
  2. 모델은 함수 안에서 만듭니다. `llm` 인자가 오면 그것을 씁니다.
  3. 도구는 결정적이어야 합니다. 같은 인자에 항상 같은 결과를 돌려주세요.

[이 파일의 구조]
  기초 파트 — 도구 3개(조회형 · 연쇄형 · 판단형)와 agent ↔ tools 순환 그래프
  심화 파트 — MAX_TOOL_CALLS 예산과 should_stop 조기 종료 판정
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

MODEL_ID = "us.anthropic.claude-sonnet-4-5-20250929-v1:0"
REGION = "us-east-1"

DATA = json.loads(
    (Path(__file__).resolve().parent.parent / "data" / "ops_fixtures.json").read_text(
        encoding="utf-8"
    )
)


def _default_llm():
    from langchain_aws import ChatBedrockConverse

    return ChatBedrockConverse(model=MODEL_ID, region_name=REGION, temperature=0)


# ══════════════════════════════════════════════════════════════════
# 기초 파트 (7점)
# ══════════════════════════════════════════════════════════════════

# ── 도구 인자 스키마 ────────────────────────────────────────────────
# 모델은 이 description을 읽고 무엇을 넣을지 정합니다.
# 설명이 부실하면 모델이 엉뚱한 값을 채워 넣습니다. 스키마도 프롬프트입니다.

class DeployArgs(BaseModel):
    """get_deploy_history 의 인자 스키마입니다."""

    service: str = Field(
        ...,
        description=(
            "배포 이력을 조회할 서비스 이름입니다. "
            "예: 'payment-api', 'auth-service'. "
            "알람이나 사용자 질문에 적힌 서비스 이름을 그대로 넣으세요."
        ),
    )


class LogsArgs(BaseModel):
    """get_logs 의 인자 스키마입니다."""

    service: str = Field(
        ...,
        description="로그를 조회할 서비스 이름입니다. 예: 'payment-api'.",
    )
    since: str | None = Field(
        default=None,
        description=(
            "로그를 볼 기준 시각입니다. ISO8601 문자열로 넣습니다. "
            "예: '2026-08-11T02:58:00+09:00'. "
            "보통 get_deploy_history 가 알려준 최근 배포 시각을 그대로 넣습니다. "
            "생략하면 장애 구간이 아닌 평상시 로그만 보게 되어 원인을 찾기 어렵습니다."
        ),
    )


class MetricsArgs(BaseModel):
    """get_metrics 의 인자 스키마입니다."""

    service: str = Field(
        ...,
        description="지표를 조회할 서비스 이름입니다. 예: 'payment-api'.",
    )


# ── 도구 구현 ──────────────────────────────────────────────────────
# 세 도구 모두 고정 데이터(practice/data/ops_fixtures.json)만 읽습니다.
# 같은 인자에는 항상 같은 문자열이 나옵니다. 그래야 채점과 재현이 가능합니다.

@tool(args_schema=DeployArgs)
def get_deploy_history(service: str) -> str:
    """지정한 서비스의 최근 배포 이력을 최신순으로 돌려줍니다.

    장애 조사의 첫 단계에서 씁니다. "언제부터 이상해졌나"를 좁히려면
    먼저 "최근에 무엇이 바뀌었나"를 알아야 하기 때문입니다.
    여기서 얻은 배포 시각을 get_logs 의 since 인자로 넘기면
    문제 구간의 로그를 바로 볼 수 있습니다.

    쓰지 말아야 할 때: 배포와 무관한 일반 질문이거나, 이미 배포 시각을 알고 있을 때.
    """
    service = (service or "").strip()
    if not service:
        return "서비스 이름이 비어 있습니다. 조회할 서비스 이름을 지정해 주세요."

    history = DATA["deploys"].get(service)
    if not history:
        return f"[{service}] 배포 이력이 없습니다. 서비스 이름을 확인해 주세요."

    lines = [f"[{service}] 최근 배포 이력 (최신순, 총 {len(history)}건)"]
    for item in history:
        lines.append(f"- {item['version']} / 배포시각 {item['at']} / 담당 {item['by']}")
    lines.append("가장 최근 배포 시각을 get_logs 의 since 인자로 넘겨 보세요.")
    return "\n".join(lines)


@tool(args_schema=LogsArgs)
def get_logs(service: str, since: str | None = None) -> str:
    """지정한 서비스의 로그를 돌려줍니다. since를 주면 그 시각 구간의 로그를 봅니다.

    get_deploy_history 로 배포 시각을 먼저 알아낸 다음에 쓰는 것이 정석입니다.
    since 없이 부르면 평상시 로그만 나오므로 장애 원인이 보이지 않습니다.

    쓰지 말아야 할 때: 조사할 시각 구간이 전혀 특정되지 않았을 때. 먼저 배포 이력부터 보세요.
    """
    service = (service or "").strip()
    if not service:
        return "서비스 이름이 비어 있습니다. 조회할 서비스 이름을 지정해 주세요."

    logs = DATA["logs"]
    since = (since or "").strip()

    if since:
        hit = logs.get(f"{service}@{since}")
        if hit:
            return f"[{service}] {since} 전후 로그\n{hit}"
        fallback = logs.get(f"{service}@default")
        if fallback:
            return (
                f"[{service}] {since} 구간에 남은 로그가 없습니다. 평상시 로그를 대신 보여 줍니다.\n"
                f"{fallback}"
            )
        return f"[{service}] 로그가 없습니다. 서비스 이름을 확인해 주세요."

    fallback = logs.get(f"{service}@default")
    if fallback:
        return (
            f"[{service}] 평상시 로그 (구간 미지정)\n{fallback}\n"
            "장애 구간을 보려면 배포 시각을 since 인자로 넘기세요."
        )
    return f"[{service}] 로그가 없습니다. 서비스 이름을 확인해 주세요."


@tool(args_schema=MetricsArgs)
def get_metrics(service: str) -> str:
    """지정한 서비스의 현재 지표(오류율·p99 지연·CPU)를 읽고 정상/이상까지 판정해 돌려줍니다.

    단순 조회가 아니라 판단을 붙여 줍니다. 오류율 5% 이상 또는 p99 3000ms 이상이면
    '이상'으로 표시합니다. 장애가 지금도 진행 중인지, 이미 회복됐는지 확인할 때 씁니다.

    쓰지 말아야 할 때: 원인 자체를 묻는 질문. 지표는 증상만 알려 주고 원인은 로그에 있습니다.
    """
    service = (service or "").strip()
    if not service:
        return "서비스 이름이 비어 있습니다. 조회할 서비스 이름을 지정해 주세요."

    metrics = DATA["metrics"].get(service)
    if not metrics:
        return f"[{service}] 지표가 없습니다. 서비스 이름을 확인해 주세요."

    error_rate = metrics["error_rate_5m"]
    p99 = metrics["p99_latency_ms"]
    cpu = metrics["cpu"]

    # 판단형 도구입니다. 임계값이 고정이므로 결과는 항상 결정적입니다.
    reasons = []
    if error_rate >= 0.05:
        reasons.append(f"오류율 {error_rate:.1%}가 임계 5%를 넘었습니다")
    if p99 >= 3000:
        reasons.append(f"p99 지연 {p99}ms가 임계 3000ms를 넘었습니다")
    verdict = "이상" if reasons else "정상"

    lines = [
        f"[{service}] 최근 5분 지표 판정: {verdict}",
        f"- 오류율(5m): {error_rate:.1%}",
        f"- p99 지연: {p99}ms",
        f"- CPU 사용률: {cpu:.0%}",
        "판정 근거: " + ("; ".join(reasons) if reasons else "임계값을 넘은 지표가 없습니다"),
    ]
    return "\n".join(lines)


# 모델에 묶을 도구 목록입니다. 조회형 · 연쇄형 · 판단형 세 종류를 갖췄습니다.
TOOLS: list = [get_deploy_history, get_logs, get_metrics]

# should_stop 의 '근거 충분' 판정에 쓰는 필수 도구 집합입니다.
REQUIRED_TOOLS = {"get_deploy_history", "get_logs", "get_metrics"}

SYSTEM_PROMPT = """당신은 SDS 운영팀의 장애 원인 조사 담당자입니다.

조사 순서를 지키세요.
1. get_deploy_history 로 최근 배포가 있었는지, 있었다면 그 시각이 언제인지 확인합니다.
2. get_logs 에 1번에서 얻은 배포 시각을 since 인자로 넘겨 그 구간의 로그를 봅니다.
3. get_metrics 로 증상의 크기(오류율·지연)를 확인합니다.

규칙:
- 도구가 돌려준 값만 근거로 씁니다. 추측으로 원인을 단정하지 마세요.
- 같은 도구를 같은 인자로 다시 부르지 마세요. 결과는 항상 같습니다.
- 근거가 모이면 원인 · 근거 · 다음 조치를 한국어로 정리해 답합니다."""


def build_agent(llm=None):
    """도구를 쓸 수 있는 Agent 그래프를 만들어 컴파일해 반환합니다.

    위상:
        START → agent → (도구 호출이 있으면) tools → agent → ... → END

    agent 노드와 tools 노드가 서로를 가리키는 순환입니다.
    탈출은 두 군데에서 일어납니다.
      - 모델이 더 이상 도구를 부르지 않을 때 (정상 종료)
      - should_stop 이 멈추라고 할 때 (예산 초과 · 중복 호출 · 근거 충분)

    심화 파트의 should_stop 을 agent 노드 맨 앞에서 부르기 때문에,
    모델이 아무리 도구를 더 부르려 해도 MAX_TOOL_CALLS 를 넘을 수 없습니다.
    """
    from langchain_core.messages import AIMessage, SystemMessage
    from langgraph.graph import END, START, MessagesState, StateGraph
    from langgraph.prebuilt import ToolNode

    llm = llm or _default_llm()
    model = llm.bind_tools(TOOLS)

    def agent_node(state: MessagesState) -> dict[str, Any]:
        """다음 행동을 정합니다. 멈춰야 하면 모델을 부르지 않고 끝냅니다."""
        messages = state["messages"]

        # 지금까지 실제로 실행된 도구 호출 횟수 = 쌓여 있는 ToolMessage 개수입니다.
        tool_calls_made = sum(1 for m in messages if getattr(m, "type", "") == "tool")

        stop, reason = should_stop(messages, tool_calls_made)
        if stop:
            # 모델을 부르지 않고 조사를 마칩니다. 토큰이 여기서 절약됩니다.
            return {
                "messages": [
                    AIMessage(
                        content=(
                            f"조사를 종료합니다. 사유: {reason} "
                            f"(도구 호출 {tool_calls_made}/{MAX_TOOL_CALLS}회). "
                            "지금까지 모은 근거로 판단해 주세요."
                        )
                    )
                ]
            }

        response = model.invoke([SystemMessage(content=SYSTEM_PROMPT), *messages])
        return {"messages": [response]}

    def route(state: MessagesState) -> str:
        """모델이 도구를 부르려 하면 tools 로 보내고, 아니면 끝냅니다."""
        last = state["messages"][-1]
        if getattr(last, "tool_calls", None):
            return "tools"
        return END

    graph = StateGraph(MessagesState)
    graph.add_node("agent", agent_node)
    graph.add_node("tools", ToolNode(TOOLS))

    graph.add_edge(START, "agent")
    graph.add_conditional_edges("agent", route, {"tools": "tools", END: END})
    graph.add_edge("tools", "agent")  # ← 여기가 순환입니다.

    return graph.compile()


# ══════════════════════════════════════════════════════════════════
# 심화 파트 (3점) — 못 해도 과제는 통과합니다
# ══════════════════════════════════════════════════════════════════

# 한 번의 조사에서 허용할 도구 호출 상한입니다.
# 도구가 3개이므로 한 번씩 다 써 보고 한두 번 더 확인할 여유를 둔 값입니다.
MAX_TOOL_CALLS = 5


def _tool_calls_in(messages: list) -> list[tuple[str, str]]:
    """메시지에서 (도구 이름, 정규화된 인자) 쌍을 호출 순서대로 뽑습니다.

    인자는 키를 정렬한 JSON 문자열로 바꿔 비교합니다.
    키 순서가 달라도 같은 호출이면 같은 문자열이 되게 하기 위해서입니다.
    """
    calls: list[tuple[str, str]] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            if isinstance(tc, dict):
                name = tc.get("name", "")
                args = tc.get("args", {})
            else:
                name = getattr(tc, "name", "")
                args = getattr(tc, "args", {})
            calls.append((name, json.dumps(args, sort_keys=True, ensure_ascii=False)))
    return calls


def should_stop(messages: list, tool_calls_made: int) -> tuple[bool, str]:
    """더 조사할지 멈출지 결정합니다. LLM을 호출하지 않습니다.

    판정 규칙 (위에서부터 먼저 걸리는 것을 씁니다):
      - tool_calls_made >= MAX_TOOL_CALLS        -> (True, "예산 초과")
      - 같은 도구를 같은 인자로 2회 이상 호출함  -> (True, "중복 호출")
      - 세 도구를 모두 한 번 이상 호출함         -> (True, "근거 충분")
      - 그 외                                    -> (False, "조사 계속")

    Args:
        messages: 지금까지의 메시지 목록. 도구 호출 기록이 들어 있습니다.
        tool_calls_made: 지금까지 실행한 도구 호출 횟수

    Returns:
        (중단할지 여부, 이유 문자열)
    """
    # 1. 예산 — 가장 강한 규칙입니다. 무한 루프를 여기서 끊습니다.
    if tool_calls_made >= MAX_TOOL_CALLS:
        return True, "예산 초과"

    calls = _tool_calls_in(messages or [])

    # 2. 중복 — 결정적인 도구를 같은 인자로 또 부르면 새 정보가 없습니다.
    if calls and max(Counter(calls).values()) >= 2:
        return True, "중복 호출"

    # 3. 근거 충분 — 세 도구를 다 썼으면 상한에 닿기 전에 멈춥니다.
    if REQUIRED_TOOLS <= {name for name, _ in calls}:
        return True, "근거 충분"

    return False, "조사 계속"
