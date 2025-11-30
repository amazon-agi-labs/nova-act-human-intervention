#!/usr/bin/env bash
set -e

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SDK_ROOT="$SCRIPT_DIR"
CDK_LAMBDA_HANDLERS="${SDK_ROOT}/../cdk/lambda-packages/handlers"

# Flags
UPDATE_LAMBDA=false
SKIP_TESTS=false
SKIP_BUILD=false

# Function to print colored output
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_section() {
    echo ""
    echo -e "${BLUE}================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}================================${NC}"
}

# Function to show usage
show_usage() {
    cat << EOF
Usage: $0 [OPTIONS]

Build, lint, type-check, and test all SDK packages.

OPTIONS:
    -h, --help              Show this help message
    -u, --update-lambda     Copy common and service packages to CDK lambda handlers
    -s, --skip-tests        Skip running tests
    -b, --skip-build        Skip building distribution packages

EXAMPLES:
    # Run all checks and tests
    $0

    # Run checks and update lambda packages
    $0 --update-lambda

    # Run only linting and type checking (skip tests and build)
    $0 --skip-tests --skip-build

EOF
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        -h|--help)
            show_usage
            exit 0
            ;;
        -u|--update-lambda)
            UPDATE_LAMBDA=true
            shift
            ;;
        -s|--skip-tests)
            SKIP_TESTS=true
            shift
            ;;
        -b|--skip-build)
            SKIP_BUILD=true
            shift
            ;;
        *)
            print_error "Unknown option: $1"
            show_usage
            exit 1
            ;;
    esac
done

# Check if virtual environment is activated or use local one
if [[ -z "${VIRTUAL_ENV}" ]]; then
    if [[ -f "${SDK_ROOT}/.venv/bin/activate" ]]; then
        print_info "Activating virtual environment..."
        source "${SDK_ROOT}/.venv/bin/activate"
    else
        print_error "Virtual environment not found at ${SDK_ROOT}/.venv"
        print_info "Please create it first: python -m venv .venv"
        exit 1
    fi
fi

# Check if hatch is installed
if ! command -v hatch &> /dev/null; then
    print_error "Hatch is not installed in the virtual environment"
    print_info "Install it with: pip install hatch"
    exit 1
fi

# Install dev dependencies in the main venv if not present (for IDE integration)
print_info "Checking development dependencies..."
DEV_DEPS_MISSING=false

for tool in ruff mypy pytest; do
    if ! python -c "import $tool" 2>/dev/null; then
        DEV_DEPS_MISSING=true
        break
    fi
done

if [[ "$DEV_DEPS_MISSING" == true ]]; then
    print_info "Installing development dependencies in virtual environment..."
    pip install -q ruff mypy pytest pytest-mock pytest-xdist
    print_success "Development dependencies installed"
else
    print_info "Development dependencies already installed"
fi

print_section "SDK Build and Test Script"
print_info "SDK Root: $SDK_ROOT"
print_info "Update Lambda: $UPDATE_LAMBDA"
print_info "Skip Tests: $SKIP_TESTS"
print_info "Skip Build: $SKIP_BUILD"

# Array of packages to process in order
PACKAGES=("common" "client" "service")

# Process each package
for PACKAGE in "${PACKAGES[@]}"; do
    print_section "Processing: $PACKAGE"

    PACKAGE_DIR="${SDK_ROOT}/${PACKAGE}"

    if [[ ! -d "$PACKAGE_DIR" ]]; then
        print_error "Package directory not found: $PACKAGE_DIR"
        exit 1
    fi

    cd "$PACKAGE_DIR"

    # For packages that depend on common, install common first to avoid sync errors
    if [[ "$PACKAGE" != "common" ]]; then
        print_info "Setting up hatch environment for ${PACKAGE}..."

        # Create the hatch environment without syncing dependencies
        hatch env create default 2>/dev/null || true

        # Get the hatch environment path and install common directly
        HATCH_ENV_PATH=$(hatch env find default)
        if [[ -n "$HATCH_ENV_PATH" && -f "$HATCH_ENV_PATH/bin/pip" ]]; then
            print_info "Installing common package directly in hatch environment..."
            "$HATCH_ENV_PATH/bin/pip" install -e ../common -q
            print_success "Common package installed in hatch environment"
        else
            print_warning "Could not find hatch environment pip, will attempt normal installation"
        fi
    fi

    # Install the current package in editable mode
    print_info "Installing ${PACKAGE} package in hatch environment..."
    hatch run pip install -e . -q 2>&1 | grep -v "Requirement already satisfied" || true

    # 1. Linting with Ruff
    print_info "Running Ruff linting for ${PACKAGE}..."
    if hatch run ruff check .; then
        print_success "Ruff linting passed for ${PACKAGE}"
    else
        print_error "Ruff linting failed for ${PACKAGE}"
        exit 1
    fi

    # 2. Format checking with Ruff
    print_info "Checking formatting with Ruff for ${PACKAGE}..."
    if hatch run ruff format --check .; then
        print_success "Format check passed for ${PACKAGE}"
    else
        print_error "Format check failed for ${PACKAGE}"
        print_info "Run 'hatch run ruff format .' to fix formatting"
        exit 1
    fi

    # 3. Type checking with mypy
    print_info "Running mypy type checking for ${PACKAGE}..."
    if hatch run mypy src/; then
        print_success "Type checking passed for ${PACKAGE}"
    else
        print_error "Type checking failed for ${PACKAGE}"
        exit 1
    fi

    # 4. Run tests
    if [[ "$SKIP_TESTS" == false ]]; then
        print_info "Running tests for ${PACKAGE}..."
        if hatch run pytest -v; then
            print_success "Tests passed for ${PACKAGE}"
        else
            print_error "Tests failed for ${PACKAGE}"
            exit 1
        fi
    else
        print_info "Skipping tests for ${PACKAGE}"
    fi

    # 5. Build distribution packages
    if [[ "$SKIP_BUILD" == false ]]; then
        print_info "Building distribution packages for ${PACKAGE}..."

        # Clean previous builds
        rm -rf dist/ build/
        find . -maxdepth 1 -name "*.egg-info" -type d -exec rm -rf {} + 2>/dev/null || true

        if hatch build; then
            print_success "Build completed for ${PACKAGE}"

            # Show what was built
            if [[ -d "dist" ]]; then
                print_info "Built packages:"
                ls -lh dist/
            fi

            # Install the package in the main venv so subsequent packages can find it
            print_info "Installing ${PACKAGE} in main virtual environment..."
            pip install -e . -q
            print_success "${PACKAGE} installed in main virtual environment"
        else
            print_error "Build failed for ${PACKAGE}"
            exit 1
        fi
    else
        print_info "Skipping build for ${PACKAGE}"

        # Even if skipping build, install in editable mode for subsequent packages
        print_info "Installing ${PACKAGE} in main virtual environment (editable mode)..."
        pip install -e . -q
        print_success "${PACKAGE} installed in main virtual environment"
    fi

    echo ""
