"""
Utility helpers for the /add command.

Keeps constants, keyboard builders, caption parsing, and message
builders separate from the handler logic in handlers/add.py.
"""

import re
import html
from dataclasses import dataclass
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.helpers import escape_markdown
from config import LOG_CHAT_ID as LOG_GROUP_ID

# ⚠️ Set these to the chat ids of the public channel / group where verified
# cards should be announced (with the bid button). Same pattern as
# LOG_CHAT_ID above — add the bot to each, grab update.effective_chat.id.
from config import CHANNEL_CHAT_ID, GROUP_CHAT_ID
# ---------- Constants ----------


def escape_md(text) -> str:
    """
    Escapes text for Telegram's legacy Markdown parse mode.

    Without this, characters like `_`, `*`, `` ` `` and `[` are treated as
    formatting markers instead of literal characters — e.g. a username like
    "KING_OF_MYCENAE" would render as "KINGOFMYCENAE" with the middle part
    italicized, because the underscores get consumed as italic delimiters.
    Every piece of user-supplied text (usernames, character names, series
    names, etc.) that gets interpolated into a caption sent with
    parse_mode="Markdown" should be passed through this first.
    """
    if text is None:
        return ""
    return escape_markdown(str(text), version=1)


def get_display_name(user) -> str:
    """
    Raw (unescaped, unlinked) display name for a telegram.User — the shared
    source of truth used by both the Markdown and HTML mention builders
    below, so both stay in sync.
    """
    if user is None:
        return "Someone"
    return user.full_name or (f"@{user.username}" if user.username else "Someone")


def build_user_mention(user) -> str:
    """
    Builds a clickable Markdown link to a user's Telegram account — works
    even for users without a public @username, unlike a plain "@username"
    mention. Usable anywhere a caption/message is sent with
    parse_mode="Markdown".
    """
    if user is None:
        return "Someone"
    return f"[{escape_md(get_display_name(user))}](tg://user?id={user.id})"


def build_mention_from_id(user_id, display_name: str) -> str:
    """
    Same idea as build_user_mention, but for cases where only a bare user id
    and a display label (e.g. "@username") were stored earlier — such as a
    card's original seller — rather than a full telegram.User object.
    """
    name = (display_name or "Someone").lstrip("@")
    return f"[{escape_md(name)}](tg://user?id={user_id})"


def escape_html(text) -> str:
    """
    Escapes text for Telegram's HTML parse mode (&, <, >). Only needed for
    messages sent with parse_mode="HTML" — see build_user_mention_html below
    for why some messages use HTML instead of Markdown.
    """
    if text is None:
        return ""
    return html.escape(str(text), quote=False)


def build_user_mention_html(user) -> str:
    """
    HTML-mode equivalent of build_user_mention.

    Telegram's legacy "Markdown" parse mode doesn't reliably combine a bold
    span with a link/mention entity in the same message — messages that need
    both (e.g. "**Auction Closed!** ... Winner: [Name](tg://user?id=...)")
    can end up with the mention silently rendered as plain text instead of a
    clickable link. Any message that needs a mention alongside other
    formatting is built with this + parse_mode="HTML" instead.
    """
    if user is None:
        return "Someone"
    return f'<a href="tg://user?id={user.id}">{escape_html(get_display_name(user))}</a>'


def build_mention_from_id_html(user_id, display_name: str) -> str:
    """HTML-mode equivalent of build_mention_from_id — see build_user_mention_html."""
    name = (display_name or "Someone").lstrip("@")
    return f'<a href="tg://user?id={user_id}">{escape_html(name)}</a>'


def build_mention(user_id, display_label: str) -> str:
    """
    Best-effort clickable mention for use in the auction-close messages.

    If display_label is already a real "@username" (the form get_display_name
    and the "submitted_by" field both use when the person has a public
    username), it's returned as-is: Telegram auto-links any genuine
    @username that appears in message text, regardless of parse_mode, so
    this is the most reliable way to link to someone. Only falls back to
    the tg://user HTML deep-link — which needs the user's id and doesn't
    render as consistently across every client — when there's no username
    to work with.
    """
    if display_label and display_label.startswith("@"):
        return display_label
    return build_mention_from_id_html(user_id, display_label)


