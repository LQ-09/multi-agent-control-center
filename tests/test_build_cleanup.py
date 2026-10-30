import plistlib
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from cleanup_build_apps import cleanup, BUILD_APPS, APP_ID

class BuildCleanupTests(unittest.TestCase):
    def app(self, path, identifier=APP_ID):
        (path / 'Contents').mkdir(parents=True)
        (path / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': identifier}))

    @patch('cleanup_build_apps.REGISTER', Path('/nonexistent-lsregister'))
    def test_only_known_build_copies_removed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve()
            for relative in BUILD_APPS:self.app(root/relative)
            installed=root/'Applications/Agent Control Center.app';self.app(installed)
            state=root/'build/data.sqlite';state.write_bytes(b'preserve')
            self.assertEqual(len(cleanup(root)),3)
            self.assertTrue(installed.exists());self.assertEqual(state.read_bytes(),b'preserve')
            self.assertEqual(cleanup(root),[])

    def test_wrong_identity_and_symlink_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();app=root/BUILD_APPS[0];self.app(app,'other.app')
            with self.assertRaises(ValueError):cleanup(root)
            self.assertTrue(app.exists())
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp).resolve();target=root/'installed';self.app(target)
            (root/'build').mkdir();(root/'build/pkg-payload').symlink_to(target.parent)
            with self.assertRaises(ValueError):
                # A symlink at the exact app location must never be traversed.
                (target.parent/'Agent Control Center.app').symlink_to(target)
                cleanup(root)
            self.assertTrue(target.exists())
