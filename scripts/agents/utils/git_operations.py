#!/usr/bin/env python3
"""Git operations utilities for agent system."""

import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple
from dataclasses import dataclass


@dataclass
class MergeConflict:
    """Represents a merge conflict."""
    
    file_path: str
    conflict_markers: List[str]
    our_content: str
    their_content: str


class GitOperations:
    """Git operations wrapper for safe repository manipulation."""
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize Git operations.
        
        Args:
            repo_path: Path to git repository
        """
        self.repo_path = Path(repo_path).resolve()
        if not (self.repo_path / ".git").exists():
            raise ValueError(f"Not a git repository: {self.repo_path}")
    
    def _run_git(self, *args, check=True, capture_output=True) -> subprocess.CompletedProcess:
        """
        Run a git command.
        
        Args:
            *args: Git command arguments
            check: Raise exception on error
            capture_output: Capture stdout/stderr
            
        Returns:
            CompletedProcess instance
        """
        cmd = ["git", "-C", str(self.repo_path)] + list(args)
        result = subprocess.run(
            cmd,
            check=check,
            capture_output=capture_output,
            text=True,
        )
        return result
    
    def fetch_all(self):
        """Fetch all remote branches."""
        self._run_git("fetch", "--all", "--prune")
    
    def checkout(self, branch: str, create: bool = False):
        """
        Checkout a branch.
        
        Args:
            branch: Branch name
            create: Create branch if it doesn't exist
        """
        if create:
            self._run_git("checkout", "-b", branch)
        else:
            self._run_git("checkout", branch)
    
    def checkout_pr(self, pr_number: int, branch_name: str):
        """
        Checkout a PR branch locally.
        
        Args:
            pr_number: PR number
            branch_name: Local branch name to create
        """
        # Fetch the PR
        self._run_git("fetch", "origin", f"pull/{pr_number}/head:{branch_name}")
        self.checkout(branch_name)
    
    def get_current_branch(self) -> str:
        """
        Get current branch name.
        
        Returns:
            Current branch name
        """
        result = self._run_git("rev-parse", "--abbrev-ref", "HEAD")
        return result.stdout.strip()
    
    def has_uncommitted_changes(self) -> bool:
        """
        Check if there are uncommitted changes.
        
        Returns:
            True if there are uncommitted changes
        """
        result = self._run_git("status", "--porcelain")
        return bool(result.stdout.strip())
    
    def get_merge_conflicts(self) -> List[str]:
        """
        Get list of files with merge conflicts.
        
        Returns:
            List of file paths with conflicts
        """
        result = self._run_git("diff", "--name-only", "--diff-filter=U", check=False)
        if result.returncode != 0:
            return []
        
        files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        return files
    
    def has_merge_conflicts(self, base_branch: str = "main") -> bool:
        """
        Check if there would be merge conflicts with base branch.
        
        Args:
            base_branch: Base branch to check against
            
        Returns:
            True if conflicts exist
        """
        # Save current branch
        current_branch = self.get_current_branch()
        
        # Try a test merge
        try:
            # Create a temporary branch for testing
            test_branch = f"test-merge-{current_branch}"
            self._run_git("checkout", "-b", test_branch)
            
            # Try to merge
            result = self._run_git("merge", "--no-commit", "--no-ff", base_branch, check=False)
            has_conflicts = result.returncode != 0
            
            # Abort the merge
            self._run_git("merge", "--abort", check=False)
            
            return has_conflicts
        finally:
            # Return to original branch and cleanup
            self._run_git("checkout", current_branch, check=False)
            self._run_git("branch", "-D", test_branch, check=False)
    
    def merge(self, branch: str, no_ff: bool = True, message: Optional[str] = None) -> bool:
        """
        Merge a branch.
        
        Args:
            branch: Branch to merge
            no_ff: Use --no-ff flag (preserve commit history)
            message: Merge commit message
            
        Returns:
            True if merge successful, False if conflicts
        """
        args = ["merge"]
        
        if no_ff:
            args.append("--no-ff")
        
        if message:
            args.extend(["-m", message])
        
        args.append(branch)
        
        result = self._run_git(*args, check=False)
        return result.returncode == 0
    
    def abort_merge(self):
        """Abort an in-progress merge."""
        self._run_git("merge", "--abort", check=False)
    
    def commit(self, message: str, allow_empty: bool = False):
        """
        Create a commit.
        
        Args:
            message: Commit message
            allow_empty: Allow empty commits
        """
        args = ["commit", "-m", message]
        if allow_empty:
            args.append("--allow-empty")
        
        self._run_git(*args)
    
    def add_all(self):
        """Add all changes to staging."""
        self._run_git("add", ".")
    
    def add_files(self, *files: str):
        """
        Add specific files to staging.
        
        Args:
            *files: File paths to add
        """
        self._run_git("add", *files)
    
    def push(self, branch: Optional[str] = None, force: bool = False):
        """
        Push commits to remote.
        
        Args:
            branch: Branch to push (current branch if None)
            force: Force push
        """
        args = ["push", "origin"]
        
        if branch:
            args.append(branch)
        else:
            args.append("HEAD")
        
        if force:
            args.append("--force")
        
        self._run_git(*args)
    
    def reset_hard(self, ref: str = "HEAD"):
        """
        Hard reset to a reference.
        
        Args:
            ref: Git reference to reset to
        """
        self._run_git("reset", "--hard", ref)
    
    def clean(self, force: bool = True, directories: bool = True):
        """
        Clean untracked files.
        
        Args:
            force: Force clean
            directories: Remove untracked directories
        """
        args = ["clean"]
        
        if force:
            args.append("-f")
        if directories:
            args.append("-d")
        
        self._run_git(*args)
    
    def get_diff(self, ref1: Optional[str] = None, ref2: Optional[str] = None) -> str:
        """
        Get diff between references.
        
        Args:
            ref1: First reference (None for working tree)
            ref2: Second reference (None for HEAD)
            
        Returns:
            Diff output
        """
        args = ["diff"]
        
        if ref1:
            args.append(ref1)
        if ref2:
            args.append(ref2)
        
        result = self._run_git(*args)
        return result.stdout
    
    def get_changed_files(self, ref: str = "HEAD") -> List[str]:
        """
        Get list of changed files.
        
        Args:
            ref: Reference to compare against
            
        Returns:
            List of changed file paths
        """
        result = self._run_git("diff", "--name-only", ref)
        files = [f.strip() for f in result.stdout.split("\n") if f.strip()]
        return files
    
    def get_file_at_ref(self, file_path: str, ref: str) -> str:
        """
        Get file content at a specific reference.
        
        Args:
            file_path: File path
            ref: Git reference
            
        Returns:
            File content
        """
        result = self._run_git("show", f"{ref}:{file_path}")
        return result.stdout
    
    def create_branch(self, branch_name: str, start_point: Optional[str] = None):
        """
        Create a new branch.
        
        Args:
            branch_name: Name of the new branch
            start_point: Starting point (commit, branch, tag)
        """
        args = ["branch", branch_name]
        if start_point:
            args.append(start_point)
        
        self._run_git(*args)
    
    def delete_branch(self, branch_name: str, force: bool = False):
        """
        Delete a branch.
        
        Args:
            branch_name: Branch to delete
            force: Force deletion
        """
        flag = "-D" if force else "-d"
        self._run_git("branch", flag, branch_name)
    
    def resolve_conflict_with_ours(self, file_path: str):
        """
        Resolve conflict by taking 'ours' version.
        
        Args:
            file_path: File with conflict
        """
        self._run_git("checkout", "--ours", file_path)
        self._run_git("add", file_path)
    
    def resolve_conflict_with_theirs(self, file_path: str):
        """
        Resolve conflict by taking 'theirs' version.
        
        Args:
            file_path: File with conflict
        """
        self._run_git("checkout", "--theirs", file_path)
        self._run_git("add", file_path)
