"""Verify modules reference only imported globals."""

from __future__ import annotations

import ast
import builtins
import sys
from pathlib import Path
from symtable import SymbolTable, symtable


BASE_DIRS = (Path("src") / "meta_mcp",)


def _builtins() -> set[str]:
    return set(dir(builtins)) | {"__file__"}


def _module_defined(symbols: list) -> set[str]:
    defined: set[str] = set()
    for symbol in symbols:
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_parameter():
            defined.add(symbol.get_name())
    return defined


def _find_missing_globals(table: SymbolTable, module_defined: set[str]) -> set[str]:
    missing: set[str] = set()
    for symbol in table.get_symbols():
        if not symbol.is_referenced():
            continue
        name = symbol.get_name()
        if name in module_defined or name in _builtins():
            continue
        if symbol.is_assigned() or symbol.is_imported() or symbol.is_parameter():
            continue
        if table.get_type() == "module" or symbol.is_global():
            missing.add(name)
    return missing


def _walk_tables(table: SymbolTable) -> list[SymbolTable]:
    pending = [table]
    tables: list[SymbolTable] = []
    while pending:
        current = pending.pop()
        tables.append(current)
        pending.extend(current.get_children())
    return tables


def _annotation_names(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    names: set[str] = set()

    def record(node: ast.AST | None) -> None:
        if node is None:
            return
        for child in ast.walk(node):
            if isinstance(child, ast.Name):
                names.add(child.id)

    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign):
            record(node.annotation)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            record(node.returns)
            for arg in (*node.args.args, *node.args.kwonlyargs):
                record(arg.annotation)
            if node.args.vararg:
                record(node.args.vararg.annotation)
            if node.args.kwarg:
                record(node.args.kwarg.annotation)
    return names


def _check_file(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    annotation_names = _annotation_names(source)
    try:
        table = symtable(source, str(path), "exec")
    except SyntaxError as exc:
        print(f"Skipping {path} due to syntax error: {exc}", file=sys.stderr)
        return set()
    module_defined = _module_defined(table.get_symbols())
    missing: set[str] = set()
    for child in _walk_tables(table):
        missing.update(_find_missing_globals(child, module_defined))
    return missing - annotation_names


def main() -> int:
    failures: dict[Path, set[str]] = {}
    for base_dir in BASE_DIRS:
        for path in sorted(base_dir.rglob("*.py")):
            missing = _check_file(path)
            if missing:
                failures[path] = missing

    if not failures:
        print("No missing imports detected.")
        return 0

    print("Missing imports detected:")
    for path, missing in sorted(failures.items()):
        missing_list = ", ".join(sorted(missing))
        print(f"- {path}: {missing_list}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
