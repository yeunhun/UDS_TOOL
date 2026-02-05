import json
from typing import Any, Dict, List, Union

def load_config(file_path: str) -> Dict[str, Any]:
    with open(file_path, 'r') as file:
        return json.load(file)

def get_testcase_paths(config: Dict[str, Any]) -> List[str]:
    """Return testcase path patterns from config.json.

    Supports:
      config["testcase"]["paths"] as list[str] or str
    Example:
      "testcase": {"format": "xlsx", "paths": ["input/supportfiles/*.xlsx"]}
    If missing, returns [] (caller should fallback to legacy behavior).
    """
    testcase_cfg = config.get("testcase", {}) if isinstance(config, dict) else {}
    paths: Union[List[str], str, None] = testcase_cfg.get("paths")

    if paths is None:
        return []
    if isinstance(paths, str):
        return [paths]
    if isinstance(paths, list):
        return [str(p) for p in paths if str(p).strip()]
    return []
