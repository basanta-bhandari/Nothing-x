import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from nothingx import startup
from nothingx.variants import BACKENDS, DISTRIBUTIONS, backend_name, variant_id
from nothingx.updater import select_artifact


class DistributionChecks(unittest.TestCase):
    def test_only_three_rust_distributions_exist(self):
        root = Path(__file__).resolve().parents[1]
        registry = json.loads((root / "variants.json").read_text())
        self.assertEqual(BACKENDS, ("rust",))
        self.assertEqual({v["id"] for v in registry["variants"]}, {"rust-" + d for d in DISTRIBUTIONS})
        for distribution in DISTRIBUTIONS:
            self.assertEqual(variant_id("rust", distribution), "rust-" + distribution)
        with self.assertRaises(ValueError):
            backend_name("cpp")

    def test_update_selection_never_crosses_platform_or_variant(self):
        artifacts = [{"variant": "rust-" + d, "file": d + ".pkg", "os": "macos" if d == "macos" else "linux", "arch": "x86_64", "size": 12, "sha256": "a" * 64} for d in DISTRIBUTIONS]
        manifest = {"artifacts": artifacts}
        self.assertEqual(select_artifact(manifest, "rust-macos", "macos", "x86_64")["file"], "macos.pkg")
        with self.assertRaises(ValueError):
            select_artifact(manifest, "rust-macos", "linux", "x86_64")

    def test_flatpak_startup_uses_exported_application(self):
        with patch.dict(os.environ, {"FLATPAK_ID": "io.github.basanta_bhandari.NothingX"}):
            self.assertEqual(startup.launch_command(), ["flatpak", "run", "io.github.basanta_bhandari.NothingX", "--connect"])
            with self.assertRaises(OSError):
                startup.set_enabled(True)

    def test_flatpak_permission_scope_includes_bluetooth_and_audio(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "packaging/flatpak/io.github.basanta_bhandari.NothingX.json").read_text())
        self.assertIn("--allow=bluetooth", manifest["finish-args"])
        self.assertIn("--socket=pulseaudio", manifest["finish-args"])
        self.assertNotIn("--filesystem=host", manifest["finish-args"])


if __name__ == "__main__":
    unittest.main()
