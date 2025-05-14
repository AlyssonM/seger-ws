# src/utils/dict_diff.py
from typing import Any, Dict

def _flat(d: Dict[str, Any], prefix: str = "") -> Dict[str, Any]:
    """Achata dicionário em 'a.b.c': valor."""
    out = {}
    for k, v in d.items():
        path = f"{prefix}.{k}" if prefix else k
        if isinstance(v, dict):
            out.update(_flat(v, path))
        else:
            out[path] = v
    return out

def dict_diff(a: Dict[str, Any], b: Dict[str, Any]) -> Dict[str, Any]:
    flat_a, flat_b = _flat(a), _flat(b)
    missing_in_a   = {k: flat_b[k] for k in flat_b if k not in flat_a}
    missing_in_b   = {k: flat_a[k] for k in flat_a if k not in flat_b}
    different_vals = {
        k: {"regex": flat_a[k], "llm": flat_b[k]}
        for k in flat_a.keys() & flat_b.keys()
        if flat_a[k] != flat_b[k]
    }
    return {
        "missing_in_regex": missing_in_a,
        "missing_in_llm":   missing_in_b,
        "different_values": different_vals,
    }

def has_diff(diff: dict) -> bool:
    return any(diff[key] for key in ("missing_in_regex",
                                     "missing_in_llm",
                                     "different_values"))
