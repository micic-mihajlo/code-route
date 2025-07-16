import os
from typing import Dict, List

from .base import BaseTool


class LSTool(BaseTool):
    @property
    def name(self) -> str:
        return 'lstool'

    @property
    def description(self) -> str:
        return 'Lists files and directories with optional glob pattern filtering'

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'path': {
                    'type': 'string',
                    'description': 'Absolute path to directory to list'
                },
                'ignore': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'List of glob patterns to ignore',
                    'default': []
                }
            },
            'required': ['path']
        }

    def execute(self, **kwargs) -> str:
        path = kwargs.get('path')
        ignore_patterns = kwargs.get('ignore', [])

        if not path:
            return 'Error: No path provided'

        if not os.path.isabs(path):
            return f'Error: Path must be absolute, got: {path}'

        if not os.path.exists(path):
            return f'Error: Path does not exist: {path}'

        if not os.path.isdir(path):
            return f'Error: Path is not a directory: {path}'

        try:
            entries = []
            for item in sorted(os.listdir(path)):
                if self._should_ignore(item, ignore_patterns):
                    continue
                    
                item_path = os.path.join(path, item)
                if os.path.isdir(item_path):
                    entries.append(f'[dir]  {item}/')
                else:
                    size = self._get_file_size(item_path)
                    entries.append(f'[file] {item} ({size})')

            if not entries:
                return f'Directory is empty: {path}'

            return f'Contents of {path}:\n\n' + '\n'.join(entries)

        except PermissionError:
            return f'Error: Permission denied accessing: {path}'
        except Exception as e:
            return f'Error listing directory: {e!s}'

    def _should_ignore(self, item: str, patterns: List[str]) -> bool:
        """Check if item matches any ignore pattern"""
        import fnmatch
        return any(fnmatch.fnmatch(item, pattern) for pattern in patterns)

    def _get_file_size(self, path: str) -> str:
        """Get human-readable file size"""
        try:
            size = os.path.getsize(path)
            if size < 1024:
                return f'{size}B'
            elif size < 1024 * 1024:
                return f'{size // 1024}KB'
            else:
                return f'{size // (1024 * 1024)}MB'
        except:
            return '?' 