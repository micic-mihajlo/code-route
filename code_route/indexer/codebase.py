"""
Codebase indexer for Code Route.

Provides file and symbol indexing for codebase understanding,
navigation, and context generation.
"""

import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple
import fnmatch


class SymbolKind(Enum):
    """Types of code symbols."""
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    METHOD = "method"
    PROPERTY = "property"
    VARIABLE = "variable"
    CONSTANT = "constant"
    INTERFACE = "interface"
    TYPE = "type"
    ENUM = "enum"
    IMPORT = "import"
    EXPORT = "export"


@dataclass
class Symbol:
    """A code symbol (class, function, variable, etc.)."""
    name: str
    kind: SymbolKind
    file_path: str
    line_start: int
    line_end: int
    column_start: int = 0
    column_end: int = 0
    signature: str = ""
    docstring: str = ""
    parent: Optional[str] = None  # Parent symbol name
    children: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def qualified_name(self) -> str:
        """Get fully qualified name."""
        if self.parent:
            return f"{self.parent}.{self.name}"
        return self.name

    @property
    def location(self) -> str:
        """Get location string."""
        return f"{self.file_path}:{self.line_start}"


@dataclass
class FileIndex:
    """Index for a single file."""
    path: str
    language: str
    size_bytes: int
    line_count: int
    symbols: List[Symbol] = field(default_factory=list)
    imports: List[str] = field(default_factory=list)
    exports: List[str] = field(default_factory=list)
    hash: str = ""
    indexed_at: datetime = field(default_factory=datetime.now)

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)

    def get_symbol(self, name: str) -> Optional[Symbol]:
        """Get symbol by name."""
        for sym in self.symbols:
            if sym.name == name or sym.qualified_name == name:
                return sym
        return None

    def get_symbols_by_kind(self, kind: SymbolKind) -> List[Symbol]:
        """Get symbols of a specific kind."""
        return [s for s in self.symbols if s.kind == kind]


@dataclass
class ProjectIndex:
    """Index for an entire project."""
    root_path: str
    name: str
    files: Dict[str, FileIndex] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def file_count(self) -> int:
        return len(self.files)

    @property
    def total_symbols(self) -> int:
        return sum(f.symbol_count for f in self.files.values())

    @property
    def languages(self) -> Set[str]:
        return {f.language for f in self.files.values()}

    def get_file(self, path: str) -> Optional[FileIndex]:
        """Get file index by path."""
        # Try exact match first
        if path in self.files:
            return self.files[path]

        # Try relative path
        for file_path, file_idx in self.files.items():
            if file_path.endswith(path) or path.endswith(file_path):
                return file_idx

        return None

    def search_symbols(
        self,
        query: str,
        kind: Optional[SymbolKind] = None,
        file_pattern: Optional[str] = None,
    ) -> List[Symbol]:
        """
        Search for symbols.

        Args:
            query: Name pattern (supports wildcards)
            kind: Filter by symbol kind
            file_pattern: Filter by file pattern

        Returns:
            Matching symbols
        """
        results = []

        for file_path, file_idx in self.files.items():
            # Apply file pattern filter
            if file_pattern and not fnmatch.fnmatch(file_path, file_pattern):
                continue

            for symbol in file_idx.symbols:
                # Apply kind filter
                if kind and symbol.kind != kind:
                    continue

                # Apply name pattern
                if fnmatch.fnmatch(symbol.name.lower(), query.lower()):
                    results.append(symbol)
                elif fnmatch.fnmatch(symbol.qualified_name.lower(), query.lower()):
                    results.append(symbol)

        return results

    def get_all_symbols(self, kind: Optional[SymbolKind] = None) -> List[Symbol]:
        """Get all symbols, optionally filtered by kind."""
        symbols = []
        for file_idx in self.files.values():
            if kind:
                symbols.extend(file_idx.get_symbols_by_kind(kind))
            else:
                symbols.extend(file_idx.symbols)
        return symbols


