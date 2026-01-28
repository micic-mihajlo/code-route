"""
Symbol extraction for various programming languages.

Uses regex-based extraction with optional tree-sitter support
for more accurate parsing.
"""

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Pattern, TYPE_CHECKING

if TYPE_CHECKING:
    from .codebase import Symbol, SymbolKind


class SymbolExtractor(ABC):
    """Base class for language-specific symbol extractors."""

    @abstractmethod
    def extract(self, content: str, file_path: str) -> List["Symbol"]:
        """
        Extract symbols from source code.

        Args:
            content: Source code content
            file_path: Path to the file

        Returns:
            List of extracted symbols
        """
        pass

    @abstractmethod
    def extract_imports(self, content: str) -> List[str]:
        """Extract import statements."""
        pass

    @abstractmethod
    def extract_exports(self, content: str) -> List[str]:
        """Extract export statements."""
        pass


class PythonExtractor(SymbolExtractor):
    """Symbol extractor for Python code."""

    # Regex patterns
    CLASS_PATTERN = re.compile(
        r'^class\s+(\w+)(?:\s*\(([^)]*)\))?\s*:',
        re.MULTILINE
    )
    FUNCTION_PATTERN = re.compile(
        r'^(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*([^:]+))?\s*:',
        re.MULTILINE
    )
    METHOD_PATTERN = re.compile(
        r'^\s+(?:async\s+)?def\s+(\w+)\s*\(([^)]*)\)(?:\s*->\s*([^:]+))?\s*:',
        re.MULTILINE
    )
    VARIABLE_PATTERN = re.compile(
        r'^(\w+)\s*(?::\s*([^=]+))?\s*=',
        re.MULTILINE
    )
    IMPORT_PATTERN = re.compile(
        r'^(?:from\s+(\S+)\s+)?import\s+(.+)$',
        re.MULTILINE
    )
    CONSTANT_PATTERN = re.compile(
        r'^([A-Z][A-Z0-9_]*)\s*=',
        re.MULTILINE
    )

    def extract(self, content: str, file_path: str) -> List["Symbol"]:
        from .codebase import Symbol, SymbolKind

        symbols = []
        lines = content.split('\n')

        # Extract classes
        for match in self.CLASS_PATTERN.finditer(content):
            name = match.group(1)
            bases = match.group(2) or ""
            line_start = content[:match.start()].count('\n') + 1
            line_end = self._find_block_end(lines, line_start - 1)

            # Extract docstring
            docstring = self._extract_docstring(lines, line_start)

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=f"class {name}({bases})" if bases else f"class {name}",
                docstring=docstring,
            ))

        # Extract functions (top-level)
        for match in self.FUNCTION_PATTERN.finditer(content):
            # Check it's not a method (no indentation)
            start_pos = match.start()
            if start_pos > 0 and content[start_pos - 1] not in '\n':
                continue

            name = match.group(1)
            params = match.group(2) or ""
            return_type = match.group(3) or ""
            line_start = content[:start_pos].count('\n') + 1
            line_end = self._find_block_end(lines, line_start - 1)

            docstring = self._extract_docstring(lines, line_start)

            sig = f"def {name}({params})"
            if return_type:
                sig += f" -> {return_type.strip()}"

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                line_start=line_start,
                line_end=line_end,
                signature=sig,
                docstring=docstring,
            ))

        # Extract constants
        for match in self.CONSTANT_PATTERN.finditer(content):
            name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.CONSTANT,
                file_path=file_path,
                line_start=line,
                line_end=line,
            ))

        return symbols

    def _find_block_end(self, lines: List[str], start_idx: int) -> int:
        """Find the end of an indented block."""
        if start_idx >= len(lines):
            return start_idx + 1

        # Get base indentation
        base_indent = len(lines[start_idx]) - len(lines[start_idx].lstrip())

        # Find where indentation returns to base or less
        for i in range(start_idx + 1, len(lines)):
            line = lines[i]
            if line.strip():  # Non-empty line
                indent = len(line) - len(line.lstrip())
                if indent <= base_indent:
                    return i
        return len(lines)

    def _extract_docstring(self, lines: List[str], start_line: int) -> str:
        """Extract docstring from following lines."""
        if start_line >= len(lines):
            return ""

        # Look for docstring on next non-empty line
        for i in range(start_line, min(start_line + 3, len(lines))):
            line = lines[i].strip()
            if line.startswith('"""') or line.startswith("'''"):
                # Single line docstring
                if line.count('"""') >= 2 or line.count("'''") >= 2:
                    quote = '"""' if '"""' in line else "'''"
                    return line.strip(quote).strip()

                # Multi-line docstring
                quote = '"""' if line.startswith('"""') else "'''"
                doc_lines = [line[3:]]
                for j in range(i + 1, len(lines)):
                    if quote in lines[j]:
                        doc_lines.append(lines[j].split(quote)[0])
                        break
                    doc_lines.append(lines[j].strip())
                return "\n".join(doc_lines).strip()

        return ""

    def extract_imports(self, content: str) -> List[str]:
        imports = []
        for match in self.IMPORT_PATTERN.finditer(content):
            from_module = match.group(1)
            import_part = match.group(2)

            if from_module:
                imports.append(f"from {from_module} import {import_part}")
            else:
                imports.append(f"import {import_part}")

        return imports

    def extract_exports(self, content: str) -> List[str]:
        """Python uses __all__ for exports."""
        exports = []

        # Look for __all__
        all_match = re.search(r'__all__\s*=\s*\[([^\]]+)\]', content)
        if all_match:
            items = all_match.group(1)
            for item in re.findall(r'["\'](\w+)["\']', items):
                exports.append(item)

        return exports


