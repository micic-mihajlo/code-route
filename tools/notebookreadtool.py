import json
import os
from typing import Dict

from .base import BaseTool


class NotebookReadTool(BaseTool):
    @property
    def name(self) -> str:
        return 'notebookreadtool'

    @property
    def description(self) -> str:
        return 'Reads and displays Jupyter notebook contents'

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'file_path': {
                    'type': 'string',
                    'description': 'Path to the Jupyter notebook file'
                },
                'cell_types': {
                    'type': 'array',
                    'items': {
                        'type': 'string',
                        'enum': ['code', 'markdown', 'raw']
                    },
                    'description': 'Types of cells to include (default: all)',
                    'default': ['code', 'markdown', 'raw']
                },
                'include_outputs': {
                    'type': 'boolean',
                    'description': 'Whether to include cell outputs (default: false)',
                    'default': False
                }
            },
            'required': ['file_path']
        }

    def execute(self, **kwargs) -> str:
        file_path = kwargs.get('file_path')
        cell_types = kwargs.get('cell_types', ['code', 'markdown', 'raw'])
        include_outputs = kwargs.get('include_outputs', False)

        if not file_path:
            return 'Error: No file path provided'

        if not os.path.isfile(file_path):
            return f'Error: {file_path} is not a file'

        try:
            with open(file_path, encoding='utf-8') as f:
                notebook = json.load(f)

            if 'cells' not in notebook:
                return 'Error: Invalid notebook format'

            result = []
            for cell in notebook['cells']:
                cell_type = cell.get('cell_type', '')
                if cell_type not in cell_types:
                    continue

                result.append(f'[{cell_type.upper()} CELL]')
                result.append(''.join(cell.get('source', [])))

                if include_outputs and cell_type == 'code':
                    outputs = cell.get('outputs', [])
                    if outputs:
                        result.append('\n[OUTPUTS]')
                        for output in outputs:
                            if 'text' in output:
                                result.append(''.join(output['text']))
                            elif 'data' in output and 'text/plain' in output['data']:
                                result.append(''.join(output['data']['text/plain']))

                result.append('\n' + '-' * 80 + '\n')

            return '\n'.join(result) if result else 'No matching cells found'
        except json.JSONDecodeError:
            return 'Error: Invalid JSON in notebook file'
        except Exception as e:
            return f'Error reading notebook: {e!s}' 