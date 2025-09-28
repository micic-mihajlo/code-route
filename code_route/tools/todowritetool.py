import json
import os
from typing import Dict, List, Optional

from .base import BaseTool


class TodoWriteTool(BaseTool):
    def __init__(self):
        super().__init__()
        self.session_file = os.path.join(os.getcwd(), '.code_route_todos.json')
        self._load_todos()

    @property
    def name(self) -> str:
        return 'todowritetool'

    @property
    def description(self) -> str:
        return '''Manages a persistent todo list for tracking complex tasks.
        
        Operations: create_list, add_task, update_status, remove_task, get_list, clear_all.
        State persists across tool calls - no need to resend entire list.'''

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'operation': {
                    'type': 'string',
                    'enum': ['create_list', 'add_task', 'update_status', 'remove_task', 'get_list', 'clear_all'],
                    'description': 'Operation to perform'
                },
                'todos': {
                    'type': 'array',
                    'items': {
                        'type': 'object',
                        'properties': {
                            'content': {'type': 'string', 'minLength': 1},
                            'status': {'type': 'string', 'enum': ['pending', 'in_progress', 'completed']},
                            'priority': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                            'id': {'type': 'string'}
                        },
                        'required': ['content', 'status', 'priority', 'id']
                    },
                    'description': 'Initial todo list (only for create_list operation)'
                },
                'task_id': {
                    'type': 'string',
                    'description': 'Task ID for update_status, remove_task operations'
                },
                'new_status': {
                    'type': 'string',
                    'enum': ['pending', 'in_progress', 'completed'],
                    'description': 'New status for update_status operation'
                },
                'task': {
                    'type': 'object',
                    'properties': {
                        'content': {'type': 'string', 'minLength': 1},
                        'priority': {'type': 'string', 'enum': ['high', 'medium', 'low']},
                        'id': {'type': 'string'}
                    },
                    'required': ['content', 'priority', 'id'],
                    'description': 'Task to add (for add_task operation)'
                }
            },
            'required': ['operation']
        }

    def execute(self, **kwargs) -> str:
        operation = kwargs.get('operation')
        
        if operation == 'create_list':
            return self._create_list(kwargs.get('todos', []))
        elif operation == 'add_task':
            return self._add_task(kwargs.get('task'))
        elif operation == 'update_status':
            return self._update_status(kwargs.get('task_id'), kwargs.get('new_status'))
        elif operation == 'remove_task':
            return self._remove_task(kwargs.get('task_id'))
        elif operation == 'get_list':
            return self._get_list()
        elif operation == 'clear_all':
            return self._clear_all()
        else:
            return f'Error: Unknown operation "{operation}"'

    def _create_list(self, todos: List[Dict]) -> str:
        """Create new todo list, replacing any existing one"""
        if not todos:
            return 'Error: No todos provided for create_list'

        validation_errors = self._validate_todos(todos)
        if validation_errors:
            return f'Validation errors:\n' + '\n'.join(validation_errors)

        self.todos = {todo['id']: todo for todo in todos}
        self._save_todos()
        return f'Created todo list with {len(todos)} tasks'

    def _add_task(self, task: Optional[Dict]) -> str:
        """Add single task to existing list"""
        if not task:
            return 'Error: No task provided'

        task_id = task.get('id')
        if not task_id:
            return 'Error: Task missing required id field'

        if task_id in self.todos:
            return f'Error: Task with ID "{task_id}" already exists'

        task['status'] = 'pending'
        
        validation_errors = self._validate_todos([task])
        if validation_errors:
            return f'Validation error: {validation_errors[0]}'

        self.todos[task_id] = task
        self._save_todos()
        return f'Added task: {task["content"]}'

    def _update_status(self, task_id: Optional[str], new_status: Optional[str]) -> str:
        """Update status of existing task"""
        if not task_id:
            return 'Error: No task_id provided'
        
        if not new_status:
            return 'Error: No new_status provided'

        if task_id not in self.todos:
            return f'Error: Task "{task_id}" not found'

        old_status = self.todos[task_id]['status']
        self.todos[task_id]['status'] = new_status
        self._save_todos()
        
        return f'Updated "{task_id}": {old_status} → {new_status}'

    def _remove_task(self, task_id: Optional[str]) -> str:
        """Remove task from list"""
        if not task_id:
            return 'Error: No task_id provided'

        if task_id not in self.todos:
            return f'Error: Task "{task_id}" not found'

        removed_task = self.todos.pop(task_id)
        self._save_todos()
        return f'Removed task: {removed_task["content"]}'

    def _get_list(self) -> str:
        """Get formatted current todo list"""
        if not self.todos:
            return 'Todo list is empty'

        todos_list = list(self.todos.values())
        return self._format_todo_list(todos_list)

    def _clear_all(self) -> str:
        """Clear all todos"""
        count = len(self.todos)
        self.todos = {}
        self._save_todos()
        return f'Cleared {count} tasks from todo list'

    def _load_todos(self) -> None:
        """Load todos from session file"""
        self.todos = {}
        if os.path.exists(self.session_file):
            try:
                with open(self.session_file, 'r') as f:
                    self.todos = json.load(f)
        except Exception:
            self.todos = {}

    def _save_todos(self) -> None:
        """Save todos to session file"""
        try:
            with open(self.session_file, 'w') as f:
                json.dump(self.todos, f, indent=2)
        except Exception:
            pass  # fail silently if saving fails

    def _validate_todos(self, todos: List[Dict]) -> List[str]:
        """Validate todo items and return list of errors"""
        errors = []
        for i, todo in enumerate(todos):
            for field in ['content', 'status', 'priority', 'id']:
                if not todo.get(field):
                    errors.append(f'Todo {i+1}: Missing required field "{field}"')

            status = todo.get('status')
            if status not in ['pending', 'in_progress', 'completed']:
                errors.append(f'Todo {i+1}: Invalid status "{status}"')

            priority = todo.get('priority')
            if priority not in ['high', 'medium', 'low']:
                errors.append(f'Todo {i+1}: Invalid priority "{priority}"')

        return errors

    def _format_todo_list(self, todos: List[Dict]) -> str:
        """Format todos for display"""
        if not todos:
            return 'Todo list is empty'

        output = ['📋 **Current Todo List**\n']
        pending = [t for t in todos if t['status'] == 'pending']
        in_progress = [t for t in todos if t['status'] == 'in_progress']
        completed = [t for t in todos if t['status'] == 'completed']

        if in_progress:
            output.append('🚀 **In Progress:**')
            for todo in in_progress:
                priority_icon = self._get_priority_icon(todo['priority'])
                output.append(f'  {priority_icon} {todo["content"]} (ID: {todo["id"]})')
            output.append('')

        if pending:
            output.append('⏳ **Pending:**')
            for todo in pending:
                priority_icon = self._get_priority_icon(todo['priority'])
                output.append(f'  {priority_icon} {todo["content"]} (ID: {todo["id"]})')
            output.append('')

        if completed:
            output.append('✅ **Completed:**')
            for todo in completed:
                output.append(f'  ✓ {todo["content"]} (ID: {todo["id"]})')

        return '\n'.join(output)

    def _get_priority_icon(self, priority: str) -> str:
        """Get icon for priority level"""
        icons = {'high': '🔴', 'medium': '🟡', 'low': '🟢'}
        return icons.get(priority, '⚪') 