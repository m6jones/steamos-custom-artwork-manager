import os
import re
import shlex
import shutil

def split_command(exec_cmd: str):
    """
    Splits a full command line string into (binary_path, arguments).
    Resolves the binary path to an absolute path if possible.
    """
    exec_cmd = exec_cmd.strip()
    if not exec_cmd:
        return "", ""
        
    try:
        parts = shlex.split(exec_cmd)
    except Exception:
        parts = exec_cmd.split()
        
    if not parts:
        return "", ""
        
    binary = parts[0]
    args = shlex.join(parts[1:]) if len(parts) > 1 else ""
    
    # Resolve relative binary to absolute path
    if not os.path.isabs(binary):
        abs_binary = shutil.which(binary)
        if abs_binary:
            binary = abs_binary
            
    return binary, args

def parse_desktop_file(filepath: str):
    """
    Parses a Linux .desktop file to extract Name, Exec, and Icon keys under [Desktop Entry].
    """
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            lines = f.readlines()
    except Exception:
        return None
        
    in_desktop_entry = False
    name = None
    exec_cmd = None
    icon = None
    app_type = None
    
    for line in lines:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
            
        # Section detection
        if line.startswith("[") and line.endswith("]"):
            if line.lower() == "[desktop entry]":
                in_desktop_entry = True
            else:
                in_desktop_entry = False
            continue
            
        if in_desktop_entry:
            if "=" in line:
                parts = line.split("=", 1)
                key = parts[0].strip()
                value = parts[1].strip()
                
                # Check for localized names (e.g. Name[en_US]), we prefer base Name
                if key == "Name":
                    name = value
                elif key == "Exec":
                    # Remove %f, %u, etc. parameters
                    exec_cmd = re.sub(r'%[fFuUdiDnNoOkKvV]', '', value).strip()
                elif key == "Icon":
                    icon = value
                elif key == "Type":
                    app_type = value

    # We filter for Application type or default
    if name and exec_cmd and (app_type == "Application" or app_type is None):
        binary_path, arguments = split_command(exec_cmd)
        is_flatpak = "flatpak run" in exec_cmd or "flatpak" in filepath.lower()
        return {
            "name": name,
            "exec": binary_path,
            "args": arguments,
            "icon_name": icon or "",
            "is_flatpak": is_flatpak,
            "desktop_file": filepath
        }
        
    return None


def scan_installed_applications():
    """
    Scans system and user paths for desktop launchers.
    Returns a sorted list of unique application dictionaries.
    """
    dirs = [
        "/usr/share/applications",
        os.path.expanduser("~/.local/share/applications"),
        "/var/lib/flatpak/exports/share/applications",
        os.path.expanduser("~/.local/share/flatpak/exports/share/applications")
    ]
    
    apps = {}
    for d in dirs:
        if os.path.exists(d) and os.path.isdir(d):
            for file in os.listdir(d):
                if file.endswith(".desktop"):
                    full_path = os.path.join(d, file)
                    app_info = parse_desktop_file(full_path)
                    if app_info:
                        # De-duplicate by name, prefering user-specific or newer files
                        app_name = app_info["name"]
                        apps[app_name] = app_info
                        
    sorted_apps = sorted(apps.values(), key=lambda x: x["name"].lower())
    return sorted_apps

if __name__ == "__main__":
    scanned = scan_installed_applications()
    print(f"Scanned {len(scanned)} applications.")
    if scanned:
        print("First 3 applications parsed:")
        for a in scanned[:3]:
            print(a)
