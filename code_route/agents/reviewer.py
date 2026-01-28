"""Reviewer agent specialized for code review and testing."""

from typing import List, Optional, TYPE_CHECKING

from ..core.types import Message, MessageRole, ToolSchema
from .base import AgentCapabilities, AgentResult, AgentRole, AgentTask, BaseAgent

if TYPE_CHECKING:
    from ..providers.base import BaseProvider
    from ..tools.base import BaseTool
    from ..core.events import EventBus


REVIEWER_PROMPT = '''You are a Reviewer agent specialized in code review and quality assurance.

## Your Capabilities
- Read and analyze code files
- Search codebase for patterns and issues
- Run linting tools
- Execute tests via bash
- Suggest specific fixes with diff format

## Review Guidelines
1. **Be constructive** - Focus on actionable feedback
2. **Be specific** - Point to exact lines and files
3. **Prioritize** - Critical issues first, style issues last
4. **Consider context** - Understand the change's purpose

## Review Checklist
- [ ] Logic correctness
- [ ] Error handling
- [ ] Edge cases
- [ ] Performance concerns
- [ ] Security issues
- [ ] Code style consistency
- [ ] Test coverage

## Response Format
1. Summary of changes reviewed
2. Critical issues (bugs, security)
3. Suggestions (improvements, alternatives)
4. Minor issues (style, naming)
5. Overall assessment

## Important Rules
- Don't suggest changes just for the sake of change
- Accept multiple valid approaches
- Consider trade-offs, not just ideals
- Be respectful in feedback
'''


class ReviewerAgent(BaseAgent):
    """
    Agent specialized for code review and quality assurance.

    Has access to:
    - File reading tools
    - Code search (grep, glob)
    - Linting tools
    - Bash for running tests
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.REVIEWER

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_write_code=False,
            can_read_files=True,
            can_execute_commands=True,
            can_search_web=False,
            can_delegate=False,
            can_review=True,
            tool_names=set(self.tools.keys()),
        )

    @property
    def system_prompt(self) -> str:
        return REVIEWER_PROMPT

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a review task."""
        await self._emit_event("agent.started", {
            "agent": self.role.value,
            "task_id": task.id,
            "description": task.description,
        })

        iterations = 0
        total_tokens = 0
        findings = []

        try:
            messages = self._build_messages(task)

            while iterations < task.max_iterations:
                iterations += 1

                tool_schemas = [
                    ToolSchema(
                        name=t.name,
                        description=t.description,
                        parameters=t.input_schema
                    )
                    for t in self.tools.values()
                ]

                response = await self.provider.complete(
                    messages=[Message(role=MessageRole(m["role"]), content=m["content"]) for m in messages],
                    tools=tool_schemas,
                )

                total_tokens += response.usage.total_tokens

                if response.tool_calls:
                    tool_results = []

                    for tc in response.tool_calls:
                        tool = self.tools.get(tc.name)
                        if not tool:
                            tool_results.append(f"Error: Tool '{tc.name}' not found")
                            continue

                        await self._emit_event("tool.started", {
                            "tool": tc.name,
                        })

                        result = await tool.execute_async(**tc.arguments)

                        # Track linting findings
                        if tc.name == "lintingtool" and result.success:
                            findings.append({
                                "type": "lint",
                                "file": tc.arguments.get("file_path", ""),
                                "result": result.output[:500],
                            })

                        await self._emit_event("tool.completed", {
                            "tool": tc.name,
                            "success": result.success,
                        })

                        tool_results.append(result.output if result.success else f"Error: {result.error}")

                    messages.append({
                        "role": "assistant",
                        "content": response.content,
                        "tool_calls": [
                            {"id": tc.id, "name": tc.name, "arguments": tc.arguments}
                            for tc in response.tool_calls
                        ]
                    })

                    for tc, result in zip(response.tool_calls, tool_results):
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        })

                    continue

                await self._emit_event("agent.completed", {
                    "agent": self.role.value,
                    "task_id": task.id,
                    "success": True,
                })

                return AgentResult(
                    task_id=task.id,
                    success=True,
                    output=response.content,
                    artifacts=[{"type": "review_findings", "data": findings}] if findings else [],
                    iterations_used=iterations,
                    tokens_used=total_tokens,
                )

            return AgentResult(
                task_id=task.id,
                success=False,
                output="",
                error=f"Reached maximum iterations ({task.max_iterations})",
                iterations_used=iterations,
                tokens_used=total_tokens,
            )

        except Exception as e:
            await self._emit_event("agent.error", {
                "agent": self.role.value,
                "task_id": task.id,
                "error": str(e),
            })
            return AgentResult.err(task.id, str(e))
