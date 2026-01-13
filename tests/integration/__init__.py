"""Integration tests for Meta MCP Server.

This package contains end-to-end integration tests that verify
multiple phases work together correctly.

Test Organization:
- test_full_discovery_flow.py: Phase 1 + 2 + 5 + 6 (Discovery, Schema, TOON)
- test_lease_governance_flow.py: Phase 3 + 4 (Leases, Governance, Tokens)
- test_notification_flow.py: Phase 8 (Notifications, list_changed)
- test_macro_integration.py: Phase 7 + 4 (Macros, Governance)
- test_end_to_end_scenario.py: Complete workflow across all phases
"""
