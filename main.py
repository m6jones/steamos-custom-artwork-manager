import os
import sys
import json
import shutil
import requests
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QListWidget, QListWidgetItem, QLineEdit, QPushButton, QLabel,
    QSplitter, QGroupBox, QFileDialog, QDialog, QScrollArea,
    QGridLayout, QComboBox, QMessageBox, QProgressDialog
)
from PySide6.QtCore import Qt, QThread, Signal, QSize
from PySide6.QtGui import QPixmap, QIcon

# Import custom modules
import vdf_handler
import scanner
from api_client import SteamGridDBClient

# Configuration file path
CONFIG_DIR = os.path.expanduser("~/.config/steamos-add-app-to-steam")
CONFIG_FILE = os.path.join(CONFIG_DIR, "config.json")

def load_config():
    """Loads settings from configuration file."""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {"api_key": "", "steam_user": ""}

def save_config(config):
    """Saves settings to configuration file."""
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(config, f, indent=4)
    except Exception:
        pass

# --- Background Worker Threads ---

class ImageDownloadWorker(QThread):
    """Downloads an image from a URL in the background."""
    finished = Signal(str, bytes) # asset_type, binary data
    failed = Signal(str, str)     # asset_type, error message
    
    def __init__(self, asset_type: str, url: str):
        super().__init__()
        self.asset_type = asset_type
        self.url = url
        
    def run(self):
        try:
            response = requests.get(self.url, timeout=10)
            response.raise_for_status()
            self.finished.emit(self.asset_type, response.content)
        except Exception as e:
            self.failed.emit(self.asset_type, str(e))

class AutocompleteWorker(QThread):
    """Queries SteamGridDB Autocomplete API in the background."""
    finished = Signal(list)
    failed = Signal(str)
    
    def __init__(self, client: SteamGridDBClient, term: str):
        super().__init__()
        self.client = client
        self.term = term
        
    def run(self):
        try:
            results = self.client.search_game(self.term)
            self.finished.emit(results)
        except Exception as e:
            self.failed.emit(str(e))

class FetchAssetsWorker(QThread):
    """Queries SteamGridDB asset endpoints in the background."""
    finished = Signal(str, list) # asset_type, results list
    failed = Signal(str, str)    # asset_type, error message
    
    def __init__(self, client: SteamGridDBClient, game_id: int, asset_type: str):
        super().__init__()
        self.client = client
        self.game_id = game_id
        self.asset_type = asset_type
        
    def run(self):
        try:
            if self.asset_type == "grid":
                res = self.client.get_grids(self.game_id)
            elif self.asset_type == "hero":
                res = self.client.get_heroes(self.game_id)
            elif self.asset_type == "logo":
                res = self.client.get_logos(self.game_id)
            elif self.asset_type == "icon":
                res = self.client.get_icons(self.game_id)
            elif self.asset_type == "landscape":
                res = self.client.get_landscape_grids(self.game_id)
            else:
                res = []
            self.finished.emit(self.asset_type, res)
        except Exception as e:
            self.failed.emit(self.asset_type, str(e))

# --- UI Helper Widgets ---

