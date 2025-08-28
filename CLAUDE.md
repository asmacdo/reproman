# ReproMan Development Setup

## Environment Setup
```bash
# Activate the development environment
pyenv activate reproman-dev

# Install with all dependencies (including development tools)
pip install -e .[full]
```

## Key Commands
```bash
# Testing
pytest                    # Run all tests
pytest -s                # Run tests with output
flake8 reproman/         # Code linting (120 char line limit)

# Main CLI
reproman --help          # Show available commands
reproman create --help   # Help for specific commands

# Development
python setup.py develop           # Development installation
python setup.py build_manpage     # Build manual pages
```

## Project Status
- **Current State**: Semi-dead project needing resurrection
- **Main Issues**: Tests broken, documentation outdated, compatibility issues
- **Testing**: Uses pytest framework

## Architecture Overview
- `reproman/cmdline/` - Command line interface
- `reproman/interface/` - High-level interface functions  
- `reproman/resource/` - Resource management (cloud resources)
- `reproman/support/` - Support modules and utilities
- `reproman/tests/` - Test suites

## Development Workflow
1. Make changes in relevant module
2. Run `pytest` to test (once tests are fixed)
3. Run `flake8 reproman/` for code quality
4. Test CLI commands work: `reproman --help`

## Notes
- tox.ini shows old Python versions (2.7, 3.4) - needs updating
- Installation scheme: `pip install -e .[full]` gets all dependencies
- Uses custom setuptools build commands for docs
- Max line length: 120 characters
- Follow conventional commits, keep very concise
- prefer to keep a commit just the top line only