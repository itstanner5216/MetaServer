#!/bin/bash
set -e

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}GitHub Secrets Setup Helper${NC}\n"

# Check for gh CLI
if ! command -v gh &> /dev/null; then
    echo -e "${YELLOW}GitHub CLI (gh) is required but not installed.${NC}"
    echo "Install it from: https://cli.github.com/"
    exit 1
fi

# Check authentication
if ! gh auth status &> /dev/null; then
    echo -e "${YELLOW}Not authenticated with GitHub CLI. Running auth...${NC}"
    gh auth login
fi

echo -e "${GREEN}✅ Authenticated with GitHub${NC}\n"

# Codecov token
echo -e "${BLUE}Setting up Codecov token...${NC}"
echo "1. Visit https://codecov.io and sign in with GitHub"
echo "2. Add repository: itstanner5216/MetaServer"
echo "3. Copy your repository token"
echo ""
read -p "Enter your Codecov token (or press Enter to skip): " codecov_token

if [[ -n "$codecov_token" ]]; then
    gh secret set CODECOV_TOKEN --body "$codecov_token"
    echo -e "${GREEN}✅ CODECOV_TOKEN set${NC}\n"
else
    echo -e "${YELLOW}⚠️  Skipped Codecov token${NC}\n"
fi

# Completion message
echo -e "${GREEN}Setup complete!${NC}"
echo -e "\n${BLUE}Next steps:${NC}"
echo "1. Configure PyPI trusted publishing at: https://pypi.org/manage/account/publishing/"
echo "2. Run validation: gh workflow run validate-setup.yml"
echo "3. Check setup issue in your repository"
