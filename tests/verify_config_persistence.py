
import os
import sys
import logging
from dotenv import load_dotenv, find_dotenv

# Ensure backend module is in path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.join(project_root, 'backend'))

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.services.agent_service import agent_service

def verify_persistence():
    logger.info("--- Verifying Configuration Persistence ---")
    
    # 1. Simulate saving config
    test_config = {
        "base_url": "https://api.openai.com/v1",
        "api_key": "sk-test-persistence-key",
        "model": "gpt-4-turbo",
        "research_field": "Test Field",
        "verbose_llm": True
    }
    
    # Mocking what configure_agent does internally regarding .env
    try:
        from dotenv import set_key, find_dotenv
        env_file = find_dotenv()
        if not env_file:
            env_file = os.path.join(project_root, ".env")
            open(env_file, 'a').close()
        
        logger.info(f"Writing test config to {env_file}...")
        set_key(env_file, "AGENT_BASE_URL", test_config["base_url"])
        set_key(env_file, "AGENT_API_KEY", test_config["api_key"])
        set_key(env_file, "AGENT_MODEL", test_config["model"])
        set_key(env_file, "AGENT_RESEARCH_FIELD", test_config["research_field"])
        
    except Exception as e:
        logger.error(f"Failed to write .env: {e}")
        return False

    # 2. Simulate loading config (what main.py does)
    # We need to reload dotenv because os.environ might not be updated immediately by set_key in all environments
    load_dotenv(override=True)
    
    loaded_config = agent_service.load_config_from_env()
    
    if not loaded_config:
        logger.error("FAILED: load_config_from_env returned None")
        return False
        
    # 3. Verify values
    if loaded_config["base_url"] == test_config["base_url"] and \
       loaded_config["api_key"] == test_config["api_key"] and \
       loaded_config["model"] == test_config["model"]:
        logger.info("SUCCESS: Configuration persisted and loaded correctly.")
        logger.info(f"Loaded: {loaded_config}")
        return True
    else:
        logger.error("FAILED: Loaded config does not match saved config.")
        logger.error(f"Expected: {test_config}")
        logger.error(f"Got: {loaded_config}")
        return False

if __name__ == "__main__":
    verify_persistence()
