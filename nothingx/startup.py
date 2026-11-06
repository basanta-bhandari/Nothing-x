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
    if os.environ.get("FLATPAK_ID"):
        from .preferences import read_preferences
        return bool(read_preferences().get("startup_enabled", False))
    return startup_path().is_file()


def desktop_argument(value):
    return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$").replace("%", "%%") + '"'


def launch_command():
    if os.environ.get("FLATPAK_ID"):
        return ["flatpak", "run", os.environ["FLATPAK_ID"], "--connect"]
    if sys.platform == "darwin" and getattr(sys, "frozen", False):
        return ["/usr/bin/open", "-a", str(Path(sys.executable).parents[2]), "--args", "--connect"]
    return [sys.executable, "-m", "nothingx", "--backend", backend_name(), "--connect"]


def set_enabled(value, system=None, command=None):
    if os.environ.get("FLATPAK_ID") and system is None:
        raise OSError("Use the desktop startup permission dialog for Flatpak.")
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


def request_flatpak_startup(value, callback, parent):
    import asyncio
    import threading
    import uuid
    from PySide6.QtCore import QObject, Signal

    class Request(QObject):
        finished = Signal(bool, str)

    request = Request(parent)
    request.finished.connect(callback)

    async def portal():
        from dbus_next import Message, Variant, MessageType
        from dbus_next.aio import MessageBus
        bus = await MessageBus().connect()
        try:
            token = "nothingx" + uuid.uuid4().hex
            response = asyncio.get_running_loop().create_future()
            path = "/org/freedesktop/portal/desktop/request/" + bus.unique_name[1:].replace(".", "_") + "/" + token
            def received(message):
                if message.path == path and message.interface == "org.freedesktop.portal.Request" and message.member == "Response" and not response.done():
                    response.set_result(message.body[0])
            bus.add_message_handler(received)
            reply = await bus.call(Message(destination="org.freedesktop.portal.Desktop", path="/org/freedesktop/portal/desktop", interface="org.freedesktop.portal.Background", member="RequestBackground", signature="sa{sv}", body=["", {"handle_token": Variant("s", token), "reason": Variant("s", "Keep Nothing X device controls available and open at startup."), "autostart": Variant("b", bool(value)), "commandline": Variant("as", ["nothingx", "--connect"])}]))
            if reply.message_type == MessageType.ERROR:
                raise OSError("Your desktop could not change startup permission.")
            if await response != 0:
                raise OSError("Startup permission was not granted.")
        finally:
            bus.disconnect()

    def run():
        try:
            asyncio.run(asyncio.wait_for(portal(), 120))
            result = bool(value), ""
        except Exception as error:
            result = enabled(), str(error) or "Startup permission timed out."
        try:
            request.finished.emit(*result)
        except RuntimeError:
            pass
    threading.Thread(target=run, daemon=True).start()
    return request
