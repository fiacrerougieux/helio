#!/bin/bash
# Sun Sleuth - Complete Installation Script for Linux/macOS
# Installs everything: Python dependencies, security sandbox, and sets up environment

set -e  # Exit on error

echo "========================================"
echo "Sun Sleuth - Complete Installation"
echo "========================================"
echo ""
echo "This will install:"
echo "  1. Python dependencies (pvlib, pandas, numpy, etc.)"
echo "  2. Security sandbox (Bubblewrap/sandbox-exec)"
echo "  3. Configure environment"
echo ""

# Check if Python is available
if ! command -v python3 &> /dev/null; then
    echo "ERROR: Python 3 not found."
    echo "Please install Python 3.9+ first:"
    echo "  Ubuntu/Debian: sudo apt-get install python3 python3-pip"
    echo "  macOS: brew install python3"
    exit 1
fi

# Detect OS
OS="$(uname -s)"
echo "Detected OS: $OS"
echo ""

echo "Step 1/3: Installing Python dependencies..."
echo "========================================"
echo ""

# Upgrade pip
python3 -m pip install --upgrade pip

# Install dependencies
python3 -m pip install -r requirements.txt

if [ $? -ne 0 ]; then
    echo ""
    echo "ERROR: Failed to install Python dependencies."
    echo "Please check your internet connection and try again."
    exit 1
fi

echo ""
echo "Step 2/3: Installing security sandbox..."
echo "========================================"
echo ""

case "$OS" in
    Linux*)
        echo "Installing Bubblewrap for Linux..."

        # Try to detect package manager and install
        if command -v apt-get &> /dev/null; then
            echo "Using apt-get (requires sudo)..."
            sudo apt-get update
            sudo apt-get install -y bubblewrap
        elif command -v dnf &> /dev/null; then
            echo "Using dnf (requires sudo)..."
            sudo dnf install -y bubblewrap
        elif command -v yum &> /dev/null; then
            echo "Using yum (requires sudo)..."
            sudo yum install -y bubblewrap
        elif command -v pacman &> /dev/null; then
            echo "Using pacman (requires sudo)..."
            sudo pacman -S --noconfirm bubblewrap
        else
            echo "WARNING: No supported package manager found."
            echo "Please install bubblewrap manually for your distribution."
            echo "You can still use the system with basic isolation."
        fi
        ;;

    Darwin*)
        echo "macOS detected - using built-in sandbox-exec"
        echo "No installation needed! ✓"
        ;;

    *)
        echo "WARNING: Unsupported OS: $OS"
        echo "Security sandbox may not be available."
        ;;
esac

# Run sandbox configuration script
echo ""
echo "Configuring sandbox..."
if [ -f "scripts/install_sandbox.py" ]; then
    python3 scripts/install_sandbox.py
else
    echo "Sandbox configuration script not found (skipping)..."
fi

echo ""
echo "Step 3/3: Testing installation..."
echo "========================================"
echo ""

# Test core dependencies
python3 -c "import pvlib; import pandas; import numpy; print('✓ Core dependencies OK')"

if [ $? -ne 0 ]; then
    echo "ERROR: Dependency test failed."
    exit 1
fi

# Test OpenRouter client
python3 -c "from agent.openrouter_client import OpenRouterClient; print('✓ OpenRouter client OK')" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "⚠ OpenRouter client not configured (optional - set OPENROUTER_API_KEY to use cloud LLM)"
else
    echo "✓ OpenRouter client OK"
fi

# Test secure executor
python3 -c "from agent.secure_executor import SecureExecutor; SecureExecutor().test_environment()"

echo ""
echo "========================================"
echo "Installation Complete!"
echo "========================================"
echo ""
echo "You can now run Sun Sleuth:"
echo "  ./helio.py"
echo ""
echo "Or using python directly:"
echo "  python3 helio.py"
echo ""
echo "Optional: Set OPENROUTER_API_KEY for cloud LLM access"
echo "  export OPENROUTER_API_KEY=your-key-here"
echo ""
