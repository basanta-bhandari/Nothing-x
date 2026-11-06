from pathlib import Path
import plistlib
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from nothingx import __version__
from tools.publish_release import validate_mac_archive


class ReleaseChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.archive = Path(self.directory.name) / "NothingX-macos-arm64.app.zip"

    def make_archive(self, version=__version__, identity="io.github.basanta_bhandari.NothingX", duplicate=False):
        info = plistlib.dumps({"CFBundleShortVersionString": version, "CFBundleIdentifier": identity})
        with zipfile.ZipFile(self.archive, "w") as archive:
            archive.writestr("Nothing X.app/Contents/Info.plist", info)
            if duplicate:
                archive.writestr("Other.app/Contents/Info.plist", info)

    def test_matching_mac_package_is_accepted(self):
        self.make_archive()
        validate_mac_archive(self.archive)

    def test_stale_mac_package_is_rejected(self):
        self.make_archive(version="0.5.0")
        with self.assertRaises(ValueError):
            validate_mac_archive(self.archive)

    def test_wrong_app_identity_is_rejected(self):
        self.make_archive(identity="unrelated.application")
        with self.assertRaises(ValueError):
            validate_mac_archive(self.archive)

    def test_multiple_apps_are_rejected(self):
        self.make_archive(duplicate=True)
        with self.assertRaises(ValueError):
            validate_mac_archive(self.archive)


if __name__ == "__main__":
    unittest.main()
