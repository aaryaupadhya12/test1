import json, os, tempfile, unittest
from src.env import IncidentEnv
from src.fake_model import FakeModel, call, bad_call, scripted
from src.harness import run_episode, print_trajectory, save_trajectory, NUDGE

BASE = {"arrivals": 900, "capacity": 500, "base_delay": 20}
BROWNOUT = {**BASE, "id": "brownout_B", "degraded": {"B": 0.5}}
CONTROL = {**BASE, "id": "control", "degraded": {}}

def check_pairing(messages):
    asked = {tc["id"] for m in messages if m["role"] == "assistant" for tc in m.get("tool_calls", [])}
    answered = {m["tool_call_id"] for m in messages if m["role"] == "tool"}
    assert asked == answered, f"unpaired tool calls: {asked ^ answered}"

class TestHarness(unittest.TestCase):
    def test_normal_episode(self):
        model = FakeModel([
            scripted(call("c1", "get_metrics", {"zone": "B"})),
            scripted(call("c2", "shift_traffic", {"zone_source": "B", "zone_destination": "A", "split_percentage": 25})),
            scripted(call("c3", "shift_traffic", {"zone_source": "B", "zone_destination": "C", "split_percentage": 20})),
            scripted(call("c4", "submit", {})),
        ])
        traj = run_episode(IncidentEnv(), BROWNOUT, model)
        print(); print_trajectory(traj)
        self.assertEqual(traj.ended_by, "submit")
        self.assertAlmostEqual(traj.grader.reward, 0.95)
        self.assertEqual(traj.totals["input_tokens"], 40)
        for msgs in model.seen:
            check_pairing(msgs)

    def test_malformed_args_survive(self):
        model = FakeModel([scripted(bad_call("c1", "shift_traffic", "{zone_source: B")),
                           scripted(call("c2", "submit", {}))])
        traj = run_episode(IncidentEnv(), CONTROL, model)
        print(); print_trajectory(traj)
        self.assertIn("error", traj.steps[0].observation)
        self.assertEqual(traj.ended_by, "submit")
        for msgs in model.seen:
            check_pairing(msgs)               # the bad call still got a tool result

    def test_plain_text_gets_nudge(self):
        model = FakeModel([scripted(text="I think everything is fine."),
                           scripted(call("c1", "submit", {}))])
        traj = run_episode(IncidentEnv(), CONTROL, model)
        print(); print_trajectory(traj)
        self.assertEqual(model.seen[1][-1], {"role": "user", "content": NUDGE})
        self.assertEqual(traj.ended_by, "submit")

    def test_max_turns(self):
        traj = run_episode(IncidentEnv(), BROWNOUT, FakeModel([]), max_turns=3)
        print(); print_trajectory(traj)
        self.assertEqual(traj.ended_by, "max_turns")
        self.assertEqual(len(traj.steps), 3)

    def test_save_roundtrip(self):
        traj = run_episode(IncidentEnv(), CONTROL, FakeModel([scripted(call("c1", "submit", {}))]))
        with tempfile.TemporaryDirectory() as d:
            with open(save_trajectory(traj, d)) as f:
                data = json.load(f)
        print("\nsaved keys:", list(data))
        self.assertEqual(data["ended_by"], "submit")

if __name__ == "__main__":
    unittest.main()