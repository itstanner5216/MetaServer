"""Tests for AST analyzer utility."""

import pytest
from pathlib import Path
import tempfile
from scripts.agents.utils.ast_analyzer import ASTAnalyzer, FunctionSignature


@pytest.fixture
def temp_python_file():
    """Create a temporary Python file for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir)
        
        # Create a test Python file
        test_file = repo_path / "test_module.py"
        test_file.write_text("""
import os
from typing import List

def hello_world():
    \"\"\"A simple function.\"\"\"
    return "Hello, World!"

def add_numbers(a: int, b: int = 0) -> int:
    \"\"\"Add two numbers.\"\"\"
    return a + b

class TestClass:
    \"\"\"A test class.\"\"\"
    
    def method_one(self, x):
        return x * 2
    
    def _private_method(self):
        pass
""")
        
        yield repo_path, "test_module.py"


def test_ast_analyzer_init(temp_python_file):
    """Test ASTAnalyzer initialization."""
    repo_path, _ = temp_python_file
    analyzer = ASTAnalyzer(repo_path=str(repo_path))
    assert analyzer.repo_path == repo_path


def test_analyze_file_functions(temp_python_file):
    """Test analyzing function definitions."""
    repo_path, file_path = temp_python_file
    analyzer = ASTAnalyzer(repo_path=str(repo_path))
    
    analysis = analyzer.analyze_file(file_path)
    
    # Should find 2 functions
    assert len(analysis.functions) >= 2
    
    # Check function names
    func_names = [f.name for f in analysis.functions]
    assert "hello_world" in func_names
    assert "add_numbers" in func_names


def test_analyze_file_classes(temp_python_file):
    """Test analyzing class definitions."""
    repo_path, file_path = temp_python_file
    analyzer = ASTAnalyzer(repo_path=str(repo_path))
    
    analysis = analyzer.analyze_file(file_path)
    
    # Should find 1 class
    assert len(analysis.classes) >= 1
    
    # Check class name
    class_names = [c.name for c in analysis.classes]
    assert "TestClass" in class_names


def test_analyze_file_imports(temp_python_file):
    """Test analyzing import statements."""
    repo_path, file_path = temp_python_file
    analyzer = ASTAnalyzer(repo_path=str(repo_path))
    
    analysis = analyzer.analyze_file(file_path)
    
    # Should find imports
    assert len(analysis.imports) >= 2
    
    # Check import modules
    import_modules = [i.module for i in analysis.imports]
    assert "os" in import_modules
    assert "typing" in import_modules


def test_find_api_functions(temp_python_file):
    """Test finding public API functions."""
    repo_path, file_path = temp_python_file
    analyzer = ASTAnalyzer(repo_path=str(repo_path))
    
    analysis = analyzer.analyze_file(file_path)
    api_functions = analyzer.find_api_functions(analysis)
    
    # Should not include private methods
    func_names = [f.name for f in api_functions]
    assert "hello_world" in func_names
    assert "add_numbers" in func_names
    assert "_private_method" not in func_names


def test_compare_signatures():
    """Test comparing function signatures."""
    analyzer = ASTAnalyzer()
    
    # Create two function signatures
    old_sig = FunctionSignature(
        name="test_func",
        args=["a", "b"],
        defaults=[],
        return_type="int",
        decorators=[],
        lineno=1,
        file_path="test.py",
    )
    
    new_sig = FunctionSignature(
        name="test_func",
        args=["a", "b", "c"],  # Added parameter
        defaults=[],
        return_type="int",
        decorators=[],
        lineno=1,
        file_path="test.py",
    )
    
    # Compare signatures
    comparison = analyzer.compare_signatures(old_sig, new_sig)
    
    # Should detect breaking change
    assert comparison["is_breaking"] is True
    assert len(comparison["changes"]) > 0
