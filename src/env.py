OVERLOADED_MS = 5000
import random
import copy
class IncidentEnv:
    ZONES =("A","B","C")
    def reset(self,scenerio):
        self.capacity = {z : scenerio["capacity"] for z in self.ZONES}
        self.delay = {z: scenerio["base_delay"] for z in self.ZONES}

        self.split ={z : 1/3 for z in self.ZONES}
        self.arrivals = scenerio["arrivals"]

        # degrading multiple zones: so make degraded a dictionary 
        for zone, severity in scenerio["degraded"].items():
            self.capacity[zone] = self.capacity[zone] * severity
            self.delay[zone] = self.delay[zone] * 2 
        
        self.start_split = dict(self.split)

        self.slo_ms = scenerio.get("slo_ms",300)
        self.cost_budget = scenerio.get("cost_budget", 0.4)
        self.max_steps = scenerio.get("max_steps",8)
        self.step_used = 0
        self.done = False

    def zone_latency(self,zone):
        load = self.split[zone] * self.arrivals
        cap = self.capacity[zone]
        base = self.delay[zone]

        if load >= cap:
            overloaded = True
            mean = OVERLOADED_MS
            p99 = OVERLOADED_MS
        else:
            overloaded = False
            mean = base + 1000 / (cap - load)
            p99 = 4.6 * mean

        return {"load": load, "mean_ms": mean, "p99_ms": p99, "overloaded": overloaded}


    def get_metrics(self,zone):
        if zone not in self.ZONES:
            return {"error": f"unknown zone '{zone}'"}
        if not hasattr(self, "split"):
            raise RuntimeError("call reset() before using the environment")
        return self.zone_latency(zone)
    
    def shift_traffic(self,zone_source,zone_destination,split_percentage):
        for zone in (zone_source,zone_destination):
            if zone not in self.ZONES:
                return {"error": f"Unkown'{zone}'"}
        if zone_source == zone_destination:
            return {"error": "sorce and destination for spilling must be different"}
        
        if not isinstance(split_percentage, (int, float)) or split_percentage < 0 or split_percentage > 100:
            return {"error": "pct must be a number between 0 and 100"}
        #Easy way to understnd is Zone one loses and one 2 gains 
        moved = self.split[zone_source] * split_percentage / 100
        self.split[zone_source] = self.split[zone_source] - moved
        self.split[zone_destination] = self.split[zone_destination] + moved

        # create a shallow copy so that the encironemnt state os npt changed all the time 
        return dict(self.split)
    
    def submit(self):
        self.done = True
        return{"status": "submitted"}
    
    def grade(self):
        metrics = {z: self.zone_latency(z) for z in self.ZONES}
        worst_p99 = max(m["p99_ms"] for m in metrics.values())
        overloaded = any(m["overloaded"] for m in metrics.values())

        slo_ok = 1.0 if worst_p99 <= self.slo_ms else 0.0
        cost = sum(max(0,self.split[zone] - self.start_split[zone]) for zone in self.ZONES)
        cost_ok = 1.0 if cost <= self.cost_budget + 1e-9 else 0.0

        efficiency = max(0, 1 - self.step_used / self.max_steps)

        raw = 0.6 * slo_ok + 0.3 * cost_ok + 0.1 * efficiency

        reward = 0.0 if overloaded else raw

        signals = {
            "slo_ok": slo_ok, 
            "cost_ok": cost_ok, 
            "efficiency": efficiency,
               "worst_p99_ms": worst_p99, 
               "cost": cost,
               "overloaded": overloaded, 
               "raw_reward": raw
        }
        
        return reward , signals
    

    def step(self, name , args):
        # submmited 
        if self.done:
            return {"error" : " epsiode is already submmited"}
        
        self.step_used += 1

        tools = {
            "get_metrics": self.get_metrics,
            "shift_traffic": self.shift_traffic,
            "submit": self.submit,
        }

        if name not in tools:
            return {"error" : "bro choose a known tool"}
        
        try:
            return tools[name](**args)
        except TypeError as e:
            return {"error": f"bad argument {e}"}
    

    def tool_schema(self):
        from .tool_schema import GET_METRICS_SCHEMA, SHIFT_TRAFFIC_SCHEMA, SUBMIT_SCHEMA
        return [GET_METRICS_SCHEMA, SHIFT_TRAFFIC_SCHEMA, SUBMIT_SCHEMA]

    
    
                      


    

            


        




