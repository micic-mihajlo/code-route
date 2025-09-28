import json
import os
from typing import Dict

from .base import BaseTool


class NotebookEditTool(BaseTool):
    @property
    def name(self) -> str:
        return 'notebookedittool'

    @property
    def description(self) -> str:
        return 'Modifies Jupyter notebook cells'

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'file_path': {
                    'type': 'string',
                    'description': 'Path to the Jupyter notebook file'
                },
                'cell_index': {
                    'type': 'integer',
                    'description': 'Index of the cell to modify (0-based)'
                },
                'cell_type': {
                    'type': 'string',
                    'enum': ['code', 'markdown', 'raw'],
                    'description': 'New cell type'
                },
                'source': {
                    'type': 'string',
                    'description': 'New cell source content'
                },
                'operation': {
                    'type': 'string',
                    'enum': ['update', 'insert', 'delete'],
                    'description': 'Operation to perform on the cell',
                    'default': 'update'
                }
            },
            'required': ['file_path', 'cell_index', 'operation']
        }

    def execute(self, **kwargs) -> str:
        file_path = kwargs.get('file_path')
        cell_index = kwargs.get('cell_index')
        cell_type = kwargs.get('cell_type')
        source = kwargs.get('source')
        operation = kwargs.get('operation', 'update')

        if not file_path:
            return 'Error: No file path provided'

        if not os.path.isfile(file_path):
            return f'Error: {file_path} is not a file'

        try:
            with open(file_path, encoding='utf-8') as f:
                notebook = json.load(f)

            if 'cells' not in notebook:
                return 'Error: Invalid notebook format'

            cells = notebook['cells']
            if cell_index < 0 or cell_index > len(cells):
                return f'Error: Cell index {cell_index} out of range'

            if operation == 'delete':
                del cells[cell_index]
            elif operation == 'insert':
                if not cell_type or not source:
                    return 'Error: cell_type and source are required for insert operation'
                new_cell = {
                    'cell_type': cell_type,
                    'metadata': {},
                    'source': source.split('\n')
                }
                cells.insert(cell_index, new_cell)
            elif operation == 'update':
                if cell_index >= len(cells):
                    return f'Error: Cell index {cell_index} out of range'
                cell = cells[cell_index]
                if cell_type:
                    cell['cell_type'] = cell_type
                if source:
                    cell['source'] = source.split('\n')

            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(notebook, f, indent=1)

            return f'Successfully {operation}d cell at index {cell_index}'
        except json.JSONDecodeError:
            return 'Error: Invalid JSON in notebook file'
        except Exception as e:
            return f'Error modifying notebook: {e!s}' 