RARITY_LABEL = "𝙍𝘼𝙍𝙄𝙏𝙔"
THEME_LABEL = "𝑻𝒉𝒆𝒎𝒆"

ALLOWED_RARITIES_TEXT = (
    "⚠️ You can only add characters from these rarities:\n\n"
    "🟡 Legendary (Chibis)\n"
    "🔮 Limiteds\n"
    "🎐 Celestial"
)

# Normalized (lowercase) rarity names that are allowed to be added
ALLOWED_RARITIES = {
    "legendary": "🟡 Legendary (Chibis)",
    "limited edition": "🔮 Limited Edition",
    "limited": "🔮 Limited Edition",
    "celestial": "🎐 Celestial",
}

# Callback data values (kept as constants to avoid typos across files)
CB_ADD_HUSBANDO = "add_husbando"
CB_ADD_WAIFU = "add_waifu"

# Maps callback_data -> internal type stored in user_data
CALLBACK_TO_TYPE = {
    CB_ADD_HUSBANDO: "husbando",
    CB_ADD_WAIFU: "waifu",
}

# Maps internal type -> display label
TYPE_LABEL = {
    "husbando": "Husbando",
    "waifu": "Waifu",
}

# Currency emoji used when displaying / logging base price
CURRENCY_EMOJI = "⛀"

# Callback data prefixes for the verification buttons in the log group
CB_VERIFY_PREFIX = "verify_"
CB_REJECT_PREFIX = "reject_"

# Callback data prefix for the "Place Bid" button shown on public posts
CB_BID_PREFIX = "bid_"

# How long a verified card stays open for bidding before it's auto-closed.
AUCTION_DURATION_SECONDS = 2 * 24 * 60 * 60  # 2 days

# Percentage charged on a bid that an admin cancels via /cancelbid,
# based on the cancelled bid's amount.
CANCELLATION_CHARGE_RATE = 0.10


def calculate_cancellation_charge(amount: Optional[int]) -> int:
    """10% charge on a cancelled bid, rounded to the nearest whole unit."""
    if not amount:
        return 0
    return round(amount * CANCELLATION_CHARGE_RATE)


# ---------- Keyboard builders ----------

def get_add_choice_keyboard() -> InlineKeyboardMarkup:
    """Inline keyboard offering Husbando / Waifu choice."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👨 Add Husbando", callback_data=CB_ADD_HUSBANDO),
                InlineKeyboardButton("👩 Add Waifu", callback_data=CB_ADD_WAIFU),
            ]
        ]
    )


def get_bid_keyboard(
    submission_id: str, bot_username: str, highest_bid: Optional[int] = None
) -> InlineKeyboardMarkup:
    """Inline keyboard with a single Place Bid button, shown on the public post
    in the channel/group once a card has been verified.

    The button is a deep link (not callback_data) that opens the user's DM
    with the bot, pre-filled with a /start payload identifying the card, so
    they can enter their bid privately instead of in the channel/group.
    """
    label = "Place Bid"
    if highest_bid is not None:
        label = f"{CURRENCY_EMOJI} Bid ({highest_bid})"
    deep_link = f"https://t.me/{bot_username}?start={CB_BID_PREFIX}{submission_id}"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(label, url=deep_link),
            ]
        ]
    )


def get_verification_keyboard(submission_id: str) -> InlineKeyboardMarkup:
    """Inline keyboard with Verified / Rejected buttons shown in the log group."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ Verified", callback_data=f"{CB_VERIFY_PREFIX}{submission_id}"
                ),
                InlineKeyboardButton(
                    "❌ Rejected", callback_data=f"{CB_REJECT_PREFIX}{submission_id}"
                ),
            ]
        ]
    )


# ---------- Message builders ----------

def build_rarity_notice(kind_label: str) -> str:
    """
    Message shown right after the user picks Husbando/Waifu.
    Tells them exactly what to send next.
    """
    kind_lower = kind_label.lower()
    return (
        f"You chose to add a **{kind_label}**.\n\n"
        f"{ALLOWED_RARITIES_TEXT}\n\n"
        f"📸 Now send a **{kind_lower} card from your harem** "
        f"(the image with its caption) that matches one of the rarities above."
    )


