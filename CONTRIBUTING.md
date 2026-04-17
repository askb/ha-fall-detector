<!-- SPDX-License-Identifier: Apache-2.0 -->
<!-- SPDX-FileCopyrightText: 2025 The Linux Foundation -->

# Contributing to HA Fall Detector

Thank you for your interest in contributing! This document explains how to set
up a development environment, run tests, and submit changes.

---

## Table of Contents

- [Development Setup](#development-setup)
- [Project Structure](#project-structure)
- [Running Tests](#running-tests)
- [Running Linters](#running-linters)
- [Pre-commit Hooks](#pre-commit-hooks)
- [Commit Message Format](#commit-message-format)
- [Pull Request Process](#pull-request-process)
- [Code Style](#code-style)
- [Development Tips](#development-tips)
- [Using AI Assistants for Maintenance](#using-ai-assistants-for-maintenance)
- [Getting Help](#getting-help)

---

## Development Setup

### Prerequisites

- Python 3.12 or newer
- Docker and Docker Compose (for add-on testing)
- Git
- A running Home Assistant instance (for integration testing)

### Clone and Setup

```bash
# Clone the repository
git clone https://github.com/askb/ha-fall-detector.git
cd ha-fall-detector

# Create a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install all development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install

# Verify the setup
pytest --co  # List all discovered tests (no execution)
pre-commit run --all-files  # Run all linters
```

### Development Dependencies

The `[dev]` extra installs:

| Package | Purpose |
|---|---|
| `pytest` | Test runner |
| `pytest-cov` | Coverage reporting |
| `pytest-asyncio` | Async test support |
| `pytest-homeassistant-custom-component` | HA integration test framework |
| `ruff` | Linting and formatting |
| `mypy` | Static type checking |
| `yamllint` | YAML linting |
| `pre-commit` | Git hook management |

---

## Project Structure

```
ha-fall-detector/
├── addon/
│   └── fall_detector/
│       ├── Dockerfile              # Add-on container definition
│       ├── config.yaml             # Add-on metadata for HA
│       ├── requirements.txt        # Python dependencies
│       ├── fall_detector/          # Main Python package
│       │   ├── __init__.py
│       │   ├── main.py             # FastAPI application entry point
│       │   ├── pipeline.py         # Detection pipeline orchestration
│       │   ├── person_gate.py      # Event filtering
│       │   ├── pose.py             # MoveNet pose estimation
│       │   ├── scoring.py          # Fall scoring algorithm
│       │   ├── confirmation.py     # Confirmation state machine
│       │   ├── alerts.py           # Alert manager
│       │   ├── mqtt_client.py      # MQTT connection handling
│       │   ├── api.py              # FastAPI route definitions
│       │   └── config.py           # Configuration loading
│       ├── tests/                  # Add-on tests
│       │   ├── conftest.py
│       │   ├── test_pipeline.py
│       │   ├── test_scoring.py
│       │   ├── test_confirmation.py
│       │   ├── test_alerts.py
│       │   ├── test_api.py
│       │   ├── integration/        # Integration tests (Docker)
│       │   ├── fixtures/           # Test images, mock data
│       │   └── utils/              # Test utilities
│       └── docker-compose.test.yaml
│
├── custom_components/
│   └── fall_detector/
│       ├── __init__.py             # Integration setup
│       ├── manifest.json           # HA integration manifest
│       ├── config_flow.py          # Setup wizard
│       ├── coordinator.py          # Data update coordinator
│       ├── const.py                # Constants
│       ├── binary_sensor.py        # Binary sensor entities
│       ├── sensor.py               # Sensor entities
│       ├── switch.py               # Switch entities
│       ├── services.py             # Service definitions
│       ├── services.yaml           # Service descriptions
│       ├── strings.json            # UI strings
│       ├── translations/           # Localization
│       │   └── en.json
│       ├── diagnostics.py          # Diagnostics data
│       └── tests/                  # Integration tests
│           ├── conftest.py
│           ├── test_config_flow.py
│           ├── test_coordinator.py
│           ├── test_binary_sensor.py
│           ├── test_sensor.py
│           ├── test_switch.py
│           ├── test_services.py
│           └── test_events.py
│
├── docs/                           # Documentation
│   ├── architecture.md
│   ├── setup.md
│   ├── tuning.md
│   ├── threat-model.md
│   ├── troubleshooting.md
│   └── testing.md
│
├── .github/
│   └── workflows/                  # CI/CD
│       ├── ci.yaml                 # Main CI pipeline
│       └── release.yaml            # Release automation
│
├── .pre-commit-config.yaml         # Pre-commit hook configuration
├── pyproject.toml                  # Python project configuration
├── README.md
├── CONTRIBUTING.md                 # This file
├── LICENSE                         # Apache-2.0
└── LICENSES/
    └── Apache-2.0.txt
```

---

## Running Tests

### Full Suite

```bash
pytest
```

### With Coverage

```bash
pytest --cov=addon/fall_detector --cov=custom_components/fall_detector --cov-report=term-missing
```

### Add-on Tests

```bash
pytest addon/fall_detector/tests/ -v
```

### Integration Tests

```bash
pytest custom_components/fall_detector/tests/ -v
```

### Specific Test

```bash
pytest addon/fall_detector/tests/test_scoring.py::test_horizontal_body_high_score -v
```

### Docker Integration Tests

```bash
cd addon/fall_detector
docker compose -f docker-compose.test.yaml up --build --abort-on-container-exit
```

---

## Running Linters

### All Linters (via Pre-commit)

```bash
pre-commit run --all-files
```

### Individual Linters

```bash
# Python linting
ruff check .

# Python formatting check
ruff format --check .

# Python formatting (apply fixes)
ruff format .

# Type checking
mypy addon/fall_detector/ custom_components/fall_detector/

# YAML linting
yamllint .
```

---

## Pre-commit Hooks

Pre-commit hooks run automatically on every `git commit`. They are configured
in `.pre-commit-config.yaml`.

### Installed Hooks

| Hook | Purpose |
|---|---|
| `ruff` (lint) | Python linting (replaces flake8, isort, pycodestyle) |
| `ruff-format` | Python formatting (replaces black) |
| `mypy` | Static type checking |
| `yamllint` | YAML file validation |
| `check-yaml` | YAML syntax check |
| `check-json` | JSON syntax check |
| `end-of-file-fixer` | Ensure files end with newline |
| `trailing-whitespace` | Remove trailing whitespace |
| `check-merge-conflict` | Detect merge conflict markers |
| `check-added-large-files` | Prevent large binary files |

### Usage

```bash
# Install hooks (one-time setup)
pre-commit install

# Run on all files
pre-commit run --all-files

# Run a specific hook
pre-commit run ruff --all-files

# Update hooks to latest versions
pre-commit autoupdate

# Skip hooks in an emergency (NOT recommended)
# git commit --no-verify -m "emergency fix"
```

> **Important:** Do not use `--no-verify` to bypass hooks. If a hook fails,
> fix the issue.

---

## Commit Message Format

We use [Conventional Commits](https://www.conventionalcommits.org/).

### Format

```
<type>(<scope>): <subject>

<body>

<footer>

Signed-off-by: Your Name <your@email.com>
```

### Types

| Type | Description |
|---|---|
| `feat` | New feature |
| `fix` | Bug fix |
| `docs` | Documentation changes |
| `test` | Adding or updating tests |
| `refactor` | Code change that neither fixes a bug nor adds a feature |
| `perf` | Performance improvement |
| `chore` | Build process, CI, dependency updates |
| `ci` | CI/CD changes |
| `style` | Formatting, missing semicolons (no logic change) |

### Scopes

| Scope | Component |
|---|---|
| `addon` | Add-on changes |
| `integration` | HACS integration changes |
| `pipeline` | Detection pipeline changes |
| `scoring` | Fall scoring algorithm |
| `api` | Add-on HTTP API |
| `mqtt` | MQTT communication |
| `docs` | Documentation |
| `ci` | CI/CD workflows |

### Examples

```bash
# Feature
git commit -s -m "feat(addon): add zone exclusion support for camera zones"

# Bug fix
git commit -s -m "fix(integration): handle MQTT disconnect during coordinator update"

# Documentation
git commit -s -m "docs: add camera placement guide to tuning documentation"

# Test
git commit -s -m "test(scoring): add test cases for edge case body angles"

# Refactor
git commit -s -m "refactor(pipeline): extract frame preprocessing into separate module"
```

### Sign-off Requirement

All commits must include a `Signed-off-by` line (DCO compliance). Use the
`-s` flag:

```bash
git commit -s -m "feat: add new feature"
```

---

## Pull Request Process

### Before Submitting

1. ✅ Create a feature branch from `main`:
   ```bash
   git checkout -b feat/your-feature-name
   ```
2. ✅ Make your changes with clear, focused commits.
3. ✅ Run the full test suite: `pytest`
4. ✅ Run all linters: `pre-commit run --all-files`
5. ✅ Update documentation if your change affects user-facing behavior.
6. ✅ Add tests for new functionality.

### Submitting

1. Push your branch:
   ```bash
   git push origin feat/your-feature-name
   ```
2. Open a pull request against `main`.
3. Fill in the PR template with:
   - **What** — description of the change.
   - **Why** — motivation and context.
   - **How** — approach taken.
   - **Testing** — how you tested the change.
4. Link any related issues.

### Review Process

- A maintainer will review your PR.
- CI must pass (tests + linters).
- At least one approving review is required.
- Address review feedback with additional commits (don't force-push during
  review).
- Once approved, the PR will be squash-merged.

### After Merge

- Delete your feature branch.
- The change will be included in the next release.

---

## Code Style

### Python

- **Version**: Python 3.12+ features are allowed.
- **Formatter**: ruff format (line length 88).
- **Linter**: ruff (comprehensive rule set).
- **Type hints**: Required for all function signatures.
- **Docstrings**: Required for all public functions and classes. Use Google
  style.
- **Imports**: Sorted by ruff (isort-compatible).

```python
# Good example
from typing import Any

from fall_detector.config import Settings


async def process_frame(
    frame: bytes,
    camera: str,
    settings: Settings,
) -> dict[str, Any]:
    """Process a single frame through the detection pipeline.

    Args:
        frame: Raw JPEG frame bytes.
        camera: Camera name.
        settings: Application settings.

    Returns:
        Detection result with score and keypoints.

    Raises:
        InferenceError: If pose estimation fails.
    """
    ...
```

### YAML

- **Indentation**: 2 spaces.
- **Quotes**: Use quotes for strings that could be misinterpreted (e.g.,
  `"true"`, `"1883"`).
- **Validated by**: yamllint with the project's `.yamllint` config.

### Markdown

- **Line length**: 79 characters (soft wrap for readability in terminals).
- **Headings**: ATX style (`#`, `##`, `###`).
- **Lists**: Use `-` for unordered lists.
- **Code blocks**: Always specify the language (` ```python `, ` ```yaml `,
  ` ```bash `).

---

## Development Tips

### Hot-Reload the Add-on

During development, you can mount your local source into the Docker container
for rapid iteration:

```bash
cd addon/fall_detector
docker run -d \
  --name fall-detector-dev \
  -p 5000:5000 \
  -v "$(pwd)/fall_detector:/app/fall_detector" \
  -e LOG_LEVEL=debug \
  -e FRIGATE_URL=http://host.docker.internal:5000 \
  -e MQTT_HOST=host.docker.internal \
  fall-detector-test
```

Changes to Python files are reflected after restarting the container (or
use `--reload` if uvicorn supports your mount configuration).

### Testing the Integration in HA

For integration development, you can symlink the custom component into a HA
dev instance:

```bash
ln -s /path/to/ha-fall-detector/custom_components/fall_detector \
      /path/to/ha-config/custom_components/fall_detector
```

Then restart HA to load the latest code.

### Debugging the Scoring Algorithm

The scoring module has a standalone debug mode:

```bash
python -m fall_detector.scoring --image test_image.jpg --debug
```

This outputs the per-feature scores and final confidence without needing the
full pipeline.

### MQTT Debugging

Use [MQTT Explorer](https://mqtt-explorer.com/) to visualize MQTT traffic in
real-time. Connect to your broker and subscribe to `fall_detector/#` and
`frigate/#`.

---

## Using AI Assistants for Maintenance

AI coding assistants (GitHub Copilot, Claude, etc.) can help with routine
maintenance tasks. Here are safe patterns:

### Safe: Refactoring with Tests

```
Prompt: "Refactor the scoring module to extract the torso angle calculation
into a separate function. Ensure all existing tests still pass."
```

This is safe because existing tests validate the behavior is preserved.

### Safe: Adding Tests

```
Prompt: "Add test cases for the confirmation state machine covering the
transition from CONFIRMING back to IDLE when the score drops below threshold."
```

Adding tests is always safe — it increases coverage without changing behavior.

### Safe: Documentation Updates

```
Prompt: "Update the README entity reference table to include the new
pipeline_latency sensor that was added in the last commit."
```

### Caution: Changing Detection Logic

```
Prompt: "Modify the fall scoring algorithm to add a new feature based on
the rate of change of the torso angle."
```

Changes to detection logic require careful testing:
1. Run the full test suite.
2. Test with debug frames on a real system.
3. Compare before/after scores on known scenarios.
4. Have a human review the changes.

### Never: Security-Sensitive Changes

Do not use AI assistants for:
- Modifying authentication or authorization logic.
- Changing MQTT topic structures (could break existing deployments).
- Modifying configuration parsing (could introduce injection vulnerabilities).

Always have a human review security-sensitive changes.

---

## Getting Help

- **Questions**: Open a [Discussion](https://github.com/askb/ha-fall-detector/discussions).
- **Bugs**: Open an [Issue](https://github.com/askb/ha-fall-detector/issues).
- **Security**: Email askb23@gmail.com (do not open a public issue for
  security vulnerabilities).
- **Chat**: Join the Home Assistant community forums.

---

## License

By contributing, you agree that your contributions will be licensed under the
Apache License 2.0. See [LICENSE](LICENSE) for the full text.
