"""Researcher agent specialized for information gathering."""

from typing import List, Optional, TYPE_CHECKING

from ..core.types import Message, MessageRole, ToolSchema
from .base import AgentCapabilities, AgentResult, AgentRole, AgentTask, BaseAgent

if TYPE_CHECKING:
    from ..providers.base import BaseProvider
    from ..tools.base import BaseTool
    from ..core.events import EventBus


RESEARCHER_PROMPT = '''You are a Researcher agent specialized in gathering and synthesizing information.

## Your Capabilities
- Search the web using DuckDuckGo
- Scrape and analyze web pages
- Search codebase with grep and glob
- Read files to understand code
- Open URLs in browser for user verification

## Research Guidelines
1. **Be thorough** - Check multiple sources when possible
2. **Be accurate** - Verify information before reporting
3. **Be concise** - Summarize findings clearly
4. **Cite sources** - Reference where information came from

## Response Format
1. Summarize the research question
2. List key findings with sources
3. Provide relevant code snippets or quotes
4. Note any uncertainties or gaps

## Important Rules
- For codebase questions, search before making assumptions
- For web searches, use specific queries
- Distinguish between facts and inferences
- If information is unclear, say so
'''


class ResearcherAgent(BaseAgent):
    """
    Agent specialized for information gathering and research.

    Has access to:
    - Web search and scraping
    - Codebase search (grep, glob)
    - File reading
    """

    @property
    def role(self) -> AgentRole:
        return AgentRole.RESEARCHER

    @property
    def capabilities(self) -> AgentCapabilities:
        return AgentCapabilities(
            can_write_code=False,
            can_read_files=True,
            can_execute_commands=False,
            can_search_web=True,
            can_delegate=False,
            can_review=False,
            tool_names=set(self.tools.keys()),
        )

    @property
    def system_prompt(self) -> str:
        return RESEARCHER_PROMPT

    async def execute(self, task: AgentTask) -> AgentResult:
        """Execute a research task."""
        await self._emit_event("agent.started", {
            "agent": self.role.value,
            "task_id": task.id,
            "description": task.description,
        })

        iterations = 0
        total_tokens = 0
        sources = []

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

                        # Track sources
                        if tc.name == "duckduckgotool":
                            sources.append({"type": "web_search", "query": tc.arguments.get("query", "")})
                        elif tc.name == "webscrapertool":
                            sources.append({"type": "web_page", "url": tc.arguments.get("url", "")})
                        elif tc.name == "greptool":
                            sources.append({"type": "code_search", "pattern": tc.arguments.get("pattern", "")})

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
                    artifacts=[{"type": "sources", "data": sources}] if sources else [],
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
