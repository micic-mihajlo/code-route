"""Tool package utilities."""

import importlib
import inspect
import pkgutil
from typing import List

from .base import BaseTool


def get_all_tools() -> List[BaseTool]:
    """Discover and instantiate all importable tools in this package."""
    tools: List[BaseTool] = []

    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name == "base" or module_info.ispkg:
            continue

        try:
            module = importlib.import_module(f"{__name__}.{module_info.name}")
        except Exception:
            # Skip tools with missing optional dependencies.
            continue

        for _, obj in inspect.getmembers(module, inspect.isclass):
            if not issubclass(obj, BaseTool) or obj is BaseTool:
                continue
            try:
                tools.append(obj())
            except Exception:
                continue

    return tools


__all__ = ["BaseTool", "get_all_tools"]
