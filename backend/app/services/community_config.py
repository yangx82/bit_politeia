import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

RULES_FILE_PATH = os.path.join(os.path.dirname(__file__), "../agent/protocol/community_rules.json")


class CommunityConfig:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.load_rules()
        return cls._instance

    def load_rules(self):
        """Load rules from JSON file."""
        try:
            with open(RULES_FILE_PATH, encoding="utf-8") as f:
                self.rules = json.load(f)
            logger.info("Community Config Loaded Successfully")
        except Exception as e:
            logger.error(f"Failed to load community rules: {e}")
            # Fallback defaults
            self.rules = {"organization": {"group_size": {"max": 10, "min": 3}, "max_levels": 11}}

    def save_rules(self):
        """Save current rules to JSON file."""
        try:
            with open(RULES_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(self.rules, f, indent=4)
            logger.info("Community Config Saved Successfully")
        except Exception as e:
            logger.error(f"Failed to save community rules: {e}")

    def get_group_capacity(self) -> int:
        return self.rules.get("organization", {}).get("group_size", {}).get("max", 10)

    def get_max_levels(self) -> int:
        return self.rules.get("organization", {}).get("max_levels", 11)

    def update_parameter(self, path: str, value: Any) -> bool:
        """
        Update a parameter using dot notation.
        e.g., 'organization.group_size.max'
        """
        keys = path.split(".")
        current = self.rules

        try:
            for key in keys[:-1]:
                if key not in current:
                    current[key] = {}
                current = current[key]

            # Simple validation for specific critical keys could go here
            current[keys[-1]] = value
            self.save_rules()
            logger.info(f"Parameter {path} updated to {value}")
            return True
        except Exception as e:
            logger.error(f"Failed to update parameter {path}: {e}")
            return False

    def get_all_rules_text(self) -> str:
        return json.dumps(self.rules, indent=2)


community_config = CommunityConfig()