def build_success_message(card: "ParsedCard") -> str:
    """Confirmation message once a valid card has been submitted."""
    return (
        "✅ Submission accepted!\n\n"
        f"👤 Owner: {escape_md(card.username)}\n"
        f"📚 Anime : {escape_md(card.series)}\n"
        f"🃏 Character: {escape_md(card.char_name)} [[{card.theme_emoji}]]\n"
        f"{card.rarity_emoji} Rarity: {escape_md(card.rarity)}\n\n"
        "Your card has been added successfully! 🎉"
    )


def build_wrong_type_message(expected: str, got: str) -> str:
    return (
        f"❌ You selected **{TYPE_LABEL[expected]}**, but the card you sent "
        f"is a **{TYPE_LABEL.get(got, got)}**.\n\n"
        f"Please send a {TYPE_LABEL[expected].lower()} card from your harem instead."
    )


def build_wrong_rarity_message(rarity: str) -> str:
    return (
        f"❌ **{escape_md(rarity)}** is not an allowed rarity.\n\n"
        f"{ALLOWED_RARITIES_TEXT}\n\n"
        "Please send a card matching one of these rarities."
    )


def build_parse_failed_message() -> str:
    return (
        "❌ I couldn't read that card's details.\n\n"
        "Please make sure you're sending the original image with its caption intact, "
        "exactly as it appears in your harem."
    )


def build_price_prompt_message(card: "ParsedCard") -> str:
    """Asks the user for the base price after the card passes validation."""
    return (
        f"✅ Got your **{escape_md(card.char_name)}** card!\n\n"
        f"💰 Now send me the **base price** for this card.\n"
        f"Just reply with a number (e.g. `500`)."
    )


def build_invalid_price_message() -> str:
    return (
        "❌ That doesn't look like a valid price.\n\n"
        "Please send the base price as a plain number (e.g. `500`), with no letters or symbols."
    )


def build_pending_verification_message(card: "ParsedCard", price: int) -> str:
    """Shown to the user right after they submit the base price."""
    return (
        "📨 Your submission has been sent for verification.\n\n"
        f"🃏 Character: {escape_md(card.char_name)}\n"
        f"{card.rarity_emoji} Rarity: {escape_md(card.rarity)} [[{card.theme_emoji}]]\n"
        f"{CURRENCY_EMOJI} Base Price: {price}\n\n"
        "You'll be notified here once it's reviewed."
    )


def build_log_caption(card: "ParsedCard", price: int, submitted_by, submission_id: Optional[str] = None) -> str:
    """
    Caption sent with the card photo to the log/verification group.

    submission_id is only known once the log message itself has been sent
    (it's the log message's own id), so this is first called without it and
    then re-called with it once we know it, so admins can see the item id
    right in the log group and later use it with /endauction.
    """
    lines = [
        "🆕 New card submission awaiting verification",
        "",
        f"👤 Submitted by: {escape_md(submitted_by)}",
        f"📚 Anime: {escape_md(card.series)}",
        f"🃏 Character: {escape_md(card.char_name)} [[{card.theme_emoji}]]",
        f"{card.rarity_emoji} Rarity: {escape_md(card.rarity)}",
        f"🔖 Type: {TYPE_LABEL.get(card.card_type, card.card_type)}",
        f"{CURRENCY_EMOJI} Base Price: {price}",
    ]
    if submission_id:
        lines.append(f"🆔 Item ID: `{submission_id}`")
    lines.append("")
    lines.append("Please verify or reject this submission below.")
    return "\n".join(lines)


def build_log_decision_suffix(status: str, decided_by) -> str:
    """Appended to the log caption once an admin makes a decision."""
    if status == "verified":
        return f"\n\n✅ Verified by {escape_md(decided_by)}"
    return f"\n\n❌ Rejected by {escape_md(decided_by)}"


def build_user_verified_message(card: "ParsedCard", price: int) -> str:
    return (
        "✅ Your submission has been **verified** and added!\n\n"
        f"🃏 Character: {escape_md(card.char_name)}\n"
        f"{card.rarity_emoji} Rarity: {escape_md(card.rarity)}\n"
        f"{CURRENCY_EMOJI} Base Price: {price}\n\n"
        "Thanks for contributing! 🎉"
    )


