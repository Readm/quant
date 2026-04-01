"""
factor_library — 自动加载所有已注册的生成因子
=============================================
使用方式：
  from experts.factor_library import GENERATED_FACTORS, GENERATED_TEMPLATES

  GENERATED_FACTORS: dict[str, callable]   # template_key → compute_score fn
  GENERATED_TEMPLATES: list[dict]          # [{key, name, params, type}]
  GENERATED_PARAM_RANGES: dict             # {template_key: {param: [lo, hi]}}
"""

import json
import importlib.util
import sys
from pathlib import Path

_FACTOR_DIR = Path(__file__).parent / "factors"
_REGISTRY   = Path(__file__).parent / "registry.json"

GENERATED_FACTORS:      dict = {}   # key → compute_score(closes, data, inds, ext, params, t)
GENERATED_TEMPLATES:    list = []   # [{key, name, params, type}]
GENERATED_PARAM_RANGES: dict = {}   # {key: {param: [lo, hi]}}

_loaded = False


def _load():
    global _loaded
    if _loaded:
        return
    _loaded = True

    if not _FACTOR_DIR.exists():
        return

    registry = {}
    if _REGISTRY.exists():
        try:
            registry = json.loads(_REGISTRY.read_text(encoding="utf-8"))
        except Exception:
            pass

    for py_file in sorted(_FACTOR_DIR.glob("*.py")):
        key = py_file.stem
        try:
            spec   = importlib.util.spec_from_file_location(f"_gf_{key}", py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            fn = getattr(module, "compute_score", None)
            if not callable(fn):
                continue

            GENERATED_FACTORS[key] = fn

            # 从模块或注册表获取元数据
            name   = getattr(module, "TEMPLATE_NAME",  registry.get(key, {}).get("name_cn", key))
            stype  = getattr(module, "STRATEGY_TYPE",  registry.get(key, {}).get("type", "trend"))
            params = getattr(module, "DEFAULT_PARAMS",  {})
            ranges = getattr(module, "PARAM_RANGES",    {})

            GENERATED_TEMPLATES.append({
                "key":    key,
                "name":   name,
                "type":   stype,
                "params": params,
            })
            if ranges:
                GENERATED_PARAM_RANGES[key] = ranges

        except Exception as e:
            print(f"  [因子库] 加载 {py_file.name} 失败: {e}")

    if GENERATED_FACTORS:
        print(f"  [因子库] 加载 {len(GENERATED_FACTORS)} 个生成因子: "
              f"{list(GENERATED_FACTORS.keys())}")


_load()
