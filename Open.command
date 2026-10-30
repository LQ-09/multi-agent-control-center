#!/bin/zsh
set -eu
cd "${0:A:h}"
# Preserve the Terminal environment so SSH and installed agent CLIs stay available.
if [[ -z "${ACC_PYTHON:-}" ]]; then
  for candidate in python3 /opt/homebrew/bin/python3.12 /opt/homebrew/bin/python3 /usr/local/bin/python3; do
    if "$candidate" -c 'import sys; assert sys.version_info >= (3,11)' 2>/dev/null; then
      export ACC_PYTHON="$(command -v "$candidate")"
      break
    fi
  done
fi
if [[ -z "${ACC_PYTHON:-}" ]]; then
  print 'Python 3.11+ is required. Set ACC_PYTHON to its executable path.'
  exit 1
fi
app="src-tauri/target/release/bundle/macos/Agent Control Center.app/Contents/MacOS/agent-control-center"
if [[ -x "Agent Control Center.app/Contents/MacOS/agent-control-center" ]]; then
  app="Agent Control Center.app/Contents/MacOS/agent-control-center"
fi
if [[ ! -x "$app" ]]; then
  print 'Build the application first: npm run tauri build -- --bundles app'
  exit 1
fi
exec "$app"
