import ast
import sys
from pathlib import Path


def _builtins() -> set[str]:
    builtins_obj = __builtins__
    if isinstance(builtins_obj, dict):
        builtins_set = set(builtins_obj.keys())
    else:
        builtins_set = set(dir(builtins_obj))
    return builtins_set | {"__file__"}


class ImportChecker(ast.NodeVisitor):
    def __init__(self) -> None:
        self.imported: set[str] = set()
        self.defined: set[str] = set()
        self.used: set[str] = set()
        self.scope_depth = 0

    def visit_Import(self, node: ast.Import) -> None:
        if self.scope_depth == 0:
            for name in node.names:
                self.imported.add((name.asname or name.name).split(".")[0])

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        if self.scope_depth == 0:
            if node.module:
                self.imported.add(node.module.split(".")[0])
            for name in node.names:
                self.imported.add((name.asname or name.name).split(".")[0])

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        if self.scope_depth == 0:
            self.defined.add(node.name)
        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        if self.scope_depth == 0:
            self.defined.add(node.name)
        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        if self.scope_depth == 0:
            self.defined.add(node.name)
        self.scope_depth += 1
        self.generic_visit(node)
        self.scope_depth -= 1

    def visit_Name(self, node: ast.Name) -> None:
        if self.scope_depth == 0:
            if isinstance(node.ctx, ast.Store):
                self.defined.add(node.id)
            elif isinstance(node.ctx, ast.Load):
                self.used.add(node.id)


def check_file(filepath: Path) -> set[str]:
    tree = ast.parse(filepath.read_text(), str(filepath))
    checker = ImportChecker()
    checker.visit(tree)
    missing = checker.used - checker.imported - checker.defined - _builtins()
    return missing


def main() -> int:
    src_root = Path("src/meta_mcp")
    issues: dict[Path, set[str]] = {}
    syntax_errors: dict[Path, SyntaxError] = {}

    for file in src_root.rglob("*.py"):
        try:
            missing = check_file(file)
        except SyntaxError as exc:
            syntax_errors[file] = exc
            continue
        if missing:
            issues[file] = missing

    if syntax_errors:
        print("Skipped files with syntax errors:")
        for file, exc in sorted(syntax_errors.items()):
            print(f"  {file}: {exc.msg} (line {exc.lineno})")

    if issues:
        print("Missing imports found:")
        for file, missing in sorted(issues.items()):
            missing_list = ", ".join(sorted(missing))
            print(f"  {file}: {missing_list}")
        return 1

    print("No missing imports found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
