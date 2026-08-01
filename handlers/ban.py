from telegram import Update, User
from telegram.ext import Application, CommandHandler, ContextTypes

from config import SUPER_ADMIN_ID, LOG_CHAT_ID as LOG_GROUP_ID
from db import ban_user, unban_user, get_user_by_username
from utils import admin_only
from utils.addutils import build_user_mention
from utils.banutlis import (
    build_ban_log_message,
    build_unban_log_message,
    build_not_banned_message,
    build_already_banned_message,
    build_ban_success_message,
    build_unban_success_message,
    build_cannot_ban_admin_message,
    build_ban_usage_message,
    build_user_not_found_message,
)


async def _resolve_target(message, context: ContextTypes.DEFAULT_TYPE, command: str):
    """
    Resolves the target of /aban or /aunban from one of three input styles:
      - replying to the target's message
      - a raw numeric Telegram user ID
      - an @username (only works if that user has started the bot before,
        since Telegram gives bots no general username -> id lookup)

    Takes the already-validated Message (not the Update) so the caller's
    None-check on update.message actually narrows the type here too.

    Returns (target_id, display, remaining_args) on success, or
    (None, error_message, None) if the target couldn't be resolved — in
    which case the caller should just reply with the error message.
    """
    args = context.args or []

    replied = message.reply_to_message
    if replied is not None and replied.from_user is not None:
        target_user: User = replied.from_user
        return target_user.id, build_user_mention(target_user), args

    if not args:
        return None, build_ban_usage_message(command), None

    first = args[0]
    remaining = args[1:]

    if first.startswith("@"):
        username = first[1:]
        target_id = await get_user_by_username(username)
        if target_id is None:
            return None, build_user_not_found_message(username), None
        return target_id, f"@{username}", remaining

    try:
        target_id = int(first)
    except ValueError:
        return None, build_ban_usage_message(command), None

    return target_id, str(target_id), remaining


@admin_only
async def aban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /aban <user_id | @username> [reason]  — or reply to their message.
    Globally bans a user from using the bot. Usable by admins and the super admin.
    """
    message = update.message
    admin = update.effective_user
    if message is None or admin is None:
        return

    target_id, display_or_error, remaining_args = await _resolve_target(message, context, "/aban")
    if target_id is None:
        await message.reply_text(display_or_error)
        return

    if target_id == SUPER_ADMIN_ID:
        await message.reply_text(build_cannot_ban_admin_message())
        return

    display = display_or_error
    reason = " ".join(remaining_args) if remaining_args else None

    newly_banned = await ban_user(target_id, admin.id, reason)

    await message.reply_text(
        build_ban_success_message(display) if newly_banned else build_already_banned_message(display),
        parse_mode="Markdown",
    )

    banned_by_display = build_user_mention(admin)
    try:
        await context.bot.send_message(
            chat_id=LOG_GROUP_ID,
            text=build_ban_log_message(display, banned_by_display, reason),
            parse_mode="Markdown",
        )
    except Exception:
        pass


@admin_only
async def aunban_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /aunban <user_id | @username>  — or reply to their message.
    Lifts a global ban. Usable by admins and the super admin.
    """
    message = update.message
    admin = update.effective_user
    if message is None or admin is None:
        return

    target_id, display_or_error, _ = await _resolve_target(message, context, "/aunban")
    if target_id is None:
        await message.reply_text(display_or_error)
        return

    display = display_or_error
    was_banned = await unban_user(target_id)

    await message.reply_text(
        build_unban_success_message(display) if was_banned else build_not_banned_message(display),
        parse_mode="Markdown",
    )

    if was_banned:
        unbanned_by_display = build_user_mention(admin)
        try:
            await context.bot.send_message(
                chat_id=LOG_GROUP_ID,
                text=build_unban_log_message(display, unbanned_by_display),
                parse_mode="Markdown",
            )
        except Exception:
            pass


def register_ban_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("aban", aban_command))
    app.add_handler(CommandHandler("aunban", aunban_command))