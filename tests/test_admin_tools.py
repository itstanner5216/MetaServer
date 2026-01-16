"""Tests for admin tools documentation and exposure policy."""

from servers import admin_tools


def test_admin_tools_docstring_mentions_registry():
    """Admin tools should document registry inclusion and governance rules."""
    doc = admin_tools.__doc__ or ""
    assert "registered" in doc.lower()
    assert "governance" in doc.lower()
    assert "read_only" in doc.lower()
