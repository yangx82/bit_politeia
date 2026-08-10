import sys
import site

user_site = site.getusersitepackages()
if user_site and user_site not in sys.path:
    sys.path.insert(0, user_site)

import io
import logging
import os
from pathlib import Path

try:
    from dotenv import find_dotenv
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    def find_dotenv(): return ""
    def _load_dotenv(*args, **kwargs): return False

logger = logging.getLogger(__name__)


def load_dotenv_safe(dotenv_path: str = None, **kwargs):
    """
    Enhanced load_dotenv that strips null characters (\x00) from the .env file.
    Null characters cause ValueError: embedded null character when set to os.environ.
    Uses find_dotenv() to support parent-directory search if no path specified.
    """
    # Use find_dotenv() to mirror standard load_dotenv behavior if no path given
    path = dotenv_path or find_dotenv()
    
    # If find_dotenv() failed, try to find .env in project root directory
    if not path:
        # From backend/app/utils/ go up 3 levels to project root
        current_file = Path(__file__).resolve()
        project_root = current_file.parent.parent.parent.parent
        env_file = project_root / '.env'
        if env_file.exists():
            path = str(env_file)
            logger.info(f"[SafeDotenv] Found .env at project root: {path}")

    if path and os.path.exists(path):
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

    # If find_dotenv() failed or file doesn't exist, fallback to standard load_dotenv
    return _load_dotenv(dotenv_path=dotenv_path, **kwargs)
