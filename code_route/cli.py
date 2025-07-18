#!/usr/bin/env python3

"""
Code Route CLI - Global command line interface

This module provides the main CLI entry point for Code Route,
handling initialization, configuration, and launching the assistant.
"""

import argparse
import os
import sys
import subprocess
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.align import Align

from .config import Config
from .assistant import Assistant
from .themes import get_themed_console, STATUS_ICONS


console = get_themed_console()


def show_banner():
    """Display the Code Route banner"""
    title_text = Text()
    title_text.append("🛤️  ", style="bright_yellow")
    title_text.append("CODE ROUTE", style="bright_blue bold")
    title_text.append("  ✨", style="bright_yellow")
    
    subtitle = Text("AI Assistant with Dynamic Tool Creation", style="cyan italic")
    
    banner_content = Align.center(
        Text.assemble(
            title_text, "\n",
            subtitle, "\n",
            Text("──────────────────────────────────", style="dim"),
        )
    )
    
    console.print(Panel(
        banner_content,
        style="primary",
        border_style="bright_blue",
        padding=(1, 2),
        title=f"{STATUS_ICONS['rocket']} Welcome",
        title_align="left"
    ))


def check_config():
    """Check if the configuration is properly set up"""
    if not getattr(Config, 'OPENROUTER_API_KEY', None):
        error_panel = Panel(
            Text.assemble(
                (f"{STATUS_ICONS['error']} Missing API Configuration\n\n", "bold red"),
                ("To use Code Route, you need to set up your OpenRouter API key:\n\n", "white"),
                ("1. ", "bright_cyan"), ("Get an API key from: ", "white"), ("https://openrouter.ai/\n", "blue underline"),
                ("2. ", "bright_cyan"), ("Create a .env file in any project directory:\n", "white"),
                ("   ", ""), ("OPENROUTER_API_KEY=your_api_key_here\n\n", "yellow"),
                ("Or set it as an environment variable:\n", "white"),
                ("   ", ""), ("export OPENROUTER_API_KEY=your_api_key_here", "yellow")
            ),
            title=f"{STATUS_ICONS['config']} Setup Required",
            border_style="red",
            padding=(1, 2)
        )
        console.print(error_panel)
        return False
    return True


def init_project():
    """Initialize Code Route in the current directory"""
    cwd = Path.cwd()
    env_file = cwd / ".env"
    
    init_steps = []
    init_steps.append(f"{STATUS_ICONS['directory']} Working directory: {cwd}")
    
    if env_file.exists():
        init_steps.append(f"{STATUS_ICONS['success']} .env file already exists")
    else:
        init_steps.append(f"{STATUS_ICONS['file']} Creating .env file...")
        with open(env_file, "w") as f:
            f.write("# Code Route Configuration\n")
            f.write("OPENROUTER_API_KEY=your_api_key_here\n")
            f.write("# E2B_API_KEY=your_e2b_key_here  # Optional for secure code execution\n")
        
        init_steps.append(f"{STATUS_ICONS['success']} Created {env_file}")
        init_steps.append(f"{STATUS_ICONS['warning']} Please edit .env and add your OpenRouter API key")
    
    init_panel = Panel(
        "\n".join(init_steps) + f"\n\n{STATUS_ICONS['sparkles']} Run 'code-route' or 'cr' to start the assistant",
        title=f"{STATUS_ICONS['rocket']} Code Route Initialized",
        border_style="green",
        padding=(1, 2)
    )
    
    console.print(init_panel)


def show_tools():
    """Show available tools"""
    try:
        assistant = Assistant()
        tools_table = Table(
            title=f"{STATUS_ICONS['tool']} Available Tools ({len(assistant.tools)} loaded)",
            show_header=True,
            header_style="bold cyan",
            border_style="cyan"
        )
        tools_table.add_column("Tool Name", style="bright_yellow", width=25)
        tools_table.add_column("Description", style="white")
        
        for tool in sorted(assistant.tools, key=lambda x: x.get('function', {}).get('name', '')):
            func_info = tool.get('function', {})
            name = func_info.get('name', 'Unknown')
            desc = func_info.get('description', 'No description available')
            
            if len(desc) > 80:
                desc = desc[:77] + "..."
            
            tools_table.add_row(f"{STATUS_ICONS.get('gear', '⚙️')} {name}", desc)
        
        if not assistant.tools:
            tools_table.add_row("No tools loaded", "Check your configuration")
        
        console.print(tools_table)
        return True
    except Exception as e:
        error_text = Text.assemble(
            (f"{STATUS_ICONS['error']} Error loading tools: ", "red"),
            (str(e), "red dim")
        )
        console.print(Panel(error_text, border_style="red"))
        return False


