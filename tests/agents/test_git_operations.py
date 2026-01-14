"""Tests for Git operations utility."""

import pytest
from pathlib import Path
import tempfile
import subprocess
from scripts.agents.utils.git_operations import GitOperations


@pytest.fixture
def temp_git_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test User"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        
        # Create initial commit
        test_file = repo_path / "test.txt"
        test_file.write_text("initial content")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        
        yield repo_path


def test_git_operations_init(temp_git_repo):
    """Test GitOperations initialization."""
    git_ops = GitOperations(repo_path=str(temp_git_repo))
    assert git_ops.repo_path == temp_git_repo


def test_get_current_branch(temp_git_repo):
    """Test getting current branch."""
    git_ops = GitOperations(repo_path=str(temp_git_repo))
    branch = git_ops.get_current_branch()
    assert branch in ["main", "master"]  # Could be either


def test_has_uncommitted_changes(temp_git_repo):
    """Test detecting uncommitted changes."""
    git_ops = GitOperations(repo_path=str(temp_git_repo))
    
    # Should have no uncommitted changes initially
    assert not git_ops.has_uncommitted_changes()
    
    # Create a new file
    test_file = temp_git_repo / "new_file.txt"
    test_file.write_text("new content")
    
    # Should now have uncommitted changes
    assert git_ops.has_uncommitted_changes()


def test_create_and_checkout_branch(temp_git_repo):
    """Test branch creation and checkout."""
    git_ops = GitOperations(repo_path=str(temp_git_repo))
    
    # Create new branch
    git_ops.create_branch("test-branch")
    
    # Checkout the branch
    git_ops.checkout("test-branch")
    
    # Verify current branch
    assert git_ops.get_current_branch() == "test-branch"


def test_add_and_commit(temp_git_repo):
    """Test adding files and committing."""
    git_ops = GitOperations(repo_path=str(temp_git_repo))
    
    # Create a new file
    test_file = temp_git_repo / "commit_test.txt"
    test_file.write_text("test content")
    
    # Add and commit
    git_ops.add_all()
    git_ops.commit("Test commit")
    
    # Should have no uncommitted changes after commit
    assert not git_ops.has_uncommitted_changes()


def test_get_changed_files(temp_git_repo):
    """Test getting list of changed files."""
    git_ops = GitOperations(repo_path=str(temp_git_repo))
    
    # Create and commit a new file
    test_file = temp_git_repo / "changed.txt"
    test_file.write_text("content")
    git_ops.add_all()
    git_ops.commit("Add changed file")
    
    # Modify the file
    test_file.write_text("modified content")
    
    # Get changed files
    changed = git_ops.get_changed_files()
    assert "changed.txt" in changed
