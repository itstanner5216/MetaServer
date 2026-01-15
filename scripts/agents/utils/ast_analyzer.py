#!/usr/bin/env python3
"""AST analysis utilities for architectural verification."""

import ast
from pathlib import Path
from typing import Dict, List, Set, Any, Optional
from dataclasses import dataclass, field


@dataclass
class FunctionSignature:
    """Represents a function signature."""
    
    name: str
    args: List[str]
    defaults: List[Any]
    return_type: Optional[str]
    decorators: List[str]
    lineno: int
    file_path: str
    
    def __hash__(self):
        return hash((self.name, tuple(self.args), self.file_path))


@dataclass
class ClassInfo:
    """Represents a class definition."""
    
    name: str
    bases: List[str]
    methods: List[FunctionSignature]
    decorators: List[str]
    lineno: int
    file_path: str


@dataclass
class ImportInfo:
    """Represents an import statement."""
    
    module: str
    names: List[str]
    alias: Optional[str]
    level: int  # For relative imports
    lineno: int
    file_path: str


@dataclass
class CodeAnalysis:
    """Complete code analysis results."""
    
    functions: List[FunctionSignature] = field(default_factory=list)
    classes: List[ClassInfo] = field(default_factory=list)
    imports: List[ImportInfo] = field(default_factory=list)
    global_vars: List[str] = field(default_factory=list)


