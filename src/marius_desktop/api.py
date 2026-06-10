"""Temporary compatibility shim — use `src.warden.api` instead."""

import src.warden.api as _warden_api

for _name, _value in _warden_api.__dict__.items():
    if _name.startswith("__"):
        continue
    globals()[_name] = _value