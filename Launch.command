#!/bin/zsh
set -eu
cd "${0:A:h}"
if ! command -v cargo >/dev/null 2>&1; then
  print 'Rust is required to build this native Tauri app. Install a Rust toolchain, then rerun this launcher.'
  print 'Official installer: https://rustup.rs/'
  exit 1
fi
if ! command -v node >/dev/null 2>&1; then
  print 'Node.js 22+ is required. Install Node, then rerun this launcher.'
  exit 1
fi
export ACC_PYTHON="$(command -v python3)"
"$ACC_PYTHON" -c 'import sys; assert sys.version_info >= (3,11), "Python 3.11+ is required"'
if [[ ! -x node_modules/.bin/tauri ]]; then
  npm install --no-audit --no-fund
fi
npm run tauri dev
