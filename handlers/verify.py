from telegram import Update
from telegram.ext import ContextTypes

from utils import check_membership
from handlers.start import send_welcome

# NOTE: adjust this import path to wherever add.py actually lives in your
# project (e.g. `from handlers.add import try_handle_bid_deeplink`).
from handlers.add import try_handle_bid_deeplink


async def check_join_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None or query.from_user is None:
        return

    await query.answer()  # acknowledge the tap so Telegram stops the loading spinner

    in_group, in_channel = await check_membership(context.bot, query.from_user.id)

    if in_group and in_channel:
        # Remove the join prompt. query.message is typed as
        # MaybeInaccessibleMessage, which doesn't guarantee a .delete()
        # method — go through context.bot.delete_message instead, using
        # attributes both Message and InaccessibleMessage always have.
        if query.message is not None:
            try:
                await context.bot.delete_message(
                    chat_id=query.message.chat.id,
                    message_id=query.message.message_id,
                )
            except Exception:
                pass  # message may already be gone or too old to delete

        # If they originally tapped "Place Bid" before joining, resume that
        # flow instead of showing the generic welcome content.
        payload = ""
        if context.user_data is not None:
            payload = context.user_data.pop("pending_start_payload", "") or ""

        if payload and await try_handle_bid_deeplink(update, context, payload):
            return

        await send_welcome(context.bot, query.from_user.id)
    else:
        await query.answer(
            "You still haven't joined both the group and channel. Please join and try again.",
            show_alert=True,
        )