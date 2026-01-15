#!/bin/bash
set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         MetaServer Development Setup                     ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# Check prerequisites
echo -e "${YELLOW}Checking prerequisites...${NC}"

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python 3 is not installed!${NC}"
    exit 1
fi

python_version=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
required_version="3.10"

# Simple version comparison
major_minor=$(echo "$python_version" | cut -d'.' -f1,2)
required_major=$(echo "$required_version" | cut -d'.' -f1)
required_minor=$(echo "$required_version" | cut -d'.' -f2)
current_major=$(echo "$major_minor" | cut -d'.' -f1)
current_minor=$(echo "$major_minor" | cut -d'.' -f2)

if [ "$current_major" -lt "$required_major" ] || { [ "$current_major" -eq "$required_major" ] && [ "$current_minor" -lt "$required_minor" ]; }; then
    echo -e "${RED}❌ Python $required_version or higher is required (found $python_version)${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Python $python_version${NC}"

# Check for UV
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}⚠️  UV is not installed. Installing...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi

echo -e "${GREEN}✅ UV installed${NC}"

# Check for gh CLI
if ! command -v gh &> /dev/null; then
    echo -e "${YELLOW}⚠️  GitHub CLI (gh) is not installed${NC}"
    echo -e "${YELLOW}   Install it from: https://cli.github.com/${NC}"
else
    echo -e "${GREEN}✅ GitHub CLI installed${NC}"
fi

# Install dependencies
echo -e "\n${YELLOW}Installing dependencies...${NC}"
uv sync
echo -e "${GREEN}✅ Dependencies installed${NC}"

# Setup pre-commit hooks if available
if [[ -f ".pre-commit-config.yaml" ]]; then
    echo -e "\n${YELLOW}Setting up pre-commit hooks...${NC}"
    uv run pre-commit install
    uv run pre-commit install --hook-type commit-msg
    echo -e "${GREEN}✅ Pre-commit hooks installed${NC}"
    
    # Run initial validation
    echo -e "\n${YELLOW}Running initial validation...${NC}"
    uv run pre-commit run --all-files || echo -e "${YELLOW}⚠️  Pre-commit found issues (this is normal on first run)${NC}"
else
    echo -e "\n${YELLOW}⚠️  .pre-commit-config.yaml not found, skipping pre-commit setup${NC}"
fi

# Run tests
echo -e "\n${YELLOW}Running tests...${NC}"
uv run pytest || echo -e "${YELLOW}⚠️  Some tests may be failing${NC}"

# Setup complete
echo -e "\n${GREEN}"
echo "╔══════════════════════════════════════════════════════════╗"
echo "║         Setup Complete! 🎉                               ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo -e "${NC}"

echo -e "\n${BLUE}Quick Start Commands:${NC}"
echo -e "  ${GREEN}uv run pytest${NC}          - Run tests"
if [[ -f "ruff.toml" ]] || uv run ruff --version &> /dev/null; then
    echo -e "  ${GREEN}uv run ruff check .${NC}    - Lint code"
    echo -e "  ${GREEN}uv run ruff format .${NC}   - Format code"
fi
if uv run pyright --version &> /dev/null; then
    echo -e "  ${GREEN}uv run pyright${NC}         - Type check"
fi

echo -e "\n${BLUE}For CI/CD setup, see the issue created in your repository.${NC}"
