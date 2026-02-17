import unittest
import os
import json
import sys

# Add backend to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'backend')))

from app.services.agent_service import AgentService

class TestAgentPersistence(unittest.TestCase):
    def setUp(self):
        self.config_path = "agent_config.json"
        # Clean up before test
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

    def tearDown(self):
        # Clean up after test
        if os.path.exists(self.config_path):
            os.remove(self.config_path)

    def test_load_defaults(self):
        """Test that it loads defaults if no config file exists."""
        service = AgentService()
        self.assertEqual(service.name, "Agent")
        self.assertEqual(service.personality, "Professional and helpful")

    def test_save_and_load(self):
        """Test saving config and reloading it."""
        service = AgentService()
        
        # Save a new config via private method (simulating configure_agent logic)
        new_config = {
            "name": "TestBot",
            "personality": "Cheeky"
        }
        service._save_config(new_config)
        
        # Verify file exists
        self.assertTrue(os.path.exists(self.config_path))
        
        # Verify content
        with open(self.config_path, 'r') as f:
            data = json.load(f)
            self.assertEqual(data["name"], "TestBot")

        # Create NEW service instance (simulating restart)
        service2 = AgentService()
        self.assertEqual(service2.name, "TestBot")
        self.assertEqual(service2.personality, "Cheeky")

if __name__ == '__main__':
    unittest.main()
