# CONTRACTS.md

Reference for every data object in `contracts.py`. These are the frozen interfaces between the environment, the harness, the model clients, and everything that reads results (QA suite, results table, dashboard).

**Rule:** after the Oct 12 freeze, changing a field name, type, or meaning needs a version bump and a `CHANGELOG.md` entry. Before 1.0, any change to the trajectory format is a minor bump.

---

## 1. How the objects fit together

```
TaskSpec ──▶ env.reset(spec) ──▶ first observation
                                      │
        ┌─────────────────────────────┘
        ▼
   pool: list[Event]  ──ContextManager.build()──▶ messages: list[dict]
        ▲                                              │
        │                                              ▼
        │                                  ModelClient.complete(messages, tools)
        │                                              │
        │                                              ▼
        │                                         ModelReply
        │                          (text, tool_calls: list[ToolCall], usage: Usage, latency_ms)
        │                                              │
        │                         harness runs each ToolCall via env.step(name, args)
        │                                              │
        └────── tool_result Event ◀─── observation ────┘
                                              │
                          each executed call is recorded as a Step
                                              │
                          env.grade() ──▶ GraderOutput
                                              │
                    Trajectory = steps + GraderOutput + metadata  ──▶ runs/*.jsonl
```

Flow in words: a `TaskSpec` configures the environment. The harness keeps an append-only pool of `Event`s. The `ContextManager` turns the pool into messages. The `ModelClient` returns a `ModelReply`. Each `ToolCall` is executed against the environment, and the result goes back into the pool. Every executed call is logged as a `Step`. When the episode ends, `grade()` returns a `GraderOutput`, and everything is packaged as one `Trajectory`.

---

## 2. `VERSIONS`

```python
VERSIONS = {"harness": "0.1.0", "env": "0.1.0", "grader": "0.1.0"}
```

| Key | What it versions | Bump when |
|---|---|---|
| `harness` | The loop, context manager, message protocol, trajectory format | Loop behavior or logging format changes |
| `env` | Simulator, tools, tool schemas | Latency model, tool semantics, or schemas change |
| `grader` | Signals, weights, thresholds, hard rules | Any change to how reward is computed |

Copied into every `Trajectory.versions`, so a result can always be traced to the code that produced it. Results from different grader versions must never be compared directly.

---

## 3. `TaskSpec`: one scenario

**Purpose:** a complete, self-contained description of one incident. Everything needed to reproduce an episode, except the model.

**Created by:** hand (v0), then the task factory (v1.5). **Read by:** `env.reset()`, the harness, the QA suite, the report.

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Unique task id, e.g. `"brownout_B_050"`. Used as the trajectory filename key. |
| `seed` | `int` | Seed for any scenario randomness. Same `(spec, seed)` must give the same score. |
| `split` | `str` | `"dev"` or `"test"`. Tune on dev, report on test only. |
| `parameters` | `dict` | Scenario inputs: degraded zone, severity, start split, arrivals, capacities. |
| `slo_ms` | `float` | p99 latency threshold for `slo_ok` (e.g. `300.0`). |
| `cost_budget` | `float` | Max fraction of traffic that may move (e.g. `0.4`). |
| `max_turns` | `int` | Turn limit for the agent (e.g. `8`). |
| `difficulty` | `str` | Label such as `"easy"`, `"medium"`, `"hard"`, `"control"`. Used to slice results. |
| `instruction` | `str` | The text the agent sees as the task. |

**Notes**
- The control task (no incident) is a normal TaskSpec with `difficulty="control"`. The right move is to change almost nothing.
- Keep randomness inside the scenario. `grade()` must be deterministic.

---

## 4. `ToolCall`: one tool call the model asked for

**Purpose:** a normalized tool call, whatever provider produced it.

**Created by:** model clients (parsing the provider response). **Read by:** the harness.

| Field | Type | Meaning |
|---|---|---|
| `id` | `str` | Provider's tool-call id. The matching tool-result message must reuse it. |
| `name` | `str` | Tool name: `get_metrics`, `shift_traffic`, or `submit`. |
| `args` | `dict` | Parsed arguments. Empty `{}` if parsing failed. |
| `raw_args` | `str` | The exact argument string from the model, kept for debugging malformed calls. |

**Notes**
- Every `ToolCall.id` needs a matching tool-result message, even when arguments were malformed. Otherwise OpenAI-style APIs reject the next request.
- A malformed call becomes an error observation, never a crash.

