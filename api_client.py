import requests
from typing import List, Dict, Any

class SteamGridDBClient:
    BASE_URL = "https://www.steamgriddb.com/api/v2"
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.headers = {
            "Authorization": f"Bearer {api_key}"
        }
        
    def _get(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Helper to run GET requests to SteamGridDB API."""
        url = f"{self.BASE_URL}/{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            if response.status_code == 401:
                raise Exception("Unauthorized: Invalid SteamGridDB API Key.")
            response.raise_for_status()
            data = response.json()
            if not data.get("success", False):
                raise Exception(f"SteamGridDB API returned error: {data.get('errors')}")
            return data
        except requests.exceptions.RequestException as e:
            raise Exception(f"Network error contacting SteamGridDB: {e}")

    def search_game(self, term: str) -> List[Dict[str, Any]]:
        """
        Searches for a game by term and returns a list of results.
        Example result item: {'id': 1904, 'name': 'Dolphin Emulator', 'release_date': ...}
        """
        if not term.strip():
            return []
        data = self._get(f"search/autocomplete/{requests.utils.quote(term)}")
        return data.get("data", [])

    def get_grids(self, game_id: int) -> List[Dict[str, Any]]:
        """Fetches portrait cover art (typically 600x900)."""
        # We query for vertical grids first
        data = self._get(f"grids/game/{game_id}", params={"dimensions": "600x900"})
        # Fallback to general grids if 600x900 is empty
        res = data.get("data", [])
        if not res:
            data = self._get(f"grids/game/{game_id}")
            res = data.get("data", [])
        return res

    def get_landscape_grids(self, game_id: int) -> List[Dict[str, Any]]:
        """Fetches landscape cover art (typically 460x215 or 920x430)."""
        data = self._get(f"grids/game/{game_id}", params={"dimensions": "460x215,920x430"})
        res = data.get("data", [])
        if not res:
            # Fallback to general grids but filter out vertical ones
            data = self._get(f"grids/game/{game_id}")
            res = [r for r in data.get("data", []) if r.get("width", 1) > r.get("height", 0)]
        return res

    def get_heroes(self, game_id: int) -> List[Dict[str, Any]]:
        """Fetches background hero banners (typically 1920x620)."""
        data = self._get(f"heroes/game/{game_id}")
        return data.get("data", [])

    def get_logos(self, game_id: int) -> List[Dict[str, Any]]:
        """Fetches transparent logo assets."""
        data = self._get(f"logos/game/{game_id}")
        return data.get("data", [])

    def get_icons(self, game_id: int) -> List[Dict[str, Any]]:
        """Fetches square icon files."""
        data = self._get(f"icons/game/{game_id}")
        return data.get("data", [])
