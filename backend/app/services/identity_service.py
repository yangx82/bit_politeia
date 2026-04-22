import json
import logging
import os
import random
import string
import time
from datetime import UTC, datetime, timedelta

logger = logging.getLogger(__name__)

class IdentityManager:
    """
    Manages identity mapping between platform-specific IDs and unified global IDs.
    Supports pairing codes for account linking.
    """

    def __init__(self, data_dir: str = None):
        if data_dir is None:
            base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            self.data_dir = os.path.join(base_dir, "data")
        else:
            self.data_dir = data_dir

        os.makedirs(self.data_dir, exist_ok=True)
        self.map_file = os.path.join(self.data_dir, "identities.json")
        
        # Mapping: platform_id -> unified_id
        self.identity_map: dict[str, str] = {}
        # Pairing codes: code -> {unified_id: str, expires: float}
        self.pairing_codes: dict[str, dict] = {}
        
        self._load_map()

    def _load_map(self):
        if os.path.exists(self.map_file):
            try:
                with open(self.map_file, "r", encoding="utf-8") as f:
                    self.identity_map = json.load(f)
            except Exception as e:
                logger.error(f"Failed to load identity map: {e}")

    def _save_map(self):
        try:
            with open(self.map_file, "w", encoding="utf-8") as f:
                json.dump(self.identity_map, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save identity map: {e}")

    def resolve_unified_id(self, platform_user_id: str, channel: str) -> str:
        """
        Returns the unified_id for a given platform user.
        If no mapping exists, it currently treats the platform_user_id as the unified_id.
        """
        key = f"{channel}:{platform_user_id}"
        if key in self.identity_map:
            return self.identity_map[key]
        
        # Default: self-mapping until linked
        return platform_user_id

    def create_pairing_code(self, unified_id: str) -> str:
        """Generates a 6-digit pairing code valid for 20 minutes."""
        # Cleanup old codes
        now = time.time()
        self.pairing_codes = {k: v for k, v in self.pairing_codes.items() if v['expires'] > now}
        
        code = ''.join(random.choices(string.digits, k=6))
        self.pairing_codes[code] = {
            "unified_id": unified_id,
            "expires": now + (20 * 60) # 20 minutes
        }
        return code

    def bind_by_code(self, code: str, platform_user_id: str, channel: str) -> bool:
        """Links a new platform account to an existing unified_id via code."""
        now = time.time()
        if code not in self.pairing_codes:
            return False
        
        entry = self.pairing_codes[code]
        if entry['expires'] < now:
            del self.pairing_codes[code]
            return False
        
        unified_id = entry['unified_id']
        key = f"{channel}:{platform_user_id}"
        
        # Perform binding
        self.identity_map[key] = unified_id
        self._save_map()
        
        # Cleanup code
        del self.pairing_codes[code]
        logger.info(f"Successfully bound {key} to unified_id {unified_id}")
        return True

    def unbind(self, platform_user_id: str, channel: str) -> bool:
        """Removes a platform-specific mapping, isolating it back to its own ID."""
        key = f"{channel}:{platform_user_id}"
        if key in self.identity_map:
            del self.identity_map[key]
            self._save_map()
            logger.info(f"Unbound {key}")
            return True
        return False

# Global Singleton
identity_manager = IdentityManager()
