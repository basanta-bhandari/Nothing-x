# Nothing X

Desktop controls for Nothing and CMF audio devices on Linux and macOS, with a desktop widget and native COSMIC panel applet.

[Try the interactive demo](https://basanta.cc/nothing-x/) · [Download the latest release](https://github.com/basanta-bhandari/Nothing-x/releases/latest)

![Nothing X showing blue CMF Buds Pro 2, their full-size charging case, and device controls](screenshots/overview.png)

Nothing X is an unofficial desktop companion for the controls that usually live in the Nothing X mobile app. It began with CMF Buds Pro 2 on CachyOS/COSMIC and now has a shared interface for Nothing and CMF earbuds and headphones.

## What it does

- Change noise cancellation, transparency, equalizer, Ultra Bass, spatial audio, low-latency mode, and other device features when supported.
- View left, right, and case battery readings; case values stay visible as **Last reported** when the case is unavailable.
- Manage Bluetooth profiles, output volume and balance, microphones, and per-application routing through PipeWire.
- Save sound presets, choose from six themes, enable startup, and check for an update that matches the installed variant.
- Keep essential device controls and battery information in a desktop widget or COSMIC panel applet.

Feature availability depends on the connected model and its firmware. CMF Buds Pro 2 is the primary development device; other model profiles remain hardware-dependent.

## Demo and screenshots

The [browser demo](https://basanta.cc/nothing-x/) runs entirely with simulated device and audio data. It is useful for trying the navigation, controls, themes, and three example device profiles without installing anything.

| Device controls | Themes |
| --- | --- |
| ![Noise control, spatial audio, equalizer, Ultra Bass, and playback controls](screenshots/overview.png) | ![Six theme choices with their visual previews](screenshots/appearance.png) |

| Audio and routing | Headphone support |
| --- | --- |
| ![Output volume, balance, and Bluetooth profile choices](screenshots/audio.png) | ![Nothing Headphone (1) in the Porcelain theme](screenshots/headphones.png) |

| Applications | Microphone |
| --- | --- |
| ![Independent stream volume, mute, and output routing](screenshots/applications.png) | ![Input selection and microphone volume controls](screenshots/microphone.png) |

| Device preferences | Glacier theme |
| --- | --- |
| ![Codec, in-ear detection, desktop name, and locator controls](screenshots/settings.png) | ![The main screen in the Glacier theme](screenshots/glacier.png) |

<details>
<summary>All six themes</summary>

| Nothing | Porcelain | Verdant |
| --- | --- | --- |
| ![Nothing theme](screenshots/overview.png) | ![Porcelain theme](screenshots/porcelain.png) | ![Verdant theme](screenshots/verdant.png) |

| Glacier | Alloy | Ion |
| --- | --- | --- |
| ![Glacier theme](screenshots/glacier.png) | ![Alloy theme](screenshots/alloy.png) | ![Ion theme](screenshots/ion.png) |

</details>

The screenshots show the 0.5 desktop preview using simulated data. The 0.6 packages retain this shared layout.

## Why it exists

Nothing and CMF devices expose useful controls through their phone companion app, while Linux desktop users also need quick access to audio routing, Bluetooth profiles, and device status. Nothing X brings those workflows together in one focused desktop interface instead of splitting them across the phone and system settings.

## Choose a build

One Rust engine and one shared Python/Cython UI, packaged for three targets:

| Version | Platform | Desktop integration |
| --- | --- | --- |
| [Flatpak](https://github.com/basanta-bhandari/Nothing-x/releases/latest/download/NothingX-linux-x86_64.flatpak) | Fedora, Debian, Ubuntu, RHEL-family and other Flatpak-capable Linux distributions | Desktop widget, tray and PipeWire controls |
| [COSMIC applet](https://github.com/basanta-bhandari/Nothing-x/releases/latest/download/NothingX-rust-applet-linux-x86_64.tar.gz) | CachyOS/COSMIC and other COSMIC installations | Native panel applet, full settings and desktop widget |
| [macOS app](https://github.com/basanta-bhandari/Nothing-x/releases/latest) | macOS | Apple Silicon and Intel `.app`/`.dmg`, menu bar, CoreAudio and desktop widget |

Enable **Settings → App → Show desktop widget** in any version. The widget shares the app's device connection, battery data and theme. It stays available when the main window is hidden; quitting the app closes it.

The 0.6 packaging replaces the C++ and AppImage variants. Earlier release assets remain historical builds. Flatpak is distributed as a GitHub release bundle and is not yet on Flathub. Download the bundle, then install:

```bash
flatpak install --user ./NothingX-linux-x86_64.flatpak
flatpak run io.github.basanta_bhandari.NothingX
```

Flatpak repository installations update through your software manager or `flatpak update`. Standalone bundles need the newer bundle installed. Linux audio controls require PipeWire's PulseAudio service; system-wide WirePlumber policy controls appear only when available.

## Run from source

Install Python 3.11+, [Rust](https://www.rust-lang.org/tools/install) 1.85+ and a C compiler for optional Cython extensions. Pair your device in system Bluetooth settings first.

```bash
git clone https://github.com/basanta-bhandari/Nothing-x.git
cd Nothing-x
./setup.sh
./run.sh
./run.sh --demo
```

Source setup is a development workflow, not a fourth distribution. On Linux, paired-device listing outside Flatpak needs BlueZ's `bluetoothctl`.

Build and install the COSMIC applet with Rust 1.93+ and the libcosmic build dependencies:

```bash
.venv/bin/python tools/build_applets.py
.venv/bin/python install-cosmic.py
```

Add **Nothing X (Rust)** in COSMIC Settings → Desktop → Panel → Applets.

## How it is built

| Layer | Technology |
| --- | --- |
| Desktop interface | [Python](https://www.python.org/) 3.11+, [PySide6 / Qt Widgets](https://doc.qt.io/qtforpython-6/), and [Cython](https://cython.org/) |
| Device engine | Rust |
| Bluetooth | [BlueZ](https://www.bluez.org/), nonblocking RFCOMM sockets, and the Qt event loop |
| Audio | [PipeWire](https://pipewire.org/), its PulseAudio interface, and [WirePlumber](https://pipewire.pages.freedesktop.org/wireplumber/) |
| COSMIC applet | Rust and [libcosmic](https://github.com/pop-os/libcosmic) |
| Packaging | Cargo, Flatpak, Cython, and [PyInstaller](https://pyinstaller.org/) |

The window and panel applet share a local service. That service owns device communication and state while the UI renders controls and receives updates. This keeps a single device connection alive even when the full window and applet are both open.

The main engineering work focused on making a desktop-first experience feel coherent:

| Problem | Solution |
| --- | --- |
| Controls felt crowded | Grouped them into Device, Audio, and Settings, with a shorter panel experience. |
| Window and panel competed for connections | Moved connection ownership into one independent local service. |
| Audio changes made the UI refresh too often | Filtered self-generated events and coalesced frequent slider updates. |
| Case battery and widgets looked inconsistent | Cached reported readings, labelled stale values, and used shared switch and slider components. |

## Development and packaging

For Python-only UI iteration, use:

```bash
./setup.sh --no-cython
```

After editing compiled UI modules, rebuild them with:

```bash
.venv/bin/python setup.py build_ext --inplace
```

Rebuild the Rust engine with `.venv/bin/python tools/build_backends.py`.

Run the device-service and shared-UI regression checks:

```bash
NOTHINGX_BACKEND=rust .venv/bin/python tests/test_beta.py -v
NOTHINGX_BACKEND=rust .venv/bin/python tests/test_ui.py -v
.venv/bin/python tests/test_distributions.py -v
```

These checks use simulated transports and cover fragmented responses, request ordering, timeouts, reconnect queues, locator deadlines, and every model profile. They do not connect to physical devices. Hardware testing is still needed for firmware-specific behavior and macOS.

Key directories:

- [`nothingx/`](nothingx/) — UI, audio integration, and local service
- [`rust-engine/`](rust-engine/) — Rust engine
- [`cosmic-applet/`](cosmic-applet/) — COSMIC panel applet

For Flatpak, install `flatpak-builder` (or `org.flatpak.Builder`) and configure Flathub, then run:

```bash
.venv/bin/python packaging/build-flatpak.py
```

The build vendors locked Cargo dependencies and downloads pinned Python wheels before an offline sandbox build. Output: `dist/NothingX-linux-<architecture>.flatpak`.

On a Mac:

```bash
./setup.sh
.venv/bin/python -m pip install -r requirements-build.txt
.venv/bin/python packaging/build-macos.py
```

Outputs: `dist/macos/Nothing X.app` and an architecture-specific `.dmg`. The **Rust packages** GitHub Actions workflow also builds macOS packages and the Linux Flatpak. Mac packages use ad-hoc signing unless `NOTHINGX_CODESIGN_IDENTITY` is set; notarization and physical-device validation remain separate release checks.

Licensed under [MIT](LICENSE). See [NOTICE](NOTICE) for assets and dependencies. Nothing X is not affiliated with Nothing or CMF.
