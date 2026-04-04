import os
import io
import logging
from dotenv import load_dotenv as _load_dotenv

logger = logging.getLogger(__name__)

def load_dotenv_safe(dotenv_path: str = None, **kwargs):
    """
    Enhanced load_dotenv that strips null characters (\x00) from the .env file.
    Null characters cause ValueError: embedded null character when set to os.environ.
    """
    # Prefer .env in the root project directory (current working directory)
    path = dotenv_path or ".env"
    
    if os.path.exists(path):
        try:
            with open(path, "rb") as f:
                content = f.read()
            
            # Strip null characters
            clean_content = content.replace(b"\x00", b"")
            if clean_content != content:
                logger.warning(f"[SafeDotenv] Null characters stripped from {path}")
            
            # Use io.StringIO for load_dotenv
            stream = io.StringIO(clean_content.decode("utf-8", errors="replace"))
            return _load_dotenv(stream=stream, **kwargs)
        except Exception as e:
            logger.error(f"[SafeDotenv] Error processing {path}: {e}")
            # Fallback to standard loading if something goes wrong
            return _load_dotenv(dotenv_path=path, **kwargs)
    
    return _load_dotenv(dotenv_path=path, **kwargs)
