import glob
import os
from typing import Dict

from .base import BaseTool


class GlobTool(BaseTool):
    @property
    def name(self) -> str:
        return 'globtool'

    @property
    def description(self) -> str:
        return 'Finds files based on pattern matching using glob patterns'

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'pattern': {
                    'type': 'string',
                    'description': 'The glob pattern to match files against'
                },
                'recursive': {
                    'type': 'boolean',
                    'description': 'Whether to search recursively (default: false)',
                    'default': False
                },
                'include_dirs': {
                    'type': 'boolean',
                    'description': 'Whether to include directories in results (default: false)',
                    'default': False
                }
            },
            'required': ['pattern']
        }

    def execute(self, **kwargs) -> str:
        pattern = kwargs.get('pattern')
        recursive = kwargs.get('recursive', False)
        include_dirs = kwargs.get('include_dirs', False)

        if not pattern:
            return 'Error: No pattern provided'

        try:
            if recursive:
                pattern = os.path.join('**', pattern)
            
            matches = glob.glob(pattern, recursive=recursive)
            
            if not include_dirs:
                matches = [m for m in matches if os.path.isfile(m)]
            
            return '\n'.join(matches) if matches else 'No files found matching the pattern'
        except Exception as e:
            return f'Error finding files: {e!s}' 