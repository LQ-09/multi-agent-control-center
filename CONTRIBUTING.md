# Contributing

Create a branch for one scoped change and open a pull request. Include the concrete problem, resulting behavior and validation. Use isolated worktrees when agents work concurrently. Keep structured handoffs under docs/handoffs/; never include raw private transcripts or credentials.

## Checks

```sh
python3 -m pip install -r requirements.txt
python3 -m unittest discover -s tests -v
python3 scripts/smoke_demo.py
npm ci
npm run build
```

## macOS release build

```sh
npm ci
python3 -m venv .build-venv
.build-venv/bin/python -m pip install -r requirements-build.txt
.build-venv/bin/python scripts/bundle_backend.py
.build-venv/bin/python scripts/smoke_demo.py "$PWD/build/runtime/acc-backend/acc-backend"
npm ci
npm run tauri build -- --bundles app
ACC_UPDATER_KEY=/absolute/private/path/acc.key python3 scripts/package_macos.py
```

The release app includes a frozen Python runtime. Users need no Python, Node or Rust to open the app. Agent CLIs and their own authentication remain external. Build products belong in GitHub Releases, never Git source history. Developer ID signing and notarization require the owner's Apple credentials; this release uses local ad-hoc signing only.

## Update releases

Keep the updater private key outside this repository and back it up securely. Losing it breaks updates for already-installed clients. Never publish it or place it in release assets. The embedded public key identifies this project's releases; forks must generate their own key and change the endpoint.

Bump package.json/package-lock.json, Cargo.toml/Cargo.lock and tauri.conf.json together. Build the frozen backend and Tauri app, then run package_macos.py with ACC_UPDATER_KEY. It stages and verifies an ad-hoc-signed app, produces the bootstrap pkg, signs the app.tar.gz with the release version, and writes build/latest.json. Upload the pkg, archive, archive.sig and latest.json to the same **non-draft, non-prerelease** GitHub release. The latest/download endpoint excludes prereleases. Publish all assets before making the release current. Never edit a published archive in place.

Before publishing, verify the archive signature and signed version, compare SHA-256 after downloading, and run unit, frozen-backend and native build checks. GUI upgrade/relaunch and denied filesystem permissions still require an installed macOS acceptance test. Do not claim the remote worker was upgraded by a desktop update.

Verify each built release before upload:

```sh
cargo run --manifest-path src-tauri/Cargo.toml --example verify_update -- src-tauri/tauri.conf.json build/latest.json build/Agent-Control-Center-0.4.0-darwin-aarch64.app.tar.gz
```

Use the archive matching the new version. This check verifies the configured public key, signed version, and rejection of modified bytes.
