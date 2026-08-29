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


def sanitize_proxy_env():
    """
    Sanitize proxy environment variables.
    1. Removes unsupported 'socks://' schemes (httpx/urllib3 expect http/https/socks5).
    2. Ensures domestic services (Feishu open API, Bootstrap server, localhost) are always in NO_PROXY.
    3. Detects if configured local proxy (e.g., 127.0.0.1:7892) is dead/unreachable; if dead, removes proxy env vars to prevent connection timeouts.
    """
    import socket

    # 1. Clean unsupported socks schemes
    for var in ["ALL_PROXY", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
        if var in os.environ and "socks" in os.environ[var].lower():
            try:
                logger.info(f"[ProxySanitizer] Removing unsupported proxy scheme in {var}={os.environ[var]}")
            except Exception:
                pass
            del os.environ[var]

    # 2. Inject domestic endpoints & dynamic LLM hosts into NO_PROXY / no_proxy
    from urllib.parse import urlparse

    domestic_hosts = [
        # P2P Bootstrap & Local
        "113.106.87.146",
        "127.0.0.1",
        "localhost",
        "bitpoliteia.com",
        ".bitpoliteia.com",
        # Feishu / Lark
        "open.feishu.cn",
        "msg-frontier.feishu.cn",
        "feishu.cn",
        ".feishu.cn",
        "larksuite.com",
        ".larksuite.com",
        # Domestic LLMs / Model Providers
        "coding.dashscope.aliyuncs.com",
        "dashscope.aliyuncs.com",
        "bailian.cn-beijing.aliyuncs.com",
        ".aliyuncs.com",
        ".aliyun.com",
        "api.deepseek.com",
        ".deepseek.com",
        "open.bigmodel.cn",
        "api.zhipuai.cn",
        ".bigmodel.cn",
        ".zhipuai.cn",
        "api.moonshot.cn",
        ".moonshot.cn",
        "qianfan.baidubce.com",
        "aip.baidubce.com",
        ".baidubce.com",
        "spark-api.xf-yun.com",
        "spark-api-open.xf-yun.com",
        "100ime-iat-api.xfyun.cn",
        ".xfyun.cn",
        ".xf-yun.com",
        "api.siliconflow.cn",
        ".siliconflow.cn",
        "api.minimax.chat",
        ".minimax.chat",
        "api.stepfun.com",
        ".stepfun.com",
        # Mirrors & Domestic Repositories
        "hf-mirror.com",
        ".hf-mirror.com",
        "gitee.com",
        "pypi.tuna.tsinghua.edu.cn",
        "mirrors.aliyun.com",
    ]

    # Dynamically extract host from configured LLM URLs
    for url_env in ["AGENT_BASE_URL", "AUX_MODEL_URL", "OPENAI_BASE_URL", "OPENAI_API_BASE", "AGENT_BOOTSTRAP_URL"]:
        val = os.environ.get(url_env)
        if val:
            try:
                parsed = urlparse(val if "://" in val else f"http://{val}")
                if parsed.hostname:
                    h = parsed.hostname.lower()
                    if h not in domestic_hosts:
                        # If domain is domestic (.cn, .aliyun, .deepseek, etc.) or private IP
                        if (
                            h.endswith(".cn")
                            or "aliyun" in h
                            or "deepseek" in h
                            or "zhipu" in h
                            or "moonshot" in h
                            or "baidu" in h
                            or "xfyun" in h
                            or "siliconflow" in h
                            or "minimax" in h
                            or "113.106." in h
                            or "192.168." in h
                            or "10." in h
                            or "172." in h
                        ):
                            domestic_hosts.append(h)
                            # Also add wildcard dot-prefix
                            if not h.startswith("."):
                                domestic_hosts.append(f".{h}")
            except Exception:
                pass

    for np_key in ["NO_PROXY", "no_proxy"]:
        current_np = os.environ.get(np_key, "")
        raw_entries = [x.strip() for x in current_np.split(",") if x.strip()]
        # Strip invalid wildcard entries (e.g. 127.* or *jd.com) that break standard curl/urllib3/httpx parsers
        cleaned_entries = []
        for entry in raw_entries:
            if entry.startswith("*."):
                cleaned_entries.append(entry[1:])  # Convert *.domain.com to .domain.com
            elif "*" in entry:
                continue  # drop broken wildcards like 127.*, 10.*, 172.*
            else:
                cleaned_entries.append(entry)
        for host in domestic_hosts:
            if host not in cleaned_entries:
                cleaned_entries.append(host)
        os.environ[np_key] = ",".join(cleaned_entries)

    # 3. Check if local proxy port is actually alive. If dead, clear proxy vars to avoid ProxyError
    proxy_val = os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or os.environ.get("https_proxy")
    if proxy_val and "127.0.0.1" in proxy_val or "localhost" in str(proxy_val):
        try:
            # Extract port
            port = int(str(proxy_val).split(":")[-1].rstrip("/"))
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(0.3)
            res = s.connect_ex(("127.0.0.1", port))
            s.close()
            if res != 0:
                # Port is closed (proxy software was shut down)
                for var in ["ALL_PROXY", "all_proxy", "HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
                    if var in os.environ:
                        del os.environ[var]
        except Exception:
            pass


# Run immediately on module import
sanitize_proxy_env()


def load_dotenv_safe(dotenv_path: str = None, **kwargs):
    """
    Enhanced load_dotenv that strips null characters (\x00) from the .env file.
    Null characters cause ValueError: embedded null character when set to os.environ.
    Uses find_dotenv() to support parent-directory search if no path specified.
    Also automatically sanitizes proxy environment variables.
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

    res = False
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
            res = _load_dotenv(stream=stream, **kwargs)
        except Exception as e:
            logger.error(f"[SafeDotenv] Error processing {path}: {e}")
            # Fallback to standard loading if something goes wrong
            res = _load_dotenv(dotenv_path=path, **kwargs)
    else:
        res = _load_dotenv(dotenv_path=dotenv_path, **kwargs)

    # Sanitize proxy after dotenv loading
    sanitize_proxy_env()
    return res
