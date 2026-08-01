from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, CallbackQueryHandler, ContextTypes

from config import GROUP_URL, CHANNEL_URL, DEFAULT_CAPTION_TEXT, LOG_CHAT_ID
from db import get_start_image, upsert_user, get_user_count
from utils import check_membership

# NOTE: adjust this import path to wherever add.py actually lives in your
# project (e.g. `from handlers.add import try_handle_bid_deeplink`).
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
    """Sends the actual welcome image/caption + redirect buttons. Called once verified."""
    file_id, caption = await get_start_image()
    caption = caption or DEFAULT_CAPTION_TEXT

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👥 Join Group", url=GROUP_URL),
                InlineKeyboardButton("📢 Join Channel", url=CHANNEL_URL),
            ]
        ]
    )

    # parse_mode="HTML" lets the caption use <b>bold</b> etc. — without it,
    # tags show up as literal text. Plain newlines/blank lines in the
    # caption itself still work regardless of parse_mode.
    if file_id:
        await bot.send_photo(
            chat_id=chat_id,
            photo=file_id,
            caption=caption,
            reply_markup=keyboard,
            parse_mode="HTML",
        )
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
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
        # A "Place Bid" deep link takes priority over the generic welcome —
        # if it's handled here, don't also send the welcome image.
        if await try_handle_bid_deeplink(update, context, payload):
            return
        await send_welcome(context.bot, message.chat_id)
    else:
        # Remember the deep-link payload so "I've Joined" can resume the bid
        # flow after membership is (re)verified, instead of losing it.
        if context.user_data is not None and payload:
            context.user_data["pending_start_payload"] = payload
        await message.reply_text(
            "🚫 You need to join our group and channel before using this bot.\n\n"
            "Tap both buttons below, then tap \"I've Joined\".",
            reply_markup=_join_prompt_markup(),
        )


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the "✅ I've Joined" button. Re-checks membership and either
    resumes a bid that was stashed when they first tapped "Place Bid", or
    falls back to the normal welcome message."""
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

    # Resume a stashed "Place Bid" deep link if there was one; otherwise show
    # the normal welcome message.
    if payload and await try_handle_bid_deeplink(update, context, payload):
        return

    await send_welcome(context.bot, user.id)


def register_start_handlers(app):
    """Register /start and its 'I've Joined' callback. Call this once when
    building your Application — if you already register these elsewhere
    (e.g. in main.py), replace that registration with this one instead of
    having both, so there's only ever one /start handler."""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))        ]
    )

    if file_id:
        await bot.send_photo(chat_id=chat_id, photo=file_id, caption=caption, reply_markup=keyboard)
    else:
        await bot.send_message(
            chat_id=chat_id,
            text=caption,
            reply_markup=keyboard,
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
        # A "Place Bid" deep link takes priority over the generic welcome —
        # if it's handled here, don't also send the welcome image.
        if await try_handle_bid_deeplink(update, context, payload):
            return
        await send_welcome(context.bot, message.chat_id)
    else:
        # Remember the deep-link payload so "I've Joined" can resume the bid
        # flow after membership is (re)verified, instead of losing it.
        if context.user_data is not None and payload:
            context.user_data["pending_start_payload"] = payload
        await message.reply_text(
            "🚫 You need to join our group and channel before using this bot.\n\n"
            "Tap both buttons below, then tap \"I've Joined\".",
            reply_markup=_join_prompt_markup(),
        )


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles the "✅ I've Joined" button. Re-checks membership and either
    resumes a bid that was stashed when they first tapped "Place Bid", or
    falls back to the normal welcome message."""
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

    # Resume a stashed "Place Bid" deep link if there was one; otherwise show
    # the normal welcome message.
    if payload and await try_handle_bid_deeplink(update, context, payload):
        return

    await send_welcome(context.bot, user.id)


def register_start_handlers(app):
    """Register /start and its 'I've Joined' callback. Call this once when
    building your Application — if you already register these elsewhere
    (e.g. in main.py), replace that registration with this one instead of
    having both, so there's only ever one /start handler."""
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))
