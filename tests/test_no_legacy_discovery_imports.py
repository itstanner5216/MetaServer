from __future__ import annotations

import re
from pathlib import Path


FORBIDDEN_PATTERNS = [
    r"from\s+meta_mcp\.discovery\s+import\s+tool_registry",
    r"from\s+src\.meta_mcp\.discovery\s+import\s+tool_registry",
    r"from\s+\.discovery\s+import\s+tool_registry",
    r"meta_mcp\.discovery\.tool_registry",
]


def test_no_new_discovery_tool_registry_imports():
    src_root = Path(__file__).resolve().parents[1] / "src"
    assert src_root.exists(), "Expected src directory to exist for import checks."

    violations: list[str] = []
    pattern = re.compile("|".join(FORBIDDEN_PATTERNS))

    for path in src_root.rglob("*.py"):
        if path.name == "discovery.py":
            continue
        content = path.read_text(encoding="utf-8")
        if pattern.search(content):
            violations.append(str(path.relative_to(src_root)))

    assert not violations, (
        "New code should not import meta_mcp.discovery.tool_registry. "
        "Use meta_mcp.registry.tool_registry instead. "
        f"Found in: {', '.join(sorted(violations))}"
    )