class ThumbnailButton(QPushButton):
    """A focusable button that downloads and previews a thumbnail image asynchronously."""
    clicked_url = Signal(str) # Emits full-resolution URL on trigger (click or Enter/Space)
    
    def __init__(self, full_url: str, thumb_url: str, display_size: QSize, parent=None):
        super().__init__(parent)
        self.full_url = full_url
        self.thumb_url = thumb_url
        self.display_size = display_size
        self.setFocusPolicy(Qt.StrongFocus)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(display_size)
        self.setText("Loading...")
        self.setStyleSheet("""
            QPushButton {
                border: 1px solid #373a40;
                background-color: #1a1b1e;
                border-radius: 4px;
                color: #e3e6e8;
            }
            QPushButton:focus {
                border: 2px solid #1c7ed6;
                background-color: #25262b;
            }
        """)
        
        # Start download
        self.worker = ImageDownloadWorker("thumb", self.thumb_url)
        self.worker.finished.connect(self.on_download_finished)
        self.worker.failed.connect(self.on_download_failed)
        self.worker.start()
        
        self.clicked.connect(self.on_clicked)
        
    def on_download_finished(self, _, data):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.setText("")
            scaled_pixmap = pixmap.scaled(self.display_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            self.setIcon(QIcon(scaled_pixmap))
            self.setIconSize(self.display_size)
        else:
            self.setText("Corrupt")
            
    def on_download_failed(self, _, err):
        self.setText("Err")
        
    def on_clicked(self):
        self.clicked_url.emit(self.full_url)

# --- Dialogs ---

class ArtworkSearchDialog(QDialog):
    """Dialog for searching game titles on SteamGridDB and picking an artwork candidate."""
    artwork_selected = Signal(str, str) # type, url or filepath
    
    def __init__(self, client: SteamGridDBClient, game_name: str, asset_type: str, parent=None):
        super().__init__(parent)
        self.client = client
        self.game_name = game_name
        self.asset_type = asset_type
        
        self.setWindowTitle(f"Search SteamGridDB - Select {asset_type.capitalize()}")
        self.resize(750, 550)
        self.setStyleSheet("""
            QDialog { background-color: #1a1b1e; color: #e3e6e8; }
            QLabel { color: #e3e6e8; }
            QLineEdit, QComboBox { background-color: #25262b; border: 1px solid #2c2e33; color: #e3e6e8; padding: 6px; border-radius: 4px; }
            QLineEdit:focus, QComboBox:focus { border: 1.5px solid #1c7ed6; }
            QPushButton { background-color: #2c2e33; border: 1px solid #373a40; color: #e3e6e8; padding: 6px 12px; border-radius: 4px; font-weight: bold; }
            QPushButton:hover { background-color: #373a40; }
            QPushButton:focus { border: 1.5px solid #1c7ed6; background-color: #373a40; }
        """)
        
        self.init_ui()
        
        # Start initial autocomplete search using current game name
        self.start_autocomplete(game_name)
        
    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # Search Bar
        search_layout = QHBoxLayout()
        self.search_input = QLineEdit(self.game_name)
        self.search_input.setPlaceholderText("Type game name to search...")
        self.search_input.returnPressed.connect(lambda: self.start_autocomplete(self.search_input.text()))
        search_layout.addWidget(self.search_input)
        
        self.search_btn = QPushButton("&Search")
        self.search_btn.clicked.connect(lambda: self.start_autocomplete(self.search_input.text()))
        search_layout.addWidget(self.search_btn)
        layout.addLayout(search_layout)
        
        # Matches selector
        match_layout = QHBoxLayout()
        match_layout.addWidget(QLabel("Match on SteamGridDB:"))
        self.match_combo = QComboBox()
        self.match_combo.currentIndexChanged.connect(self.on_match_changed)
        match_layout.addWidget(self.match_combo)
        layout.addLayout(match_layout)
        
        # Scroll Area for Thumbnails
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: 1px solid #2c2e33; background: #25262b; }")
        self.grid_widget = QWidget()
        self.grid_layout = QGridLayout(self.grid_widget)
        self.scroll_area.setWidget(self.grid_widget)
        layout.addWidget(self.scroll_area)
        
        # Status Label
        self.status_label = QLabel("Initializing search...")
        layout.addWidget(self.status_label)
        
        # Explicit tab orders
        self.setTabOrder(self.search_input, self.search_btn)
        self.setTabOrder(self.search_btn, self.match_combo)
        self.setTabOrder(self.match_combo, self.scroll_area)
        
        # Focus on input immediately
        self.search_input.setFocus()
        
    def start_autocomplete(self, query: str):
        if not query.strip():
            return
        self.status_label.setText("Searching titles...")
        self.match_combo.clear()
        
        self.autocomplete_worker = AutocompleteWorker(self.client, query)
        self.autocomplete_worker.finished.connect(self.on_autocomplete_finished)
        self.autocomplete_worker.failed.connect(self.on_autocomplete_failed)
        self.autocomplete_worker.start()
        
    def on_autocomplete_finished(self, results):
        if not results:
            self.status_label.setText("No games found on SteamGridDB matching search.")
            return
            
        self.status_label.setText(f"Found {len(results)} matches.")
        for r in results:
            self.match_combo.addItem(r["name"], r["id"])
            
        # Shift keyboard focus to the match selector combo box
        self.match_combo.setFocus()
            
    def on_autocomplete_failed(self, err):
        self.status_label.setText(f"Search failed: {err}")
        
    def on_match_changed(self, index):
        if index < 0:
            return
        game_id = self.match_combo.itemData(index)
        self.status_label.setText("Fetching graphics...")
        
        # Clear previous grid items
        for i in reversed(range(self.grid_layout.count())):
            widget = self.grid_layout.itemAt(i).widget()
            if widget:
                widget.deleteLater()
                
        self.assets_worker = FetchAssetsWorker(self.client, game_id, self.asset_type)
        self.assets_worker.finished.connect(self.on_assets_finished)
        self.assets_worker.failed.connect(self.on_assets_failed)
        self.assets_worker.start()
        
    def on_assets_finished(self, asset_type, assets):
        if not assets:
            self.status_label.setText(f"No {asset_type} assets found for this game.")
            return
            
        self.status_label.setText(f"Select a {asset_type} image using Tab/Arrow keys and press Space/Enter:")
        
        cols = 4
        size = QSize(130, 195) # Default Portrait Cover Grid (2:3)
        if self.asset_type == "hero":
            cols = 2
            size = QSize(300, 96) # Wide Banner
        elif self.asset_type == "logo":
            cols = 3
            size = QSize(200, 60) # Logo
        elif self.asset_type == "icon":
            cols = 5
            size = QSize(64, 64) # Icon
        elif self.asset_type == "landscape":
            cols = 2
            size = QSize(230, 107) # Landscape
            
        buttons = []
        for i, item in enumerate(assets):
            full_url = item["url"]
            thumb_url = item["thumb"]
            
            btn = ThumbnailButton(full_url, thumb_url, size, self)
            btn.clicked_url.connect(self.on_thumbnail_selected)
            buttons.append(btn)
            
            row = i // cols
            col = i % cols
            self.grid_layout.addWidget(btn, row, col)
            
        # Connect tab chains sequentially through generated buttons
        if buttons:
            self.setTabOrder(self.match_combo, buttons[0])
            for i in range(len(buttons) - 1):
                self.setTabOrder(buttons[i], buttons[i+1])
            # Focus on first loaded button automatically
            buttons[0].setFocus()
            
    def on_assets_failed(self, asset_type, err):
        self.status_label.setText(f"Failed to fetch {asset_type}s: {err}")
        
    def on_thumbnail_selected(self, full_url: str):
        self.artwork_selected.emit(self.asset_type, full_url)
        self.accept()

# --- Main Window ---

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("SteamOS Non-Steam App & Artwork Manager")
        self.resize(1000, 750)
        
        self.selected_assets = {
            "grid": None,  # URL or local filepath
            "hero": None,
            "logo": None,
            "icon": None,
            "landscape": None
        }
        
        self.scanned_apps = []
        self.selected_app = None
        self.config = load_config()
        self.api_client = None
        
        if self.config.get("api_key"):
            self.api_client = SteamGridDBClient(self.config["api_key"])
            
        self.init_ui()
        self.load_scanned_applications()
        self.load_steam_users()
        
    def init_ui(self):
        # Set Global Dark Theme Stylesheet with strong visual focus indicators
        self.setStyleSheet("""
            QMainWindow { background-color: #1a1b1e; color: #e3e6e8; font-family: 'Segoe UI', Arial, sans-serif; }
            QLabel { color: #e3e6e8; font-size: 13px; }
            QLineEdit, QComboBox { background-color: #25262b; border: 1px solid #2c2e33; color: #e3e6e8; padding: 8px; border-radius: 6px; font-size: 13px; }
            QLineEdit:focus, QComboBox:focus { border: 1.5px solid #1c7ed6; }
            QListWidget { background-color: #25262b; border: 1px solid #2c2e33; border-radius: 8px; padding: 5px; color: #e3e6e8; }
            QListWidget::item { padding: 8px; border-radius: 6px; margin-bottom: 2px; }
            QListWidget::item:hover { background-color: #2c2e33; }
            QListWidget::item:selected { background-color: #1c7ed6; color: #ffffff; }
            QListWidget:focus { border: 1.5px solid #1c7ed6; }
            QPushButton { background-color: #2c2e33; border: 1px solid #373a40; color: #e3e6e8; padding: 8px 16px; border-radius: 6px; font-weight: bold; font-size: 13px; }
            QPushButton:hover { background-color: #373a40; }
            QPushButton:pressed { background-color: #25262b; }
            QPushButton:focus { border: 1.5px solid #1c7ed6; background-color: #373a40; }
            QGroupBox { border: 1px solid #2c2e33; border-radius: 8px; margin-top: 15px; font-weight: bold; color: #909296; padding-top: 15px; }
            QScrollArea { border: none; background-color: transparent; }
        """)
        
        main_widget = QWidget()
        self.setCentralWidget(main_widget)
        
        main_layout = QVBoxLayout(main_widget)
        
        # --- Top Action/Settings Panel ---
        top_bar = QHBoxLayout()
        
        # User Selection
        top_bar.addWidget(QLabel("Steam Profile:"))
        self.user_combo = QComboBox()
        top_bar.addWidget(self.user_combo)
        
        # API Key
        top_bar.addWidget(QLabel("SteamGridDB API Key:"))
        self.api_key_input = QLineEdit(self.config.get("api_key", ""))
        self.api_key_input.setEchoMode(QLineEdit.Password)
        self.api_key_input.setPlaceholderText("Paste your key here...")
        top_bar.addWidget(self.api_key_input)
        
        self.save_api_btn = QPushButton("&Save Key")
        self.save_api_btn.clicked.connect(self.save_settings)
        top_bar.addWidget(self.save_api_btn)
        
        main_layout.addLayout(top_bar)
        
        # --- Center Body (Splitter) ---
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter, 1)
        
        # Left Panel (App Selection)
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        
        left_layout.addWidget(QLabel("Installed Desktop Programs:"))
        self.search_filter = QLineEdit()
        self.search_filter.setPlaceholderText("Filter applications...")
        self.search_filter.textChanged.connect(self.filter_applications)
        self.search_filter.returnPressed.connect(self.focus_app_list)
        left_layout.addWidget(self.search_filter)
        
        self.app_list = QListWidget()
        self.app_list.currentItemChanged.connect(self.on_app_selected)
        left_layout.addWidget(self.app_list)
        
        # App list actions
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("&Refresh List")
        self.refresh_btn.clicked.connect(self.load_scanned_applications)
        btn_layout.addWidget(self.refresh_btn)
        
        self.manual_btn = QPushButton("&Browse Program...")
        self.manual_btn.clicked.connect(self.on_manual_app_select)
        btn_layout.addWidget(self.manual_btn)
        left_layout.addLayout(btn_layout)
        
        splitter.addWidget(left_widget)
        
        # Right Panel (Application configuration & Artwork override)
        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        
        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(10, 0, 0, 0)
        
        # Group Box: Shortcut config
        shortcut_group = QGroupBox("Shortcut Configuration")
        shortcut_layout = QGridLayout(shortcut_group)
        
        shortcut_layout.addWidget(QLabel("App Name:"), 0, 0)
        self.name_input = QLineEdit()
        shortcut_layout.addWidget(self.name_input, 0, 1)
        
        shortcut_layout.addWidget(QLabel("Executable Path:"), 1, 0)
        self.exe_input = QLineEdit()
        shortcut_layout.addWidget(self.exe_input, 1, 1)
        
        shortcut_layout.addWidget(QLabel("Working Directory:"), 2, 0)
        self.dir_input = QLineEdit()
        shortcut_layout.addWidget(self.dir_input, 2, 1)
        
        shortcut_layout.addWidget(QLabel("Launch Arguments:"), 3, 0)
        self.args_input = QLineEdit()
        shortcut_layout.addWidget(self.args_input, 3, 1)
        
        right_layout.addWidget(shortcut_group)
        
        # Group Box: Custom Artwork overrides
        art_group = QGroupBox("Steam Library Custom Graphics overrides")
        art_layout = QGridLayout(art_group)
        
        # 1. Portrait Grid (2:3 Cover)
        art_layout.addWidget(QLabel("Portrait Grid Cover (600x900)"), 0, 0)
        self.cover_prev = QLabel("No Image Selected")
        self.cover_prev.setObjectName("coverPreview")
        self.cover_prev.setStyleSheet("border: 2px dashed #373a40; border-radius: 6px; background-color: #25262b;")
        self.cover_prev.setFixedSize(120, 180)
        self.cover_prev.setAlignment(Qt.AlignCenter)
        art_layout.addWidget(self.cover_prev, 1, 0)
        
        cover_btn_layout = QVBoxLayout()
        self.search_cover_btn = QPushButton("Search Steam&GridDB")
        self.search_cover_btn.clicked.connect(lambda: self.search_artwork_dialog("grid"))
        self.local_cover_btn = QPushButton("Local &File...")
        self.local_cover_btn.clicked.connect(lambda: self.browse_local_artwork("grid"))
        self.clear_cover_btn = QPushButton("&Clear")
        self.clear_cover_btn.clicked.connect(lambda: self.clear_selected_asset("grid"))
        cover_btn_layout.addWidget(self.search_cover_btn)
        cover_btn_layout.addWidget(self.local_cover_btn)
        cover_btn_layout.addWidget(self.clear_cover_btn)
        art_layout.addLayout(cover_btn_layout, 1, 1)
        
        # 2. Hero Banner (Wide background)
        art_layout.addWidget(QLabel("Hero Banner (1920x620)"), 2, 0)
        self.hero_prev = QLabel("No Image Selected")
        self.hero_prev.setObjectName("heroPreview")
        self.hero_prev.setStyleSheet("border: 2px dashed #373a40; border-radius: 6px; background-color: #25262b;")
        self.hero_prev.setFixedSize(300, 96)
        self.hero_prev.setAlignment(Qt.AlignCenter)
        art_layout.addWidget(self.hero_prev, 3, 0)
        
        hero_btn_layout = QVBoxLayout()
        self.search_hero_btn = QPushButton("Search Steam&GridDB")
        self.search_hero_btn.clicked.connect(lambda: self.search_artwork_dialog("hero"))
        self.local_hero_btn = QPushButton("Local &File...")
        self.local_hero_btn.clicked.connect(lambda: self.browse_local_artwork("hero"))
        self.clear_hero_btn = QPushButton("&Clear")
        self.clear_hero_btn.clicked.connect(lambda: self.clear_selected_asset("hero"))
        hero_btn_layout.addWidget(self.search_hero_btn)
        hero_btn_layout.addWidget(self.local_hero_btn)
        hero_btn_layout.addWidget(self.clear_hero_btn)
        art_layout.addLayout(hero_btn_layout, 3, 1)
        
        # 3. Logo (Overlay Title)
        art_layout.addWidget(QLabel("Title Logo Overlay"), 4, 0)
        self.logo_prev = QLabel("No Image Selected")
        self.logo_prev.setObjectName("logoPreview")
        self.logo_prev.setStyleSheet("border: 2px dashed #373a40; border-radius: 6px; background-color: #25262b;")
        self.logo_prev.setFixedSize(200, 60)
        self.logo_prev.setAlignment(Qt.AlignCenter)
        art_layout.addWidget(self.logo_prev, 5, 0)
        
        logo_btn_layout = QVBoxLayout()
        self.search_logo_btn = QPushButton("Search Steam&GridDB")
        self.search_logo_btn.clicked.connect(lambda: self.search_artwork_dialog("logo"))
        self.local_logo_btn = QPushButton("Local &File...")
        self.local_logo_btn.clicked.connect(lambda: self.browse_local_artwork("logo"))
        self.clear_logo_btn = QPushButton("&Clear")
        self.clear_logo_btn.clicked.connect(lambda: self.clear_selected_asset("logo"))
        logo_btn_layout.addWidget(self.search_logo_btn)
        logo_btn_layout.addWidget(self.local_logo_btn)
        logo_btn_layout.addWidget(self.clear_logo_btn)
        art_layout.addLayout(logo_btn_layout, 5, 1)
        
        # 4. Icon (Miniature)
        art_layout.addWidget(QLabel("Library Icon"), 6, 0)
        self.icon_prev = QLabel("No Icon Selected")
        self.icon_prev.setObjectName("iconPreview")
        self.icon_prev.setStyleSheet("border: 2px dashed #373a40; border-radius: 6px; background-color: #25262b;")
        self.icon_prev.setFixedSize(48, 48)
        self.icon_prev.setAlignment(Qt.AlignCenter)
        art_layout.addWidget(self.icon_prev, 7, 0)
        
        icon_btn_layout = QVBoxLayout()
        self.search_icon_btn = QPushButton("Search Steam&GridDB")
        self.search_icon_btn.clicked.connect(lambda: self.search_artwork_dialog("icon"))
        self.local_icon_btn = QPushButton("Local &File...")
        self.local_icon_btn.clicked.connect(lambda: self.browse_local_artwork("icon"))
        self.clear_icon_btn = QPushButton("&Clear")
        self.clear_icon_btn.clicked.connect(lambda: self.clear_selected_asset("icon"))
        icon_btn_layout.addWidget(self.search_icon_btn)
        icon_btn_layout.addWidget(self.local_icon_btn)
        icon_btn_layout.addWidget(self.clear_icon_btn)
        art_layout.addLayout(icon_btn_layout, 7, 1)
        
        # 5. Landscape Grid (Horizontal 460x215)
        art_layout.addWidget(QLabel("Landscape Grid (460x215)"), 8, 0)
        self.landscape_prev = QLabel("No Image Selected")
        self.landscape_prev.setObjectName("landscapePreview")
        self.landscape_prev.setStyleSheet("border: 2px dashed #373a40; border-radius: 6px; background-color: #25262b;")
        self.landscape_prev.setFixedSize(184, 86)
        self.landscape_prev.setAlignment(Qt.AlignCenter)
        art_layout.addWidget(self.landscape_prev, 9, 0)
        
        landscape_btn_layout = QVBoxLayout()
        self.search_landscape_btn = QPushButton("Search Steam&GridDB")
        self.search_landscape_btn.clicked.connect(lambda: self.search_artwork_dialog("landscape"))
        self.local_landscape_btn = QPushButton("Local &File...")
        self.local_landscape_btn.clicked.connect(lambda: self.browse_local_artwork("landscape"))
        self.clear_landscape_btn = QPushButton("&Clear")
        self.clear_landscape_btn.clicked.connect(lambda: self.clear_selected_asset("landscape"))
        landscape_btn_layout.addWidget(self.search_landscape_btn)
        landscape_btn_layout.addWidget(self.local_landscape_btn)
        landscape_btn_layout.addWidget(self.clear_landscape_btn)
        art_layout.addLayout(landscape_btn_layout, 9, 1)
        
        right_layout.addWidget(art_group)
        
        right_scroll.setWidget(right_widget)
        splitter.addWidget(right_scroll)
        
        # Set splitter proportions
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 7)
        
        # --- Bottom Commit Bar ---
        bottom_bar = QHBoxLayout()
        self.status_lbl = QLabel("Ready")
        bottom_bar.addWidget(self.status_lbl, 1)
        
        self.apply_btn = QPushButton("&Apply && Add to Steam")
        self.apply_btn.setObjectName("applyBtn")
        self.apply_btn.clicked.connect(self.on_apply_clicked)
        bottom_bar.addWidget(self.apply_btn)
        
        main_layout.addLayout(bottom_bar)
        
        # Set up explicit tab order sequence
        self.setup_tab_order()
        
        # Focus on the left search bar initially
        self.search_filter.setFocus()
        
    def setup_tab_order(self):
        """Sets a logical keyboard focus flow from left panels to config inputs to buttons."""
        self.setTabOrder(self.search_filter, self.app_list)
        self.setTabOrder(self.app_list, self.refresh_btn)
        self.setTabOrder(self.refresh_btn, self.manual_btn)
        
        self.setTabOrder(self.manual_btn, self.name_input)
        self.setTabOrder(self.name_input, self.exe_input)
        self.setTabOrder(self.exe_input, self.dir_input)
        self.setTabOrder(self.dir_input, self.args_input)
        
        # Cover Buttons
        self.setTabOrder(self.args_input, self.search_cover_btn)
        self.setTabOrder(self.search_cover_btn, self.local_cover_btn)
        self.setTabOrder(self.local_cover_btn, self.clear_cover_btn)
        
        # Hero Buttons
        self.setTabOrder(self.clear_cover_btn, self.search_hero_btn)
        self.setTabOrder(self.search_hero_btn, self.local_hero_btn)
        self.setTabOrder(self.local_hero_btn, self.clear_hero_btn)
        
        # Logo Buttons
        self.setTabOrder(self.clear_hero_btn, self.search_logo_btn)
        self.setTabOrder(self.search_logo_btn, self.local_logo_btn)
        self.setTabOrder(self.local_logo_btn, self.clear_logo_btn)
        
        # Icon Buttons
        self.setTabOrder(self.clear_logo_btn, self.search_icon_btn)
        self.setTabOrder(self.search_icon_btn, self.local_icon_btn)
        self.setTabOrder(self.local_icon_btn, self.clear_icon_btn)
        
        # Landscape Buttons
        self.setTabOrder(self.clear_icon_btn, self.search_landscape_btn)
        self.setTabOrder(self.search_landscape_btn, self.local_landscape_btn)
        self.setTabOrder(self.local_landscape_btn, self.clear_landscape_btn)
        
        # Footer Bar
        self.setTabOrder(self.clear_landscape_btn, self.user_combo)
        self.setTabOrder(self.user_combo, self.api_key_input)
        self.setTabOrder(self.api_key_input, self.save_api_btn)
        self.setTabOrder(self.save_api_btn, self.apply_btn)

    def focus_app_list(self):
        """Moves keyboard focus to list results if items are present, selecting the first row."""
        if self.app_list.count() > 0:
            self.app_list.setFocus()
            if not self.app_list.currentItem():
                self.app_list.setCurrentRow(0)

    def save_settings(self):
        api_key = self.api_key_input.text().strip()
        if api_key:
            self.config["api_key"] = api_key
            save_config(self.config)
            self.api_client = SteamGridDBClient(api_key)
            QMessageBox.information(self, "Settings Saved", "SteamGridDB API Key saved and loaded successfully!")
        else:
            QMessageBox.warning(self, "Invalid Key", "Please paste a valid SteamGridDB API key.")

    def load_steam_users(self):
        """Loads available Steam user profiles into the dropdown selector."""
        self.user_combo.clear()
        users = vdf_handler.find_steam_userdata_dirs()
        if not users:
            self.user_combo.addItem("No Users Found", None)
            self.status_lbl.setText("Warning: Could not locate Steam user directories!")
            return
            
        for u in users:
            self.user_combo.addItem(f"User: {u['id']}", u["path"])
            
    def load_scanned_applications(self):
        self.app_list.clear()
        self.scanned_apps = scanner.scan_installed_applications()
        for app in self.scanned_apps:
            item = QListWidgetItem(app["name"])
            item.setData(Qt.UserRole, app)
            self.app_list.addItem(item)
        self.status_lbl.setText(f"Scanned {len(self.scanned_apps)} installed applications.")
        
    def filter_applications(self, text):
        for i in range(self.app_list.count()):
            item = self.app_list.item(i)
            item.setHidden(text.lower() not in item.text().lower())
            
    def on_app_selected(self, current, previous):
        if not current:
            return
        app_data = current.data(Qt.UserRole)
        self.selected_app = app_data
        
        # Populate text fields
        self.name_input.setText(app_data["name"])
        self.exe_input.setText(app_data["exec"])
        self.args_input.setText(app_data.get("args", ""))
        
        # Calculate default directory
        exe_file = app_data["exec"].strip('"')
        self.dir_input.setText(os.path.dirname(exe_file))

        
        # Clear any previously selected artworks
        self.clear_selected_asset("grid")
        self.clear_selected_asset("hero")
        self.clear_selected_asset("logo")
        self.clear_selected_asset("icon")
        self.clear_selected_asset("landscape")
        
    def on_manual_app_select(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Executable File", "/usr/bin", "All Files (*)")
        if file_path:
            filename = os.path.basename(file_path)
            self.name_input.setText(filename.capitalize())
            self.exe_input.setText(file_path)
            self.dir_input.setText(os.path.dirname(file_path))
            self.args_input.clear()
            self.app_list.clearSelection()
            self.selected_app = None
            
    # --- Artwork Actions ---
    
    def search_artwork_dialog(self, asset_type):
        if not self.api_client:
            QMessageBox.critical(self, "No API Key", "Please enter and save a SteamGridDB API key in the top settings bar first!")
            return
            
        game_name = self.name_input.text().strip()
        if not game_name:
            QMessageBox.warning(self, "Empty Name", "Please specify an Application Name first to query artwork.")
            return
            
        dialog = ArtworkSearchDialog(self.api_client, game_name, asset_type, self)
        dialog.artwork_selected.connect(self.on_artwork_selected)
        dialog.exec()
        
    def browse_local_artwork(self, asset_type):
        file_path, _ = QFileDialog.getOpenFileName(
            self, f"Select Local {asset_type.capitalize()}", "",
            "Images (*.png *.jpg *.jpeg *.webp *.ico)"
        )
        if file_path:
            self.on_artwork_selected(asset_type, file_path)
            
    def on_artwork_selected(self, asset_type: str, source_path: str):
        """Callback when an artwork candidate (local file or remote URL) is selected."""
        self.selected_assets[asset_type] = source_path
        
        # Display Preview
        if source_path.startswith("http://") or source_path.startswith("https://"):
            self.status_lbl.setText(f"Loading preview for {asset_type}...")
            worker = ImageDownloadWorker(asset_type, source_path)
            worker.finished.connect(self.on_preview_downloaded)
            worker.failed.connect(self.on_preview_failed)
            setattr(self, f"{asset_type}_prev_worker", worker)
            worker.start()
        else:
            pixmap = QPixmap(source_path)
            self.update_preview_label(asset_type, pixmap)
            
    def on_preview_downloaded(self, asset_type, data):
        pixmap = QPixmap()
        if pixmap.loadFromData(data):
            self.update_preview_label(asset_type, pixmap)
            self.status_lbl.setText(f"Preview for {asset_type} loaded.")
        else:
            self.status_lbl.setText(f"Failed to load preview format for {asset_type}.")
            
    def on_preview_failed(self, asset_type, err):
        self.status_lbl.setText(f"Failed to download preview: {err}")
        
    def update_preview_label(self, asset_type, pixmap):
        label = None
        if asset_type == "grid":
            label = self.cover_prev
        elif asset_type == "hero":
            label = self.hero_prev
        elif asset_type == "logo":
            label = self.logo_prev
        elif asset_type == "icon":
            label = self.icon_prev
        elif asset_type == "landscape":
            label = self.landscape_prev
            
        if label and not pixmap.isNull():
            label.setPixmap(pixmap.scaled(label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            
    def clear_selected_asset(self, asset_type):
        self.selected_assets[asset_type] = None
        label = None
        txt = "No Image Selected"
        
        if asset_type == "grid":
            label = self.cover_prev
        elif asset_type == "hero":
            label = self.hero_prev
        elif asset_type == "logo":
            label = self.logo_prev
            txt = "No Image Selected"
        elif asset_type == "icon":
            label = self.icon_prev
            txt = "No Icon Selected"
        elif asset_type == "landscape":
            label = self.landscape_prev
            txt = "No Image Selected"
            
        if label:
            label.clear()
            label.setText(txt)
            
    # --- Apply Execution ---
    
    def on_apply_clicked(self):
        userdata_path = self.user_combo.currentData()
        if not userdata_path:
            QMessageBox.critical(self, "No User", "Please select a valid Steam user profile directory.")
            return
            
        app_name = self.name_input.text().strip()
        exe_path = self.exe_input.text().strip()
        start_dir = self.dir_input.text().strip()
        launch_opts = self.args_input.text().strip()
        
        if not app_name or not exe_path:
            QMessageBox.warning(self, "Missing Fields", "Application Name and Executable Path are required!")
            return
            
        # Warning if Steam is running
        if vdf_handler.is_steam_running():
            reply = QMessageBox.warning(
                self, "Steam is Running",
                "Steam is currently active. To prevent Steam from overwriting your shortcuts, "
                "it must be forcefully closed.\n\n"
                "Would you like this application to forcefully close Steam now?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                vdf_handler.kill_steam()
            else:
                return

                
        icon_path = ""
        
        # Add entry to shortcuts.vdf
        try:
            artwork_id = vdf_handler.add_non_steam_game(
                userdata_path, app_name, exe_path, start_dir, icon_path, launch_opts
            )
        except Exception as e:
            QMessageBox.critical(self, "Error Saving Shortcut", f"Could not save shortcut to shortcuts.vdf:\n{e}")
            return
            
        # Handle Artwork Downloads/Copies
        grid_folder = os.path.join(userdata_path, "config", "grid")
        os.makedirs(grid_folder, exist_ok=True)
        
        # Setup progress dialog
        progress = QProgressDialog("Applying custom artwork...", "Cancel", 0, 4, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.show()
        
        for step, (asset_type, source) in enumerate(self.selected_assets.items()):
            if progress.wasCanceled():
                break
                
            progress.setValue(step)
            if not source:
                continue
                
            ext = ".png"
            if source.lower().endswith(".jpg") or source.lower().endswith(".jpeg"):
                ext = ".jpg"
            elif source.lower().endswith(".ico"):
                ext = ".ico"
                
            filename = ""
            if asset_type == "grid":
                filename = f"{artwork_id}p{ext}"
            elif asset_type == "hero":
                filename = f"{artwork_id}_hero{ext}"
            elif asset_type == "logo":
                filename = f"{artwork_id}_logo{ext}"
            elif asset_type == "icon":
                filename = f"{artwork_id}_icon{ext}"
            elif asset_type == "landscape":
                filename = f"{artwork_id}{ext}"
                
            dest_path = os.path.join(grid_folder, filename)
            
            try:
                if source.startswith("http://") or source.startswith("https://"):
                    res = requests.get(source, timeout=15)
                    res.raise_for_status()
                    with open(dest_path, "wb") as f:
                        f.write(res.content)
                else:
                    shutil.copy2(source, dest_path)
                    
                if asset_type == "icon":
                    vdf_handler.add_non_steam_game(
                        userdata_path, app_name, exe_path, start_dir, dest_path, launch_opts
                    )
            except Exception as e:
                QMessageBox.warning(self, "Artwork Copy Failed", f"Failed to apply {asset_type} graphic:\n{e}")
                
        progress.setValue(4)
        
        QMessageBox.information(
            self, "Success",
            f"Successfully added '{app_name}' to Steam!\n\n"
            "If Steam was open, please restart Steam to see the shortcut and custom artwork."
        )

def main():
    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_UseHighDpiPixmaps)
    
    window = MainWindow()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
