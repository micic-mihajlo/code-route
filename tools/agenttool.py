from typing import Dict, List
import json
import subprocess
from .base import BaseTool

class AgentTool(BaseTool):
    @property
    def name(self) -> str:
        return 'agenttool'

    @property
    def description(self) -> str:
        return 'Runs a sub-agent to handle complex, multi-step tasks'

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'task': {
                    'type': 'string',
                    'description': 'The task description for the sub-agent'
                },
                'agent_type': {
                    'type': 'string',
                    'enum': ['code', 'research', 'analysis'],
                    'description': 'Type of agent to use',
                    'default': 'code'
                },
                'timeout': {
                    'type': 'integer',
                    'description': 'Timeout in seconds (default: 300)',
                    'default': 300
                },
                'context': {
                    'type': 'object',
                    'description': 'Additional context for the agent',
                    'default': {}
                }
            },
            'required': ['task']
        }

    def execute(self, **kwargs) -> str:
        task = kwargs.get('task')
        agent_type = kwargs.get('agent_type', 'code')
        timeout = kwargs.get('timeout', 300)
        context = kwargs.get('context', {})

        if not task:
            return 'Error: No task provided'

        try:
            # Prepare the agent input
            agent_input = {
                'task': task,
                'agent_type': agent_type,
                'context': context
            }

            # Convert to JSON string
            input_json = json.dumps(agent_input)

            # Run the agent process
            result = subprocess.run(
                ['python', '-m', 'agents.run_agent'],
                input=input_json.encode(),
                capture_output=True,
                text=True,
                timeout=timeout
            )

            if result.returncode == 0:
                return result.stdout
            else:
                return f'Error: {result.stderr}'
        except subprocess.TimeoutExpired:
            return f'Error: Agent execution timed out after {timeout} seconds'
        except Exception as e:
            return f'Error running agent: {str(e)}' 