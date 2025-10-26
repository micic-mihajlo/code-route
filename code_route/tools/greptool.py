import os
import re
import glob
from typing import Dict, List

from .base import BaseTool


class GrepTool(BaseTool):
    @property
    def name(self) -> str:
        return 'greptool'

    @property
    def description(self) -> str:
        return '''Searches for regex patterns in file contents with advanced filtering options.
        
        Supports directory searching, glob patterns, and multiple output modes.
        Never use bash grep - this tool is optimized for Code Route with proper permissions.'''

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'pattern': {
                    'type': 'string',
                    'description': 'The regex pattern to search for'
                },
                'path': {
                    'type': 'string',
                    'description': 'File or directory to search in (defaults to current directory)',
                    'default': '.'
                },
                'files': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Specific list of files to search (alternative to path/glob)'
                },
                'glob_pattern': {
                    'type': 'string',
                    'description': 'Glob pattern to filter files (e.g., "*.py", "**/*.js")'
                },
                'output_mode': {
                    'type': 'string',
                    'enum': ['content', 'files_with_matches', 'count'],
                    'description': 'Output format: content shows lines, files_with_matches shows paths, count shows match counts',
                    'default': 'content'
                },
                'case_sensitive': {
                    'type': 'boolean',
                    'description': 'Whether the search should be case sensitive',
                    'default': True
                },
                'line_numbers': {
                    'type': 'boolean',
                    'description': 'Whether to include line numbers in content mode',
                    'default': True
                },
                'context_before': {
                    'type': 'integer',
                    'description': 'Lines of context before each match (content mode only)',
                    'default': 0
                },
                'context_after': {
                    'type': 'integer',
                    'description': 'Lines of context after each match (content mode only)',
                    'default': 0
                }
            },
            'required': ['pattern']
        }

    def execute(self, **kwargs) -> str:
        pattern = kwargs.get('pattern')
        path = kwargs.get('path', '.')
        files = kwargs.get('files', [])
        glob_pattern = kwargs.get('glob_pattern')
        output_mode = kwargs.get('output_mode', 'content')
        case_sensitive = kwargs.get('case_sensitive', True)
        line_numbers = kwargs.get('line_numbers', True)
        context_before = kwargs.get('context_before', 0)
        context_after = kwargs.get('context_after', 0)

        if not pattern:
            return 'Error: No pattern provided'

        try:
            flags = 0 if case_sensitive else re.IGNORECASE
            regex = re.compile(pattern, flags)
            if files:
                search_files = files
            else:
                search_files = self._find_files(path, glob_pattern)

            if not search_files:
                return 'No files found to search'

            if output_mode == 'files_with_matches':
                return self._search_files_only(search_files, regex)
            if output_mode == 'count':
                return self._search_count(search_files, regex)
            return self._search_content(search_files, regex, line_numbers, context_before, context_after)

        except re.error as e:
            return f'Error: Invalid regex pattern: {e!s}'
        except Exception as e:
            return f'Error searching files: {e!s}'

    def _find_files(self, path: str, glob_pattern: str = None) -> List[str]:
        files = []
        
        if os.path.isfile(path):
            return [path]
        
        if not os.path.isdir(path):
            return []

        if glob_pattern:
            pattern_path = os.path.join(path, glob_pattern)
            files = glob.glob(pattern_path, recursive=True)
            files = [f for f in files if os.path.isfile(f)]
        else:
            for root, _, filenames in os.walk(path):
                for filename in filenames:
                    files.append(os.path.join(root, filename))

        return sorted(files)

    def _search_files_only(self, files: List[str], regex) -> str:
        matching_files = []
        
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    if any(regex.search(line) for line in f):
                        matching_files.append(file_path)
            except Exception:
                continue
                
        return '\n'.join(matching_files) if matching_files else 'No matches found'

    def _search_count(self, files: List[str], regex) -> str:
        results = []
        
        for file_path in files:
            try:
                count = 0
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        count += len(regex.findall(line))
                
                if count > 0:
                    results.append(f'{file_path}: {count}')
            except Exception:
                continue
                
        return '\n'.join(results) if results else 'No matches found'

    def _search_content(self, files: List[str], regex, line_numbers: bool, 
                       context_before: int, context_after: int) -> str:
        results = []
        
        for file_path in files:
            try:
                with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                    lines = f.readlines()
                
                matches = []
                for i, line in enumerate(lines):
                    if regex.search(line):
                        matches.append(i)
                
                if matches:
                    file_results = []
                    for match_line in matches:
                        start = max(0, match_line - context_before)
                        end = min(len(lines), match_line + context_after + 1)
                        
                        for line_idx in range(start, end):
                            line_content = lines[line_idx].rstrip()
                            if line_numbers:
                                prefix = f'{file_path}:{line_idx + 1}:'
                                if line_idx == match_line:
                                    file_results.append(f'{prefix} {line_content}')
                                else:
                                    file_results.append(f'{prefix}- {line_content}')
                            else:
                                file_results.append(f'{file_path}: {line_content}')
                    
                    results.extend(file_results)
                    
            except Exception:
                continue
                
        return '\n'.join(results) if results else 'No matches found' 