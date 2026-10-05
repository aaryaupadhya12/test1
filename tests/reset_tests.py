import unittest
from src.env import IncidentEnv

class TestEnv(unittest.TestCase):
    def test_two_degraded(self):
        env = IncidentEnv()
        env.reset({"arrivals": 900, "capacity": 500, "base_delay": 20,
                   "degraded": {"B": 0.5, "C": 0.3}})
        self.assertEqual(env.capacity, {"A": 500, "B": 250.0, "C": 150.0})
        self.assertEqual(env.delay, {"A": 20, "B": 40, "C": 40})

if __name__ == "__main__":
    unittest.main()