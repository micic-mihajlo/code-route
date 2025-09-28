import os
from typing import Dict, List

from .base import BaseTool


class MultiEditTool(BaseTool):
    @property
    def name(self) -> str:
        return 'multiedittool'

    @property
    def description(self) -> str:
        return '''Performs multiple find-and-replace operations on a single file in sequence.
        
        All edits are applied atomically - either all succeed or none are applied.
        Edits are applied in order, with each edit operating on the result of the previous.'''

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'file_path': {
                    'type': 'string',
                    'description': 'Absolute path to the file to modify'
                },
                'edits': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'old_string': {
                                'type': 'string',
                                'description': 'Text to replace (must be unique in file)'
                            },
                            'new_string': {
                                'type': 'string',
                                'description': 'Text to replace it with'
                            },
                            'replace_all': {
                                'type': 'boolean',
                                'description': 'Replace all occurrences (default: false)',
                                'default': False
                            }
                        },
                        'required': ['old_string', 'new_string']
                    },
                    'minItems': 1,
                    'description': 'Array of edit operations to perform sequentially'
                }
            },
            'required': ['file_path', 'edits']
        }

    def execute(self, **kwargs) -> str:
        file_path = kwargs.get('file_path')
        edits = kwargs.get('edits', [])

        if not file_path:
            return 'Error: No file_path provided'

        if not edits:
            return 'Error: No edits provided'

        if not os.path.isabs(file_path):
            return f'Error: File path must be absolute, got: {file_path}'

        if not os.path.exists(file_path):
            return f'Error: File does not exist: {file_path}'

        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            original_content = content
            edit_count = 0

            for i, edit in enumerate(edits):
                old_string = edit.get('old_string')
                new_string = edit.get('new_string')
                replace_all = edit.get('replace_all', False)

                if old_string == new_string:
                    return f'Error: Edit {i+1} - old_string and new_string are identical'

                if not old_string:
                    if i == 0 and old_string == '':
                        content = new_string
                        edit_count += 1
                        continue
                    else:
                        return f'Error: Edit {i+1} - old_string cannot be empty (except for new file creation)'

                if old_string not in content:
                    return f'Error: Edit {i+1} - old_string not found in file: "{old_string}"'

                if replace_all:
                    content = content.replace(old_string, new_string)
                    edit_count += content.count(new_string) - original_content.count(new_string)
                else:
                    if content.count(old_string) > 1:
                        return f'Error: Edit {i+1} - old_string appears multiple times, use replace_all=true or provide more context'
                    content = content.replace(old_string, new_string, 1)
                    edit_count += 1

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

            return f'Successfully applied {len(edits)} edits to {file_path}'

        except UnicodeDecodeError:
            return f'Error: File is not UTF-8 encoded: {file_path}'
        except PermissionError:
            return f'Error: Permission denied writing to: {file_path}'
        except Exception as e:
            return f'Error applying edits: {e!s}' 