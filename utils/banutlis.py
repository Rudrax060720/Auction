"""
Utility helpers for the /aban and /aunban commands.

Keeps message/keyboard builders separate from the handler logic,
matching the pattern used in addutils.py.
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from config import GROUP_URL
from utils.addutils import escape_md


def get_appeal_keyboard() -> InlineKeyboardMarkup:
    """Shown on the ban notice — links straight to the group so a banned
    user can appeal without needing any other bot interaction."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("📢 Appeal in Group", url=GROUP_URL)]]
    )


def build_ban_notice_message(reason: str | None = None) -> str:
    """Shown to a banned user any time they try to use the bot."""
    text = "🚫 You have been globally banned from using this bot."
    if reason:
        text += f"\n\nReason: {escape_md(reason)}"
    text += "\n\nIf you believe this is a mistake, you can appeal in our group below."
    return text


def build_ban_log_message(target_display: str, banned_by_display: str, reason: str | None) -> str:
    """Sent to the log group when an admin bans someone."""
    text = f"🚫 {target_display} has been globally banned.\n\nBanned by: {banned_by_display}"
    if reason:
        text += f"\nReason: {escape_md(reason)}"
    return text


def build_unban_log_message(target_display: str, unbanned_by_display: str) -> str:
    """Sent to the log group when an admin unbans someone."""
    return (
        f"✅ {target_display} has been globally unbanned.\n\n"
        f"Unbanned by: {unbanned_by_display}"
    )


def build_not_banned_message(target_display: str) -> str:
    return f"⚠️ {target_display} isn't currently banned."


def build_already_banned_message(target_display: str) -> str:
    return f"⚠️ {target_display} was already banned — reason updated."


def build_ban_success_message(target_display: str) -> str:
    return f"✅ {target_display} has been globally banned."


def build_unban_success_message(target_display: str) -> str:
    return f"✅ {target_display} has been globally unbanned."


def build_cannot_ban_admin_message() -> str:
    return "❌ You can't ban the super admin."


def build_ban_usage_message(command: str) -> str:
    return (
        f"Usage: {command} <user_id | @username> [reason] — "
        "or reply to the user's message."
    )


def build_user_not_found_message(username: str) -> str:
    return (
        f"❌ Couldn't find @{username} — they need to have started the bot "
        "at least once for me to look them up by username. Try their "
        "numeric user ID instead, or reply to one of their messages."
    )