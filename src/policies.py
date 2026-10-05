import copy
import random
from .env import IncidentEnv
def do_nothing(env):
        env.step("submit", {})
        return env.grade()

def random_policy(env, seed, n_moves=3):
    rng = random.Random(seed)
    for _ in range(n_moves):
        zone_source, zone_destination = rng.sample(env.ZONES, 2)
        split_percentage = rng.choice([10, 25, 50])
        env.step("shift_traffic", {"zone_source": zone_source,
                                    "zone_destination": zone_destination,
                                    "split_percentage": split_percentage})
    env.step("submit", {})
    return env.grade()


def best_split(env):
        # candidate 0: change nothing (the start split isn't on the 5% grid)
    candidates = [dict(env.start_split)]

        # every split on a 5% grid: a + b + c = 100
    for a in range(0, 101, 5):
        for b in range(0, 101 - a, 5):
            c = 100 - a - b
            candidates.append(dict(zip(env.ZONES, (a / 100, b / 100, c / 100))))

    best, best_cost = None, None
    for split in candidates:
        trial = copy.deepcopy(env)       # test on a copy, never on the real env
        trial.split = split
        _, s = trial.grade()             
        valid = s["slo_ok"] == 1.0 and s["cost_ok"] == 1.0 and not s["overloaded"]
        if valid and (best is None or s["cost"] < best_cost - 1e-9):
            best, best_cost = split, s["cost"]
    return best       

def run_oracle(env):
    target = best_split(env)
    if target is None:
        return None
    difference = {z : target[z] - env.split[z] for z in env.ZONES}
    still_to_give = {z : -d for z , d in difference.items() if d < -1e-9}
    still_to_get = {z: d for z , d in difference.items() if d > 1e-9}

    for zone_source in still_to_give:
        for zone_destination in still_to_get:
            amount = min(still_to_give[zone_source], still_to_get[zone_destination])
            if amount > -1e-9:
                split_percentage = min(100.0, amount / env.split[zone_source] * 100)
                result = env.step("shift_traffic", {"zone_source": zone_source,
                                                "zone_destination": zone_destination,
                                                "split_percentage": split_percentage})
                if "error" in result:
                    raise RuntimeError(f"oracle shift failed: {result}")   
                still_to_give[zone_source] -= amount
                still_to_get[zone_destination] -= amount
        
    env.step("submit",{})
    return env.grade()




    
    