def build_public_post_caption(
    card: "ParsedCard",
    price: int,
    submitted_by,
    highest_bid: Optional[int] = None,
    highest_bidder: Optional[str] = None,
) -> str:
    """Caption used when announcing a freshly verified card in the public
    channel / group, with the current highest bid (if any)."""
    lines = [
        "🎉 New card added to the collection!",
        "",
        f"📚 Anime: {escape_md(card.series)}",
        f"🃏 Character: {escape_md(card.char_name)} [[{card.theme_emoji}]]",
        f"{card.rarity_emoji} Rarity: {escape_md(card.rarity)}",
        f"🔖 Type: {TYPE_LABEL.get(card.card_type, card.card_type)}",
        f"{CURRENCY_EMOJI} Base Price: {price}",
    ]
    if highest_bid is not None:
        lines.append(
            f"🔥 Highest Bid: {highest_bid} ({highest_bidder})"
        )
    lines.append("")
    lines.append("Tap the button below to place a bid!")
    return "\n".join(lines)


def build_bid_instructions_message(submission_id: str, current_price: int) -> str:
    """Sent as an alert popup when someone taps the Place Bid button —
    tells them how to actually submit a bid amount."""
    return (
        f"{CURRENCY_EMOJI} Current price: {current_price}\n\n"
        f"To place a bid, send:\n/bid {submission_id} <amount>\n"
        "in this chat (must be higher than the current price/bid)."
    )


def build_bid_dm_prompt(card: "ParsedCard", current_amount: int) -> str:
    """Sent in the bot's DM right after a user taps 'Place Bid' and lands
    there via the deep link. Shows the card + current price/bid and asks
    them to reply with their bid amount."""
    return (
        f"🃏 **{escape_md(card.char_name)}** [[{card.theme_emoji}]]\n"
        f"{card.rarity_emoji} Rarity: {escape_md(card.rarity)}\n\n"
        f"{CURRENCY_EMOJI} Current price: {current_amount}\n\n"
        "Reply here with the amount you'd like to bid "
        "(must be higher than the current price/bid)."
    )


def build_cannot_bid_own_card_message() -> str:
    """Shown when a user tries to bid on a card they submitted themselves."""
    return "❌ You can't bid on your own card."


def build_bid_placed_message(card: "ParsedCard", amount: int) -> str:
    return (
        f"✅ Your bid of {amount} for **{escape_md(card.char_name)}** "
        "has been placed and is now the highest bid!"
    )


def build_bid_too_low_message(current_amount: int) -> str:
    return (
        f"❌ That bid is too low. The current highest is {current_amount}. "
        "Please send a higher amount."
    )


def build_outbid_notice(card: "ParsedCard", amount: int) -> str:
    return (
        f"⚠️ You've been outbid on **{escape_md(card.char_name)}**!\n"
        f"The new highest bid is {amount}."
    )


# ---------- Admin bid cancellation (/cancelbid) ----------

def build_cancel_bid_usage_message() -> str:
    return (
        "❌ Usage: `/cancelbid <item_id>`\n\n"
        "Cancels the current highest bid on that item and reverts it to "
        "the previous bid (or base price if there was no earlier bid)."
    )


def build_cancel_bid_no_bid_message() -> str:
    return "❌ There's no active bid on that item to cancel."


def build_cancel_bid_conflict_message() -> str:
    return "⚠️ A new bid just came in on that item — please try again."


def build_bid_cancelled_admin_confirmation(card: "ParsedCard", cancelled_amount: int, charge: int) -> str:
    return (
        f"✅ Cancelled the bid of {cancelled_amount} on **{escape_md(card.char_name)}**.\n\n"
        f"{CURRENCY_EMOJI} Cancellation charge: {charge} (10%) — owed by the bidder."
    )


def build_bid_cancelled_bidder_notice(card: "ParsedCard", cancelled_amount: int, charge: int) -> str:
    return (
        f"↩️ Your bid of {cancelled_amount} on **{escape_md(card.char_name)}** "
        "has been cancelled by an admin.\n\n"
        f"{CURRENCY_EMOJI} A cancellation charge of {charge} (10%) applies — "
        "please arrange payment with an admin."
    )


