import argparse
import json
import os
from pathlib import Path
import re
import shutil
import time


LEGACY_DESKTOPS = (
    "io.github.basanta_bhandari.NothingX.cpp.manual.desktop",
    "io.github.basanta_bhandari.NothingX.cpp.applet.desktop",
    "io.github.basanta_bhandari.NothingX.rust.manual.desktop",
    "io.github.basanta_bhandari.NothingXApplet.Cpp.desktop",
)
LEGACY_COMMANDS = ("nothingx-cpp", "nothingx-cpp-applet", "nothingx-rust", "cosmic-applet-nothingx-cpp")
OLD_APPLET = "io.github.basanta_bhandari.NothingXApplet.Cpp"
NEW_APPLET = "io.github.basanta_bhandari.NothingXApplet.Rust"


def migrate(prefix, config):
    prefix, config = Path(prefix), Path(config)
    installed = prefix / "share/nothingx-rust-applet"
    metadata = json.loads((installed / "nothingx/assets/build.json").read_text())
    if metadata.get("backend") != "rust" or metadata.get("distribution") != "applet" or not (prefix / "bin/cosmic-applet-nothingx-rust").is_file():
        raise RuntimeError("Install the Rust applet before migrating legacy launchers.")
    backup = prefix / "share/nothingx-migration-backups" / time.strftime("%Y%m%d-%H%M%S")
    changed = []

    def preserve(path, relative):
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)

    for path in (config / "cosmic").glob("com.system76.CosmicPanel.*/v1/plugins_*"):
        original = path.read_text()
        if OLD_APPLET not in original:
            continue
        if NEW_APPLET in original:
            updated = re.sub(r'^\s*"' + re.escape(OLD_APPLET) + r'",?\s*\n', "", original, flags=re.MULTILINE)
        else:
            updated = original.replace('"' + OLD_APPLET + '"', '"' + NEW_APPLET + '"')
        preserve(path, Path("config") / path.relative_to(config))
        if path.read_text() != original:
            raise RuntimeError("The panel configuration changed during migration. Run the installer again.")
        temporary = path.with_name(path.name + ".nothingx-new")
        temporary.write_text(updated)
        temporary.replace(path)
        changed.append(str(path))
    for name in LEGACY_DESKTOPS:
        path = prefix / "share/applications" / name
        if path.is_file():
            preserve(path, Path("applications") / name)
            path.unlink()
            changed.append(str(path))
    for name in LEGACY_COMMANDS:
        path = prefix / "bin" / name
        if path.is_file():
            preserve(path, Path("bin") / name)
            path.unlink()
            changed.append(str(path))
    if changed:
        print("Retired legacy launchers and panel entries. Backups:", backup)
    return changed


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local")
    parser.add_argument("--config", type=Path, default=Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")))
    args = parser.parse_args()
    migrate(args.prefix, args.config)
