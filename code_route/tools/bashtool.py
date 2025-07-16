import subprocess
from typing import Dict

from .base import BaseTool


class BashTool(BaseTool):
    @property
    def name(self) -> str:
        return 'bashtool'

    @property
    def description(self) -> str:
        return '''Executes shell commands with proper quoting and security measures.
        
        IMPORTANT: Avoid using find, grep, cat, ls, head, tail - use specialized tools instead.
        Always quote paths with spaces. Explain non-trivial commands clearly.
        Use && or ; to chain commands, not newlines.'''

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
                    'description': 'Timeout in seconds (default: 120, max: 600)',
                    'default': 120
                },
                'description': {
                    'type': 'string',
                    'description': 'Clear, concise description of what this command does in 5-10 words'
                },
                'is_background': {
                    'type': 'boolean',
                    'description': 'Whether to run command in background (for long-running processes)',
                    'default': False
                }
            },
            'required': ['command']
        }

    def execute(self, **kwargs) -> str:
        command = kwargs.get('command')
        timeout = min(kwargs.get('timeout', 120), 600)  # Cap at 10 minutes
        description = kwargs.get('description', '')
        is_background = kwargs.get('is_background', False)

        if not command:
            return 'Error: No command provided'

        # Security check for dangerous patterns
        dangerous_patterns = ['rm -rf /', 'sudo rm', '> /dev/null 2>&1 &']
        if any(pattern in command for pattern in dangerous_patterns):
            return f'Error: Command contains potentially dangerous pattern. Please verify: {command}'

        try:
            if is_background:
                # Start background process
                process = subprocess.Popen(
                    command,
                    shell=True,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                return f'Background process started (PID: {process.pid}). {description}'
            
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                return output if output else 'Command completed successfully'
            else:
                error_msg = result.stderr.strip()
                return f'Command failed (exit code {result.returncode}): {error_msg}'
                
        except subprocess.TimeoutExpired:
            return f'Command timed out after {timeout} seconds'
        except Exception as e:
            return f'Error executing command: {e!s}' 