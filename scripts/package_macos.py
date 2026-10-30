"""Create a local, ad-hoc-signed app installer targeting /Applications."""
import json
import plistlib
import subprocess
import shutil
import tempfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = json.loads((root/'package.json').read_text())['version']
source = root/'src-tauri/target/release/bundle/macos/Agent Control Center.app'
# Stage outside file-provider folders, which can mutate Finder metadata mid-signature.
temporary = tempfile.TemporaryDirectory(prefix='acc-pkg-')
stage = Path(temporary.name)
app = stage/source.name
shutil.copytree(source, app, symlinks=True, dirs_exist_ok=True, copy_function=shutil.copy)
# Framework Finder metadata is not part of signed executable content.
for attribute in ['com.apple.FinderInfo', 'com.apple.ResourceFork']:
    subprocess.run(['xattr', '-dr', attribute, str(app)], check=True)
# File-provider-backed folders can regenerate bundle FinderInfo during a traversal.
for bundle in [app, *app.rglob('*.framework')]:
    subprocess.run(['xattr', '-d', 'com.apple.FinderInfo', str(bundle)], stderr=subprocess.DEVNULL)
subprocess.run(['codesign', '--force', '--deep', '--sign', '-', str(app)], check=True)
subprocess.run(['codesign', '--verify', '--deep', '--strict', str(app)], check=True)
components = root/'build/pkg-components.plist'
subprocess.run(['pkgbuild', '--analyze', '--root', str(stage), str(components)], check=True)
items = plistlib.loads(components.read_bytes())
for item in items:
    item['BundleIsRelocatable'] = False
    item['BundleOverwriteAction'] = 'upgrade'
components.write_bytes(plistlib.dumps(items))
output = root/f'build/Agent-Control-Center-{version}-arm64.pkg'
subprocess.run(['pkgbuild', '--root', str(stage), '--component-plist', str(components),
    '--install-location', '/Applications', '--identifier', 'dev.ling.agent-control-center',
    '--version', version, str(output)], check=True)
print(output)
temporary.cleanup()
