"""
Project context generation for LLM calls.

Generates structured context about a codebase to help
LLMs understand the project structure and available symbols.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .codebase import CodebaseIndexer, ProjectIndex, Symbol, SymbolKind


@dataclass
class ProjectContext:
    """
    Context about a project for LLM consumption.

    Summarizes project structure, key symbols, and
    conventions to help the LLM understand the codebase.
    """
    name: str
    root_path: str
    summary: str = ""
    languages: List[str] = field(default_factory=list)
    frameworks: List[str] = field(default_factory=list)
    key_files: List[str] = field(default_factory=list)
    entry_points: List[str] = field(default_factory=list)
    conventions: List[str] = field(default_factory=list)
    file_count: int = 0
    symbol_count: int = 0

    def to_prompt(self) -> str:
        """
        Convert to prompt-ready text.

        Returns:
            Formatted context for LLM system prompt
        """
        parts = []

        parts.append(f"## Project: {self.name}")
        parts.append(f"Root: {self.root_path}")

        if self.summary:
            parts.append(f"\n{self.summary}")

        if self.languages:
            parts.append(f"\n**Languages**: {', '.join(self.languages)}")

        if self.frameworks:
            parts.append(f"**Frameworks**: {', '.join(self.frameworks)}")

        parts.append(f"**Files**: {self.file_count}")
        parts.append(f"**Symbols**: {self.symbol_count}")

        if self.key_files:
            parts.append("\n**Key Files**:")
            for f in self.key_files[:10]:
                parts.append(f"- {f}")

        if self.entry_points:
            parts.append("\n**Entry Points**:")
            for e in self.entry_points:
                parts.append(f"- {e}")

        if self.conventions:
            parts.append("\n**Conventions**:")
            for c in self.conventions:
                parts.append(f"- {c}")

        return "\n".join(parts)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "root_path": self.root_path,
            "summary": self.summary,
            "languages": self.languages,
            "frameworks": self.frameworks,
            "key_files": self.key_files,
            "entry_points": self.entry_points,
            "conventions": self.conventions,
            "file_count": self.file_count,
            "symbol_count": self.symbol_count,
        }


@dataclass
class SymbolContext:
    """Context about a specific symbol."""
    name: str
    kind: str
    file_path: str
    line: int
    signature: str = ""
    docstring: str = ""
    related_symbols: List[str] = field(default_factory=list)

    def to_prompt(self) -> str:
        """Convert to prompt-ready text."""
        parts = [f"**{self.kind}**: `{self.name}`"]
        parts.append(f"Location: {self.file_path}:{self.line}")

        if self.signature:
            parts.append(f"```\n{self.signature}\n```")

        if self.docstring:
            parts.append(self.docstring)

        if self.related_symbols:
            parts.append(f"Related: {', '.join(self.related_symbols[:5])}")

        return "\n".join(parts)


class CodebaseContext:
    """
    Generate context about a codebase for LLM calls.

    Analyzes the codebase index to produce summaries
    and relevant context for different tasks.

    Usage:
        indexer = CodebaseIndexer(path)
        await indexer.index()

        context = CodebaseContext(indexer)
        project_ctx = context.get_project_context()
        symbol_ctx = context.get_symbol_context("MyClass")
    """

    # Known frameworks by marker files/imports
    FRAMEWORK_MARKERS = {
        "django": ["django", "settings.py", "urls.py"],
        "flask": ["flask", "app.py"],
        "fastapi": ["fastapi"],
        "react": ["react", "jsx", "tsx"],
        "vue": ["vue", ".vue"],
        "angular": ["@angular"],
        "express": ["express"],
        "nextjs": ["next.config"],
        "pytest": ["pytest", "conftest.py"],
        "sqlalchemy": ["sqlalchemy"],
        "tensorflow": ["tensorflow", "keras"],
        "pytorch": ["torch"],
    }

    # Key file patterns
    KEY_FILE_PATTERNS = [
        "main.py", "app.py", "index.py", "cli.py",
        "main.js", "index.js", "app.js",
        "main.ts", "index.ts", "app.ts",
        "setup.py", "pyproject.toml", "package.json",
        "Cargo.toml", "go.mod", "pom.xml",
        "README.md", "README.rst",
        "Dockerfile", "docker-compose.yml",
        ".env.example", "config.py", "settings.py",
    ]

    def __init__(self, indexer: "CodebaseIndexer"):
        """
        Initialize context generator.

        Args:
            indexer: Codebase indexer with built index
        """
        self.indexer = indexer
        self._index = indexer._index

    def get_project_context(self) -> ProjectContext:
        """
        Generate project context.

        Returns:
            ProjectContext with project summary
        """
        if not self._index:
            return ProjectContext(
                name="Unknown",
                root_path=str(self.indexer.root_path),
            )

        # Detect frameworks
        frameworks = self._detect_frameworks()

        # Find key files
        key_files = self._find_key_files()

        # Find entry points
        entry_points = self._find_entry_points()

        # Infer conventions
        conventions = self._infer_conventions()

        # Generate summary
        summary = self._generate_summary(frameworks)

        return ProjectContext(
            name=self._index.name,
            root_path=self._index.root_path,
            summary=summary,
            languages=list(self._index.languages),
            frameworks=frameworks,
            key_files=key_files,
            entry_points=entry_points,
            conventions=conventions,
            file_count=self._index.file_count,
            symbol_count=self._index.total_symbols,
        )

    def _detect_frameworks(self) -> List[str]:
        """Detect frameworks used in the project."""
        detected = []

        # Check imports and file names
        all_imports = set()
        all_files = set()

        for file_idx in self._index.files.values():
            all_imports.update(file_idx.imports)
            all_files.add(Path(file_idx.path).name)

        for framework, markers in self.FRAMEWORK_MARKERS.items():
            for marker in markers:
                # Check imports
                if any(marker in imp for imp in all_imports):
                    detected.append(framework)
                    break
                # Check files
                if any(marker in f for f in all_files):
                    detected.append(framework)
                    break

        return list(set(detected))

    def _find_key_files(self) -> List[str]:
        """Find key files in the project."""
        key_files = []

        for pattern in self.KEY_FILE_PATTERNS:
            for file_path in self._index.files:
                if Path(file_path).name == pattern or file_path.endswith(pattern):
                    key_files.append(file_path)

        return sorted(set(key_files))[:15]

    def _find_entry_points(self) -> List[str]:
        """Find entry points (main functions, CLI commands)."""
        from .codebase import SymbolKind

        entry_points = []

        for file_idx in self._index.files.values():
            for symbol in file_idx.symbols:
                # Look for main functions
                if symbol.name in ("main", "cli", "app", "run"):
                    entry_points.append(f"{file_idx.path}:{symbol.name}")

                # Look for if __name__ == "__main__" patterns
                if symbol.kind == SymbolKind.FUNCTION:
                    if "main" in file_idx.path:
                        entry_points.append(f"{file_idx.path}:{symbol.name}")

        return entry_points[:10]

    def _infer_conventions(self) -> List[str]:
        """Infer coding conventions from the codebase."""
        conventions = []

        # Check for type hints (Python)
        has_type_hints = False
        for file_idx in self._index.files.values():
            if file_idx.language == "python":
                for symbol in file_idx.symbols:
                    if "->" in symbol.signature or ":" in symbol.signature:
                        has_type_hints = True
                        break

        if has_type_hints:
            conventions.append("Uses type hints")

        # Check for docstrings
        has_docstrings = False
        for file_idx in self._index.files.values():
            for symbol in file_idx.symbols:
                if symbol.docstring:
                    has_docstrings = True
                    break

        if has_docstrings:
            conventions.append("Includes docstrings")

        # Check for tests
        has_tests = any("test" in f.lower() for f in self._index.files)
        if has_tests:
            conventions.append("Has test files")

        # Check for async code
        has_async = any(
            "async" in s.signature
            for f in self._index.files.values()
            for s in f.symbols
        )
        if has_async:
            conventions.append("Uses async/await")

        return conventions

    def _generate_summary(self, frameworks: List[str]) -> str:
        """Generate a brief project summary."""
        parts = []

        # Main language
        lang_counts = {}
        for f in self._index.files.values():
            lang_counts[f.language] = lang_counts.get(f.language, 0) + 1

        if lang_counts:
            main_lang = max(lang_counts, key=lang_counts.get)
            parts.append(f"A {main_lang} project")

        # Frameworks
        if frameworks:
            parts.append(f"using {', '.join(frameworks[:3])}")

        # Size
        if self._index.file_count > 100:
            parts.append("(large codebase)")
        elif self._index.file_count > 20:
            parts.append("(medium codebase)")
        else:
            parts.append("(small codebase)")

        return " ".join(parts) + "."

    def get_symbol_context(
        self,
        name: str,
        include_related: bool = True,
    ) -> Optional[SymbolContext]:
        """
        Get context for a specific symbol.

        Args:
            name: Symbol name
            include_related: Include related symbols

        Returns:
            SymbolContext or None if not found
        """
        symbol = self.indexer.get_definition(name)
        if not symbol:
            return None

        related = []
        if include_related:
            # Find symbols in same file
            file_idx = self._index.get_file(symbol.file_path)
            if file_idx:
                related = [s.name for s in file_idx.symbols if s.name != name][:5]

        return SymbolContext(
            name=symbol.name,
            kind=symbol.kind.value,
            file_path=symbol.file_path,
            line=symbol.line_start,
            signature=symbol.signature,
            docstring=symbol.docstring,
            related_symbols=related,
        )

    def get_file_context(
        self,
        path: str,
        include_content: bool = False,
        max_lines: int = 100,
    ) -> Optional[Dict[str, Any]]:
        """
        Get context for a specific file.

        Args:
            path: File path
            include_content: Include file content
            max_lines: Maximum lines to include

        Returns:
            File context dict or None
        """
        file_idx = self._index.get_file(path)
        if not file_idx:
            return None

        context = {
            "path": file_idx.path,
            "language": file_idx.language,
            "lines": file_idx.line_count,
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind.value,
                    "line": s.line_start,
                    "signature": s.signature,
                }
                for s in file_idx.symbols
            ],
            "imports": file_idx.imports,
            "exports": file_idx.exports,
        }

        if include_content:
            try:
                full_path = Path(self._index.root_path) / path
                content = full_path.read_text(encoding="utf-8", errors="replace")
                lines = content.split("\n")
                if len(lines) > max_lines:
                    lines = lines[:max_lines]
                    lines.append(f"... ({file_idx.line_count - max_lines} more lines)")
                context["content"] = "\n".join(lines)
            except Exception:
                pass

        return context

    def get_relevant_context(
        self,
        query: str,
        max_symbols: int = 20,
        max_files: int = 10,
    ) -> Dict[str, Any]:
        """
        Get context relevant to a query.

        Args:
            query: Search query
            max_symbols: Maximum symbols to include
            max_files: Maximum files to include

        Returns:
            Dict with relevant context
        """
        # Search for matching symbols
        symbols = self.indexer.search(f"*{query}*", limit=max_symbols)

        # Get unique files
        files = set(s.file_path for s in symbols)

        return {
            "symbols": [
                {
                    "name": s.name,
                    "kind": s.kind.value,
                    "file": s.file_path,
                    "line": s.line_start,
                    "signature": s.signature,
                }
                for s in symbols
            ],
            "files": list(files)[:max_files],
            "query": query,
        }

    def to_prompt(
        self,
        include_structure: bool = True,
        include_key_symbols: bool = True,
        max_symbols: int = 30,
    ) -> str:
        """
        Generate full context as prompt text.

        Args:
            include_structure: Include project structure
            include_key_symbols: Include key symbol list
            max_symbols: Maximum symbols to include

        Returns:
            Formatted prompt text
        """
        from .codebase import SymbolKind

        parts = []

        # Project context
        project = self.get_project_context()
        parts.append(project.to_prompt())

        # Project structure
        if include_structure:
            structure = self.indexer.get_structure()
            parts.append("\n## Directory Structure")
            for d in structure.get("directories", [])[:20]:
                parts.append(f"  {d}/")

        # Key symbols
        if include_key_symbols:
            parts.append("\n## Key Symbols")

            # Classes
            classes = self._index.get_all_symbols(SymbolKind.CLASS)[:max_symbols // 3]
            if classes:
                parts.append("\n**Classes**:")
                for c in classes:
                    parts.append(f"- `{c.qualified_name}` ({c.file_path})")

            # Functions
            functions = self._index.get_all_symbols(SymbolKind.FUNCTION)[:max_symbols // 3]
            if functions:
                parts.append("\n**Functions**:")
                for f in functions:
                    parts.append(f"- `{f.name}` ({f.file_path})")

        return "\n".join(parts)
