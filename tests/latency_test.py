import unittest
from src.env import IncidentEnv
import inspect
from src.env import IncidentEnv
from src.policies import *
SCENARIO = {"arrivals": 900, "capacity": 500, "base_delay": 20}

class TestLatency(unittest.TestCase):
    def test_no_incident(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {}})
        for z in env.ZONES:
            r = env.zone_latency(z)
            self.assertAlmostEqual(r["load"], 300)
            self.assertAlmostEqual(r["mean_ms"], 25)
            self.assertAlmostEqual(r["p99_ms"], 115)
            self.assertFalse(r["overloaded"])

    def test_get_metrics(self):
        env = IncidentEnv()
        # ** -> means unpack all the values in the dictionary 
        env.reset({**SCENARIO,"degraded" : {}})
        env.get_metrics({**SCENARIO, "degraded":{}})
        self.assertAlmostEqual(env.get_metrics("A")["mean_ms"],25)
        self.assertIn("error", env.get_metrics("D"))

    def test_b_and_c_degraded(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {"B": 0.5, "C": 0.3}})
        a = env.zone_latency("A")
        self.assertAlmostEqual(a["mean_ms"], 25)
        self.assertFalse(a["overloaded"])
        for z in ("B", "C"):       # B: load 300 vs cap 250, C: load 300 vs cap 150
            r = env.zone_latency(z)
            self.assertTrue(r["overloaded"])
            self.assertEqual(r["p99_ms"], 5000)
    
    def test_shift_basic(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {}})
        env.shift_traffic("B", "A", 50)
        self.assertAlmostEqual(env.split["A"], 0.5)
        self.assertAlmostEqual(env.split["B"], 1/6)
        self.assertAlmostEqual(sum(env.split.values()), 1.0)
        self.assertAlmostEqual(env.start_split["A"], 1/3)   

    def test_shift_bad_input(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {}})
        before = dict(env.split)
        for args in [("D", "A", 50), ("B", "A", 150), ("B", "B", 10), ("B", "A", "50")]:
            self.assertIn("error", env.shift_traffic(*args))
        self.assertEqual(env.split, before)                
    
    def test_step_flow(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {}})
        self.assertEqual(env.step_used, 0)

        result = env.step("get_metrics", {"zone": "A"})
        self.assertNotIn("error", result)
        self.assertEqual(env.step_used, 1)

        result = env.step("shift_traffic", {"zone_source": "B",
                                            "zone_destination": "A",
                                            "split_percentage": 50})
        self.assertNotIn("error", result)          # shows the error text if the call failed
        self.assertEqual(env.step_used, 2)
        self.assertAlmostEqual(env.split["A"], 0.5)
        self.assertAlmostEqual(env.split["B"], 1 / 6)

    def test_step_bad_calls(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {}})
        before = dict(env.split)
        self.assertIn("error", env.step("fly_to_moon", {}))
        self.assertIn("error", env.step("get_metrics", {}))        # missing zone
        self.assertEqual(env.split, before)

    def test_step_submit_ends(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {}})
        env.step("submit", {})
        self.assertTrue(env.done)
        self.assertIn("error", env.step("get_metrics", {"zone": "A"}))
        self.assertEqual(env.step_used, 1)       # the refused call wasn't counted

    import inspect
    def test_schemas_match_methods(self):
        env = IncidentEnv()
        for s in env.tool_schema():
            name = s["function"]["name"]
            declared = set(s["function"]["parameters"]["properties"])
            actual = set(inspect.signature(getattr(env, name)).parameters) - {"self"}
            self.assertEqual(declared, actual)
    def test_best_split_brownout(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {"B": 0.5}})
        split = best_split(env)
        self.assertAlmostEqual(split["B"], 0.20)
        # cost of that split: about 0.1333 (check via a grade() on a copy)

    def test_best_split_control(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {}})
        self.assertEqual(best_split(env), env.start_split)    # change nothing

    def test_best_split_impossible(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {"A": 0.3, "B": 0.3, "C": 0.3}})
        self.assertIsNone(best_split(env))     # total capacity 450 < 900 demand
    
    
    def zero_error(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {"B": 0.5}})
        print("target:", best_split(env))
        reward, s = run_oracle(env)
        print("final split:", env.split)
        print("steps used:", env.steps_used)
        print("signals:", s)
        for z in env.ZONES:
            print(z, env.zone_latency(z))
        
    def test_oracle_brownout(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {"B": 0.5}})
        reward, s = run_oracle(env)
        self.assertGreaterEqual(reward, 0.9)
        self.assertAlmostEqual(env.split["B"], 0.20)
        self.assertAlmostEqual(sum(env.split.values()), 1.0)
        self.assertEqual(s["slo_ok"], 1.0)

    def test_oracle_control(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {}})
        reward, _ = run_oracle(env)
        self.assertAlmostEqual(reward, 0.9875)
        self.assertEqual(env.step_used, 1) 
    

    def test_oracle_unsolvable(self):
        env = IncidentEnv()
        env.reset({**SCENARIO, "degraded": {"A": 0.3, "B": 0.3, "C": 0.3}})
        self.assertIsNone(run_oracle(env))
        self.assertEqual(env.step_used, 0)       # didn't touch the env
    
    


if __name__ == "__main__":
    unittest.main()