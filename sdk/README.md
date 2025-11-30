# Amazon Nova Act Human Intervention SDK

Python SDK packages for the Amazon Nova Act Human Intervention Service.

## Package Overview

This directory contains three Python packages:

1. **service/** - Service/handler code (used in AWS Lambda functions)
2. **client/** - Client library for connecting to the service
3. **common/** - Common utilities shared between service and client

## Installation

Install packages in the correct dependency order:

```bash
# From the repository root:
cd sdk

# 1. Install common package (required by both service and client)
pip install ./common

# 2. Install service package (if you need to run handlers locally)
pip install ./service

# 3. Install client package (for connecting to the deployed service)
pip install ./client
```

## Usage

### Complete Usage Examples

For complete, ready-to-run examples with Nova Act integration, see the **[../samples/](../samples/)** folder:
- **[standalone-hitl-run.py](../samples/standalone-hitl-run.py)** - Standalone examples for Approval and UI Takeover patterns
- **[nova-act-integration.py](../samples/nova-act-integration.py)** - Full Nova Act integration with HumanInputCallbacks
- **[samples/README.md](../samples/README.md)** - Detailed documentation and usage instructions

### Using the Client

```python
from amzn_nova_act_human_intervention_client import HumanInterventionClient

# Create client and connect to your deployed service
client = HumanInterventionClient(websocket_url="wss://your-api.execute-api.region.amazonaws.com/prod")
# ... use the client
```

See the [client/README.md](client/README.md) for detailed API documentation.

### Rebuilding Lambda Packages

The service and common packages are also bundled in `../cdk/lambda-packages/` for Lambda deployment.
If you modify the source code in `service/` or `common/`, rebuild the Lambda packages:

```bash
cd ../cdk/lambda-assets-build
./build-lambda-packages.sh
```

This script will:
- Install dependencies from `requirements-service.txt` and `requirements-common.txt`
- Copy source code from `../../sdk/service/` and `../../sdk/common/`
- Create deployment packages in `../lambda-packages/`

## Development

All packages are exported from the internal codebase with full source code, tests, and dependencies.

### VSCode Setup

Each SDK package includes VSCode settings for proper Python path resolution and IntelliSense support. The `.vscode/settings.json` files are configured to:

1. Use the shared virtual environment at `sdk/.venv`
2. Add package source directories to Python analysis paths
3. Enable proper import resolution across packages

**Common package** (`.vscode/settings.json`):
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/../.venv/bin/python",
    "python.analysis.extraPaths": [
        "${workspaceFolder}/src"
    ]
}
```

**Client and Service packages** (`.vscode/settings.json`):
```json
{
    "python.defaultInterpreterPath": "${workspaceFolder}/../.venv/bin/python",
    "python.analysis.extraPaths": [
        "${workspaceFolder}/src",
        "${workspaceFolder}/../common/src"
    ]
}
```

**Setup Instructions:**

1. Create a virtual environment in the `sdk/` directory:
   ```bash
   cd sdk
   python -m venv .venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. Install hatch and dependencies:
   ```bash
   pip install hatch
   ```

3. Open individual package folders in VSCode:
   - `sdk/common/` - Common package
   - `sdk/client/` - Client package
   - `sdk/service/` - Service package

4. VSCode will automatically use the shared `.venv` and resolve imports correctly

**Note**: The VSCode settings use workspace-relative paths, so you should open the individual package directories (e.g., `sdk/common/`) as the workspace root in VSCode, not the top-level `sdk/` directory.

### Build and Test Script

The `build-and-test.sh` script provides automated linting, type checking, testing, and building for all SDK packages.

**Prerequisites:**
```bash
# Create and activate virtual environment in sdk/
cd sdk
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate

# Install hatch
pip install hatch
```

**Usage:**
```bash
# Run all checks and tests (linting, formatting, type checking, pytest, build)
./build-and-test.sh

# Run checks and update lambda packages for CDK deployment
./build-and-test.sh --update-lambda

# Run only linting and type checking (skip tests and build)
./build-and-test.sh --skip-tests --skip-build

# Show help
./build-and-test.sh --help
```

**What it does:**
- Runs Ruff linting and format checking
- Runs mypy type checking
- Runs pytest test suite
- Builds distribution packages (.whl and .tar.gz)
- Optionally copies packages to `cdk/lambda-packages/` for deployment

**Options:**
- `--update-lambda` - Copy common and service packages to CDK lambda handlers
- `--skip-tests` - Skip running pytest tests
- `--skip-build` - Skip building distribution packages
- `--help` - Show usage information
