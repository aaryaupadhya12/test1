import json
from .contracts import ModelClient, ModelReply, ToolCall, Usage

def call(id, name, args):
    return ToolCall(id, name, args, json.dumps(args))

def bad_call(id, name, raw):                      # malformed JSON from the "model"
    return ToolCall(id, name, {}, raw)

def scripted(*calls, text=""):
    return ModelReply(text, list(calls), Usage(input_tokens=10, output_tokens=5), 1.0)

class FakeModel(ModelClient):
    model_id = "fake"

    def __init__(self, script):
        self.script = list(script)
        self.seen = []                           

    def complete(self, messages, tools, temperature=0.0):
        self.seen.append(list(messages))
        if self.script:
            return self.script.pop(0)
        return scripted(text="(out of script)")   