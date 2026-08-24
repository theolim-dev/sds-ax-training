# Day 6. Supervisor 인시던트 대응팀

[← 전체 미션 맵](../README.md)  ·  [← Day 5](../day05/README.md)  ·  [Day 7 →](../day07/README.md)

> 전문 Agent 셋을 Supervisor가 지휘합니다. Day2의 검색과 Day4의 도구가 여기서 한 시스템으로 합쳐집니다.

## 학습 목표

- Supervisor는 질문을 읽고 어느 Agent로 보낼지 고릅니다.
- 전문 Agent는 담당 범위와 도구, 프롬프트를 좁게 잡습니다.
- Agent를 늘리면 호출 수와 추적 비용이 함께 늘어납니다. 어디까지 늘릴지 직접 재 봅니다.
- 워커가 내놓은 답을 그대로 내보내지 않고 한 번 걸러 냅니다. (심화)

---

## 기초 파트 (7점)

### 구현할 것

```python
AGENT_NAMES: list[str]                 # 전문 Agent 3개
AGENT_TOOLS: dict[str, list[str]]      # Agent -> 도구 목록
route_question(question) -> list[str]  # 어느 Agent로 보낼지 (LLM 없이)
build_supervisor(llm=None)             # 컴파일된 그래프
```

### 요구사항

1. Agent 3개를 둡니다. `log_agent`, `metric_agent`, `runbook_agent`.

2. 도구를 격리하세요. 같은 도구가 두 Agent에 들어가면 안 됩니다.
   > "혹시 몰라서" 얹어 두면 Supervisor가 어디로 보낼지 헷갈립니다. 도메인 기준으로 나누세요.

3. `route_question`은 LLM 없이 결정적 규칙으로 배분합니다.

   | 질문 성격 | Agent |
   |---|---|
   | 로그, 에러, 예외, 스택, 트레이스, 5xx/500, 영문 `log`/`exception`/`trace` | `log_agent` |
   | 지표, 수치, 지연, 레이턴시, CPU, 메모리, 오류율, 배포, 영문 `metric`/`latency` | `metric_agent` |
   | 절차, 대응, 방법, 런북, 매뉴얼, 담당, 누구, 어떻게, 영문 `runbook` | `runbook_agent` |
   | 여러 주제가 섞임 | 해당하는 것 모두 |
   | 어디에도 없음 | 빈 목록 |

   > 채점은 위 표에 없는 동의어와 영문 표기로도 확인합니다.
   > 단어를 그대로 베끼지 말고 같은 뜻의 표현을 함께 넣어 두세요.
   > 8케이스 중 1건까지 틀려도 통과합니다.
   > 해당하는 Agent만 반환하세요. 전부 부르면 정확도는 오르지만 호출 비용이 폭증합니다.

4. `routing_test.json` (day06 폴더)에 6문항 이상을 담습니다. 단일 Agent 3문항 이상, 복합 1문항 이상.

5. `eval_set.json` (저장소 루트)에 `routing` 유형을 2문항 이상 추가합니다 (`d6-01`, `d6-02`).
   Day2부터 누적해 Day7에 12문항 이상, 5유형 이상이 되어야 합니다.

   ```json
   [{"question": "payment-api 로그에 어떤 에러가 찍혔나요?", "expected": ["log_agent"]}]
   ```

### 채점 기준 (기초 7점)

| 배점 | 항목 | 무엇을 보는가 |
|---|---|---|
| 2점 | **구성** | `AGENT_NAMES` 3개가 그래프 노드로 모두 존재 |
| 2점 | **도구 격리** | 도구가 Agent 간에 겹치지 않음 |
| 1점 | **라우팅 정확도** | 공개 케이스에서 필요한 Agent를 정확히 고름 |
| 1점 | **라우팅 테스트셋** | 6문항 이상, 단일 3+ / 복합 1+ |
| 1점 | **확장 검사 게이트** | 10개 중 8개 이상 |

---

## 심화 파트 (3점)

### 왜 필요한가

워커가 만든 답을 그대로 사용자에게 넘기면 근거 없는 단정과 빈 답변이 섞여 나갑니다.
내보내기 전 검사를 Supervisor에게 맡기면 두 가지를 여기서 걸러 낼 수 있습니다.

### 구현할 것

```python
judge_output(agent_name, output) -> {"keep": bool, "reason": str}
```

| 조건 | 판정 |
|---|---|
| 비었거나 20자 미만 | `keep=False`, 사유 "저가치" |
| 근거 없는 단정 ("확실합니다" 등)인데 수치·출처가 없음 | `keep=False`, 사유 "근거 없는 단정" |
| 그 외 | `keep=True` |

그리고 워커 노드가 이 판정을 거치도록 연결하세요.

### 채점 기준 (심화 3점)

| 배점 | 항목 | 무엇을 보는가 |
|---|---|---|
| 1점 | **게이팅 결정성** | 정상, 빈 값, 짧은 값, 근거 없는 단정 네 상황을 구분 |
| 1점 | **저가치 억제** | 억제할 때 사유가 붙음 |
| 1점 | **파이프라인 연결** | Supervisor 실행 결과에 게이팅이 반영됨 |

---

## 제출

```bash
python scripts/grade.py --day 6
git add day06/ eval_set.json
git commit -m "[제출] Day6"
git push
```
