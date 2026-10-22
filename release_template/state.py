"""Durable intent before side effects, with explicit reconciliation."""

import time
import uuid

from .core import load, require, save


class State:
  def __init__(self, path, identity):
    self.path = path
    if path.exists():
      self.data = load(path)
      require(self.data.get("schema") == 1, "Unknown checkpoint schema")
      require(self.data.get("identity") == identity, "Checkpoint identity differs from this source/config/template")
    else:
      self.data = {"schema": 1, "run": uuid.uuid4().hex, "created": time.time(),
                   "identity": identity, "operations": {}, "outputs": {}, "staging": {},
                   "published": False, "cleanup_complete": False}
      self.flush()

  def flush(self):
    save(self.path, self.data)

  def intent(self, name, details):
    operation = self.data["operations"].get(name)
    if operation:
      require(operation["details"] == details, "Operation intent changed")
      return operation
    operation = {"id": uuid.uuid4().hex, "status": "pending", "details": details}
    self.data["operations"][name] = operation
    self.flush()
    return operation

  def complete(self, name):
    self.data["operations"][name]["status"] = "complete"
    self.flush()
