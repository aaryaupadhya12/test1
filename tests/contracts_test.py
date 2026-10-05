from dataclasses import asdict
import json 
from src.contracts import *


from dataclasses import asdict
import json

spec = TaskSpec(id="t0", seed=0, split="dev", parameters={}, slo_ms=300.0,
                cost_budget=0.4, max_turns=8, difficulty="easy", instruction="...")
traj = Trajectory(task_id="t0", model_id="fake", run_date="2026-10-04", run_index=0,
                  versions=VERSIONS, steps=[], grader=GraderOutput(0.0, {}, "0.1.0"),
                  ended_by="submit")
print(json.dumps(asdict(traj)))      
assert "slo_ms" in asdict(spec)   