def build_bid_reinstated_notice(card: "ParsedCard", amount: int) -> str:
    return (
        f"🔁 A higher bid on **{escape_md(card.char_name)}** was just cancelled — "
        f"your bid of {amount} is now the highest again!"
    )


def build_user_rejected_message(card: "ParsedCard") -> str:
    return (
        "❌ Your submission was **rejected** by our verification team.\n\n"
        f"🃏 Character: {escape_md(card.char_name)}\n\n"
        "Please double check the details and feel free to try again with /add."
    )


def build_auction_ended_public_caption(
    card: "ParsedCard", price: int, final_bid: Optional[int], winner_mention: Optional[str]
) -> str:
    """
    Replaces a card's caption in the channel/group once its auction closes.
    winner_mention is an HTML <a> mention — send with parse_mode="HTML".
    """
    lines = [
        "🔒 Auction ended!",
        "",
        f"📚 Anime: {escape_html(card.series)}",
        f"🃏 Character: {escape_html(card.char_name)} [{escape_html(card.theme_emoji)}]",
        f"{card.rarity_emoji} Rarity: {escape_html(card.rarity)}",
        f"🔖 Type: {TYPE_LABEL.get(card.card_type, card.card_type)}",
    ]
    if final_bid is not None:
        lines.append(f"🏆 Sold for {final_bid} to {winner_mention}")
    else:
        lines.append(f"{CURRENCY_EMOJI} Base Price: {price}")
        lines.append("😶 No bids were placed — auction closed.")
    return "\n".join(lines)


def build_auction_won_announcement(
    card: "ParsedCard", seller_mention: str, winner_mention: str, final_bid: int
) -> str:
    """
    Posted in the group/channel announcing the auction result. Both mentions
    are HTML <a> links — send with parse_mode="HTML".
    """
    return (
        "🔨 <b>Auction Closed!</b>\n\n"
        f"🃏 Character: {escape_html(card.char_name)} [{escape_html(card.theme_emoji)}]\n"
        f"{card.rarity_emoji} Rarity: {escape_html(card.rarity)}\n\n"
        f"🏆 Winner: {winner_mention}\n"
        f"👤 Seller: {seller_mention}\n"
        f"{CURRENCY_EMOJI} Final Price: {final_bid}\n\n"
        "Congratulations! 🎉 Please coordinate the trade between yourselves."
    )


def build_auction_no_bids_announcement(card: "ParsedCard", seller_mention: str) -> str:
    """
    Posted in the group/channel when an auction closes with zero bids.
    seller_mention is an HTML <a> mention — send with parse_mode="HTML".
    """
    return (
        "🔨 <b>Auction Closed — No Bids</b>\n\n"
        f"🃏 Character: {escape_html(card.char_name)} [{escape_html(card.theme_emoji)}]\n"
        f"{card.rarity_emoji} Rarity: {escape_html(card.rarity)}\n\n"
        f"👤 Seller: {seller_mention}\n\n"
        "No one placed a bid before this auction closed."
    )


def build_winner_dm_message(card: "ParsedCard", final_bid: int, seller_mention: str) -> str:
    """
    DM sent to the winning bidder once the auction closes.
    seller_mention is an HTML <a> mention — send with parse_mode="HTML".
    """
    return (
        "🎉 <b>You won the auction!</b>\n\n"
        f"🃏 Character: {escape_html(card.char_name)} [{escape_html(card.theme_emoji)}]\n"
        f"{card.rarity_emoji} Rarity: {escape_html(card.rarity)}\n"
        f"{CURRENCY_EMOJI} Final Price: {final_bid}\n"
        f"👤 Seller: {seller_mention}\n\n"
        "Please coordinate with the seller to complete the trade."
    )