class CodebaseIndexer:
    """
    Index a codebase for symbol extraction and navigation.

    Uses tree-sitter for parsing when available, falls back
    to regex-based extraction.

    Usage:
        indexer = CodebaseIndexer("/my/project")
        index = await indexer.index()

        # Search for symbols
        classes = index.search_symbols("*Service", kind=SymbolKind.CLASS)

        # Get specific file
        file_idx = index.get_file("src/main.py")
    """

    # File patterns to include by default
    DEFAULT_INCLUDE = [
        "*.py", "*.js", "*.ts", "*.tsx", "*.jsx",
        "*.java", "*.go", "*.rs", "*.rb", "*.php",
        "*.c", "*.cpp", "*.h", "*.hpp",
        "*.cs", "*.swift", "*.kt",
    ]

    # Directories to exclude
    DEFAULT_EXCLUDE = [
        "__pycache__", "node_modules", ".git", ".venv", "venv",
        "dist", "build", ".tox", ".pytest_cache", ".mypy_cache",
        "*.egg-info", ".eggs", "target", "out",
    ]

    # Language detection by extension
    LANGUAGE_MAP = {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".tsx": "typescript",
        ".jsx": "javascript",
        ".java": "java",
        ".go": "go",
        ".rs": "rust",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".swift": "swift",
        ".kt": "kotlin",
    }

    def __init__(
        self,
        root_path: Path,
        include_patterns: Optional[List[str]] = None,
        exclude_patterns: Optional[List[str]] = None,
    ):
        """
        Initialize indexer.

        Args:
            root_path: Project root directory
            include_patterns: File patterns to include
            exclude_patterns: Directory/file patterns to exclude
        """
        self.root_path = Path(root_path).resolve()
        self.include_patterns = include_patterns or self.DEFAULT_INCLUDE
        self.exclude_patterns = exclude_patterns or self.DEFAULT_EXCLUDE

        self._extractors: Dict[str, "SymbolExtractor"] = {}
        self._index: Optional[ProjectIndex] = None

    def _should_include(self, path: Path) -> bool:
        """Check if file should be included."""
        # Check exclude patterns
        for pattern in self.exclude_patterns:
            if any(fnmatch.fnmatch(part, pattern) for part in path.parts):
                return False

        # Check include patterns
        for pattern in self.include_patterns:
            if fnmatch.fnmatch(path.name, pattern):
                return True

        return False

    def _detect_language(self, path: Path) -> str:
        """Detect language from file extension."""
        return self.LANGUAGE_MAP.get(path.suffix.lower(), "unknown")

    def _get_extractor(self, language: str) -> Optional["SymbolExtractor"]:
        """Get symbol extractor for language."""
        if language not in self._extractors:
            from .symbols import get_extractor
            self._extractors[language] = get_extractor(language)
        return self._extractors.get(language)

    def _compute_hash(self, content: str) -> str:
        """Compute content hash."""
        return hashlib.md5(content.encode()).hexdigest()[:16]

    async def _index_file(self, path: Path) -> Optional[FileIndex]:
        """Index a single file."""
        try:
            content = path.read_text(encoding="utf-8", errors="replace")
            language = self._detect_language(path)
            lines = content.split("\n")

            # Get symbols
            symbols = []
            imports = []
            exports = []

            extractor = self._get_extractor(language)
            if extractor:
                symbols = extractor.extract(content, str(path))
                imports = extractor.extract_imports(content)
                exports = extractor.extract_exports(content)

            rel_path = str(path.relative_to(self.root_path))

            return FileIndex(
                path=rel_path,
                language=language,
                size_bytes=len(content),
                line_count=len(lines),
                symbols=symbols,
                imports=imports,
                exports=exports,
                hash=self._compute_hash(content),
            )

        except Exception as e:
            # Log error but don't fail
            return None

    async def index(self, incremental: bool = True) -> ProjectIndex:
        """
        Index the codebase.

        Args:
            incremental: Only reindex changed files

        Returns:
            ProjectIndex with all symbols
        """
        # Get all files to index
        files_to_index = []
        for path in self.root_path.rglob("*"):
            if path.is_file() and self._should_include(path):
                files_to_index.append(path)

        # Index files concurrently
        tasks = [self._index_file(path) for path in files_to_index]
        results = await asyncio.gather(*tasks)

        # Build index
        files = {}
        for file_idx in results:
            if file_idx:
                files[file_idx.path] = file_idx

        self._index = ProjectIndex(
            root_path=str(self.root_path),
            name=self.root_path.name,
            files=files,
            metadata={
                "include_patterns": self.include_patterns,
                "exclude_patterns": self.exclude_patterns,
            }
        )

        return self._index

    async def update(self, paths: List[Path]) -> ProjectIndex:
        """
        Update index for specific files.

        Args:
            paths: Files to reindex

        Returns:
            Updated ProjectIndex
        """
        if not self._index:
            return await self.index()

        for path in paths:
            if path.is_file() and self._should_include(path):
                file_idx = await self._index_file(path)
                if file_idx:
                    self._index.files[file_idx.path] = file_idx

        self._index.updated_at = datetime.now()
        return self._index

    def search(
        self,
        query: str,
        kind: Optional[SymbolKind] = None,
        file_pattern: Optional[str] = None,
        limit: int = 50,
    ) -> List[Symbol]:
        """
        Search for symbols.

        Args:
            query: Name pattern
            kind: Symbol kind filter
            file_pattern: File pattern filter
            limit: Maximum results

        Returns:
            Matching symbols
        """
        if not self._index:
            return []

        results = self._index.search_symbols(query, kind, file_pattern)
        return results[:limit]

    def get_definition(self, name: str) -> Optional[Symbol]:
        """Get symbol definition by name."""
        if not self._index:
            return None

        # Search all files
        for file_idx in self._index.files.values():
            symbol = file_idx.get_symbol(name)
            if symbol:
                return symbol

        return None

    def get_references(
        self,
        name: str,
        include_definition: bool = True,
    ) -> List[Tuple[str, int]]:
        """
        Find references to a symbol.

        Args:
            name: Symbol name
            include_definition: Include definition location

        Returns:
            List of (file_path, line_number) tuples
        """
        if not self._index:
            return []

        references = []

        for file_path, file_idx in self._index.files.items():
            # Simple text search (full implementation would use AST)
            try:
                content = (self.root_path / file_path).read_text(
                    encoding="utf-8", errors="replace"
                )
                for i, line in enumerate(content.split("\n"), 1):
                    if name in line:
                        # Check if it's the definition
                        is_def = any(
                            s.name == name and s.line_start == i
                            for s in file_idx.symbols
                        )
                        if include_definition or not is_def:
                            references.append((file_path, i))
            except Exception:
                pass

        return references

    def get_file_symbols(self, path: str) -> List[Symbol]:
        """Get all symbols in a file."""
        if not self._index:
            return []

        file_idx = self._index.get_file(path)
        return file_idx.symbols if file_idx else []

    def get_structure(self) -> Dict[str, Any]:
        """
        Get project structure summary.

        Returns:
            Dict with project statistics and structure
        """
        if not self._index:
            return {}

        # Count symbols by kind
        symbol_counts = {}
        for kind in SymbolKind:
            symbols = self._index.get_all_symbols(kind)
            if symbols:
                symbol_counts[kind.value] = len(symbols)

        # Count files by language
        lang_counts = {}
        for file_idx in self._index.files.values():
            lang = file_idx.language
            lang_counts[lang] = lang_counts.get(lang, 0) + 1

        # Build directory tree
        dirs = set()
        for file_path in self._index.files:
            path = Path(file_path)
            for parent in path.parents:
                if str(parent) != ".":
                    dirs.add(str(parent))

        return {
            "name": self._index.name,
            "root": self._index.root_path,
            "files": self._index.file_count,
            "symbols": self._index.total_symbols,
            "languages": list(self._index.languages),
            "symbol_counts": symbol_counts,
            "language_counts": lang_counts,
            "directories": sorted(dirs),
        }

    def save(self, path: Path) -> None:
        """Save index to file."""
        if not self._index:
            return

        data = {
            "root_path": self._index.root_path,
            "name": self._index.name,
            "created_at": self._index.created_at.isoformat(),
            "updated_at": self._index.updated_at.isoformat(),
            "metadata": self._index.metadata,
            "files": {
                file_path: {
                    "path": file_idx.path,
                    "language": file_idx.language,
                    "size_bytes": file_idx.size_bytes,
                    "line_count": file_idx.line_count,
                    "hash": file_idx.hash,
                    "imports": file_idx.imports,
                    "exports": file_idx.exports,
                    "symbols": [
                        {
                            "name": s.name,
                            "kind": s.kind.value,
                            "line_start": s.line_start,
                            "line_end": s.line_end,
                            "signature": s.signature,
                            "docstring": s.docstring,
                            "parent": s.parent,
                        }
                        for s in file_idx.symbols
                    ],
                }
                for file_path, file_idx in self._index.files.items()
            },
        }

        path.write_text(json.dumps(data, indent=2))

    @classmethod
    def load(cls, path: Path) -> "CodebaseIndexer":
        """Load index from file."""
        data = json.loads(path.read_text())

        indexer = cls(Path(data["root_path"]))

        files = {}
        for file_path, file_data in data.get("files", {}).items():
            symbols = [
                Symbol(
                    name=s["name"],
                    kind=SymbolKind(s["kind"]),
                    file_path=file_data["path"],
                    line_start=s["line_start"],
                    line_end=s["line_end"],
                    signature=s.get("signature", ""),
                    docstring=s.get("docstring", ""),
                    parent=s.get("parent"),
                )
                for s in file_data.get("symbols", [])
            ]

            files[file_path] = FileIndex(
                path=file_data["path"],
                language=file_data["language"],
                size_bytes=file_data["size_bytes"],
                line_count=file_data["line_count"],
                hash=file_data.get("hash", ""),
                imports=file_data.get("imports", []),
                exports=file_data.get("exports", []),
                symbols=symbols,
            )

        indexer._index = ProjectIndex(
            root_path=data["root_path"],
            name=data["name"],
            files=files,
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            metadata=data.get("metadata", {}),
        )

        return indexer
