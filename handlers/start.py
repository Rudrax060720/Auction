from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import GROUP_URL, CHANNEL_URL, DEFAULT_CAPTION_TEXT, LOG_CHAT_ID
from db import get_start_image, upsert_user, get_user_count
from utils import check_membership

from handlers.add import try_handle_bid_deeplink
from telegram.ext import CallbackQueryHandler


def _join_prompt_markup() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 Join Group", url=GROUP_URL),
                InlineKeyboardButton("📢 Join Channel", url=CHANNEL_URL),
            ],
            [InlineKeyboardButton("✅ I've Joined", callback_data="check_join")],
        ]
    )


async def send_welcome(bot, chat_id: int) -> None:
    """
    Sends the welcome image + DEFAULT_CAPTION_TEXT from config.
    The photo file_id is still pulled from the DB (set via /setimage),
    but the caption is always the one defined in config.py — so you
    can update the welcome text by editing DEFAULT_CAPTION_TEXT without
    needing to use /setimage again.
    """
    file_id, _ = await get_start_image()  # caption from DB is intentionally ignored

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 Join Group", url=GROUP_URL),
                InlineKeyboardButton("📢 Join Channel", url=CHANNEL_URL),
            ]
        ]
    )

    if file_id:
        await bot.send_photo(
            chat_id=chat_id,
            photo=file_id,
            caption=DEFAULT_CAPTION_TEXT,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=DEFAULT_CAPTION_TEXT,
            reply_markup=keyboard,
            parse_mode="HTML",
        )


async def _log_start_event(bot, user, is_new_user: bool) -> None:
    if not LOG_CHAT_ID:
        return

    username_str = f"@{user.username}" if user.username else "(no username)"
    name_str = user.full_name or "Unknown"
    total = await get_user_count()

    tag = "🆕 NEW USER" if is_new_user else "🔁 Returning user"
    text = (
        f"{tag} started the bot\n\n"
        f"Name: {name_str}\n"
        f"Username: {username_str}\n"
        f"User ID: {user.id}\n\n"
        f"Total users: {total}"
    )

    try:
        await bot.send_message(chat_id=LOG_CHAT_ID, text=text)
    except Exception:
        pass  # never let logging failures break the user-facing flow


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    is_new_user = await upsert_user(user.id, user.username, user.first_name)
    if is_new_user:
        await _log_start_event(context.bot, user, is_new_user)

    in_group, in_channel = await check_membership(context.bot, user.id)
    payload = context.args[0] if context.args else ""

    if in_group and in_channel:
        if await try_handle_bid_deeplink(update, context, payload):
            return
        await send_welcome(context.bot, message.chat_id)
    else:
        if context.user_data is not None and payload:
            context.user_data["pending_start_payload"] = payload
        await message.reply_text(
            "🚫 You need to join our group and channel before using this bot.\n\n"
            "Tap both buttons below, then tap \"I've Joined\".",
            reply_markup=_join_prompt_markup(),
        )


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    in_group, in_channel = await check_membership(context.bot, user.id)
    if not (in_group and in_channel):
        await query.answer("You haven't joined both yet — please join, then tap again.", show_alert=True)
        return

    await query.answer("✅ Verified!")

    payload = ""
    if context.user_data is not None:
        payload = context.user_data.pop("pending_start_payload", "") or ""

    if payload and await try_handle_bid_deeplink(update, context, payload):
        return

    await send_welcome(context.bot, user.id)


def register_start_handlers(app):
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
