#!/bin/bash
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
CDK_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$CDK_DIR")"
SDK_DIR="$REPO_ROOT/sdk"
LAMBDA_PKG_DIR="$CDK_DIR/lambda-packages"

echo "=========================================="
echo "Building Lambda Deployment Packages"
echo "=========================================="
echo "SDK Directory: $SDK_DIR"
echo "Lambda Packages: $LAMBDA_PKG_DIR"
echo ""

# Check if SDK directories exist
if [ ! -d "$SDK_DIR/service" ] || [ ! -d "$SDK_DIR/common" ]; then
    echo "❌ Error: SDK source directories not found"
    echo "   Expected: $SDK_DIR/service and $SDK_DIR/common"
    exit 1
fi

# Check if requirements files exist
if [ ! -f "$SCRIPT_DIR/requirements-common.txt" ] || [ ! -f "$SCRIPT_DIR/requirements-service.txt" ]; then
    echo "❌ Error: Requirements files not found"
    echo "   Expected: $SCRIPT_DIR/requirements-common.txt and $SCRIPT_DIR/requirements-service.txt"
    exit 1
fi

# Create temp build directory
BUILD_DIR=$(mktemp -d)
echo "Using temp directory: $BUILD_DIR"
echo ""

# Build common package first (required by service)
echo "Building common package..."
COMMON_BUILD="$BUILD_DIR/common"
mkdir -p "$COMMON_BUILD"

echo "  ✓ Copying common source code..."
cp -r "$SDK_DIR/common/src/amzn_nova_act_human_intervention_common" "$COMMON_BUILD/"

echo "  ✓ Installing common dependencies from requirements-common.txt..."
pip install     -v     --platform manylinux2014_x86_64     --target "$COMMON_BUILD"     --implementation cp     --only-binary=:all:     --python-version 3.12     -r "$SCRIPT_DIR/requirements-common.txt"

echo "  ✓ Common package built"
echo ""

# Build service package with all dependencies
echo "Building service package..."
SERVICE_BUILD="$BUILD_DIR/service"
mkdir -p "$SERVICE_BUILD"

echo "  ✓ Copying service source code..."
cp -r "$SDK_DIR/service/src/amzn_nova_act_human_intervention" "$SERVICE_BUILD/"

echo "  ✓ Installing service dependencies from requirements-service.txt..."
pip install -v     --platform manylinux2014_x86_64     --target "$SERVICE_BUILD"     --implementation cp     --only-binary=:all:     --python-version 3.12     -r "$SCRIPT_DIR/requirements-service.txt"

echo "  ✓ Service package built"
echo ""

# Copy to lambda-packages
echo "Copying to lambda-packages directory..."
rm -rf "$LAMBDA_PKG_DIR/handlers"
mkdir -p "$LAMBDA_PKG_DIR/handlers"

# Copy common package first
cp -r "$COMMON_BUILD/"* "$LAMBDA_PKG_DIR/handlers/"
# Copy service package (may overwrite some common files, that's ok)
cp -r "$SERVICE_BUILD/"* "$LAMBDA_PKG_DIR/handlers/"

echo "  ✓ Copied to $LAMBDA_PKG_DIR/handlers/"

# Cleanup unnecessary files
echo "Cleaning up unnecessary files..."
cd "$LAMBDA_PKG_DIR/handlers"

# Remove Python cache files and directories
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find . -type f -name "*.pyc" -delete 2>/dev/null || true
find . -type f -name "*.pyo" -delete 2>/dev/null || true

# Remove distribution metadata (not needed at runtime)
find . -type d -name "*.dist-info" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true

# Remove tests (if any packages include them)
find . -type d -name "tests" -exec rm -rf {} + 2>/dev/null || true
find . -type d -name "test" -exec rm -rf {} + 2>/dev/null || true

cd - > /dev/null

echo "  ✓ Removed __pycache__, *.pyc, .dist-info, and other unnecessary files"

# Cleanup temp directory
rm -rf "$BUILD_DIR"
echo ""

# Calculate size
TOTAL_SIZE=$(du -sh "$LAMBDA_PKG_DIR/handlers" | cut -f1)
echo "=========================================="
echo "Lambda Packages Built Successfully!"
echo "=========================================="
echo "Package size: $TOTAL_SIZE"
echo "Location: $LAMBDA_PKG_DIR/handlers/"
echo ""
echo "Next steps:"
echo "  1. Navigate to CDK directory: cd $CDK_DIR"
echo "  2. Deploy using the setup script: ./setup-and-deploy.sh quick-deploy"
echo ""
echo "For more deployment options, see: $CDK_DIR/CLI-GUIDE.md"
