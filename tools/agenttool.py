import json
from typing import Dict, List

from .base import BaseTool


class AgentTool(BaseTool):
    @property
    def name(self) -> str:
        return 'agenttool'

    @property
    def description(self) -> str:
        return 'Creates a focused sub-conversation to handle complex, multi-step tasks with detailed planning and execution'

    @property
    def input_schema(self) -> Dict:
        return {
            'type': 'object',
            'properties': {
                'task': {
                    'type': 'string',
                    'description': 'Detailed description of the complex task to be handled'
                },
                'task_type': {
                    'type': 'string',
                    'enum': ['code_analysis', 'implementation', 'debugging', 'research', 'refactoring', 'testing'],
                    'description': 'Type of task to optimize the approach',
                    'default': 'implementation'
                },
                'context_files': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'List of file paths relevant to the task',
                    'default': []
                },
                'requirements': {
                    'type': 'array',
                    'items': {'type': 'string'},
                    'description': 'Specific requirements or constraints',
                    'default': []
                }
            },
            'required': ['task']
        }

    def execute(self, **kwargs) -> str:
        task = kwargs.get('task')
        task_type = kwargs.get('task_type', 'implementation')
        context_files = kwargs.get('context_files', [])
        requirements = kwargs.get('requirements', [])

        if not task:
            return 'Error: No task provided'

        try:
            # Create a structured sub-task breakdown
            result = self._create_agent_plan(task, task_type, context_files, requirements)
            return result
        except Exception as e:
            return f'Error creating agent plan: {e!s}'

    def _create_agent_plan(self, task: str, task_type: str, context_files: List[str], requirements: List[str]) -> str:
        """Create a detailed plan for the sub-agent task"""
        
        plan = {
            "agent_task": task,
            "task_type": task_type,
            "execution_plan": self._generate_execution_plan(task_type),
            "context_files": context_files,
            "requirements": requirements,
            "next_steps": self._generate_next_steps(task_type)
        }
        
        # Format the response for the main assistant
        response = f"""
🤖 **Agent Task Plan Created**

**Task**: {task}
**Type**: {task_type}

**Execution Plan**:
"""
        for i, step in enumerate(plan["execution_plan"], 1):
            response += f"{i}. {step}\n"
        
        if context_files:
            response += "\n**Context Files to Analyze**:\n"
            for file in context_files:
                response += f"- {file}\n"
        
        if requirements:
            response += "\n**Requirements**:\n"
            for req in requirements:
                response += f"- {req}\n"
        
        response += "\n**Recommended Next Steps**:\n"
        for i, step in enumerate(plan["next_steps"], 1):
            response += f"{i}. {step}\n"
        
        response += f"\n**Agent Plan JSON**:\n```json\n{json.dumps(plan, indent=2)}\n```"
        
        return response

    def _generate_execution_plan(self, task_type: str) -> List[str]:
        """Generate execution steps based on task type"""
        base_steps = [
            "Analyze the requirements and scope",
            "Identify relevant tools and resources needed"
        ]
        
        type_specific_steps = {
            'code_analysis': [
                "Read and understand the target codebase",
                "Identify patterns, dependencies, and architecture",
                "Document findings and potential issues",
                "Provide recommendations"
            ],
            'implementation': [
                "Design the solution architecture",
                "Identify required dependencies and tools",
                "Implement core functionality incrementally",
                "Add tests and validation",
                "Optimize and refactor as needed"
            ],
            'debugging': [
                "Reproduce the issue consistently",
                "Analyze logs and error traces",
                "Identify root cause using debugging tools",
                "Implement and test the fix",
                "Verify the solution resolves the issue"
            ],
            'research': [
                "Define research scope and objectives",
                "Gather information from multiple sources",
                "Analyze and synthesize findings",
                "Present conclusions with supporting evidence"
            ],
            'refactoring': [
                "Analyze current code structure and issues",
                "Plan refactoring strategy to minimize risk",
                "Implement changes incrementally with tests",
                "Verify functionality is preserved",
                "Update documentation as needed"
            ],
            'testing': [
                "Analyze code coverage and test gaps",
                "Design comprehensive test cases",
                "Implement unit, integration, and edge case tests",
                "Set up automated test execution",
                "Document testing procedures"
            ]
        }
        
        return base_steps + type_specific_steps.get(task_type, [
            "Break down task into manageable components",
            "Execute each component systematically",
            "Validate results at each step"
        ])

    def _generate_next_steps(self, task_type: str) -> List[str]:
        """Generate immediate next steps recommendations"""
        common_steps = [
            "Use FileContentReaderTool to examine relevant files",
            "Use GrepTool to search for patterns or specific code",
            "Use GlobTool to locate related files"
        ]
        
        type_specific_next_steps = {
            'implementation': [
                "Use ToolCreator if new capabilities are needed",
                "Use LintingTool to ensure code quality",
                "Consider using E2BCodeTool for testing"
            ],
            'debugging': [
                "Use BashTool for running diagnostic commands",
                "Use ScreenshotTool if UI issues are involved"
            ],
            'research': [
                "Use DuckDuckGoTool for web research",
                "Use WebScraperTool for detailed information extraction"
            ]
        }
        
        return common_steps + type_specific_next_steps.get(task_type, [
            "Proceed with systematic execution of the plan"
        ]) 