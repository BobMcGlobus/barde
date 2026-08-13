"""Test setup.

The ranking and matching modules are deliberately free of Home Assistant
imports. Importing them the normal way would still execute
``custom_components/barde/__init__.py``, which is not. When Home Assistant is
not installed (a quick local run), the package is stubbed so those pure tests
still work; in CI the real package is imported.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import types

_ROOT = Path(__file__).resolve().parent.parent


def _stub_package() -> None:
    """Register custom_components.barde without running its __init__."""
    for name, path in (
        ("custom_components", _ROOT / "custom_components"),
        ("custom_components.barde", _ROOT / "custom_components" / "barde"),
    ):
        if name in sys.modules:
            continue
        module = types.ModuleType(name)
        module.__path__ = [str(path)]  # type: ignore[attr-defined]
        sys.modules[name] = module


if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

if importlib.util.find_spec("homeassistant") is None:
    _stub_package()
