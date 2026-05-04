import json
import os
from pathlib import Path

DEFAULT_CONFIG_PATH = Path("system_config.json")

class ConfigManager:
    def __init__(self, config_path=DEFAULT_CONFIG_PATH):
        self.config_path = config_path
        self.config = self.load_config()

    def load_config(self):
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                return json.load(f)
        return {
            "setup_complete": False,
            "instance_id": None,
            "paths": {
                "local_trivia": "./data/trivia",
                "assets": "./data/assets"
            },
            "settings": {
                "trivia_source": "local", # "local" or "cloud"
                "cloud_subscription_active": False
            },
            "license_status": {
                "key": None,
                "master_admin_email": None,
                "total_seats_allowed": 5,
                "active_seats": []
            },
            "users": []
        }

    def save_config(self, new_config=None):
        if new_config:
            self.config.update(new_config)
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=4)
        return self.config

    def is_setup_required(self):
        return not self.config.get("setup_complete", False)