def launch_web():
    """Launch the web interface"""
    launch_text = Text.assemble(
        (f"{STATUS_ICONS['web']} Launching Code Route Web Interface...", "bright_cyan"),
    )
    console.print(Panel(launch_text, border_style="cyan"))
    
    try:
        import streamlit
        app_path = Path(__file__).parent / "app.py"
        subprocess.run([sys.executable, "-m", "streamlit", "run", str(app_path)], check=True)
    except ImportError:
        error_text = Text.assemble(
            (f"{STATUS_ICONS['error']} Streamlit not available\n", "red"),
            ("Install with: ", "white"),
            ("pip install streamlit", "yellow")
        )
        console.print(Panel(error_text, border_style="red"))
    except Exception as e:
        error_text = Text.assemble(
            (f"{STATUS_ICONS['error']} Error launching web interface:\n", "red"),
            (str(e), "red dim")
        )
        console.print(Panel(error_text, border_style="red"))


def show_status():
    """Show system status"""
    status_table = Table(
        title=f"{STATUS_ICONS['dashboard']} Code Route System Status",
        show_header=True,
        header_style="bold cyan",
        border_style="cyan"
    )
    status_table.add_column("Component", style="bright_cyan", width=20)
    status_table.add_column("Status", style="white", width=15)
    status_table.add_column("Details", style="dim white")
    
    api_key = getattr(Config, 'OPENROUTER_API_KEY', None)
    if api_key:
        api_status = f"{STATUS_ICONS['success']} Configured"
        api_details = f"Key: ...{api_key[-8:]}" if len(api_key) > 8 else "Key set"
    else:
        api_status = f"{STATUS_ICONS['error']} Missing"
        api_details = "Required for operation"
    status_table.add_row("OpenRouter API", api_status, api_details)
    
    e2b_key = getattr(Config, 'E2B_API_KEY', None)
    if e2b_key:
        e2b_status = f"{STATUS_ICONS['success']} Configured"
        e2b_details = "Secure code execution enabled"
    else:
        e2b_status = f"{STATUS_ICONS['info']} Optional"
        e2b_details = "For secure code execution"
    status_table.add_row("E2B API", e2b_status, e2b_details)
    
    try:
        assistant = Assistant()
        tool_count = len(assistant.tools)
        tools_status = f"{STATUS_ICONS['success']} {tool_count} loaded"
        tools_details = f"Ready for use"
    except Exception as e:
        tools_status = f"{STATUS_ICONS['error']} Error"
        tools_details = str(e)[:50] + "..." if len(str(e)) > 50 else str(e)
    status_table.add_row("Tools", tools_status, tools_details)
    
    cwd = Path.cwd()
    env_exists = (cwd / ".env").exists()
    dir_status = f"{STATUS_ICONS['success']} Ready" if env_exists else f"{STATUS_ICONS['warning']} No .env"
    dir_details = str(cwd)
    status_table.add_row("Directory", dir_status, dir_details)
    
    console.print(status_table)


def main():
    """Main CLI entry point"""
    parser = argparse.ArgumentParser(
        description="Code Route - AI Assistant with Tool Creation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  code-route              Start interactive assistant
  code-route --web        Launch web interface
  code-route --init       Initialize in current directory
  code-route --tools      Show available tools
  code-route --status     Show system status
        """
    )
    
    parser.add_argument("--web", action="store_true", help="Launch web interface")
    parser.add_argument("--init", action="store_true", help="Initialize Code Route in current directory")
    parser.add_argument("--tools", action="store_true", help="Show available tools")
    parser.add_argument("--status", action="store_true", help="Show system status")
    parser.add_argument("--version", action="version", version=f"Code Route {getattr(Config, 'VERSION', '0.1.0')}")
    parser.add_argument("--no-banner", action="store_true", help="Skip banner display")
    
    args = parser.parse_args()
    
    if args.init:
        init_project()
        return
    
    if args.status:
        show_status()
        return
    
    if not args.no_banner:
        show_banner()
    
    if args.tools:
        if not check_config():
            sys.exit(1)
        show_tools()
        return
    
    if args.web:
        if not check_config():
            sys.exit(1)
        launch_web()
        return
    
    if not check_config():
        console.print("\n💡 Use 'code-route --init' to set up a new project")
        sys.exit(1)
    
    try:
        from .assistant import main as assistant_main
        assistant_main()
    except KeyboardInterrupt:
        console.print("\n[bold blue]👋 Goodbye![/bold blue]")
    except Exception as e:
        console.print(f"[red]Error starting assistant: {e}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()