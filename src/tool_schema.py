SHIFT_TRAFFIC_SCHEMA = {
  "type": "function",
  "function": {
    "name": "shift_traffic",
    "description": "Move a percentage of one zone's traffic to another zone.",
    "parameters": {
      "type": "object",
      "properties": {
        "zone_source":       {"type": "string", "enum": ["A", "B", "C"]},
        "zone_destination":  {"type": "string", "enum": ["A", "B", "C"]},
        "split_percentage":  {"type": "number", "description": "0 to 100, percent of the source's traffic"}
      },
      "required": ["zone_source", "zone_destination", "split_percentage"]
    }
  }
}

GET_METRICS_SCHEMA = {
  "type": "function",
  "function": {
    "name": "get_metrics",
    "description": "Get load, mean latency, p99 latency and the overloaded flag for one zone.",
    "parameters": {
      "type": "object",
      "properties": {
        "zone": {"type": "string", "enum": ["A", "B", "C"]}
      },
      "required": ["zone"]
    }
  }
}

SUBMIT_SCHEMA = {
  "type": "function",
  "function": {
    "name": "submit",
    "description": "End the episode. Call this when the incident is fixed.",
    "parameters": {"type": "object", "properties": {}, "required": []}
  }

}