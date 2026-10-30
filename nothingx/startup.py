import os
from pathlib import Path
import plistlib
import sys

from .variants import backend_name


def startup_path(system=None):
    system = system or sys.platform
    override = os.environ.get("NOTHINGX_STARTUP_ROOT")
    if system == "darwin":
        return Path(override or Path.home() / "Library/LaunchAgents") / "io.github.basanta_bhandari.NothingX.plist"
    root = Path(override) if override else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "autostart"
    return root / "nothingx.desktop"


def enabled():
    return startup_path().is_file()


def desktop_argument(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%") + '"'


def launch_command():
    if os.environ.get("APPIMAGE"):
        return [os.environ["APPIMAGE"], "--connect"]
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        return ["/usr/bin/open", "-a", str(Path(sys.executable).parents[2]), "--args", "--connect"]
    return [sys.executable, "-m", "nothingx", "--backend", backend_name(), "--connect"]


def set_enabled(value, system=None, command=None):
    system = system or sys.platform
    path = startup_path(system)
    if not value:
        path.unlink(missing_ok=True)
        return
    command = command or launch_command()
    working = str(Path(__file__).resolve().parents[1])
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".new")
    if system == "darwin":
        temporary.write_bytes(plistlib.dumps({"Label": "io.github.basanta_bhandari.NothingX", "ProgramArguments": command, "WorkingDirectory": working, "RunAtLoad": True, "KeepAlive": False, "ProcessType": "Interactive"}))
    else:
        temporary.write_text("[Desktop Entry]\nType=Application\nName=Nothing X\nExec=" + " ".join(desktop_argument(arg) for arg in command) + "\nPath=" + working + "\nTerminal=false\nX-GNOME-Autostart-enabled=true\n")
    temporary.replace(path)
