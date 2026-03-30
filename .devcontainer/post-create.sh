#!/bin/bash
set -e

echo "Installing workspace packages (editable mode)..."
uv sync --group dev

echo "Setting up git hooks and nbstripout..."

# Install pre-commit hooks
pre-commit install

# Also install nbstripout as a git filter (belt + suspenders with pre-commit)
nbstripout --install --attributes .gitattributes

echo "pre-commit hooks installed"
echo "nbstripout git filter installed"
