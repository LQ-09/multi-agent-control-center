"""Create a local, ad-hoc-signed app installer targeting /Applications."""
import json
import plistlib
import subprocess
from pathlib import Path

root = Path(__file__).resolve().parents[1]
version = json.loads((root/'package.json').read_text())['version']
source = root/'src-tauri/target/release/bundle/macos/Agent Control Center.app'
stage = root/'build/pkg-payload'
stage.mkdir(parents=True, exist_ok=True)
app = stage/source.name
subprocess.run(['ditto', '--norsrc', '--noextattr', str(source), str(app)], check=True)
# Framework Finder metadata is not part of signed executable content.
for attribute in ['com.apple.FinderInfo', 'com.apple.ResourceFork']:
    subprocess.run(['xattr', '-dr', attribute, str(app)], check=True)
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
