"""Integration test to verify hook system works with middleware."""

import asyncio
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import yaml

# Add parent directory to path for direct execution
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from meta_mcp.agent_detector import detect_agent_id
from meta_mcp.hooks import GateType, hook_manager


async def test_hook_disabled_by_default():
    """Verify hooks are disabled without config."""
    print("Test 1: Hooks disabled by default")
    
    # Simulate a call
    session_id = "test_session_1"
    tool_name = "read_file"
    args = {"path": "/etc/passwd"}
    
    violation, receipt = await hook_manager.run_before_tool_call(
        session_id, tool_name, args
    )
    
    assert violation is None, "Should not block when hooks disabled"
    assert receipt is None, "Should not create receipt when hooks disabled"
    print("✅ PASS: Hooks properly disabled without config\n")


async def test_hook_with_valid_config():
    """Verify hooks work with valid config."""
    print("Test 2: Hooks with valid config")
    
    # Create temp config
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "agents.yaml"
        config = {
            "enabled": True,
            "agents": [
                {
                    "agent_id": "test_agent",
                    "role_id": "tester",
                    "model_id": "test/model",
                    "allowed_tools": ["read_file"],
                    "denied_tools": ["delete_file"],
                    "allowed_paths": ["./workspace/**"],
                    "denied_paths": ["/etc/**"],
                    "max_tool_calls": 10,
                }
            ],
        }
        
        with open(config_path, "w") as f:
            yaml.dump(config, f)
        
        # Create manager with custom config
        from meta_mcp.hooks.manager import HookManager
        
        manager = HookManager(config_path=str(config_path))
        
        # Verify enabled
        assert manager.enabled is True, "Manager should be enabled"
        print("  ✓ Manager enabled")
        
        # Start agent run
        agent_id = "test_agent"
        session_id = "test_session_2"
        manager.start_agent_run(agent_id, session_id)
        print(f"  ✓ Started agent run: {agent_id}")
        
        # Test 1: Allowed tool passes
        violation, receipt = await manager.run_before_tool_call(
            session_id, "read_file", {"path": "./workspace/file.txt"}
        )
        assert violation is None, "Allowed tool should pass"
        assert receipt is not None, "Should create receipt"
        print("  ✓ Allowed tool passes")
        
        # Test 2: Denied tool blocked
        violation, receipt = await manager.run_before_tool_call(
            session_id, "delete_file", {"path": "./workspace/file.txt"}
        )
        assert violation is not None, "Denied tool should be blocked"
        assert violation.gate_type == GateType.TOOL_ALLOWLIST
        print("  ✓ Denied tool blocked by allowlist")
        
        # Test 3: Path fence blocks forbidden paths
        violation, receipt = await manager.run_before_tool_call(
            session_id, "read_file", {"path": "/etc/passwd"}
        )
        assert violation is not None, "Forbidden path should be blocked"
        assert violation.gate_type == GateType.PATH_FENCE
        print("  ✓ Forbidden path blocked by fence")
        
        print("✅ PASS: Hook system works correctly with config\n")


async def test_agent_detection():
    """Verify agent detection strategies."""
    print("Test 3: Agent detection")
    
    # Test 1: Environment variable
    import os
    os.environ["MCP_AGENT_ID"] = "env_agent"
    
    ctx = Mock()
    ctx.metadata = None
    ctx.request_context = Mock()
    del ctx.request_context.agent_id  # Ensure not set
    
    agent_id = detect_agent_id(ctx)
    assert agent_id == "env_agent", "Should detect from environment"
    print("  ✓ Environment variable detection")
    
    # Test 2: Metadata
    ctx2 = Mock()
    ctx2.metadata = {"agent_id": "metadata_agent"}
    agent_id = detect_agent_id(ctx2)
    assert agent_id == "metadata_agent", "Should detect from metadata"
    print("  ✓ Metadata detection")
    
    # Test 3: Request context
    ctx3 = Mock()
    ctx3.metadata = None
    ctx3.request_context = Mock()
    ctx3.request_context.agent_id = "context_agent"
    agent_id = detect_agent_id(ctx3)
    assert agent_id == "context_agent", "Should detect from request context"
    print("  ✓ Request context detection")
    
    # Cleanup
    del os.environ["MCP_AGENT_ID"]
    
    print("✅ PASS: Agent detection works correctly\n")


async def test_file_tools_auto_discovery():
    """Verify file tools are auto-discovered from registry."""
    print("Test 4: File tools auto-discovery")
    
    from meta_mcp.hooks.gates import PathFenceGate
    
    gate = PathFenceGate()
    file_tools = gate._get_file_tools()
    
    # Check we discovered tools
    assert len(file_tools) > 0, "Should discover file tools"
    print(f"  ✓ Discovered {len(file_tools)} file tools")
    
    # Check common file tools are present
    expected_tools = ["read_file", "write_file", "delete_file"]
    for tool in expected_tools:
        assert tool in file_tools, f"{tool} should be discovered"
    print(f"  ✓ Common tools present: {', '.join(expected_tools)}")
    
    # Verify move_file has correct args
    if "move_file" in file_tools:
        args = file_tools["move_file"]
        assert "source" in args and "destination" in args, "move_file should have source/dest"
        print("  ✓ Move tool has correct arguments")
    
    print("✅ PASS: File tools auto-discovery works\n")


async def test_existing_behavior_preserved():
    """Verify existing behavior is unchanged when hooks disabled."""
    print("Test 5: Existing behavior preserved")
    
    # Create a session without agent_id
    session_id = "non_agent_session"
    
    # Even if config exists, hooks shouldn't run without agent context
    violation, receipt = await hook_manager.run_before_tool_call(
        session_id, "any_tool", {}
    )
    
    assert violation is None, "Should not block non-agent sessions"
    assert receipt is None, "Should not track non-agent sessions"
    print("  ✓ Non-agent sessions unaffected")
    
    print("✅ PASS: Existing behavior preserved\n")


async def main():
    """Run all integration tests."""
    print("=" * 60)
    print("HOOK SYSTEM INTEGRATION TESTS")
    print("=" * 60 + "\n")
    
    try:
        await test_hook_disabled_by_default()
        await test_hook_with_valid_config()
        await test_agent_detection()
        await test_file_tools_auto_discovery()
        await test_existing_behavior_preserved()
        
        print("=" * 60)
        print("ALL TESTS PASSED ✅")
        print("=" * 60)
        return 0
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    exit(exit_code)
