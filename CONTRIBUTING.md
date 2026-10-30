# Contributing

Create a branch for one scoped change and open a pull request. Include the concrete problem, resulting behavior and validation. Use isolated worktrees when agents work concurrently. Keep structured handoffs under docs/handoffs/; never include raw private transcripts or credentials.

## Checks

```sh
python3 -m unittest discover -s tests -v
python3 scripts/smoke_demo.py
npm ci
npm run build
```

## macOS release build

```sh
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
.build-venv/bin/python scripts/bundle_backend.py
.build-venv/bin/python scripts/smoke_demo.py "$PWD/build/runtime/acc-backend/acc-backend"
npm ci
npm run tauri build -- --bundles app
python3 scripts/package_macos.py
```

The release app includes a frozen Python runtime. Users need no Python, Node or Rust to open the app. Agent CLIs and their own authentication remain external. Build products belong in GitHub Releases, never Git source history. Developer ID signing and notarization require the owner's Apple credentials; this release uses local ad-hoc signing only.
