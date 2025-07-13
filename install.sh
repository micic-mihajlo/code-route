#!/bin/bash
# Code Route Installation Script

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Icons
ROCKET="🚀"
CHECK="✅"
CROSS="❌"
WARNING="⚠️"
INFO="ℹ️"

print_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════╗"
    echo "║           🛤️  CODE ROUTE INSTALLER        ║"
    echo "║     Global AI Assistant Installation      ║"
    echo "╚═══════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_step() {
    echo -e "${BLUE}${ROCKET} $1${NC}"
}

print_success() {
    echo -e "${GREEN}${CHECK} $1${NC}"
}

print_error() {
    echo -e "${RED}${CROSS} $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}${WARNING} $1${NC}"
}

print_info() {
    echo -e "${CYAN}${INFO} $1${NC}"
}

check_requirements() {
    print_step "Checking system requirements..."
    
    # Check Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3.9+ is required but not installed"
        exit 1
    fi
    
    python_version=$(python3 -c "import sys; print('.'.join(map(str, sys.version_info[:2])))")
    required_version="3.9"
    
    if ! python3 -c "import sys; exit(0 if sys.version_info >= (3, 9) else 1)" 2>/dev/null; then
        print_error "Python 3.9+ is required (found: $python_version)"
        exit 1
    fi
    
    print_success "Python $python_version found"
    
    # Check if pip is available
    if ! command -v pip3 &> /dev/null && ! command -v pip &> /dev/null; then
        print_error "pip is required but not installed"
        exit 1
    fi
    
    print_success "pip found"
}

install_with_pip() {
    print_step "Installing Code Route with pip..."
    
    # Install from local directory
    if [ -f "pyproject.toml" ]; then
        pip3 install -e . || pip install -e .
        print_success "Installed Code Route from local directory"
    else
        # Install from git (future)
        print_info "Installing from PyPI (when available) or git repository"
        # pip3 install code-route || pip install code-route
        print_error "Please run this script from the Code Route repository directory"
        exit 1
    fi
}

install_with_uv() {
    print_step "Installing Code Route with uv (recommended)..."
    
    # Check if uv is installed
    if ! command -v uv &> /dev/null; then
        print_info "uv not found, installing uv first..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        source ~/.bashrc 2>/dev/null || source ~/.zshrc 2>/dev/null || true
        export PATH="$HOME/.cargo/bin:$PATH"
    fi
    
    if command -v uv &> /dev/null; then
        if [ -f "pyproject.toml" ]; then
            uv pip install -e .
            print_success "Installed Code Route with uv"
        else
            print_error "Please run this script from the Code Route repository directory"
            exit 1
        fi
    else
        print_warning "Failed to install uv, falling back to pip"
        install_with_pip
    fi
}

verify_installation() {
    print_step "Verifying installation..."
    
    if command -v code-route &> /dev/null; then
        print_success "code-route command is available"
        code-route --version
    else
        print_error "code-route command not found in PATH"
        print_info "You may need to add ~/.local/bin to your PATH"
        print_info "Add this to your ~/.bashrc or ~/.zshrc:"
        echo "export PATH=\"\$HOME/.local/bin:\$PATH\""
        exit 1
    fi
    
    if command -v cr &> /dev/null; then
        print_success "cr command is available"
    else
        print_warning "cr shortcut command not found (this is optional)"
    fi
}

setup_completion() {
    print_step "Setting up shell completion (optional)..."
    
    # Create basic completion script
    completion_dir="$HOME/.local/share/bash-completion/completions"
    mkdir -p "$completion_dir"
    
    cat > "$completion_dir/code-route" << 'EOF'
_code_route_completion() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"
    opts="--web --init --tools --status --version --help"
    
    COMPREPLY=( $(compgen -W "${opts}" -- ${cur}) )
    return 0
}
complete -F _code_route_completion code-route
complete -F _code_route_completion cr
EOF
    
    print_success "Shell completion installed"
    print_info "Restart your shell or run: source ~/.bashrc"
}

show_next_steps() {
    echo
    print_success "Installation complete!"
    echo
    print_info "Next steps:"
    echo "1. Run 'code-route --init' in any project directory to set up"
    echo "2. Get an OpenRouter API key from https://openrouter.ai/"
    echo "3. Add your API key to the .env file"
    echo "4. Run 'code-route' to start the assistant"
    echo
    print_info "Available commands:"
    echo "  code-route          - Start interactive assistant"
    echo "  code-route --web    - Launch web interface"
    echo "  code-route --init   - Initialize in current directory"
    echo "  code-route --tools  - Show available tools"
    echo "  code-route --status - Show system status"
    echo "  cr                  - Short alias for code-route"
    echo
    print_info "Documentation: https://github.com/micic-mihajlo/code-route"
}

main() {
    print_banner
    
    check_requirements
    
    # Choose installation method
    if command -v uv &> /dev/null || [ "$1" = "--uv" ]; then
        install_with_uv
    else
        install_with_pip
    fi
    
    verify_installation
    setup_completion
    show_next_steps
}

# Run main function
main "$@"