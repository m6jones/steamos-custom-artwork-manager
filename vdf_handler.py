import os
import shutil
import binascii
import psutil
import vdf

def calculate_shortcut_ids(exe_path: str, app_name: str):
    """
    Computes the 32-bit shortcut AppID and the 64-bit Launch ID (for artwork filenames).
    
    The 32-bit AppID is a CRC32 of: '"<exe_path>"<app_name>' bitwise OR'd with 0x80000000.
    The 64-bit Launch ID is: (short_appid << 32) | 0x02000000.
    """
    # Wrap executable in quotes if not already present
    formatted_exe = f'"{exe_path}"' if not (exe_path.startswith('"') and exe_path.endswith('"')) else exe_path
    
    combined_string = formatted_exe + app_name
    crc = binascii.crc32(combined_string.encode('utf-8')) & 0xffffffff
    
    # 32-bit AppID (unsigned)
    short_appid_unsigned = crc | 0x80000000
    
    # Convert to signed 32-bit integer for shortcuts.vdf parser ('i' pack format)
    short_appid_signed = short_appid_unsigned - 0x100000000 if short_appid_unsigned >= 0x80000000 else short_appid_unsigned
    
    # 64-bit Launch/Artwork ID (must use the unsigned value to shift correctly)
    long_appid = (short_appid_unsigned << 32) | 0x02000000
    
    return short_appid_signed, long_appid


def is_steam_running() -> bool:
    """Checks if any Steam client process is currently running."""
    for proc in psutil.process_iter(['name']):
        try:
            name = proc.info['name']
            if name and ('steam' in name.lower() or name.lower() == 'steamwebhelper'):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass
    return False

def kill_steam() -> bool:
    """Forcefully terminates all Steam processes to prevent them from overwriting config files."""
    steam_procs = []
    for proc in psutil.process_iter(['name', 'pid']):
        try:
            name = proc.info['name']
            if name and ('steam' in name.lower() or name.lower() == 'steamwebhelper'):
                steam_procs.append(proc)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
            
    if not steam_procs:
        return False
        
    for proc in steam_procs:
        try:
            proc.kill()  # Sends SIGKILL
        except Exception:
            pass
            
    # Wait up to 3 seconds for processes to terminate
    psutil.wait_procs(steam_procs, timeout=3)
    return True


def find_steam_userdata_dirs():
    """
    Locates Steam userdata directories.
    Returns a list of dicts with:
      'path': path to the userdata/<userID>/ folder
      'id': the user ID
    """
    possible_paths = [
        os.path.expanduser("~/.steam/root/userdata"),
        os.path.expanduser("~/.steam/steam/userdata"),
        os.path.expanduser("~/.local/share/Steam/userdata"),
    ]
    
    userdata_dirs = []
    for base in possible_paths:
        if os.path.exists(base) and os.path.isdir(base):
            for entry in os.listdir(base):
                full_path = os.path.join(base, entry)
                if os.path.isdir(full_path) and entry.isdigit():
                    userdata_dirs.append({
                        "path": full_path,
                        "id": entry
                    })
            break # Stop at the first directory that exists
            
    return userdata_dirs

def add_non_steam_game(
    userdata_path: str,
    app_name: str,
    exe_path: str,
    start_dir: str = "",
    icon_path: str = "",
    launch_options: str = ""
) -> int:
    """
    Adds or updates a non-Steam game entry in shortcuts.vdf.
    
    Returns the 64-bit Launch ID of the game.
    """
    config_dir = os.path.join(userdata_path, "config")
    os.makedirs(config_dir, exist_ok=True)
    vdf_path = os.path.join(config_dir, "shortcuts.vdf")
    
    # Calculate IDs
    short_appid, long_appid = calculate_shortcut_ids(exe_path, app_name)
    
    # Convert unsigned short AppID to a signed 32-bit int if needed by VDF format (some parsers write it as signed)
    # The binary writer of vdf library handles unsigned int values fine.
    
    # Load existing shortcuts
    shortcuts_data = {"shortcuts": {}}
    if os.path.exists(vdf_path) and os.path.getsize(vdf_path) > 0:
        # Create a backup before making edits
        backup_path = vdf_path + ".bak"
        shutil.copy2(vdf_path, backup_path)
        
        try:
            with open(vdf_path, "rb") as f:
                shortcuts_data = vdf.binary_load(f)
        except Exception as e:
            print(f"Error loading binary VDF: {e}. Reinitializing shortcuts.")
            shortcuts_data = {"shortcuts": {}}
            
    # Ensure standard shortcuts key structure
    if "shortcuts" not in shortcuts_data:
        shortcuts_data["shortcuts"] = {}
        
    # Check if this appid already exists, if so we update it; otherwise append
    shortcuts = shortcuts_data["shortcuts"]
    existing_index = None
    
    for idx, shortcut in shortcuts.items():
        # AppID matching
        if shortcut.get("appid") == short_appid or shortcut.get("AppName") == app_name:
            existing_index = idx
            break
            
    # Prepare entry
    # Executable quotes handling
    formatted_exe = f'"{exe_path}"' if not (exe_path.startswith('"') and exe_path.endswith('"')) else exe_path
    
    if not start_dir:
        # Default working directory to exe parent
        raw_exe = exe_path.strip('"')
        start_dir = os.path.dirname(raw_exe)
    formatted_dir = f'"{start_dir}"' if not (start_dir.startswith('"') and start_dir.endswith('"')) else start_dir
    
    new_entry = {
        "appid": short_appid,
        "AppName": app_name,
        "exe": formatted_exe,
        "StartDir": formatted_dir,
        "icon": icon_path,
        "LaunchOptions": launch_options,
        "IsShortcut": 1,
        "AllowDesktopConfig": 1,
        "AllowOverlay": 1,
        "OpenVR": 0,
        "Devkit": 0,
        "tags": {}
    }
    
    if existing_index is not None:
        shortcuts[existing_index] = new_entry
        print(f"Updated existing shortcut for '{app_name}' (ID: {long_appid})")
    else:
        # Find next free index string (VDF uses sequential string indices like "0", "1", "2"...)
        indices = [int(k) for k in shortcuts.keys() if k.isdigit()]
        next_idx = str(max(indices) + 1) if indices else "0"
        shortcuts[next_idx] = new_entry
        print(f"Added new shortcut for '{app_name}' at index {next_idx} (ID: {long_appid})")
        
    # Write back binary VDF
    with open(vdf_path, "wb") as f:
        vdf.binary_dump(shortcuts_data, f)
        
    return short_appid & 0xffffffff
