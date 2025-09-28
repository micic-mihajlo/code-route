import os
import re
from pathlib import Path

from dotenv import load_dotenv

from openai import OpenAI
from rich.console import Console
from rich.panel import Panel

from .base import BaseTool

load_dotenv()

class ToolCreatorTool(BaseTool):
    name = "toolcreator"
    description = '''
    Creates a new tool based on a natural language description.
    Use this when you need a new capability that isn't available in current tools.
    The tool will be automatically generated and saved to the tools directory.
    Returns the generated tool code and creation status.
    '''
    input_schema = {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Natural language description of what the tool should do"
            }
        },
        "required": ["description"]
    }

    def __init__(self):
        self.client = OpenAI(
            api_key=os.getenv('OPENROUTER_API_KEY'),
            base_url="https://openrouter.ai/api/v1"
        )
        self.console = Console()
        self.tools_dir = Path(__file__).parent.parent / "tools"

    def _sanitize_filename(self, name: str) -> str:
        """Convert tool name to valid Python filename"""
        return name + '.py'

    def _validate_tool_name(self, name: str) -> bool:
        """Validate tool name matches required pattern"""
        return bool(re.match(r'^[a-zA-Z0-9_-]{1,64}$', name))

    def execute(self, **kwargs) -> str:
        description = kwargs.get("description")

        prompt = f"""Create a Python tool class that follows our BaseTool interface. The tool should:

1. {description}

Important:
- The filename MUST EXACTLY match the tool name used in the class
- The name property MUST EXACTLY match the class name in lowercase
- For example, if the class is `WeatherTool`, then:
  - name property must be "weathertool"
  - file must be weathertool.py

Here's the required structure (including imports and format):

```python
from .base import BaseTool
import requests

class ToolName(BaseTool):
    name = "toolname"
    description = '''
    Detailed description here.
    Multiple lines for clarity.
    '''
    input_schema = {{
        "type": "object",
        "properties": {{
        }},
        "required": []
    }}

    def execute(self, **kwargs) -> str:
        pass
```

Generate the complete tool implementation following this exact structure.
Return ONLY the Python code without any explanation or markdown formatting.
"""

        try:
            response = self.client.chat.completions.create(
                model="google/gemini-2.5-flash-preview",
                max_tokens=8000,
                temperature=0,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            tool_code = response.choices[0].message.content.strip()

            name_match = re.search(r'name\s*=\s*["\']([a-zA-Z0-9_-]+)["\']', tool_code)
            if not name_match:
                return "Error: Could not extract tool name from generated code"

            tool_name = name_match.group(1)
            filename = self._sanitize_filename(tool_name)

            self.tools_dir.mkdir(exist_ok=True)

            file_path = self.tools_dir / filename
            with open(file_path, 'w') as f:
                f.write(tool_code)

            result = f"""[bold green]✅ Tool created successfully![/bold green]
Tool name: [cyan]{tool_name}[/cyan]
File created: [cyan]{filename}[/cyan]

[bold]Generated Tool Code:[/bold]
{Panel(tool_code, border_style="green")}

[bold green]✨ Tool is ready to use![/bold green]
Type 'refresh' to load your new tool."""

            return result

        except Exception as e:
            return f"[bold red]Error creating tool:[/bold red] {e!s}"
