from typing import Dict
import subprocess
from .base import BaseTool

class BashTool(BaseTool):
    @property
    def name(self) -> str:
        return 'bashtool'

    @property
    def description(self) -> str:
        return 'Executes shell commands in the environment. Use with caution as this can modify the system.'

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'command': {
                    'type': 'string',
                    'description': 'The shell command to execute'
                },
                'timeout': {
                    'type': 'integer',
                    'description': 'Timeout in seconds (default: 30)',
                    'default': 30
                }
            },
            'required': ['command']
        }

    def execute(self, **kwargs) -> str:
        command = kwargs.get('command')
        timeout = kwargs.get('timeout', 30)

        if not command:
            return 'Error: No command provided'

        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                return result.stdout
            else:
                return f'Error: {result.stderr}'
        except subprocess.TimeoutExpired:
            return f'Error: Command timed out after {timeout} seconds'
        except Exception as e:
            return f'Error executing command: {str(e)}' 