class ASTAnalyzer:
    """Python AST analysis for architectural verification."""
    
    def __init__(self, repo_path: str = "."):
        """
        Initialize AST analyzer.
        
        Args:
            repo_path: Path to repository
        """
        self.repo_path = Path(repo_path).resolve()
    
    def analyze_file(self, file_path: str) -> CodeAnalysis:
        """
        Analyze a Python file.
        
        Args:
            file_path: Path to Python file (relative to repo)
            
        Returns:
            CodeAnalysis object
        """
        full_path = self.repo_path / file_path
        
        if not full_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        with open(full_path) as f:
            source = f.read()
        
        try:
            tree = ast.parse(source, filename=str(file_path))
        except SyntaxError as e:
            raise ValueError(f"Syntax error in {file_path}: {e}")
        
        analysis = CodeAnalysis()
        
        # Analyze the AST
        self._analyze_node(tree, analysis, file_path)
        
        return analysis
    
    def _analyze_node(self, node: ast.AST, analysis: CodeAnalysis, file_path: str):
        """
        Recursively analyze AST node.
        
        Args:
            node: AST node
            analysis: CodeAnalysis to populate
            file_path: Current file path
        """
        for child in ast.walk(node):
            # Function definitions
            if isinstance(child, ast.FunctionDef):
                sig = self._extract_function_signature(child, file_path)
                analysis.functions.append(sig)
            
            # Class definitions
            elif isinstance(child, ast.ClassDef):
                class_info = self._extract_class_info(child, file_path)
                analysis.classes.append(class_info)
            
            # Import statements
            elif isinstance(child, ast.Import):
                for alias in child.names:
                    import_info = ImportInfo(
                        module=alias.name,
                        names=[alias.name],
                        alias=alias.asname,
                        level=0,
                        lineno=child.lineno,
                        file_path=file_path,
                    )
                    analysis.imports.append(import_info)
            
            # Import from statements
            elif isinstance(child, ast.ImportFrom):
                names = [alias.name for alias in child.names]
                import_info = ImportInfo(
                    module=child.module or "",
                    names=names,
                    alias=None,
                    level=child.level,
                    lineno=child.lineno,
                    file_path=file_path,
                )
                analysis.imports.append(import_info)
    
    def _extract_function_signature(self, node: ast.FunctionDef, file_path: str) -> FunctionSignature:
        """
        Extract function signature from AST node.
        
        Args:
            node: FunctionDef node
            file_path: Current file path
            
        Returns:
            FunctionSignature object
        """
        # Extract arguments
        args = []
        for arg in node.args.args:
            args.append(arg.arg)
        
        # Extract defaults
        defaults = []
        for default in node.args.defaults:
            if isinstance(default, ast.Constant):
                defaults.append(default.value)
            else:
                defaults.append(ast.unparse(default))
        
        # Extract return type
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)
        
        # Extract decorators
        decorators = []
        for decorator in node.decorator_list:
            decorators.append(ast.unparse(decorator))
        
        return FunctionSignature(
            name=node.name,
            args=args,
            defaults=defaults,
            return_type=return_type,
            decorators=decorators,
            lineno=node.lineno,
            file_path=file_path,
        )
    
    def _extract_class_info(self, node: ast.ClassDef, file_path: str) -> ClassInfo:
        """
        Extract class information from AST node.
        
        Args:
            node: ClassDef node
            file_path: Current file path
            
        Returns:
            ClassInfo object
        """
        # Extract base classes
        bases = []
        for base in node.bases:
            bases.append(ast.unparse(base))
        
        # Extract methods
        methods = []
        for item in node.body:
            if isinstance(item, ast.FunctionDef):
                sig = self._extract_function_signature(item, file_path)
                methods.append(sig)
        
        # Extract decorators
        decorators = []
        for decorator in node.decorator_list:
            decorators.append(ast.unparse(decorator))
        
        return ClassInfo(
            name=node.name,
            bases=bases,
            methods=methods,
            decorators=decorators,
            lineno=node.lineno,
            file_path=file_path,
        )
    
    def compare_signatures(
        self,
        old_sig: FunctionSignature,
        new_sig: FunctionSignature,
    ) -> Dict[str, Any]:
        """
        Compare two function signatures for breaking changes.
        
        Args:
            old_sig: Original signature
            new_sig: New signature
            
        Returns:
            Dictionary with comparison results
        """
        changes = {
            "is_breaking": False,
            "changes": [],
        }
        
        # Check if function was removed
        if old_sig and not new_sig:
            changes["is_breaking"] = True
            changes["changes"].append("Function removed")
            return changes
        
        # Check argument changes
        if old_sig.args != new_sig.args:
            changes["is_breaking"] = True
            changes["changes"].append(f"Arguments changed: {old_sig.args} -> {new_sig.args}")
        
        # Check return type changes
        if old_sig.return_type != new_sig.return_type:
            changes["changes"].append(
                f"Return type changed: {old_sig.return_type} -> {new_sig.return_type}"
            )
        
        # Check decorator changes (might affect behavior)
        if set(old_sig.decorators) != set(new_sig.decorators):
            changes["changes"].append(
                f"Decorators changed: {old_sig.decorators} -> {new_sig.decorators}"
            )
        
        return changes
    
    def find_api_functions(self, analysis: CodeAnalysis) -> List[FunctionSignature]:
        """
        Find public API functions (not starting with _).
        
        Args:
            analysis: CodeAnalysis object
            
        Returns:
            List of public functions
        """
        return [f for f in analysis.functions if not f.name.startswith("_")]
    
    def find_tool_functions(self, analysis: CodeAnalysis) -> List[FunctionSignature]:
        """
        Find FastMCP tool functions (decorated with @mcp.tool).
        
        Args:
            analysis: CodeAnalysis object
            
        Returns:
            List of tool functions
        """
        tool_functions = []
        
        for func in analysis.functions:
            # Check for FastMCP decorators
            for decorator in func.decorators:
                if "mcp.tool" in decorator or "@tool" in decorator:
                    tool_functions.append(func)
                    break
        
        return tool_functions
    
    def find_import_errors(self, analysis: CodeAnalysis) -> List[ImportInfo]:
        """
        Find potentially problematic imports.
        
        Args:
            analysis: CodeAnalysis object
            
        Returns:
            List of problematic imports
        """
        problematic = []
        
        for imp in analysis.imports:
            # Check for old import patterns
            if "src.meta_mcp" in imp.module:
                problematic.append(imp)
            
            # Check for relative imports that might break
            if imp.level > 0 and not imp.module:
                problematic.append(imp)
        
        return problematic
    
    def extract_dataflow_patterns(self, file_path: str) -> List[str]:
        """
        Extract data flow patterns from a file.
        
        Args:
            file_path: Path to Python file
            
        Returns:
            List of data flow patterns
        """
        full_path = self.repo_path / file_path
        
        with open(full_path) as f:
            source = f.read()
        
        tree = ast.parse(source, filename=str(file_path))
        
        patterns = []
        
        # Look for function call chains
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Extract call chain
                call_chain = self._extract_call_chain(node)
                if call_chain:
                    patterns.append(" -> ".join(call_chain))
        
        return patterns
    
    def _extract_call_chain(self, node: ast.Call) -> List[str]:
        """
        Extract function call chain from AST node.
        
        Args:
            node: Call node
            
        Returns:
            List of function names in call chain
        """
        chain = []
        
        current = node.func
        while current:
            if isinstance(current, ast.Name):
                chain.insert(0, current.id)
                break
            elif isinstance(current, ast.Attribute):
                chain.insert(0, current.attr)
                current = current.value
            elif isinstance(current, ast.Call):
                current = current.func
            else:
                break
        
        return chain
