# Guide: Python Application Development on SteamOS

This document details the best practices, packaging models, GUI considerations, and environment details for building and deploying Python applications on **SteamOS** (specifically tailored for the Steam Deck).

---

## 1. Understanding the SteamOS Environment

SteamOS uses an **immutable root filesystem** (A/B partition layout) to ensure stability and seamless updates.

*   **Immutable Root:** System directories like `/usr`, `/bin`, `/lib`, and `/etc` (partially) are read-only.
*   **Wiped on Updates:** Disabling read-only mode (`steamos-readonly disable`) to install packages via `pacman` or global `pip` is highly discouraged; any modifications to root partitions will be wiped out when SteamOS updates.
*   **Persistent Directories:** The user home directory (`/home/deck`), `/var`, and `/tmp` are writeable and persist across system updates.

---

## 2. Development Setup

Because SteamOS does not include compilers, headers, or development tools in the base image, you should use isolation containers to build your app.

### Using Distrobox
Distrobox is built into SteamOS and allows you to run mutable Linux containers (Arch, Fedora, Ubuntu) that share the host system's graphical display, sockets, and home folder.
```bash
# Create an Arch Linux container
distrobox create --name dev-box --image archlinux:latest

# Enter the container
distrobox enter dev-box

# Inside the container, you can use package managers and build tools normally
sudo pacman -Syu python-pip python-virtualenv base-devel git
```

### Project Workspace Isolation
Always use virtual environments inside your project folders to isolate package dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 3. Deployment Models for SteamOS

There are three primary ways to distribute a Python app to SteamOS users.

### Model A: Persistent Folder + Bash Launcher (Recommended for Utilities)
For local utilities or setup tools, package your code inside a folder placed in `/home/deck/` (e.g., `~/Applications/my-app/`) and execute it via a shell script wrapper.

#### Directory Layout
```text
~/Applications/my-app/
├── .venv/            # Local virtual environment containing python libraries
├── main.py           # Application entry point
├── run.sh            # Bash wrapper script
└── icon.png          # App icon
```

#### Bash Launcher (`run.sh`)
Your launcher must resolve absolute paths dynamically, as Steam launches shortcuts from arbitrary working directories.
```bash
#!/bin/bash
# Get the absolute directory where the script resides
APP_DIR="$(dirname "$(readlink -f "$0")")"

# Activate the local virtual environment
source "$APP_DIR/.venv/bin/activate"

# Run the python app in the background or foreground
python "$APP_DIR/main.py" "$@"
```
*Make sure to run `chmod +x run.sh`.*

#### Adding to Steam
1. Open Steam in **Desktop Mode**.
2. Click **Add a Game** > **Add a Non-Steam Game...**.
3. Browse and select `run.sh`.
4. In the shortcut properties, rename it to your App Name and set the working directory to the parent folder.

---

### Model B: Flatpak Sandbox (Recommended for Desktop Distribution)
Flatpak is SteamOS's official sandboxed application distribution format. It is integrated directly into the **Discover Software Center**.

*   **Immune to System Updates:** Flatpaks carry their own runtime dependencies and are stored entirely within the persistent home directory (`~/.var/app/` and `~/.local/share/flatpak/`).
*   **Manifest Configuration:** You write a YAML manifest (`org.example.MyApp.yml`) utilizing a `simple` build module to invoke `pip` and compile dependencies into the `/app` prefix.

#### Sample Flatpak Manifest Module
```yaml
id: org.example.MyApp
runtime: org.kde.Platform
runtime-version: '6.6' # Uses KDE Plasma 6 runtime (Qt standard)
sdk: org.kde.Sdk
command: start-app.sh
modules:
  - name: python-dependencies
    buildsystem: simple
    build-commands:
      - pip3 install --prefix=/app -r requirements.txt
  - name: my-app
    buildsystem: simple
    build-commands:
      - install -D main.py /app/bin/main.py
      - install -D start-app.sh /app/bin/start-app.sh
    sources:
      - type: dir
        path: .
```

> [!TIP]
> If your application needs to modify Steam configuration (such as adding shortcuts to `shortcuts.vdf` or custom artwork to `grid/`), you must request host filesystem permissions in your Flatpak manifest:
> `--filesystem=host` or `--filesystem=~/.steam`

---

### Model C: Decky Loader Plugins (Best for Game Mode Integration)
If your app should integrate directly into the Steam Deck's Quick Access Menu (QAM), you should build it as a **Decky Loader plugin**.

*   **Architecture:** Decky plugins consist of:
    1.  **Frontend (React/TypeScript):** Rendered inside Steam's Chromium-based Game Mode UI.
    2.  **Backend (Python sidecar):** A `main.py` daemon running in the background with root privileges, handling system scripts, VDF editing, or filesystem tasks.
*   **Communication:** Frontend UI elements communicate with the Python backend via JSON-RPC or REST calls exposed by the Decky Loader API.

---

## 4. GUI Framework Selection for SteamOS

KDE Plasma is the desktop shell of SteamOS, making Qt-based frameworks the best native choice.

1.  **PySide6 / PyQt6 (Recommended):**
    *   **Native Integration:** Qt matches the look and feel of the KDE Plasma Desktop.
    *   **Performance:** Excellent UI rendering performance, supports hardware acceleration, and has rich widgets.
    *   **Flatpak Support:** Standard KDE SDKs contain Python-Qt bindings out of the box, drastically reducing Flatpak bundle sizes.
2.  **Tkinter:**
    *   **Pros:** Included in the standard library.
    *   **Cons:** Visual layout looks dated; scaling on the 1280x800 Steam Deck screen in Game Mode can cause clipping and font display issues.
3.  **Local Web Server + WebView (Flask/FastAPI + PyWebView):**
    *   **Pros:** Allows building modern UI using standard HTML/CSS/JS (React, Vue, or Tailwind).
    *   **Cons:** Higher memory footprint due to embedded browser instances (WebKit/Chromium).

---

## 5. User Interface & Input Adaptations

Developing for SteamOS means your app must work well on a hand-held screen with controller inputs.

### Display Scaling
The Steam Deck screen is **1280 × 800** (16:10 aspect ratio, 7-inch size).
*   **Design for touch:** Buttons should be at least 44x44 pixels to be easily clickable via the touchscreen.
*   **Qt High-DPI Scaling:** Configure high-DPI scaling flags in your Python application before initializing the Qt Application instance:
    ```python
    import os
    import sys
    from PySide6.QtWidgets import QApplication
    
    # Enable High DPI Scaling
    os.environ["QT_AUTO_SCREEN_SCALE_FACTOR"] = "1"
    app = QApplication(sys.argv)
    ```

### Controller Navigation
When running in Game Mode (Big Picture Mode), users navigate using the D-Pad or Joysticks.
*   Ensure that all GUI controls support keyboard focus navigation (e.g., Tab order). In Game Mode, Steam translates controller presses into standard keyboard navigation keys (arrows, Tab, Enter).
*   Test that UI text is legible from a distance of 2–3 feet (font sizes should be 12pt or larger).
