"""
Utility helpers for /itemlist and /myitem.

Keeps constants, keyboard builders, and message builders separate from the
handler logic in handlers/itemlist.py — same pattern as utils/addutils.py.

Place this file at: utils/itemlistutils.py
"""

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from utils.addutils import escape_md, TYPE_LABEL

# ---------- Constants ----------

ITEMS_PER_PAGE = 8

CB_ITEMLIST_PREFIX = "il_"   # callback_data format: "il_<filter>_<page>"
CB_MYITEM_PREFIX = "mi_"     # callback_data format: "mi_<page>"

FILTER_ALL = "all"
FILTER_HUSBANDO = "husbando"
FILTER_WAIFU = "waifu"

FILTER_LABEL = {
    FILTER_ALL: "All",
    FILTER_HUSBANDO: "👨 Husbando",
    FILTER_WAIFU: "👩 Waifu",
}


# ---------- Data helpers ----------

def filter_posts(public_posts: dict, filter_key: str) -> list:
    """
    Returns a list of (submission_id, post) tuples from PUBLIC_POSTS matching
    the given filter, in stable (insertion) order.

    PUBLIC_POSTS only ever holds currently-active auctions — closed/ended
    ones are popped out in _finalize_auction — so this naturally only shows
    open listings, with no extra "is it still open" check needed.
    """
    items = list(public_posts.items())
    if filter_key in (FILTER_HUSBANDO, FILTER_WAIFU):
        items = [
            (sid, post) for sid, post in items
            if post["card"].card_type == filter_key
        ]
    return items


def paginate(items: list, page: int):
    """Slices items for the given 0-indexed page.

    Returns (page_items, total_pages, clamped_page).
    """
    total_pages = max(1, (len(items) + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    page = max(0, min(page, total_pages - 1))
    start = page * ITEMS_PER_PAGE
    page_items = items[start:start + ITEMS_PER_PAGE]
    return page_items, total_pages, page


def current_price(post: dict) -> int:
    """The number to show for a listing: highest bid if any, else base price."""
    return post["highest_bid"] if post.get("highest_bid") is not None else post["price"]


# ---------- Keyboard builders ----------

def get_itemlist_keyboard(filter_key: str, page: int, total_pages: int) -> InlineKeyboardMarkup:
    def label(key: str) -> str:
        text = FILTER_LABEL[key]
        return f"• {text} •" if key == filter_key else text

    filter_row = [
        InlineKeyboardButton(label(FILTER_ALL), callback_data=f"{CB_ITEMLIST_PREFIX}{FILTER_ALL}_0"),
        InlineKeyboardButton(label(FILTER_HUSBANDO), callback_data=f"{CB_ITEMLIST_PREFIX}{FILTER_HUSBANDO}_0"),
        InlineKeyboardButton(label(FILTER_WAIFU), callback_data=f"{CB_ITEMLIST_PREFIX}{FILTER_WAIFU}_0"),
    ]

    nav_row = []
    if page > 0:
        nav_row.append(
            InlineKeyboardButton("◀ Prev", callback_data=f"{CB_ITEMLIST_PREFIX}{filter_key}_{page - 1}")
        )
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="il_noop"))
    if page < total_pages - 1:
        nav_row.append(
            InlineKeyboardButton("Next ▶", callback_data=f"{CB_ITEMLIST_PREFIX}{filter_key}_{page + 1}")
        )

    return InlineKeyboardMarkup([filter_row, nav_row])


def get_myitem_keyboard(page: int, total_pages: int) -> InlineKeyboardMarkup:
    nav_row = []
    if page > 0:
        nav_row.append(InlineKeyboardButton("◀ Prev", callback_data=f"{CB_MYITEM_PREFIX}{page - 1}"))
    nav_row.append(InlineKeyboardButton(f"{page + 1}/{total_pages}", callback_data="mi_noop"))
    if page < total_pages - 1:
        nav_row.append(InlineKeyboardButton("Next ▶", callback_data=f"{CB_MYITEM_PREFIX}{page + 1}"))
    return InlineKeyboardMarkup([nav_row])


# ---------- Message builders ----------

def build_item_line(submission_id: str, post: dict) -> str:
    """One compact line per item for the list views.

    Shows the highest bid (🔥) if the item has one, otherwise the base
    price (no emoji), per the item's current status. The theme emoji is
    shown right after the character name, and no submission id is shown
    here (use the card's photo/caption in the group for that).
    """
    card = post["card"]
    price = current_price(post)
    bid_tag = "🔥" if post.get("highest_bid") is not None else ""
    type_label = TYPE_LABEL.get(card.card_type, card.card_type)
    price_part = f"{bid_tag} {price}".strip()
    return (
        f"{card.rarity_emoji} **{escape_md(card.char_name)}** [{card.theme_emoji}] "
        f"({type_label}) — {price_part}"
    )


def build_itemlist_header(filter_key: str, total_count: int) -> str:
    label = FILTER_LABEL[filter_key]
    if total_count == 0:
        return f"📦 **Item List** — {label}\n\nNo active auctions in this category right now."
    return f"📦 **Item List** — {label}\n\n🗂 {total_count} item(s) currently up for auction:\n"


def build_itemlist_message(public_posts: dict, filter_key: str, page: int):
    """Returns (text, keyboard) for a given filter + page of /itemlist."""
    items = filter_posts(public_posts, filter_key)
    page_items, total_pages, page = paginate(items, page)

    header = build_itemlist_header(filter_key, len(items))
    if not items:
        text = header
    else:
        lines = [build_item_line(sid, post) for sid, post in page_items]
        text = header + "\n" + "\n".join(lines)

    keyboard = get_itemlist_keyboard(filter_key, page, total_pages)
    return text, keyboard


def build_myitem_header(total_count: int) -> str:
    if total_count == 0:
        return (
            "📦 **My Items**\n\n"
            "You don't have any active auction listings right now.\n"
            "Use /add to submit a card!"
        )
    return f"📦 **My Items**\n\n🗂 {total_count} of your item(s) currently up for auction:\n"


def build_myitem_message(public_posts: dict, user_id: int, page: int):
    """Returns (text, keyboard) for a given page of /myitem, scoped to user_id's own listings."""
    items = [
        (sid, post) for sid, post in public_posts.items()
        if post.get("owner_id") == user_id
    ]
    page_items, total_pages, page = paginate(items, page)

    header = build_myitem_header(len(items))
    if not items:
        text = header
    else:
        lines = [build_item_line(sid, post) for sid, post in page_items]
        text = header + "\n" + "\n".join(lines)

    keyboard = get_myitem_keyboard(page, total_pages)
    return text, keyboard