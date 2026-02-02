"""Tool package utilities."""

import importlib
import inspect
import pkgutil
from typing import Iterable, List

from .base import BaseTool

TOOL_PROFILES = {
    # Pi-like default coding toolset: small, practical, deterministic.
    "coding": [
        "bashtool",
        "filecontentreadertool",
        "filecreatortool",
        "fileedittool",
        "multiedittool",
        "diffeditortool",
        "lstool",
        "globtool",
        "greptool",
        "lintingtool",
        "todowritetool",
    ],
    "minimal": [
        "bashtool",
        "filecontentreadertool",
        "filecreatortool",
        "fileedittool",
    ],
    "full": None,  # resolved to all discovered tools
}


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


def get_tools_for_profile(
    profile: str = "coding",
    *,
    include: Iterable[str] = (),
    exclude: Iterable[str] = (),
) -> List[BaseTool]:
    """Load tools for a named profile with optional include/exclude overrides."""
    tools = get_all_tools()
    by_name = {tool.name: tool for tool in tools}
    include_set = set(include)
    exclude_set = set(exclude)

    if profile not in TOOL_PROFILES:
        raise ValueError(
            f"Unknown tool profile '{profile}'. Available: {', '.join(sorted(TOOL_PROFILES.keys()))}"
        )

    profile_names = TOOL_PROFILES[profile]
    if profile_names is None:
        selected_names = set(by_name.keys())
    else:
        selected_names = set(profile_names)

    selected_names |= include_set
    selected_names -= exclude_set

    # Keep stable order from discovery for determinism.
    return [tool for tool in tools if tool.name in selected_names]


__all__ = [
    "BaseTool",
    "get_all_tools",
    "get_tools_for_profile",
    "TOOL_PROFILES",
]
