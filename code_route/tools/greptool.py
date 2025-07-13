import os
import re
from typing import Dict

from .base import BaseTool


class GrepTool(BaseTool):
    @property
    def name(self) -> str:
        return 'greptool'

    @property
    def description(self) -> str:
        return 'Searches for patterns in file contents using regex'

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'pattern': {
                    'type': 'string',
                    'description': 'The regex pattern to search for'
                },
                'files': {
                    'type': 'array',
                    'items': {
                        'type': 'string'
                    },
                    'description': 'List of files to search in'
                },
                'case_sensitive': {
                    'type': 'boolean',
                    'description': 'Whether the search should be case sensitive (default: true)',
                    'default': True
                },
                'line_numbers': {
                    'type': 'boolean',
                    'description': 'Whether to include line numbers in results (default: true)',
                    'default': True
                }
            },
            'required': ['pattern', 'files']
        }

    def execute(self, **kwargs) -> str:
        pattern = kwargs.get('pattern')
        files = kwargs.get('files', [])
        case_sensitive = kwargs.get('case_sensitive', True)
        line_numbers = kwargs.get('line_numbers', True)

        if not pattern:
            return 'Error: No pattern provided'
        if not files:
            return 'Error: No files provided'

        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
            results = []

            for file_path in files:
                if not os.path.isfile(file_path):
                    results.append(f'Error: {file_path} is not a file')
                    continue

                try:
                    with open(file_path, encoding='utf-8') as f:
                        for i, line in enumerate(f, 1):
                            if regex.search(line):
                                if line_numbers:
                                    results.append(f'{file_path}:{i}: {line.rstrip()}')
                                else:
                                    results.append(f'{file_path}: {line.rstrip()}')
                except Exception as e:
                    results.append(f'Error reading {file_path}: {e!s}')

            return '\n'.join(results) if results else 'No matches found'
        except Exception as e:
            return f'Error searching files: {e!s}' 