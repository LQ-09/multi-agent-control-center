"""Create a local, ad-hoc-signed app installer targeting /Applications."""
import json
import plistlib
import subprocess
import shutil
import tempfile
from pathlib import Path
from cleanup_build_apps import cleanup

root = Path(__file__).resolve().parents[1]
version = json.loads((root/'package.json').read_text())['version']
source = root/'src-tauri/target/release/bundle/macos/Agent Control Center.app'
# Stage outside file-provider folders, which can mutate Finder metadata mid-signature.
temporary = tempfile.TemporaryDirectory(prefix='acc-pkg-')
try:
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
    # Archive exactly the verified app, not the metadata-mutated build directory.
    archive = root/f'build/Agent-Control-Center-{version}-darwin-aarch64.app.tar.gz'
    import os
    subprocess.run(['tar', '-czf', str(archive), '-C', str(stage), app.name], check=True,
        env={**os.environ, 'COPYFILE_DISABLE':'1'})
    key = os.environ.get('ACC_UPDATER_KEY')
    if not key:
        raise SystemExit('Set ACC_UPDATER_KEY to the private signing key path; no unsigned update is published.')
    subprocess.run(['npx', 'tauri', 'signer', 'sign', '-f', key, '-p', '', '--app-version', version, str(archive)], check=True)
    manifest={'version':version,'notes':'Concise handoffs, explicit blocked results, scoped Codex workspace writes, automatic task start and transparent quota widget. 简洁交接、阻塞状态、限定项目写入、创建即运行及透明悬浮窗。',
        'platforms':{'darwin-aarch64':{'url':f'https://github.com/LQ-09/multi-agent-control-center/releases/download/v{version}/{archive.name}',
        'signature':Path(str(archive)+'.sig').read_text().strip()}}}
    (root/'build/latest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(archive)
finally:
    temporary.cleanup()

# The pkg and signed archive are the deliverables; loose apps confuse app discovery.
for removed in cleanup(root):
    print(f"Removed build copy: {removed}")
