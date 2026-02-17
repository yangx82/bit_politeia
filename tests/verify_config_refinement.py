import unittest
import os
import json
import sys
from unittest.mock import patch, MagicMock

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.services.agent_service import AgentService

class TestAgentConfigRefinement(unittest.TestCase):
    def setUp(self):
        self.config_path = "agent_config.json"
        # Clean up
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

    def tearDown(self):
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

    def test_exclude_sensitive_keys(self):
        """Test that sensitive keys are NOT saved to json."""
        service = AgentService()
        
        config = {
            "name": "PublicAgent",
            "api_key": "secret_key",
            "base_url": "https://api.openai.com",
            "personality": "Friendly"
        }
        
        service._save_config(config)
        
        with open(self.config_path, 'r') as f:
            saved = json.load(f)
            self.assertEqual(saved["name"], "PublicAgent")
            self.assertEqual(saved["personality"], "Friendly")
            self.assertNotIn("api_key", saved)
            self.assertNotIn("base_url", saved)

    @patch.dict(os.environ, {"AGENT_NAME": "EnvAgent", "AGENT_PERSONALITY": "EnvPersonality"})
    def test_env_override(self):
        """Test that ENV variables override JSON config."""
        # Create a conflicting JSON config first
        with open(self.config_path, 'w') as f:
            json.dump({"name": "JsonAgent", "personality": "JsonPersonality"}, f)
            
        service = AgentService()
        self.assertEqual(service.name, "EnvAgent")
        self.assertEqual(service.personality, "EnvPersonality")

if __name__ == '__main__':
    unittest.main()
