from langchain_core.tools import tool
from ..services.identity_service import identity_manager

@tool
def get_account_pairing_code(platform_user_id: str, channel: str) -> str:
    """
    Generates a 6-digit pairing code to link this account to another platform.
    The code is valid for 20 minutes.
    
    Args:
        platform_user_id: The unique ID of the user on the current platform.
        channel: The name of the current communication channel (e.g., 'feishu', 'web', 'telegram').
    """
    unified_id = identity_manager.resolve_unified_id(platform_user_id, channel)
    code = identity_manager.create_pairing_code(unified_id)
    return (f"Your pairing code is: **{code}**\n\n"
            f"Enter this code in your other account (e.g., in Telegram or Feishu) "
            f"using the `bind_account` command to link them together.\n"
            f"This code will expire in 20 minutes.")

@tool
def bind_account_by_code(code: str, platform_user_id: str, channel: str) -> str:
    """
    Links this account to another account using a pairing code.
    Once linked, both accounts will share the same conversation context and settings.
    
    Args:
        code: The 6-digit pairing code obtained from your other account.
        platform_user_id: The unique ID of the user on the current platform.
        channel: The name of the current communication channel (e.g., 'feishu', 'web', 'telegram').
    """
    success = identity_manager.bind_by_code(code, platform_user_id, channel)
    if success:
        return ("Successfully linked accounts! Your sessions across these channels "
                "will now be synchronized. You may need to refresh your current session "
                "to see updated history.")
    else:
        return ("Failed to link accounts. The pairing code may be invalid or expired. "
                "Please generate a new code and try again.")

@tool
def unbind_account(platform_user_id: str, channel: str) -> str:
    """
    Removes the link between this platform account and the unified identity.
    After unbinding, this account will have its own independent session context again.
    
    Args:
        platform_user_id: The unique ID of the user on the current platform.
        channel: The name of the current communication channel.
    """
    success = identity_manager.unbind(platform_user_id, channel)
    if success:
        return ("Successfully unbound account. This channel will now use its own "
                "independent session context.")
    else:
        return "This account is not currently linked to any other identities."
