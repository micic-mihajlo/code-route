"""
Code Route Indexer - Codebase understanding via tree-sitter.

Provides symbol extraction, code navigation, and
project structure analysis.
"""

from .codebase import (
    CodebaseIndexer,
    ProjectIndex,
    FileIndex,
    Symbol,
    SymbolKind,
)
from .symbols import (
    SymbolExtractor,
    PythonExtractor,
    JavaScriptExtractor,
    TypeScriptExtractor,
)
from .context import (
    ProjectContext,
    CodebaseContext,
)

__all__ = [
    # Indexer
    "CodebaseIndexer",
    "ProjectIndex",
    "FileIndex",
    "Symbol",
    "SymbolKind",
    # Extractors
    "SymbolExtractor",
    "PythonExtractor",
    "JavaScriptExtractor",
    "TypeScriptExtractor",
    # Context
    "ProjectContext",
    "CodebaseContext",
]
