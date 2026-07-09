# Steam Custom Artwork & Shortcut Manager

A powerful, native Python application for SteamOS and Linux that allows you to easily add non-Steam applications (like Flatpaks or standalone executables) into your Steam Library, while automatically scraping and applying beautiful grid artwork from SteamGridDB.

Unlike adding games manually, this tool correctly handles the 32-bit and 64-bit Steam ID math behind the scenes, guarantees full synchronization with Big Picture Mode, and manages Steam's memory watchdogs so your library shortcuts are never accidentally wiped on exit.

## Features
* **Auto-Discovery**: Scans your system (`.desktop` files) for installed applications and Flatpaks.
* **SteamGridDB Integration**: Built-in search interface to instantly find and apply custom artwork for all formats:
  * Portrait Grid Cover (600x900)
  * Hero Banner Background (1920x620)
  * Transparent Logo
  * Landscape Grid (460x215)
  * Square Icon
* **SteamOS Watchdog Safe**: Automatically forces Steam to drop its memory cache before writing to the binary `shortcuts.vdf` file, preventing Game Mode from overwriting your new shortcuts on restart.
* **Math-Accurate IDs**: Splits Flatpak targets and arguments identically to Steam's internal CRC32 hashing algorithm, ensuring Steam natively recognizes the generated artwork filenames using the signed/unsigned 32-bit AppID format.

## Prerequisites
* Python 3.10+
* A valid SteamGridDB API key (you will be prompted to enter this in the app, and it will be saved locally).

## Installation

Clone the repository and set up a Python virtual environment:

```bash
git clone https://github.com/m6jones/steamos-custom-artwork-manager.git
cd steamos-custom-artwork-manager
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Usage

Simply run the application from the terminal:

```bash
python3 main.py
```

1. Select an app from the "Scanned Apps" dropdown, or click "Manual Executable..." to browse your filesystem.
2. Enter your SteamGridDB API Key at the bottom (only required on first launch).
3. Click "Search SteamGridDB" next to any of the artwork slots to pick your custom images.
4. Click **Apply Shortcut & Artwork**. The app will safely close Steam if it is running, apply the changes, and you're good to go!

## Creating a Desktop Shortcut

If you want to add this app to your system's Application Launcher, you can create a `.desktop` file pointing to the virtual environment's python binary:

```ini
[Desktop Entry]
Name=Steam Custom Artwork Manager
Comment=Easily add non-Steam games and apply GridDB artwork
Exec=/path/to/repo/.venv/bin/python3 /path/to/repo/main.py
Icon=steam
Terminal=false
Type=Application
Categories=Utility;Game;
```
