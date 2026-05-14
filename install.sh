#!/usr/bin/env bash
set -euo pipefail

# sgm installer
# Usage: curl -fsSL https://raw.githubusercontent.com/palexander/sgm/main/install.sh | bash
# Or with a specific version:
# SGM_VERSION=v0.1.0 curl -fsSL ... | bash

GITHUB_REPO="paul-cmz/sgm"
TOOL_NAME="sgm"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[sgm]${NC} $*"; }
success() { echo -e "${GREEN}[sgm]${NC} $*"; }
warn()    { echo -e "${YELLOW}[sgm]${NC} $*"; }
error()   { echo -e "${RED}[sgm]${NC} $*" >&2; exit 1; }

# Detect OS
OS=$(uname -s)
case "$OS" in
  Linux*)  OS=linux ;;
  Darwin*) OS=macos ;;
  *)       error "Unsupported OS: $OS" ;;
esac

# Detect architecture
ARCH=$(uname -m)
case "$ARCH" in
  x86_64)          ARCH=x86_64 ;;
  amd64)           ARCH=x86_64 ;;
  arm64|aarch64)   ARCH=aarch64 ;;
  *)               error "Unsupported architecture: $ARCH" ;;
esac

info "Detected: $OS/$ARCH"

# ── Install uv if not present ─────────────────────────────────────────────────

install_uv() {
  info "uv not found — installing..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  # Make uv available in the current shell
  export PATH="$HOME/.local/bin:$PATH"
  if ! command -v uv &>/dev/null; then
    error "uv installation succeeded but 'uv' is still not on PATH. Please add \$HOME/.local/bin to your PATH and re-run."
  fi
  success "uv installed"
}

if ! command -v uv &>/dev/null; then
  install_uv
else
  info "uv already installed ($(uv --version))"
fi

# ── Resolve the target version ────────────────────────────────────────────────

if [ -z "${SGM_VERSION:-}" ]; then
  info "Fetching latest release..."
  SGM_VERSION=$(curl -fsSL "https://api.github.com/repos/${GITHUB_REPO}/releases/latest" \
    | grep '"tag_name"' \
    | sed 's/.*"tag_name": *"\([^"]*\)".*/\1/')
  if [ -z "$SGM_VERSION" ]; then
    error "Could not determine latest version. Try setting SGM_VERSION=vX.Y.Z explicitly."
  fi
fi

# Strip leading 'v'
VERSION_NUM="${SGM_VERSION#v}"
info "Installing sgm ${SGM_VERSION}..."

# ── Download and install wheel ────────────────────────────────────────────────

WHEEL_NAME="sgm-${VERSION_NUM}-py3-none-any.whl"
WHEEL_URL="https://github.com/${GITHUB_REPO}/releases/download/${SGM_VERSION}/${WHEEL_NAME}"

info "Downloading ${WHEEL_NAME}..."
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

curl -fsSL -o "${TMP_DIR}/${WHEEL_NAME}" "$WHEEL_URL" \
  || error "Failed to download wheel from:\n  ${WHEEL_URL}\n\nCheck https://github.com/${GITHUB_REPO}/releases for available versions."

uv tool install --python 3.12 "${TMP_DIR}/${WHEEL_NAME}"

# ── Verify install ────────────────────────────────────────────────────────────

if ! command -v sgm &>/dev/null; then
  TOOL_BIN_DIR=$(uv tool dir)/bin
  warn "sgm was installed but is not on your PATH."
  warn "Add this to your shell profile:"
  warn "  export PATH=\"${TOOL_BIN_DIR}:\$PATH\""
else
  success "sgm ${SGM_VERSION} installed successfully!"
  echo ""
  echo "  Run 'sgm --help' to get started."
  echo "  Run 'sgm init' inside a repo to bootstrap governance."
  echo ""
fi
