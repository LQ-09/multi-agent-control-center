"""Collect upstream notices into the bundled runtime, without user files."""
import json
import shutil
import subprocess
import sys
from importlib.metadata import distribution
from pathlib import Path
root=Path(__file__).resolve().parents[1]
out=root/'build/runtime/acc-backend/licenses';out.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'THIRD_PARTY_NOTICES.md',out/'THIRD_PARTY_NOTICES.md')
shutil.copy2(root/'LICENSE',out/'PROJECT-LICENSE.txt')
python_license=Path(sys.base_prefix)/'lib'/f'python{sys.version_info.major}.{sys.version_info.minor}'/'LICENSE.txt'
if python_license.exists():shutil.copy2(python_license,out/'CPython-LICENSE.txt')
for name in ['pyinstaller','certifi']:
    dist=distribution(name)
    for path in dist.files or []:
        if 'license' in str(path).lower() or 'copying' in str(path).lower():
            source=Path(dist.locate_file(path))
            if source.is_file():shutil.copy2(source,out/(name+'-'+source.name))
for name in ['react','react-dom','scheduler']:
    license=root/'node_modules'/name/'LICENSE'
    if license.exists():shutil.copy2(license,out/(name+'-LICENSE.txt'))
cargo=shutil.which('cargo') or str(Path.home()/'.cargo/bin/cargo')
meta=json.loads(subprocess.check_output([cargo,'metadata','--offline','--format-version','1','--manifest-path',str(root/'src-tauri/Cargo.toml')]))
notices=[]
for package in meta['packages']:
    base=Path(package['manifest_path']).parent
    if base==root/'src-tauri':continue
    notices.append({k:package.get(k) for k in ['name','version','license','repository']})
    candidates=[p for p in base.iterdir() if p.is_file() and p.name.lower().startswith(('license','copying','notice'))]
    if package.get('license_file'):candidates.append(base/package['license_file'])
    for source in set(candidates):
        if source.is_file():shutil.copy2(source,out/(package['name']+'-'+package['version']+'-'+source.name))
(out/'rust-packages.json').write_text(json.dumps(notices,indent=2))
