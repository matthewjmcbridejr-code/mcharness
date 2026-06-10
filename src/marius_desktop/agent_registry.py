"""Temporary compatibility shim — use `src.warden.agent_registry` instead."""

import src.warden.agent_registry as _warden_agent_registry

for _name, _value in _warden_agent_registry.__dict__.items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value