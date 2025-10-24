# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Ansible Runner is a tool and Python library that provides a stable interface abstraction to Ansible. It can operate as a standalone CLI tool, a container image interface, or as an importable Python module. The project supports Python 3.10+ and uses Ansible core as its execution engine.

## Development Commands

### Setup
```bash
# Create virtual environment and install in development mode
pip install -e .

# Install tox for running linters and tests
pip install tox
```

### Running Tests
```bash
# Run all tests (linters, unit, integration)
tox

# Run only linters (flake8, yamllint, mypy, pylint)
tox -e linters

# Run only unit tests
tox -e unit

# Run only integration tests
tox -e integration

# Run unit tests with coverage
pytest test/unit -vv -n auto --cov --cov-report html --cov-report term --cov-report xml

# Run integration tests with coverage
pytest test/integration -vv -n auto --cov --cov-report html --cov-report term --cov-report xml

# Run a single test file
pytest test/unit/test_runner.py -vv

# Run a specific test
pytest test/integration/test_transmit_worker_process.py::test_error_on_empty_line_processor -xvs
```

### Linting
```bash
# All linters
tox -e linters

# Individual linters
flake8 docs src/ansible_runner test
yamllint -s .
mypy src/ansible_runner
pylint src/ansible_runner test
```

### Documentation
```bash
# Build docs
tox -e docs

# Clean build artifacts
tox -e clean
```

## Architecture

### Core Components

**1. Configuration Layer** (`src/ansible_runner/config/`)
- `BaseConfig` - Abstract base class for all configurations
- `RunnerConfig` - Configuration for playbook/role execution
- `CommandConfig` - Configuration for ad-hoc commands
- `InventoryConfig` - Configuration for inventory operations
- `DocConfig` - Configuration for documentation retrieval
- `AnsibleCfgConfig` - Configuration for ansible.cfg generation

**2. Execution Layer**
- `Runner` (`runner.py`) - Core execution engine that runs Ansible via pexpect or subprocess
- `interface.py` - Public API functions: `run()`, `run_async()`, `run_command()`, etc.
- Runner modes: `pexpect` (default, interactive) or `subprocess` (non-interactive)

**3. Streaming/Remote Execution** (`streaming.py`)
The streaming module enables distributed execution across networked nodes using a three-component architecture:

- **Transmitter** - Serializes job data and private data directory, sends to Worker
- **Worker** - Receives job data, executes Ansible, streams events back
- **Processor** - Receives and processes event stream, writes artifacts

Flow: `Transmitter → (network/socket) → Worker → (network/socket) → Processor`

This is used by AWX/Controller for executing jobs on remote execution nodes via receptor.

**4. Plugin System**
- Entry point based: `ansible_runner.plugins`
- Plugins can hook into status and event callbacks
- Loaded via importlib_metadata

### Key Concepts

**Private Data Directory Structure:**
```
private_data_dir/
├── artifacts/          # Output artifacts (created by runner)
│   └── <ident>/
│       ├── job_events/ # JSON event files
│       ├── stdout      # Combined stdout
│       └── rc          # Return code
├── env/                # Environment settings
│   ├── settings        # YAML/JSON config
│   └── envvars         # Environment variables
├── inventory/          # Ansible inventory
├── project/            # Playbooks and roles
└── ...
```

**Runner Isolation:**
- **Process Isolation**: Run Ansible in containers (podman/docker)
- **Directory Isolation**: Copy artifacts to isolated directory

**Event Handling:**
The runner uses a custom `awx_display` callback plugin to capture Ansible events as structured JSON, which are then processed by:
- `event_handler` - Called for each Ansible event
- `status_handler` - Called for status changes (starting, running, successful, failed)
- `finished_callback` - Called when execution completes
- `artifacts_handler` - Called when artifacts are ready

### Important Implementation Details

**Streaming Error Handling:**
When working with `Processor.run()` in streaming.py:
- Empty line from `readline()` indicates EOF (connection closed/aborted)
- Must check `len(line) == 0` BEFORE attempting JSON parsing
- Distinguish between: EOF errors, OS read errors, and JSON parsing errors
- Each error type should have a specific, actionable error message

**Test Organization:**
- `test/unit/` - Unit tests (fast, mocked)
- `test/integration/` - Integration tests (slower, use real Ansible)
- `test/fixtures/projects/` - Sample playbooks/projects for testing
- Use `project_fixtures` pytest fixture to access test projects

**Pylint Configuration:**
Many complexity-related pylint checks are disabled (see pyproject.toml). Focus on correctness over strict adherence to complexity metrics.

## Pull Request Guidelines

- Target the `devel` branch (not `main`)
- Use `git rebase` instead of `git merge` to avoid merge commits
- Ensure all linters pass before submitting
- Add tests for new functionality
- Integration tests may fail locally if ansible-playbook is not in PATH - this is acceptable if unit tests pass

## Testing Notes

- Tests use pytest with xdist for parallel execution (`-n auto`)
- Integration tests require Ansible to be installed and accessible
- Some tests are parameterized for multiple runtimes (docker/podman) using `@pytest.mark.test_all_runtimes`
- The `project_fixtures` fixture copies test projects to tmp_path for isolation