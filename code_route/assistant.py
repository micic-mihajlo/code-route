# cr.py
# import anthropic
import importlib
import inspect
import json
import logging
import pkgutil
import sys
from typing import Any, Dict, List

from openai import OpenAI
from prompt_toolkit import prompt
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.spinner import Spinner
from rich.syntax import Syntax
from rich.table import Table
from rich.tree import Tree
from rich.text import Text

from .config import Config
from .prompts.system_prompts import SystemPrompts
from .tools.base import BaseTool
from .themes import get_themed_console, STATUS_ICONS

# Configure logging to only show ERROR level and above
logging.basicConfig(
    level=logging.ERROR,
    format='%(levelname)s: %(message)s'
)

class Assistant:
    """
    The Assistant class manages:
    - Loading of tools from a specified directory.
    - Interaction with the OpenRouter API (message completion).
    - Handling user commands such as 'refresh' and 'reset'.
    - Token usage tracking and display.
    - Tool execution upon request from model responses.
    """

    def __init__(self):
        if not getattr(Config, 'OPENROUTER_API_KEY', None):
            raise ValueError("No OPENROUTER_API_KEY found in environment variables")

        # Initialize OpenRouter client using OpenAI client
        self.client = OpenAI(
            api_key=Config.OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1"
        )

        self.conversation_history: List[Dict[str, Any]] = []
        self.console = get_themed_console()

        self.thinking_enabled = getattr(Config, 'ENABLE_THINKING', False)
        self.temperature = getattr(Config, 'DEFAULT_TEMPERATURE', 0.65)
        self.total_tokens_used = 0
        self.current_model = Config.MODEL

        self.tools = self._load_tools()

    def export_conversation(self, filename: str):
        """
        Exports the current conversation history to a JSON file.
        """
        try:
            conversation_json = json.dumps(self.conversation_history, indent=2)
            with open(filename, 'w') as f:
                f.write(conversation_json)
            self.console.print(f"[green]Conversation exported successfully to {filename}[/green]")
        except OSError as e:
            self.console.print(f"[red]Error exporting conversation to {filename}: {e}[/red]")
        except Exception as e: # Catch any other unexpected errors during export
            self.console.print(f"[red]An unexpected error occurred during export to {filename}: {e}[/red]")

    def _execute_uv_install(self, package_name: str) -> bool:
        """
        Execute the uvpackagemanager tool directly to install the missing package.
        Returns True if installation seems successful (no errors in output), otherwise False.
        """
        class ToolUseMock:
            name = "uvpackagemanager"
            input = {
                "command": "install",
                "packages": [package_name]
            }

        result = self._execute_tool(ToolUseMock())
        if "Error" not in result and "failed" not in result.lower():
            self.console.print("[green]The package was installed successfully.[/green]")
            return True
        else:
            self.console.print(f"[red]Failed to install {package_name}. Output:[/red] {result}")
            return False

    def _load_tools(self) -> List[Dict[str, Any]]:
        """
        Dynamically load all tool classes from the tools directory.
        If a dependency is missing, prompt the user to install it via uvpackagemanager.

        Returns:
            A list of tools (dicts) containing their 'name', 'description', and 'input_schema'.
        """
        tools = []
        tools_path = getattr(Config, 'TOOLS_DIR', None)

        if tools_path is None:
            self.console.print("[red]TOOLS_DIR not set in Config[/red]")
            return tools

        # clear cached tool modules for fresh import
        for module_name in list(sys.modules.keys()):
            if module_name.startswith('code_route.tools.') and module_name != 'code_route.tools.base':
                del sys.modules[module_name]

        try:
            for module_info in pkgutil.iter_modules([str(tools_path)]):
                if module_info.name == 'base':
                    continue

                # attempt loading the tool module
                try:
                    module = importlib.import_module(f'code_route.tools.{module_info.name}')
                    self._extract_tools_from_module(module, tools)
                except ImportError as e:
                    # handle missing dependencies
                    missing_module = self._parse_missing_dependency(str(e))
                    self.console.print(f"\n[yellow]Missing dependency:[/yellow] {missing_module} for tool {module_info.name}")
                    
                    user_response = 'n' # Default to 'n'
                    if sys.stdin.isatty(): # Check if running in an interactive terminal
                        try:
                            user_response = input(f"Would you like to install {missing_module}? (y/n): ").lower()
                        except EOFError: # Handle cases where input is not available (e.g. piped input)
                            self.console.print("[yellow]EOFError reading input. Defaulting to 'n' for installation.[/yellow]")
                            user_response = 'n'
                    else:
                        self.console.print(f"[yellow]Non-interactive session. Defaulting to 'n' for installing {missing_module}.[/yellow]")

                    if user_response == 'y':
                        success = self._execute_uv_install(missing_module)
                        if success:
                            # retry loading the module after installation
                            try:
                                module = importlib.import_module(f'code_route.tools.{module_info.name}')
                                self._extract_tools_from_module(module, tools)
                            except Exception as retry_err:
                                self.console.print(f"[red]Failed to load tool after installation: {retry_err!s}[/red]")
                        else:
                            self.console.print(f"[red]Installation of {missing_module} failed. Skipping this tool.[/red]")
                    else:
                        self.console.print(f"[yellow]Skipping tool {module_info.name} due to missing dependency[/yellow]")
                except Exception as mod_err:
                    self.console.print(f"[red]Error loading module {module_info.name}:[/red] {mod_err!s}")
        except Exception as overall_err:
            self.console.print(f"[red]Error in tool loading process:[/red] {overall_err!s}")

        return tools

    def _parse_missing_dependency(self, error_str: str) -> str:
        """
        Parse the missing dependency name from an ImportError string.
        """
        if "No module named" in error_str:
            parts = error_str.split("No module named")
            missing_module = parts[-1].strip(" '\"")
            # Remove any single quotes around the module name
            missing_module = missing_module.strip("'\"")
            # If it's a submodule, get the main package
            if "." in missing_module:
                missing_module = missing_module.split(".")[0]
        else:
            missing_module = "unknown"
        return missing_module

    def _extract_tools_from_module(self, module, tools: List[Dict[str, Any]]) -> None:
        """
        given a tool module, find and instantiate all tool classes (subclasses of BaseTool).
        append them to the 'tools' list.
        """
        for name, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and issubclass(obj, BaseTool) and obj != BaseTool):
                try:
                    tool_instance = obj()
                    tools.append({
                        "type": "function",
                        "function": {
                            "name": tool_instance.name,
                            "description": tool_instance.description,
                            "parameters": tool_instance.input_schema
                        }
                    })
                    self.console.print(f"{STATUS_ICONS['success']} [success]Loaded tool:[/success] [tool]{tool_instance.name}[/tool]")
                except Exception as tool_init_err:
                    self.console.print(f"[red]Error initializing tool {name}:[/red] {tool_init_err!s}")

    def refresh_tools(self):
        """
        refresh the list of tools and show newly discovered tools using a table.
        """
        current_tool_names = {tool['function']['name'] for tool in self.tools}
        self.tools = self._load_tools()
        new_tool_names = {tool['function']['name'] for tool in self.tools}
        added_tools = new_tool_names - current_tool_names

        if not added_tools:
            refresh_panel = Panel(
                f"{STATUS_ICONS['refresh']} Tool list refreshed - no changes detected",
                style="warning",
                border_style="yellow"
            )
            self.console.print(refresh_panel)
            self.display_available_tools()
            return

        refresh_text = Text.assemble(
            (f"{STATUS_ICONS['sparkles']} Tool list refreshed!", "success bold")
        )
        self.console.print(Panel(refresh_text, style="success", border_style="green"))

        if added_tools:
            new_tools_table = Table(
                title=f"{STATUS_ICONS['sparkles']} New Tools Added",
                show_header=True,
                header_style="bold success",
                border_style="success"
            )
            new_tools_table.add_column("Name", style="tool", width=25)
            new_tools_table.add_column("Description", style="white")
            for tool_name in sorted(list(added_tools)):
                tool_info = next((t for t in self.tools if t['function']['name'] == tool_name), None)
                if tool_info:
                    func_info = tool_info.get('function', {})
                    description = func_info.get('description', 'No description provided.')
                    new_tools_table.add_row(f"{STATUS_ICONS['gear']} {tool_name}", description.strip())
            self.console.print(new_tools_table)
            self.console.print()

        self.display_available_tools()

    def set_model(self, model_name: str) -> str:
        """
        Switch to a different model.
        """
        if model_name not in Config.AVAILABLE_MODELS:
            return f"Model '{model_name}' not available. Use 'models' command to see available models."
        
        old_model = self.current_model
        self.current_model = model_name
        model_display_name = Config.AVAILABLE_MODELS[model_name]
        return f"Switched from {Config.AVAILABLE_MODELS.get(old_model, old_model)} to {model_display_name}"

    def list_models(self) -> str:
        """
        List all available models.
        """
        models_table = Table(title="Available Models", show_header=True, header_style="bold cyan", border_style="cyan")
        models_table.add_column("Model ID", style="yellow", width=35)
        models_table.add_column("Display Name", style="white")
        models_table.add_column("Status", style="green", width=10)
        
        for model_id, display_name in Config.AVAILABLE_MODELS.items():
            status = "Current" if model_id == self.current_model else ""
            models_table.add_row(model_id, display_name, status)
        
        self.console.print(models_table)
        return f"Current model: {Config.AVAILABLE_MODELS.get(self.current_model, self.current_model)}"

    def display_available_tools(self):
        """
        Display a nicely formatted list of currently loaded tool names.
        """
        if not self.tools:
            no_tools_panel = Panel(
                f"{STATUS_ICONS['warning']} No tools available - check your configuration",
                style="warning",
                border_style="yellow"
            )
            self.console.print(no_tools_panel)
            return

        # Get just the names and sort them
        tool_names = sorted([tool.get('function', {}).get('name', 'N/A') for tool in self.tools])

        # Create a more visual display
        tools_text = Text()
        tools_text.append(f"{STATUS_ICONS['tool']} Available tools ({len(tool_names)}): ", style="cyan bold")
        
        for i, name in enumerate(tool_names):
            if i > 0:
                tools_text.append(" • ", style="dim")
            tools_text.append(name, style="tool")

        tools_panel = Panel(
            tools_text,
            title=f"{STATUS_ICONS['dashboard']} Tool Status",
            border_style="cyan",
            padding=(0, 1)
        )
        self.console.print(tools_panel)

    def _display_tool_usage(self, tool_name: str, input_data: Dict, result: Any):
        """
        if SHOW_TOOL_USAGE is enabled, display the input and result of a tool execution
        using rich.tree.Tree for better structure and highlighting.
        handles special cases like image data and large outputs for cleaner display.
        """
        if not getattr(Config, 'SHOW_TOOL_USAGE', False):
            return

        # determine status and set styles
        is_error = isinstance(result, str) and result.startswith("Error")
        status_icon = "❌" if is_error else "✅"
        panel_title = f"{status_icon} Tool {'Error' if is_error else 'Executed'}: {tool_name}"
        panel_border_style = "red" if is_error else "green"

        # clean up input and result data
        cleaned_input = self._clean_data_for_display(input_data)
        cleaned_result = self._clean_data_for_display(result)

        # create the main tree for the tool call
        tree = Tree(
            label="",
            guide_style="dim",
        )

        # add input node
        input_node = tree.add("📥 [yellow]Input:[/yellow]")
        # format input as JSON with syntax highlighting
        try:
            input_json_str = json.dumps(cleaned_input, indent=2)
            input_syntax = Syntax(input_json_str, "json", theme="default", line_numbers=False)
            input_node.add(input_syntax)
        except TypeError: # handle cases where input might not be JSON serializable after cleaning
             input_node.add(str(cleaned_input))

        # add result node
        output_node = tree.add("📤 [green]Result:[/green]")
        # format result (check if it's already string or needs JSON dump)
        if isinstance(cleaned_result, str):
            # if it looks like JSON, try highlighting
            if cleaned_result.strip().startswith(("{", "[")):
                 try:
                     # validate and reformat for consistent indentation
                     parsed_json = json.loads(cleaned_result)
                     result_json_str = json.dumps(parsed_json, indent=2)
                     result_syntax = Syntax(result_json_str, "json", theme="default", line_numbers=False)
                     output_node.add(result_syntax)
                 except json.JSONDecodeError:
                     output_node.add(cleaned_result) # add as plain text if not valid JSON
            else:
                 output_node.add(cleaned_result) # add as plain text
        else:
             # assume it's dict/list, format as JSON
             try:
                 result_json_str = json.dumps(cleaned_result, indent=2)
                 result_syntax = Syntax(result_json_str, "json", theme="default", line_numbers=False)
                 output_node.add(result_syntax)
             except TypeError: # Fallback if not serializable
                 output_node.add(str(cleaned_result))

        # wrap the tree in a Panel
        panel = Panel(
            tree,
            title=panel_title,
            border_style=panel_border_style,
            title_align="left",
            padding=(1, 1)
        )

        self.console.print(panel)
        self.console.print("---")

    def _clean_data_for_display(self, data):
        """
        helper method to clean data for display by handling various data types
        and removing/replacing large content like base64 strings.
        """
        if isinstance(data, str):
            try:
                # try to parse as JSON first
                parsed_data = json.loads(data)
                return self._clean_parsed_data(parsed_data)
            except json.JSONDecodeError:
                # if it's a long string, check for base64 patterns
                if len(data) > 1000 and ';base64,' in data:
                    return "[base64 data omitted]"
                return data
        elif isinstance(data, dict):
            return self._clean_parsed_data(data)
        else:
            return data

    def _clean_parsed_data(self, data):
        """
        recursively clean parsed JSON/dict data, handling nested structures
        and replacing large data with placeholders.
        """
        if isinstance(data, dict):
            cleaned = {}
            for key, value in data.items():
                # handle image data in various formats
                if key in ['data', 'image', 'source'] and isinstance(value, str):
                    if len(value) > 1000 and (';base64,' in value or value.startswith('data:')):
                        cleaned[key] = "[base64 data omitted]"
                    else:
                        cleaned[key] = value
                else:
                    cleaned[key] = self._clean_parsed_data(value)
            return cleaned
        elif isinstance(data, list):
            return [self._clean_parsed_data(item) for item in data]
        elif isinstance(data, str) and len(data) > 1000 and ';base64,' in data:
            return "[base64 data omitted]"
        return data

    def _execute_tool(self, tool_use):
        """
        given a tool usage request (with tool name and inputs),
        dynamically load and execute the corresponding tool.
        """
        tool_name = tool_use.name
        tool_input = tool_use.input or {}
        tool_result = None

        try:
            module = importlib.import_module(f'code_route.tools.{tool_name}')
            tool_instance = self._find_tool_instance_in_module(module, tool_name)

            if not tool_instance:
                tool_result = f"Tool not found: {tool_name}"
            else:
                # execute the tool with the provided input
                try:
                    result = tool_instance.execute(**tool_input)
                    # keep structured data intact for display function
                    tool_result = result
                except Exception as exec_err:
                    tool_result = f"Error executing tool '{tool_name}': {exec_err!s}"
        except ImportError:
            tool_result = f"Failed to import tool: {tool_name}"
        except Exception as e:
            tool_result = f"Error executing tool: {e!s}"

        # display tool usage with proper handling of structured data
        self._display_tool_usage(tool_name, tool_input, tool_result)
        return tool_result

    def _find_tool_instance_in_module(self, module, tool_name: str):
        """
        search a given module for a tool class matching tool_name and return an instance of it.
        """
        for _, obj in inspect.getmembers(module):
            if (inspect.isclass(obj) and issubclass(obj, BaseTool) and obj != BaseTool):
                candidate_tool = obj()
                if candidate_tool.name == tool_name:
                    return candidate_tool
        return None

    def _display_token_usage(self, usage):
        """
        display token usage using rich.progress.Progress.
        tries to show prompt vs completion tokens if available.
        """
        # extract token counts, default to 0 if not present
        prompt_tokens = getattr(usage, 'prompt_tokens', getattr(usage, 'input_tokens', 0))
        completion_tokens = getattr(usage, 'completion_tokens', getattr(usage, 'output_tokens', 0))
        # ensure total_tokens_used is up-to-date BEFORE display (it's updated after this call in _get_completion)
        # we'll use the newly received tokens for the display logic here.
        current_call_tokens = prompt_tokens + completion_tokens
        previous_total = self.total_tokens_used # total before this call
        new_total = previous_total + current_call_tokens

        max_tokens = Config.MAX_CONVERSATION_TOKENS
        used_percentage = (new_total / max_tokens) * 100
        remaining_tokens = max(0, max_tokens - new_total)

        # setup progress display
        progress = Progress(
            TextColumn("[bold blue]Tokens:[/]"),
            BarColumn(bar_width=40),
            TextColumn("[progress.percentage]{task.percentage:>3.1f}%"),
            TextColumn("|"),
            TextColumn("[green]{task.completed:,}[/] / [dim]{task.total:,}[/]"),
            TextColumn(f"(Current: P:{prompt_tokens:,} + C:{completion_tokens:,} = {current_call_tokens:,})")

        )

        # add task to progress bar
        progress.add_task("Conversation Progress", total=max_tokens, completed=new_total)

        self.console.print("\nToken Usage:")
        self.console.print(progress)

        # update the color based on percentage
        color = "green"
        if used_percentage > 75:
            color = "yellow"
        if used_percentage > 90:
            color = "red"

        # update the progress bar style AFTER adding the task
        progress.columns[1].style = color # BarColumn style


        # print warning if remaining tokens are low
        if remaining_tokens < 20000:
            self.console.print(f"[bold red]Warning: Only {remaining_tokens:,} tokens remaining![/bold red]")

        self.console.print("---")

    def _get_completion(self):
        """
        get a completion from the OpenRouter API.
        handles both text-only and multimodal messages.
        """
        try:
            # create a copy of the conversation history with system message as first user message if needed
            messages = []

            # check if we need to add the system message
            system_message_added = False
            if self.conversation_history and len(self.conversation_history) > 0:
                # copy existing messages
                for msg in self.conversation_history:
                    # skip any system messages as OpenRouter might not support them
                    if msg.get('role') == 'system':
                        system_message_added = True
                        # convert system message to user message for compatibility
                        messages.append({
                            "role": "user",
                            "content": f"System instructions: {msg.get('content', '')}"
                        })
                    else:
                        messages.append(msg)

            # if no system message was found and added, add it as the first user message
            if not system_message_added and (not messages or messages[0].get('role') != 'user'):
                # add system instructions as a user message at the beginning
                messages.insert(0, {
                    "role": "user",
                    "content": f"System instructions: {SystemPrompts.DEFAULT}\n\n{SystemPrompts.TOOL_USAGE}"
                })

            # make the API call
            response = self.client.chat.completions.create(
                model=self.current_model,
                max_tokens=min(
                    Config.MAX_TOKENS,
                    Config.MAX_CONVERSATION_TOKENS - self.total_tokens_used
                ),
                temperature=self.temperature,
                tools=self.tools,
                messages=messages
            )

            # response received

            # update token usage based on response usage
            if hasattr(response, 'usage') and response.usage:
                # handle different token usage formats
                if hasattr(response.usage, 'prompt_tokens') and hasattr(response.usage, 'completion_tokens'):
                    # OpenAI format
                    message_tokens = response.usage.prompt_tokens + response.usage.completion_tokens
                elif hasattr(response.usage, 'input_tokens') and hasattr(response.usage, 'output_tokens'):
                    # anthropic format
                    message_tokens = response.usage.input_tokens + response.usage.output_tokens
                else:
                    # fallback to total_tokens if available
                    message_tokens = getattr(response.usage, 'total_tokens', 0)

                self.total_tokens_used += message_tokens
                self._display_token_usage(response.usage)

            if self.total_tokens_used >= Config.MAX_CONVERSATION_TOKENS:
                self.console.print("\n[bold red]Token limit reached! Please reset the conversation.[/bold red]")
                return "Token limit reached! Please type 'reset' to start a new conversation."

            # validate response structure
            if not hasattr(response, 'choices') or not response.choices:
                self.console.print("[red]Error: Invalid response from API[/red]")
                return "Error: Invalid response from API"

            # check if the model wants to use tools
            choice = response.choices[0]
            if not hasattr(choice, 'message') or not choice.message:
                self.console.print("[red]Error: Invalid message format in response[/red]")
                return "Error: Invalid message format in response"

            if hasattr(choice, 'finish_reason') and choice.finish_reason == "tool_calls" and hasattr(choice.message, 'tool_calls') and choice.message.tool_calls:

                tool_results = []
                message = response.choices[0].message

                # add the assistant's message to the conversation history
                self.conversation_history.append({
                    "role": "assistant",
                    "content": message.content,
                    "tool_calls": message.tool_calls
                })

                # process each tool call
                for tool_call in message.tool_calls:
                    # extract tool information
                    tool_name = tool_call.function.name
                    tool_args = json.loads(tool_call.function.arguments)

                    # print the specific tool being handled
                    self.console.print(f"\n[bold yellow]  Handling Tool: {tool_name}...[/bold yellow]\n")

                    # display tool arguments before execution
                    try:
                        input_json_str = json.dumps(tool_args, indent=2)
                        # add background_color="default" to use terminal background
                        input_syntax = Syntax(input_json_str, "json", theme="default", line_numbers=False, background_color="default")
                        self.console.print("[yellow]  Arguments:[/yellow]")
                        self.console.print(input_syntax)
                        self.console.print("---") # separator after args
                    except TypeError:
                        self.console.print(f"[yellow]  Arguments:[/yellow] {tool_args!s}")
                        self.console.print("---")


                    # execute the tool
                    try:
                        # find and execute the tool
                        module = importlib.import_module(f'code_route.tools.{tool_name}')
                        tool_instance = self._find_tool_instance_in_module(module, tool_name)

                        if not tool_instance:
                            result = f"Tool not found: {tool_name}"
                        else:
                            # execute the tool with the provided input
                            result = tool_instance.execute(**tool_args)
                    except Exception as e:
                        result = f"Error executing tool '{tool_name}': {e!s}"

                    # add the tool result to the conversation
                    tool_results.append({
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "name": tool_name,
                        "content": json.dumps(result) if isinstance(result, (dict, list)) else str(result)
                    })

                # add all tool results to the conversation history
                for tool_result in tool_results:
                    self.conversation_history.append(tool_result)

                # continue the conversation with the tool results
                return self._get_completion()  # recursive call

            # final assistant response
            message = response.choices[0].message
            if hasattr(message, 'content') and message.content:
                self.conversation_history.append({
                    "role": "assistant",
                    "content": message.content
                })
                return message.content
            else:
                self.console.print("[red]No content in final response.[/red]")
                return "No response content available."

        except Exception as e:
            logging.error(f"Error in _get_completion: {e!s}")
            self.console.print(f"[red]Error: {e!s}[/red]")
            return f"Error: {e!s}"

    def chat(self, user_input):
        """
        process a chat message from the user.
        user_input can be either a string (text-only) or a list (multimodal message)
        """
        # handle special commands only for text-only messages
        if isinstance(user_input, str):
            if user_input.lower() == 'refresh':
                self.refresh_tools()
                return "Tools refreshed successfully!"
            elif user_input.lower() == 'reset':
                self.reset()
                return "Conversation reset!"
            elif user_input.lower() == 'quit':
                return "Goodbye!"
            elif user_input.lower() == 'models':
                return self.list_models()
            elif user_input.lower().startswith('model '):
                model_name = user_input[6:].strip()
                return self.set_model(model_name)

        try:
            # add user message to conversation history
            self.conversation_history.append({
                "role": "user",
                "content": user_input  # this can be either string or list
            })

            # show thinking indicator if enabled
            if self.thinking_enabled:
                with Live(Spinner('aesthetic', text=' Thinking...', style="cyan"),
                         refresh_per_second=10, transient=True):
                    response = self._get_completion()
            else:
                response = self._get_completion()

            return response

        except Exception as e:
            logging.error(f"Error in chat: {e!s}")
            return f"Error: {e!s}"

    def reset(self):
        """
        Reset the assistant's memory and token usage.
        """
        self.conversation_history = []
        self.total_tokens_used = 0
        
        reset_text = Text.assemble(
            (f"{STATUS_ICONS['refresh']} Assistant memory has been reset!", "success bold")
        )
        reset_panel = Panel(reset_text, style="success", border_style="green")
        self.console.print(reset_panel)

        welcome_text = f"""
# {STATUS_ICONS['rocket']} Code Route - AI Assistant Framework

**Available Commands:**
• `refresh` - Reload available tools
• `reset` - Clear conversation history  
• `models` - List available models
• `model <name>` - Switch models
• `quit` - Exit application

**Ready to assist with tool creation and execution!**
"""
        self.console.print(Markdown(welcome_text))
        self.display_available_tools()


