import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.migrate_legacy import migrate, OLD_APPLET, NEW_APPLET


class MigrationChecks(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.prefix = Path(self.directory.name) / "local"
        self.config = Path(self.directory.name) / "config"
        metadata = self.prefix / "share/nothingx-rust-applet/nothingx/assets/build.json"
        metadata.parent.mkdir(parents=True)
        metadata.write_text(json.dumps({"backend": "rust", "distribution": "applet", "version": "0.6.0"}))
        binary = self.prefix / "bin/cosmic-applet-nothingx-rust"
        binary.parent.mkdir(parents=True)
        binary.write_text("Rust applet")
        self.panel = self.config / "cosmic/com.system76.CosmicPanel.Panel/v1/plugins_wings"
        self.panel.parent.mkdir(parents=True)

    def test_migration_preserves_other_plugins_and_backs_up_launchers(self):
        original = f'Some(([\n    "unrelated.plugin",\n    "{OLD_APPLET}",\n], []))\n'
        self.panel.write_text(original)
        legacy = self.prefix / "share/applications/io.github.basanta_bhandari.NothingX.cpp.applet.desktop"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("Old C++ launcher")
        changed = migrate(self.prefix, self.config)
        self.assertIn("unrelated.plugin", self.panel.read_text())
        self.assertIn(NEW_APPLET, self.panel.read_text())
        self.assertNotIn(OLD_APPLET, self.panel.read_text())
        self.assertFalse(legacy.exists())
        backups = self.prefix / "share/nothingx-migration-backups"
        self.assertEqual(next(backups.glob("*/applications/*.desktop")).read_text(), "Old C++ launcher")
        self.assertEqual(next(backups.glob("*/config/cosmic/*/v1/plugins_wings")).read_text(), original)
        self.assertEqual(len(changed), 2)
        self.assertEqual(migrate(self.prefix, self.config), [])

    def test_existing_rust_plugin_is_not_duplicated(self):
        self.panel.write_text(f'Some(([\n    "{NEW_APPLET}",\n    "{OLD_APPLET}",\n], []))\n')
        migrate(self.prefix, self.config)
        self.assertEqual(self.panel.read_text().count(NEW_APPLET), 1)
        self.assertNotIn(OLD_APPLET, self.panel.read_text())

    def test_missing_rust_install_keeps_legacy_configuration(self):
        self.panel.write_text(OLD_APPLET)
        (self.prefix / "bin/cosmic-applet-nothingx-rust").unlink()
        with self.assertRaises(RuntimeError):
            migrate(self.prefix, self.config)
        self.assertEqual(self.panel.read_text(), OLD_APPLET)


if __name__ == "__main__":
    unittest.main()
