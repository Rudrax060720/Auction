from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)

from db import get_active_auctions
from utils.addutils import ParsedCard
from utils.Itemlistutils import (
    build_itemlist_message,
    build_myitem_message,
    CB_ITEMLIST_PREFIX,
    CB_MYITEM_PREFIX,
    FILTER_ALL,
)


async def _load_public_posts() -> dict:
    """
    Fetches all active auctions from MongoDB and reshapes them back into the
    {submission_id: post} structure that build_itemlist_message /
    build_myitem_message expect — the same shape the old in-memory
    PUBLIC_POSTS dict had, including "card" as a ParsedCard object (not the
    plain dict Mongo stores it as), since those builders use dot-access
    like post["card"].char_name.
    """
    docs = await get_active_auctions()
    posts = {}
    for doc in docs:
        post = dict(doc)
        post["card"] = ParsedCard(**doc["card"])
        posts[doc["submission_id"]] = post
    return posts


# ---------- /itemlist command ----------
async def itemlist_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    public_posts = await _load_public_posts()
    text, keyboard = build_itemlist_message(public_posts, FILTER_ALL, 0)
    await message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ---------- Callback handler for filter/page buttons on /itemlist ----------
async def itemlist_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.data is None:
        return

    if query.data == "il_noop":
        await query.answer()
        return

    if not query.data.startswith(CB_ITEMLIST_PREFIX):
        return

    payload = query.data[len(CB_ITEMLIST_PREFIX):]
    try:
        filter_key, page_str = payload.rsplit("_", 1)
        page = int(page_str)
    except ValueError:
        await query.answer()
        return

    await query.answer()

    public_posts = await _load_public_posts()
    text, keyboard = build_itemlist_message(public_posts, filter_key, page)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except Exception:
        # Telegram raises "message is not modified" if the tapped button
        # produces identical text+markup (e.g. re-tapping the active
        # filter, or Prev/Next at a boundary) — safe to ignore.
        pass


# ---------- /myitem command ----------
async def myitem_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    user = update.effective_user
    if user is None:
        return

    public_posts = await _load_public_posts()
    text, keyboard = build_myitem_message(public_posts, user.id, 0)
    await message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# ---------- Callback handler for page buttons on /myitem ----------
async def myitem_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.data is None:
        return

    if query.data == "mi_noop":
        await query.answer()
        return

    if not query.data.startswith(CB_MYITEM_PREFIX):
        return

    user = update.effective_user
    if user is None:
        return

    try:
        page = int(query.data[len(CB_MYITEM_PREFIX):])
    except ValueError:
        await query.answer()
        return

    await query.answer()

    public_posts = await _load_public_posts()
    text, keyboard = build_myitem_message(public_posts, user.id, page)
    try:
        await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
    except Exception:
        pass


# ---------- Registration ----------
def register_itemlist_handlers(app: Application):
    app.add_handler(CommandHandler("itemlist", itemlist_command))
    app.add_handler(CommandHandler("myitem", myitem_command))
    app.add_handler(CallbackQueryHandler(itemlist_callback, pattern="^(il_)"))
    app.add_handler(CallbackQueryHandler(myitem_callback, pattern="^(mi_)"))