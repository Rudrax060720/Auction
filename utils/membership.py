from telegram import Bot
from telegram.error import TelegramError

from config import GROUP_CHAT_ID, CHANNEL_CHAT_ID

JOINED_STATUSES = {"member", "administrator", "creator"}


async def _is_member(bot: Bot, chat_id, user_id: int) -> bool:
    if not chat_id:
        # Not configured — treat as "no requirement" rather than blocking everyone
        return True
    try:
        member = await bot.get_chat_member(chat_id, user_id)
        return member.status in JOINED_STATUSES
    except TelegramError:
        # e.g. user never started a chat with the bot, or bot isn't in the chat
        return False


async def check_membership(bot: Bot, user_id: int) -> tuple[bool, bool]:
    """Returns (in_group, in_channel)."""
    in_group = await _is_member(bot, GROUP_CHAT_ID, user_id)
    in_channel = await _is_member(bot, CHANNEL_CHAT_ID, user_id)
    return in_group, in_channel