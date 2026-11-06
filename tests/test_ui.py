import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

os.environ["QT_QPA_PLATFORM"] = "offscreen"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtTest import QTest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from nothingx.preferences import save_preferences
from nothingx.themes import THEMES
from nothingx.ui import MainWindow
from test_beta import AudioStub


class InterfaceChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix="nothingx-ui-check-")
        self.addCleanup(self.directory.cleanup)
        QSettings.setPath(QSettings.Format.NativeFormat, QSettings.Scope.UserScope, self.directory.name)
        self.environment = patch.dict(os.environ, {"NOTHINGX_PREFERENCES": str(Path(self.directory.name) / "preferences.json")})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.audio = patch("nothingx.service.make_audio", lambda parent: AudioStub(parent))
        self.audio.start()
        self.addCleanup(self.audio.stop)
        self.window = MainWindow(demo=True)
        self.addCleanup(self.window.desktop_widget.deleteLater)
        self.addCleanup(self.window.backend_client.stop)
        self.addCleanup(self.window.deleteLater)
        self.window.show()
        QTest.qWait(100)

    def test_all_themes_and_representative_device_types_render(self):
        for model in ("B172", "B170", "B164"):
            self.window.backend_client.service.start_demo(model)
            for theme in THEMES:
                with self.subTest(model=model, theme=theme):
                    self.window.apply_theme(theme)
                    self.app.processEvents()
                    self.assertEqual(self.app.property("nothingx_theme"), theme)
                    self.assertFalse(self.window.grab().isNull())

    def test_external_theme_update_is_detected_after_atomic_replace(self):
        theme = next(name for name in THEMES if name != self.window.theme_name)
        save_preferences(theme=theme)
        for _ in range(40):
            QTest.qWait(50)
            if self.window.theme_name == theme:
                break
        self.assertEqual(self.window.theme_name, theme)
        self.assertFalse(self.window.theme_timer.isActive())

    def test_disconnect_clears_pending_controls(self):
        self.window.pending.add("anc")
        self.window.requested["anc"] = "Off"
        self.window.preset_active = "anc"
        self.window.on_status("disconnected", "Disconnected")
        self.assertFalse(self.window.pending)
        self.assertFalse(self.window.requested)
        self.assertIsNone(self.window.preset_active)
        self.assertIn("Put both buds", self.window.connection_tip.text())

    def test_connection_hint_survives_errors_and_connecting(self):
        self.window.on_status("disconnected", "Disconnected")
        tip = self.window.connection_tip.text()
        self.window.show_message("Control connection unavailable", True)
        self.assertEqual(self.window.connection_tip.text(), tip)
        self.assertTrue(self.window.connection_tip.isVisible())
        self.assertTrue(self.window.banner.isVisible())
        self.window.on_status("connecting", "Connecting")
        self.assertTrue(self.window.connection_tip.isVisible())
        self.window.on_status("connected", "Connected")
        self.assertFalse(self.window.connection_tip.isVisible())

    def test_hint_is_visible_before_the_service_sends_any_status(self):
        with patch("nothingx.core.NativeClient.start"):
            window = MainWindow(demo=False)
        self.addCleanup(window.desktop_widget.deleteLater)
        self.addCleanup(window.backend_client.stop)
        self.addCleanup(window.deleteLater)
        window.show()
        self.assertTrue(window.connection_tip.isVisible())
        self.assertIn("Put both buds", window.connection_tip.text())

    def test_widget_and_window_show_the_same_disconnected_hint(self):
        self.window.set_widget_enabled(True)
        self.window.on_status("disconnected", "Disconnected")
        self.assertTrue(self.window.desktop_widget.connection_tip.isVisible())
        self.assertEqual(self.window.desktop_widget.connection_tip.text(), self.window.connection_tip.text())

    def test_headphones_do_not_get_case_instructions(self):
        self.window.backend_client.service.start_demo("B170")
        self.window.on_status("disconnected", "Disconnected")
        self.assertNotIn("both buds", self.window.connection_tip.text())
        self.assertIn("Turn on your headphones", self.window.connection_tip.text())

    def test_widget_shares_device_state_and_theme(self):
        self.window.set_widget_enabled(True)
        widget = self.window.desktop_widget
        self.assertTrue(widget.isVisible())
        self.assertIn("CMF", widget.name.text())
        self.assertIn("%", widget.battery.text())
        self.window.apply_theme("porcelain")
        self.assertFalse(widget.grab().isNull())
        widget.close()
        self.assertFalse(self.window.widget_toggle.isChecked())

    def test_widget_dismissal_restores_hidden_settings(self):
        self.window.set_widget_enabled(True)
        self.window.hide()
        self.window.desktop_widget.close()
        self.assertTrue(self.window.isVisible())


if __name__ == "__main__":
    unittest.main()
