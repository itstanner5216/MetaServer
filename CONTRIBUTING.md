# Contributing to MetaServer

## Development Setup

1. Clone the repository
2. Install dependencies: `uv sync` (or `pip install -e ".[dev]"`)
3. Run tests: `pytest`
4. Run linting: `ruff check src/ tests/`

## Pull Request Process

1. Create a feature branch from `main`
2. Write tests for new functionality
3. Ensure CI passes (all Python versions, coverage ≥ 85%)
4. Submit a PR with a clear description of changes

## Code Style

- Type hints on all public functions
- Docstrings on all public classes and functions
- Follow existing patterns in the codebase (see any module for examples)

## Testing

- Tests live in `tests/` mirroring the `src/` structure
- Use `pytest` with `pytest-asyncio` for async tests
- Mock Redis with `FakeRedis` class pattern (see `tests/test_governance_session_key.py`)

## Security

See [SECURITY.md](SECURITY.md) for vulnerability reporting.
