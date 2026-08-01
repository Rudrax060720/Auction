"""
Global ban enforcement.

Register both handlers here at group=-1 in your Application so they run
BEFORE every other handler (commands, message routers, callbacks, etc.):

    from handlers.ban_guard import BOT_COMMANDS, global_ban_check_message, global_ban_check_callback
    app.add_handler(CommandHandler(BOT_COMMANDS, global_ban_check_message), group=-1)
    app.add_handler(CallbackQueryHandler(global_ban_check_callback, pattern=".*"), group=-1)

CommandHandler(BOT_COMMANDS, ...) — not MessageHandler(filters.ALL, ...)
and not MessageHandler(filters.COMMAND, ...) — is deliberate:
  - filters.ALL would reply to every message the user sends, including
    unrelated group chatter.
  - filters.COMMAND matches ANY slash-command, including ones meant for a
    different bot in the same group (e.g. "/roll", another bot's "/ban").
  - filters.Command(...) only takes an only_start bool, not a list of
    command names — it can't restrict to specific commands at all.
CommandHandler is the one PTB class that both accepts a list of specific
command names AND correctly handles "/cmd@botusername" targeting, so it
only fires for commands THIS bot registers, listed in BOT_COMMANDS below.
Button taps are always a deliberate interaction with this bot, so the
callback guard still matches everything.

IMPORTANT: keep BOT_COMMANDS in sync with every CommandHandler you
register elsewhere (add.py, ban.py, admin.py, start.py, etc.) — add the
name here whenever you add a new command, or the guard won't catch a
banned user running it.

Raising ApplicationHandlerStop inside a handler stops the update from
reaching ANY other handler in ANY group for this update — that's what
actually makes the ban apply "everywhere" in one place, instead of having
to sprinkle an is_banned() check into every single command handler.
"""

from telegram import Update
from telegram.ext import ContextTypes, ApplicationHandlerStop

from db import is_banned
from utils.banutlis import build_ban_notice_message, get_appeal_keyboard

# Every command name this bot registers, WITHOUT the leading "/". Update this
# whenever a new CommandHandler is added anywhere in the project.
BOT_COMMANDS = [
    "start",
    "add",
    "aban",
    "aunban",
    "setimage",
    "addadmin",
    "removeadmin",
    "itemlist",
    "myitem",
]


async def global_ban_check_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    if not await is_banned(user.id):
        return  # not banned — let every other handler run normally

    await message.reply_text(
        build_ban_notice_message(),
        parse_mode="Markdown",
        reply_markup=get_appeal_keyboard(),
    )
    raise ApplicationHandlerStop


async def global_ban_check_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return

    if not await is_banned(user.id):
        return  # not banned — let every other handler run normally

    await query.answer(
        "🚫 You are globally banned from using this bot.", show_alert=True
    )
    raise ApplicationHandlerStop