done

# Update Lambda packages if requested
if [[ "$UPDATE_LAMBDA" == true ]]; then
    print_section "Updating Lambda Packages"

    if [[ ! -d "$CDK_LAMBDA_HANDLERS" ]]; then
        print_error "CDK lambda handlers directory not found: $CDK_LAMBDA_HANDLERS"
        exit 1
    fi

    # Update common package
    print_info "Copying common package to lambda handlers..."
    COMMON_SRC="${SDK_ROOT}/common/src/amzn_nova_act_human_intervention_common"
    COMMON_DST="${CDK_LAMBDA_HANDLERS}/amzn_nova_act_human_intervention_common"

    if [[ -d "$COMMON_SRC" ]]; then
        rm -rf "$COMMON_DST"

        # Use rsync to exclude cache and test artifacts
        if command -v rsync &> /dev/null; then
            rsync -a \
                --exclude='__pycache__' \
                --exclude='*.pyc' \
                --exclude='*.pyo' \
                --exclude='*.pyd' \
                --exclude='.pytest_cache' \
                --exclude='.mypy_cache' \
                --exclude='.ruff_cache' \
                --exclude='*.egg-info' \
                --exclude='.DS_Store' \
                "$COMMON_SRC/" "$COMMON_DST"
        else
            # Fallback to cp and manual cleanup
            cp -r "$COMMON_SRC" "$COMMON_DST"
            find "$COMMON_DST" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
            find "$COMMON_DST" -type f -name "*.pyc" -delete 2>/dev/null || true
            find "$COMMON_DST" -type f -name "*.pyo" -delete 2>/dev/null || true
            find "$COMMON_DST" -type f -name "*.pyd" -delete 2>/dev/null || true
            find "$COMMON_DST" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
            find "$COMMON_DST" -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
            find "$COMMON_DST" -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
            find "$COMMON_DST" -type f -name ".DS_Store" -delete 2>/dev/null || true
        fi

        print_success "Common package copied to lambda handlers"
    else
        print_error "Common package source not found: $COMMON_SRC"
        exit 1
    fi

    # Update service package
    print_info "Copying service package to lambda handlers..."
    SERVICE_SRC="${SDK_ROOT}/service/src/amzn_nova_act_human_intervention"
    SERVICE_DST="${CDK_LAMBDA_HANDLERS}/amzn_nova_act_human_intervention"

    if [[ -d "$SERVICE_SRC" ]]; then
        rm -rf "$SERVICE_DST"

        # Use rsync to exclude cache and test artifacts
        if command -v rsync &> /dev/null; then
            rsync -a \
                --exclude='__pycache__' \
                --exclude='*.pyc' \
                --exclude='*.pyo' \
                --exclude='*.pyd' \
                --exclude='.pytest_cache' \
                --exclude='.mypy_cache' \
                --exclude='.ruff_cache' \
                --exclude='*.egg-info' \
                --exclude='.DS_Store' \
                "$SERVICE_SRC/" "$SERVICE_DST"
        else
            # Fallback to cp and manual cleanup
            cp -r "$SERVICE_SRC" "$SERVICE_DST"
            find "$SERVICE_DST" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
            find "$SERVICE_DST" -type f -name "*.pyc" -delete 2>/dev/null || true
            find "$SERVICE_DST" -type f -name "*.pyo" -delete 2>/dev/null || true
            find "$SERVICE_DST" -type f -name "*.pyd" -delete 2>/dev/null || true
            find "$SERVICE_DST" -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
            find "$SERVICE_DST" -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
            find "$SERVICE_DST" -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
            find "$SERVICE_DST" -type f -name ".DS_Store" -delete 2>/dev/null || true
        fi

        print_success "Service package copied to lambda handlers"
    else
        print_error "Service package source not found: $SERVICE_SRC"
        exit 1
    fi

    # Clean up any remaining cache files in the lambda handlers directory
    print_info "Cleaning up cache files in lambda handlers..."
    find "$CDK_LAMBDA_HANDLERS" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    find "$CDK_LAMBDA_HANDLERS" -type f -name "*.pyc" -delete 2>/dev/null || true

    print_success "Lambda packages updated successfully"
fi

# Final summary
print_section "Summary"
print_success "All checks passed! ✓"
