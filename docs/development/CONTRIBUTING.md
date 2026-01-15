# Contributing to MetaServer

## Development Workflow

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/amazing-feature`
3. Install pre-commit hooks: `uv run pre-commit install`
4. Make your changes
5. Run tests: `uv run pytest`
6. Commit changes: `git commit -m 'Add amazing feature'`
7. Push to branch: `git push origin feature/amazing-feature`
8. Open a Pull Request

## Code Quality Standards

- All code must pass Ruff linting
- All code must be formatted with Ruff
- Type hints are required for new code
- Test coverage must be ≥80%
- All tests must pass

## Automated Checks

Pre-commit hooks will run automatically on commit. To run manually:
```bash
uv run pre-commit run --all-files
```

CI will run on all pull requests:
- ✅ Linting (Ruff)
- ✅ Formatting (Ruff)
- ✅ Type checking (Pyright)
- ✅ Tests (pytest)
- ✅ Coverage (Codecov)
- ✅ Security (CodeQL)

## Release Process

Releases are automated via GitHub Actions:

1. Update version in `pyproject.toml`
2. Create and push tag: `git tag -a v1.0.0 -m "Release 1.0.0"`
3. Push tag: `git push origin v1.0.0`
4. GitHub Actions will:
   - Build package
   - Create GitHub release
   - Publish to PyPI
