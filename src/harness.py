import json, os
import time
from dataclasses import asdict
from datetime import date

from .contracts import VERSIONS, ContextManager, Event, GraderOutput, Step, Trajectory, Usage

SYSTEM_PROMPT = (
    "You are an on-call engineer responding to a latency incident across three zones (A, B, C).\n"
    "Tools: get_metrics(zone), shift_traffic(zone_source, zone_destination, split_percentage), submit().\n"
    "Investigate before acting, and move only as much traffic as needed. "
    "Call submit() when the incident is resolved or when no action is needed."
)
NUDGE = "Use a tool, or call submit() if you are done."

def parse_args(call):
    """Returns (args, None) or (None, error_text)."""
    try:
        args = json.loads(call.raw_args) if call.raw_args else call.args
    except json.JSONDecodeError as e:
        return None, f"malformed arguments: {e}"
    if not isinstance(args, dict):
        return None, "arguments must be a JSON object"
    return args, None

def run_episode(env, scenario, model, max_turns=8, ctx=None, run_index=0):
    ctx = ctx or ContextManager()
    tools = env.tool_schema()
    observation = env.reset(scenario)
    pool = [Event(0, "system", {"role": "system", "content": SYSTEM_PROMPT}),
            Event(0, "task", {"role": "user", "content": observation})]
    steps, ended_by, error = [], "max_turns", None

    try:
        for turn in range(1, max_turns + 1):
            reply = model.complete(ctx.build(pool), tools)

            msg = {"role": "assistant", "content": reply.text}
            if reply.tool_calls:
                msg["tool_calls"] = [
                    {"id": c.id, "type": "function",
                     "function": {"name": c.name, "arguments": c.raw_args or json.dumps(c.args)}}
                    for c in reply.tool_calls]
            pool.append(Event(turn, "assistant", msg))

            if not reply.tool_calls:                       # plain-text reply: count the turn, nudge
                steps.append(Step(turn, None, {}, {"note": "plain text reply"},
                                  reply.latency_ms, 0.0, reply.usage))
                pool.append(Event(turn, "nudge", {"role": "user", "content": NUDGE}))
                continue

            for i, c in enumerate(reply.tool_calls):
                args, err = parse_args(c)
                t0 = time.perf_counter()
                obs = {"error": err} if err else env.step(c.name, args)
                tool_ms = (time.perf_counter() - t0) * 1000
                # every tool call gets a result message, even a malformed one
                pool.append(Event(turn, "tool_result", {"role": "tool", "tool_call_id": c.id,
                                                        "content": json.dumps(obs)}))
                # usage and model time belong to the whole reply, so count them once
                steps.append(Step(turn, c.name, args or {}, obs,
                                  reply.latency_ms if i == 0 else 0.0, tool_ms,
                                  reply.usage if i == 0 else Usage()))
            if env.done:
                ended_by = "submit"
                break
    except Exception as e:                                 # grade() still runs; the error is recorded
        ended_by, error = "error", repr(e)

    reward, signals = env.grade()
    totals = {"turns": len({s.turn for s in steps}),
              "input_tokens": sum(s.usage.input_tokens for s in steps),
              "output_tokens": sum(s.usage.output_tokens for s in steps),
              "model_ms": sum(s.model_ms for s in steps),
              "tool_ms": sum(s.tool_ms for s in steps)}
    if error:
        totals["error"] = error
    return Trajectory(
        task_id=scenario.get("id", "adhoc"), model_id=model.model_id,
        run_date=date.today().isoformat(), run_index=run_index,
        versions=VERSIONS, steps=steps,
        grader=GraderOutput(reward, signals, VERSIONS["grader"]),
        ended_by=ended_by, totals=totals,
        context_policy={"name": ctx.name, "version": VERSIONS["harness"]})

def save_trajectory(traj, folder="runs"):
    os.makedirs(folder, exist_ok=True)
    name = f"{traj.task_id}__{traj.model_id.replace('/', '_')}__{traj.run_index}.json"
    path = os.path.join(folder, name)
    with open(path, "w") as f:
        json.dump(asdict(traj), f, indent=2)
    return path

def _round(x):
    if isinstance(x, float):
        return round(x, 4)
    if isinstance(x, dict):
        return {k: _round(v) for k, v in x.items()}
    return x

def print_trajectory(traj):
    for s in traj.steps:
        print(f"turn {s.turn}  {s.tool or 'text'} {s.args} -> {_round(s.observation)}")
    print(f"ended_by: {traj.ended_by}  reward: {traj.grader.reward:.4f}")