---

## 5. `Usage`: token accounting for one model call

**Purpose:** the numbers cost is computed from.

**Created by:** model clients (from each response's `usage` field). **Read by:** the cost calculation, the report.

| Field | Type | Meaning |
|---|---|---|
| `input_tokens` | `int` | Prompt tokens sent. |
| `output_tokens` | `int` | Tokens generated. |
| `cached_tokens` | `int` | Prompt tokens served from cache (often billed lower). |
| `reasoning_tokens` | `int` | Hidden reasoning tokens, when the provider reports them. |

**Notes**
- Providers differ on whether reasoning tokens are included inside `output_tokens`. Decide once per provider and document it in `pricing.py`.
- Cost is always `usage × price`, computed in one place, never inside a client.

---

## 6. `ModelReply`: what a model returned

**Purpose:** the single normalized reply type. Every provider is converted into this.

**Created by:** `ModelClient.complete()`. **Read by:** the harness.

| Field | Type | Meaning |
|---|---|---|
| `text` | `str` | Plain text content. May be non-empty even when tool calls exist. |
| `tool_calls` | `list[ToolCall]` | Zero or more calls. Empty means the model answered in plain text. |
| `usage` | `Usage` | Token counts for this call. |
| `latency_ms` | `float` | Wall-clock time of the model call, measured by the client. |
| `logprobs` | `Optional[list]` | Token log-probabilities when the provider returns them, else `None`. Needed for the fast-tier logits trick. |

---

## 7. `ModelClient`: the provider interface

**Purpose:** one interface for every model, so the harness never knows which provider it is talking to.

```python
class ModelClient:
    model_id: str
    def complete(self, messages: list[dict], tools: list[dict],
                 temperature: float = 0.0) -> ModelReply: ...
```

| Member | Meaning |
|---|---|
| `model_id` | Exact provider model id, recorded in every trajectory. |
| `complete(messages, tools, temperature)` | Takes chat messages and tool JSON schemas, returns a `ModelReply`. |

**Implementations (planned):** `FakeModel` (scripted, offline tests), `OpenAICompatClient` (Token Factory, OpenAI, Qwen on vLLM), an Anthropic adapter.

**Notes**
- The base `complete` should raise `NotImplementedError` so a missing override fails loudly.
- Clients normalize and measure. They do not retry silently or compute cost.

---

## 8. `GraderOutput`: the result of grading

**Purpose:** the reward plus every signal that produced it.

**Created by:** `env.grade()`. **Read by:** the harness (stores it), QA suite, report.

| Field | Type | Meaning |
|---|---|---|
| `reward` | `float` | Final score in `[0, 1]`, after hard rules. |
| `signals` | `dict` | Every component, including raw values for debugging. |
| `grader_version` | `str` | Version of the grading logic, from `VERSIONS["grader"]`. |

**Signals (keys are frozen once chosen):**

| Key | Meaning |
|---|---|
| `slo_ok` | 1.0 if the worst zone's p99 is at or below `slo_ms`, else 0.0. |
| `cost_ok` | 1.0 if traffic moved is at or below `cost_budget`, else 0.0. |
| `no_collateral` | 1.0 if no healthy zone ended overloaded or SLO-violating. |
| `diagnosed_zone` | 1.0 if the first shift moved traffic out of the truly degraded zone. |
| `worst_p99_ms`, `cost` | Raw debug values. |

**Hard rule:** any zone overloaded at submit forces `reward = 0`, but the raw signals are still returned.

---

## 9. `Step`: one executed action

**Purpose:** the per-action log inside a trajectory. One `Step` per executed tool call (or per turn with no tool call, where `tool` is `None`).

**Created by:** the harness. **Read by:** the report, the dashboard replay.

| Field | Type | Meaning |
|---|---|---|
| `turn` | `int` | 1-based turn number. |
| `tool` | `Optional[str]` | Tool name, or `None` for a plain-text turn. |
| `args` | `dict` | Arguments passed to the tool. |
| `observation` | `dict` | What the tool returned, including error dicts. |
| `model_ms` | `float` | Time spent in the model call for this turn. |
| `tool_ms` | `float` | Time spent executing the tool. |
| `usage` | `Usage` | Token usage of the model call that produced this step. |

**Notes**
- If one reply contains several tool calls, they share the same `usage`. Count it once when summing totals.
- Planned addition: `context_tokens`, the input size after the context manager runs.

---

## 10. `Trajectory`: one full episode

**Purpose:** the unit of record. One per episode, saved as JSON or one JSONL line. All results are computed from these.

**Created by:** `run_episode()`. **Read by:** QA suite, report, dashboard.

| Field | Type | Meaning |
|---|---|---|
| `task_id` | `str` | Which `TaskSpec` was run. |
| `model_id` | `str` | Exact model id used. |
| `run_date` | `str` | ISO date. APIs change silently, so this matters. |
| `run_index` | `int` | 0 to 4, for the five runs per task. |
| `versions` | `dict` | Copy of `VERSIONS` at run time. |
| `steps` | `list[Step]` | Ordered actions taken. |
| `grader` | `GraderOutput` | Final reward and signals. |
| `ended_by` | `str` | `"submit"`, `"max_turns"`, or `"error"`. Always logged, because it exposes episodes that ran out of turns. |
| `totals` | `dict` | Rollups: tokens, `cost_usd`, time per phase (model, tool, verifier). |
| `context_policy` | `dict` | `{"name": "identity", "version": "0.1.0", ...params}`. |
| `parent_id` | `Optional[str]` | Parent trajectory for future subagents. `None` for now. |

**Notes**
- Fields without defaults come first, defaults last. That is a dataclass requirement.
- Never overwrite a trajectory file. A new run is a new file.

---

## 11. `Event`: one item in the observation pool

**Purpose:** the append-only record of everything that happened in an episode. The pool is the source of truth, and nothing is ever deleted from it.

**Created by:** the harness. **Read by:** the `ContextManager`.

| Field | Type | Meaning |
|---|---|---|
| `turn` | `int` | Turn the event belongs to. `0` for the system prompt and task. |
| `kind` | `str` | `"system"`, `"task"`, `"assistant"`, `"tool_result"`, or `"nudge"`. |
| `payload` | `dict` | The actual chat message, e.g. `{"role": "tool", "tool_call_id": "...", "content": "..."}`. |

**Notes**
- `payload` must already be a valid chat message with a `role`, because `build()` returns payloads directly.
- A `nudge` is the short user message added after a plain-text reply ("Use a tool or call submit").

---

## 12. `ContextManager`: pool in, messages out

**Purpose:** decides what the model sees on each turn. It is a pure function of the pool.

```python
class ContextManager:
    name = "identity"
    def build(self, pool: list[Event]) -> list[dict]:
        return [e.payload for e in pool]
```

| Member | Meaning |
|---|---|
| `name` | Identifier recorded in `Trajectory.context_policy`. |
| `build(pool)` | Returns the message list to send to the model. |

**Rules every variant must follow**
1. Always keep the system prompt and the task message.
2. Never drop an assistant `tool_calls` message without its tool results, or the reverse. Drop or compress them as pairs.
3. Be deterministic. No model calls inside `build` for now.

**Planned variants:** `identity` (v0), `last_n(k)`, `state_digest`. Every model gets the same one, and changing it is a harness minor version bump.

---

## 13. Example trajectory

From the smoke test:

```json
{
  "task_id": "t0",
  "model_id": "fake",
  "run_date": "2026-10-04",
  "run_index": 0,
  "versions": {"harness": "0.1.0", "env": "0.1.0", "grader": "0.1.0"},
  "steps": [],
  "grader": {"reward": 0.0, "signals": {}, "grader_version": "0.1.0"},
  "ended_by": "submit",
  "totals": {},
  "context_policy": {},
  "parent_id": null
}
```

---

## 14. Quick reference

| Object | Made by | Used by | Lives in |
|---|---|---|---|
| `TaskSpec` | You / task factory | env, harness, QA | `tasks/*.json` |
| `ToolCall` | Model clients | Harness | Inside `ModelReply` |
| `Usage` | Model clients | Cost calc, report | `ModelReply`, `Step` |
| `ModelReply` | Model clients | Harness | In memory |
| `ModelClient` | You (interface) | Harness | `clients/` |
| `GraderOutput` | `env.grade()` | Harness, QA, report | `Trajectory.grader` |
| `Step` | Harness | Report, dashboard | `Trajectory.steps` |
| `Trajectory` | Harness | QA, report, dashboard | `runs/*.jsonl` |
| `Event` | Harness | ContextManager | In memory (pool) |
| `ContextManager` | You | Harness | `context.py` |