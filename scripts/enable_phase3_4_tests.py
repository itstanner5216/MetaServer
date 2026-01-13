#!/usr/bin/env python3
"""
Script to enable Phase 3 and Phase 4 tests by uncommenting them.

This script removes the pytest.mark.skip decorators and uncomments
all test code in the Phase 3 and Phase 4 test files.
"""

import re
from pathlib import Path


def process_file(file_path: Path) -> None:
    """Process a test file to uncomment tests."""
    print(f"Processing {file_path.name}...")

    with open(file_path, 'r') as f:
        content = f.read()

    # Remove pytestmark skip line
    content = re.sub(
        r'pytestmark = pytest\.mark\.skip\(reason="Phase [34] not yet implemented"\)\n\n',
        '',
        content
    )

    # Add imports at the top after the docstring
    imports_to_add = []

    if 'lease' in file_path.name:
        imports_to_add.extend([
            'from src.meta_mcp.leases.models import ToolLease',
            'from src.meta_mcp.leases import lease_manager',
        ])

    if 'token' in file_path.name or 'capability' in file_path.name:
        imports_to_add.extend([
            'from src.meta_mcp.governance.tokens import generate_token, verify_token, decode_token',
            'from src.meta_mcp.config import Config',
        ])

    if 'policy' in file_path.name:
        imports_to_add.extend([
            'from src.meta_mcp.governance.policy import evaluate_policy',
            'from src.meta_mcp.state import ExecutionMode',
        ])

    if 'governance_integration' in file_path.name or 'schema_leakage' in file_path.name:
        imports_to_add.extend([
            'from src.meta_mcp.leases import lease_manager',
            'from src.meta_mcp.governance.tokens import generate_token, verify_token',
            'from src.meta_mcp.governance.policy import evaluate_policy',
            'from src.meta_mcp.config import Config',
            'from src.meta_mcp.state import governance_state, ExecutionMode',
        ])

    # Find the position after imports
    match = re.search(r'(import pytest\nfrom [^\n]+\n)', content)
    if match and imports_to_add:
        pos = match.end()
        imports_str = '\n'.join(imports_to_add) + '\n'
        content = content[:pos] + imports_str + content[pos:]

    # Uncomment all test code within async def test_ functions
    # This is a simplified approach - uncomment lines starting with #
    lines = content.split('\n')
    new_lines = []
    in_test = False

    for line in lines:
        # Detect test function start
        if re.match(r'^(async )?def test_', line):
            in_test = True
        elif in_test and re.match(r'^(async )?def ', line):
            in_test = False

        # Uncomment if in test function and line starts with #
        if in_test and line.strip().startswith('#'):
            # Remove leading # and one space
            stripped = line.lstrip()
            if stripped.startswith('# '):
                uncommented = line.replace('# ', '', 1)
                new_lines.append(uncommented)
            elif stripped.startswith('#'):
                uncommented = line.replace('#', '', 1)
                new_lines.append(uncommented)
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    # Remove empty pass statements
    content = '\n'.join(new_lines)
    content = re.sub(r'\n\n    pass\n', '\n', content)

    # Write back
    with open(file_path, 'w') as f:
        f.write(content)

    print(f"  ✓ {file_path.name} updated")


def main():
    """Main entry point."""
    test_dir = Path(__file__).parent.parent / 'tests'

    # Phase 3 test files
    phase3_files = [
        'test_lease_models.py',
        'test_lease_manager.py',
        'test_lease_security.py',
    ]

    # Phase 4 test files
    phase4_files = [
        'test_token_security.py',
        'test_schema_leakage.py',
        'test_capability_tokens.py',
        'test_governance_integration.py',
        'test_policy_engine.py',
    ]

    all_files = phase3_files + phase4_files

    print(f"Enabling {len(all_files)} test files...")
    print()

    for filename in all_files:
        file_path = test_dir / filename
        if file_path.exists():
            try:
                process_file(file_path)
            except Exception as e:
                print(f"  ✗ Error processing {filename}: {e}")
        else:
            print(f"  ⚠ File not found: {filename}")

    print()
    print("Done! Run tests with:")
    print("  pytest tests/test_lease_*.py tests/test_*_security.py tests/test_governance_*.py tests/test_policy_*.py tests/test_capability_*.py -v")


if __name__ == '__main__':
    main()
