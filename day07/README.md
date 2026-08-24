# Day 7. 계측과 누적 평가

[← 전체 미션 맵](../README.md)  ·  [← Day 6](../day06/README.md)  ·  [Day 8~10 →](../day08/README.md)

> 6일간 쌓은 시스템을 측정합니다. Day2에 심어 둔 문항을 여기서 회수합니다.

## 학습 목표

- 관측은 무엇을 했는지를 남기고, 평가는 잘했는지를 판정합니다.
- trace는 결정적 구조체라 LLM 출력과 무관하게 검사할 수 있습니다.
- 통과율 하나로는 품질을 알 수 없습니다. 유형별로 쪼개야 뚫린 곳이 보입니다.
- 한쪽을 고쳤을 때 다른 쪽이 깨지지 않았는지 확인합니다. (심화)

---

## 기초 파트 (7점)

### 구현할 것

```python
TraceCollector                              # 실행 기록
run_eval(answer_fn, eval_set, judge=None)   # 유형별 집계
```

### 요구사항

1. `TraceCollector`: `record(event, name, **fields)` / `events` / `dump(path)`
   - `event`는 `llm_start`, `llm_end`, `tool_start`, `tool_end` 중 하나입니다
   - `dump`는 JSON Lines로 씁니다. 한 줄에 이벤트 하나.
   - 지연 시간 같은 부가 필드도 실을 수 있어야 합니다

2. `run_eval`: 반환 스키마를 그대로 지키세요.

   ```python
   {
     "total": 14,
     "passed": 11,
     "by_type": {"fact": {"total": 5, "passed": 5}, "no_answer": {...}},
     "failures": [{"id": "d5-01", "type": "guardrail", "status": "fail", "detail": "..."}],
   }
   ```

   > **한 문항이 예외를 던져도 전체가 멈추면 안 됩니다.** 그 문항은 `status`를 `error`로 남기고 다음으로 넘어가세요.
   > 14문항 돌리다 3번째에서 죽으면 나머지 11문항의 상태를 영영 모릅니다.

3. `eval_set.json`: Day2부터 누적해 12문항 이상, 5유형 이상이 되어야 합니다.

4. `day07/growth.md`: Day2에 심어 둔 문항 중 그때 실패했던 것을 회수합니다.
   지금은 통과하는지, 무엇이 그걸 바꿨는지를 100자 이상 쓰세요.

### 채점 기준 (기초 7점)

| 배점 | 항목 | 무엇을 보는가 |
|---|---|---|
| 2점 | **평가셋 누적** | 12문항 이상, 5유형 이상, id 중복 없음 |
| 2점 | **집계 형식** | 반환 스키마 준수, 유형별 합이 전체와 일치 |
| 1점 | **예외 격리** | 한 문항이 터져도 전체가 멈추지 않고 `error`로 기록 |
| 1점 | **계측** | 이벤트 기록 + 지연 필드 + JSON Lines dump |
| 1점 | **확장 검사 게이트** | 10개 중 8개 이상 (`growth.md` 포함) |

---

## 심화 파트 (3점)

### 왜 필요한가

통과율 총합만 보면 어느 유형이 좋아졌고 어느 유형이 깨졌는지 알 수 없습니다.
한 유형을 고치다 다른 유형을 깨뜨리는 일이 자주 생깁니다.
전체 점수가 올라도 안전 유형이 뚫렸다면 배포하면 안 되는데, 그 사실은 유형별 비교에서만 드러납니다.

### 구현할 것

```python
compare_eval(before, after) -> {"fixed": [...], "regressed": [...], "delta": int, "safe": bool}
```

- `fixed`: before에서 실패했다가 after에서 통과한 문항 id
- `regressed`: before에서 통과했다가 after에서 실패한 문항 id
- `safe`: `regressed`가 비었으면 `True`

### 채점 기준 (심화 3점)

| 배점 | 항목 | 무엇을 보는가 |
|---|---|---|
| 1점 | **비교의 결정성** | 개선과 회귀를 정확히 분리 |
| 1점 | **회귀 탐지** | 통과 수가 늘어도 회귀가 있으면 `safe=False` |
| 1점 | **회귀 없음 판정** | 무조건 `False`를 내는 구현은 인정하지 않음 |

---

## 제출

```bash
python scripts/grade.py --day 7
git add day07/ eval_set.json
git commit -m "[제출] Day7"
git push
```