def main():
    """
    Entry point for the assistant CLI loop.
    Provides a prompt for user input and handles commands.
    """
    console = get_themed_console()
    from .themes import PROMPT_STYLE
    
    try:
        assistant = Assistant()
    except ValueError as e:
        error_panel = Panel(
            Text.assemble(
                (f"{STATUS_ICONS['error']} Configuration Error: ", "red bold"),
                (str(e), "red"),
                ("\n\nPlease ensure OPENROUTER_API_KEY is set correctly.", "white")
            ),
            border_style="red"
        )
        console.print(error_panel)
        return

    # Show initial welcome
    welcome_text = f"""
# {STATUS_ICONS['rocket']} Code Route - AI Assistant Framework

**Available Commands:**
• `refresh` - Reload available tools
• `reset` - Clear conversation history  
• `models` - List available models
• `model <name>` - Switch models
• `quit` - Exit application

**Ready to assist with tool creation and execution!**
"""
    console.print(Markdown(welcome_text))
    assistant.display_available_tools()

    while True:
        try:
            user_input = prompt(f"{STATUS_ICONS['user']} You: ", style=PROMPT_STYLE).strip()
            
            if not user_input:
                continue

            if user_input.lower() == 'quit':
                goodbye_text = Text.assemble(
                    (f"{STATUS_ICONS['heart']} Goodbye! Thanks for using Code Route!", "primary bold")
                )
                console.print(Panel(goodbye_text, style="primary", border_style="blue"))
                break
            elif user_input.lower() == 'reset':
                assistant.reset()
                continue
            elif user_input.lower().startswith('export '):
                parts = user_input.split(maxsplit=1)
                if len(parts) < 2 or not parts[1].strip():
                    console.print("[bold red]Export command requires a filename. Usage: export <filename>[/bold red]")
                else:
                    filename = parts[1].strip()
                    # Assuming assistant.export_conversation(filename) will be implemented
                    # For now, let's simulate the call and success
                    try:
                        # Placeholder for actual export logic:
                        # assistant.export_conversation(filename)
                        # This is where the actual method call will go.
                        # For this step, we'll just print a message as if it worked.
                        # In a future step, we'll implement assistant.export_conversation.
                        with open(filename, 'w') as f:
                            # Simulate writing some conversation data for testing purposes
                            f.write(json.dumps(assistant.conversation_history, indent=2))
                        console.print(f"\n[bold green]Conversation exported to {filename}[/bold green]")
                    except Exception as e:
                        console.print(f"\n[bold red]Error exporting conversation: {e!s}[/bold red]")
                continue

            response = assistant.chat(user_input)
            
            # Display the response with nice formatting
            try:
                response_text = Text()
                response_text.append(f"{STATUS_ICONS['assistant']} ", style="bright_magenta")
                response_text.append("Code Route:", style="bright_magenta bold")
                console.print(response_text)
            except Exception as style_error:
                console.print(f"[red]Style error: {style_error}[/red]")
                console.print("🤖 Code Route:")
            if isinstance(response, str):
                # Handle rich markup in responses
                try:
                    console.print(Markdown(response))
                except Exception:
                    # Fallback to safe printing
                    safe_response = response.replace('[', '\\[').replace(']', '\\]')
                    console.print(safe_response)
            else:
                console.print(str(response))

        except KeyboardInterrupt:
            continue
        except EOFError:
            break


if __name__ == "__main__":
    main()