class JavaScriptExtractor(SymbolExtractor):
    """Symbol extractor for JavaScript/JSX code."""

    CLASS_PATTERN = re.compile(
        r'^(?:export\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?\s*{',
        re.MULTILINE
    )
    FUNCTION_PATTERN = re.compile(
        r'^(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(([^)]*)\)',
        re.MULTILINE
    )
    ARROW_PATTERN = re.compile(
        r'^(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\([^)]*\)\s*=>',
        re.MULTILINE
    )
    CONST_PATTERN = re.compile(
        r'^(?:export\s+)?const\s+(\w+)\s*=',
        re.MULTILINE
    )
    IMPORT_PATTERN = re.compile(
        r'^import\s+(?:{([^}]+)}|(\w+))\s+from\s+["\']([^"\']+)["\']',
        re.MULTILINE
    )
    EXPORT_PATTERN = re.compile(
        r'^export\s+(?:default\s+)?(?:class|function|const|let|var)?\s*(\w+)',
        re.MULTILINE
    )

    def extract(self, content: str, file_path: str) -> List["Symbol"]:
        from .codebase import Symbol, SymbolKind

        symbols = []

        # Extract classes
        for match in self.CLASS_PATTERN.finditer(content):
            name = match.group(1)
            extends = match.group(2) or ""
            line = content[:match.start()].count('\n') + 1

            sig = f"class {name}"
            if extends:
                sig += f" extends {extends}"

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.CLASS,
                file_path=file_path,
                line_start=line,
                line_end=line + 1,  # Simplified
                signature=sig,
            ))

        # Extract functions
        for match in self.FUNCTION_PATTERN.finditer(content):
            name = match.group(1)
            params = match.group(2) or ""
            line = content[:match.start()].count('\n') + 1

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                line_start=line,
                line_end=line + 1,
                signature=f"function {name}({params})",
            ))

        # Extract arrow functions
        for match in self.ARROW_PATTERN.finditer(content):
            name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.FUNCTION,
                file_path=file_path,
                line_start=line,
                line_end=line + 1,
                signature=f"const {name} = () =>",
            ))

        return symbols

    def extract_imports(self, content: str) -> List[str]:
        imports = []
        for match in self.IMPORT_PATTERN.finditer(content):
            module = match.group(3)
            imports.append(module)
        return imports

    def extract_exports(self, content: str) -> List[str]:
        exports = []
        for match in self.EXPORT_PATTERN.finditer(content):
            name = match.group(1)
            if name:
                exports.append(name)
        return exports


class TypeScriptExtractor(JavaScriptExtractor):
    """Symbol extractor for TypeScript code."""

    INTERFACE_PATTERN = re.compile(
        r'^(?:export\s+)?interface\s+(\w+)(?:\s+extends\s+([^{]+))?\s*{',
        re.MULTILINE
    )
    TYPE_PATTERN = re.compile(
        r'^(?:export\s+)?type\s+(\w+)\s*=',
        re.MULTILINE
    )
    ENUM_PATTERN = re.compile(
        r'^(?:export\s+)?enum\s+(\w+)\s*{',
        re.MULTILINE
    )

    def extract(self, content: str, file_path: str) -> List["Symbol"]:
        from .codebase import Symbol, SymbolKind

        # Get base JS symbols
        symbols = super().extract(content, file_path)

        # Add TypeScript-specific symbols
        for match in self.INTERFACE_PATTERN.finditer(content):
            name = match.group(1)
            extends = match.group(2) or ""
            line = content[:match.start()].count('\n') + 1

            sig = f"interface {name}"
            if extends:
                sig += f" extends {extends.strip()}"

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.INTERFACE,
                file_path=file_path,
                line_start=line,
                line_end=line + 1,
                signature=sig,
            ))

        for match in self.TYPE_PATTERN.finditer(content):
            name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.TYPE,
                file_path=file_path,
                line_start=line,
                line_end=line + 1,
                signature=f"type {name}",
            ))

        for match in self.ENUM_PATTERN.finditer(content):
            name = match.group(1)
            line = content[:match.start()].count('\n') + 1

            symbols.append(Symbol(
                name=name,
                kind=SymbolKind.ENUM,
                file_path=file_path,
                line_start=line,
                line_end=line + 1,
                signature=f"enum {name}",
            ))

        return symbols


class GenericExtractor(SymbolExtractor):
    """Fallback extractor for unsupported languages."""

    def extract(self, content: str, file_path: str) -> List["Symbol"]:
        return []

    def extract_imports(self, content: str) -> List[str]:
        return []

    def extract_exports(self, content: str) -> List[str]:
        return []


# Registry of extractors
_EXTRACTORS: Dict[str, SymbolExtractor] = {}


def get_extractor(language: str) -> SymbolExtractor:
    """
    Get symbol extractor for a language.

    Args:
        language: Language name

    Returns:
        SymbolExtractor instance
    """
    global _EXTRACTORS

    if language not in _EXTRACTORS:
        if language == "python":
            _EXTRACTORS[language] = PythonExtractor()
        elif language in ("javascript", "jsx"):
            _EXTRACTORS[language] = JavaScriptExtractor()
        elif language in ("typescript", "tsx"):
            _EXTRACTORS[language] = TypeScriptExtractor()
        else:
            _EXTRACTORS[language] = GenericExtractor()

    return _EXTRACTORS[language]


def register_extractor(language: str, extractor: SymbolExtractor) -> None:
    """Register a custom extractor for a language."""
    global _EXTRACTORS
    _EXTRACTORS[language] = extractor
