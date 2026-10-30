"""Remove only this project's known disposable macOS app bundles."""
import plistlib
import shutil
import subprocess
from pathlib import Path

APP_ID = 'dev.ling.agent-control-center'
BUILD_APPS = (
    'build/pkg-payload/Agent Control Center.app',
    'build/.pkg-payload/Agent Control Center.app',
    'src-tauri/target/release/bundle/macos/Agent Control Center.app',
)
REGISTER = Path('/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/Support/lsregister')


def cleanup(root):
    root = Path(root).resolve()
    removed = []
    for relative in BUILD_APPS:
        app = root / relative
        if not app.exists():
            continue
        # Never follow a build-directory symlink to an installed or unrelated app.
        if app.resolve() != app or not app.is_dir():
            raise ValueError(f'Refusing unexpected build path: {app}')
        info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
        if info.get('CFBundleIdentifier') != APP_ID:
            raise ValueError(f'Refusing unrelated application: {app}')
        if REGISTER.exists():
            result = subprocess.run([str(REGISTER), '-u', str(app)], capture_output=True, text=True)
            if result.returncode:
                print(f'Could not unregister build copy (macOS may retain a cached entry): {app}')
        shutil.rmtree(app)
        removed.append(app)
    return removed


if __name__ == '__main__':
    for app in cleanup(Path(__file__).resolve().parents[1]):
        print(f'Removed build copy: {app}')