def build_seller_sold_dm_message(card: "ParsedCard", final_bid: int, winner_mention: str) -> str:
    """
    DM sent to the seller once their card sells at auction close.
    winner_mention is an HTML <a> mention — send with parse_mode="HTML".
    """
    return (
        "💰 <b>Your card has been sold!</b>\n\n"
        f"🃏 Character: {escape_html(card.char_name)} [{escape_html(card.theme_emoji)}]\n"
        f"{card.rarity_emoji} Rarity: {escape_html(card.rarity)}\n"
        f"{CURRENCY_EMOJI} Final Price: {final_bid}\n"
        f"🏆 Winner: {winner_mention}\n\n"
        "Please coordinate with the winner to complete the trade."
    )


def build_seller_no_bids_dm_message(card: "ParsedCard") -> str:
    """DM sent to the seller when their auction closes with no bids. Send with parse_mode="HTML"."""
    return (
        "😶 <b>Your auction ended with no bids.</b>\n\n"
        f"🃏 Character: {escape_html(card.char_name)} [[{escape_html(card.theme_emoji)}]]\n"
        f"{card.rarity_emoji} Rarity: {escape_html(card.rarity)}\n\n"
        "Feel free to submit it again with /add."
    )


def build_end_auction_usage_message() -> str:
    return (
        "❌ Usage: `/endauction <item_id>`\n\n"
        "You'll find an item's ID in its submission message in this log group."
    )


def build_end_auction_not_found_message() -> str:
    return "❌ No active auction found with that item ID."


def parse_price(text: str) -> Optional[int]:
    """
    Parses a base price from user input.
    Accepts plain digits, optionally with commas/spaces as thousand separators.
    Returns None if the input isn't a valid positive whole number.
    """
    if not text:
        return None

    cleaned = text.strip().replace(",", "").replace(" ", "")
    if not cleaned.isdigit():
        return None

    price = int(cleaned)
    if price <= 0:
        return None

    return price


# ---------- Caption parsing ----------

@dataclass
class ParsedCard:
    username: str
    card_type: str          # "waifu" or "husbando"
    series: str
    owned: str
    total: str
    card_id: str
    char_name: str
    theme_emoji: str
    copies: str
    rarity_emoji: str
    rarity: str              # normalized display form, e.g. "Celestial"


# Flexible pattern — tolerant of extra whitespace / blank lines between fields.
_CAPTION_RE = re.compile(
    r"OwO!\s*Check out\s*(?P<username>.+?)'s\s*(?P<type>waifu|husbando)"
    r".*?"
    r"(?P<series>\S.*?)\s+(?P<owned>\d+)\s*/\s*(?P<total>\d+)"
    r".*?"
    r"(?P<card_id>\d+)\s*:\s*(?P<char_name>.+?)\s*\[(?P<theme_emoji>[^\]]+)\]\s*x\s*(?P<copies>\d+)"
    r".*?"
    r"\(\s*(?P<rarity_emoji>\S+)\s*" + RARITY_LABEL + r"\s*:\s*(?P<rarity>[^)]+?)\s*\)",
    re.DOTALL,
)


def parse_card_caption(caption: str) -> Optional[ParsedCard]:
    """
    Parse a card caption in the bot's drop format:

        OwO! Check out <username>'s waifu

        <Series Name> <owned>/<total>
        <ID>: <Character Name> [<Theme Emoji>] x<copies>
        (<Rarity Emoji>RARITY: <Rarity>)

        <Theme Emoji>Theme<Theme Emoji>

    Returns a ParsedCard, or None if the caption doesn't match the format.
    """
    if not caption:
        return None

    match = _CAPTION_RE.search(caption)
    if not match:
        return None

    data = match.groupdict()
    return ParsedCard(
        username=data["username"].strip(),
        card_type=data["type"].strip().lower(),
        series=data["series"].strip(),
        owned=data["owned"].strip(),
        total=data["total"].strip(),
        card_id=data["card_id"].strip(),
        char_name=data["char_name"].strip(),
        theme_emoji=data["theme_emoji"].strip(),
        copies=data["copies"].strip(),
        rarity_emoji=data["rarity_emoji"].strip(),
        rarity=data["rarity"].strip(),
    )


def is_allowed_rarity(rarity: str) -> bool:
    """Check whether a parsed rarity string is one of the 3 allowed rarities."""
    return rarity.strip().lower() in ALLOWED_RARITIES
