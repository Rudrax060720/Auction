"""
Giveaway system.

/giveaway <winners> <duration>  — super admin only; creates a giveaway with a
                                  unique ticket, time limit and winner count,
                                  posts it to the group + channel.
                                  Duration format: 30m / 2h / 1d
/participate <ticket>           — DM only; join the active giveaway before
                                  the deadline. Must be in group + channel.
/select <number>                — super admin only; draw winner #<number>
                                  randomly (1 … total_winners).
/cancelwinner <number>          — super admin only; cancel a drawn winner slot
                                  and re-draw a new one from remaining participants.
"""

import random
import secrets
import string
from datetime import datetime, timedelta, timezone

from telegram import Update
from telegram.ext import CommandHandler, ContextTypes, Application

from config import GROUP_CHAT_ID, CHANNEL_CHAT_ID
from db import (
    create_giveaway,
    get_active_giveaway,
    add_giveaway_participant,
    get_giveaway_participants,
    mark_giveaway_slot_drawn,
    get_giveaway_drawn_slots,
    cancel_giveaway_slot,
    close_giveaway,
    close_giveaway_participation,
)
from utils import check_membership, super_admin_only


# ---------- helpers ----------

def _generate_ticket() -> str:
    """8-character uppercase alphanumeric ticket code."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(8))


def _ordinal(n: int) -> str:
    suffixes = {1: "st", 2: "nd", 3: "rd"}
    return f"{n}{suffixes.get(n if n < 20 else n % 10, 'th')}"


def _parse_duration(text: str) -> timedelta | None:
    """Parses 30m / 2h / 1d into a timedelta. Returns None if invalid."""
    text = text.strip().lower()
    if len(text) < 2:
        return None
    unit = text[-1]
    try:
        value = int(text[:-1])
    except ValueError:
        return None
    if value <= 0:
        return None
    if unit == "m":
        return timedelta(minutes=value)
    if unit == "h":
        return timedelta(hours=value)
    if unit == "d":
        return timedelta(days=value)
    return None


def _format_deadline(deadline: datetime) -> str:
    return deadline.strftime("%d %b %Y, %H:%M UTC")


def _format_duration(td: timedelta) -> str:
    total_seconds = int(td.total_seconds())
    if total_seconds >= 86400 and total_seconds % 86400 == 0:
        v = total_seconds // 86400
        return f"{v} day{'s' if v != 1 else ''}"
    if total_seconds >= 3600 and total_seconds % 3600 == 0:
        v = total_seconds // 3600
        return f"{v} hour{'s' if v != 1 else ''}"
    v = total_seconds // 60
    return f"{v} minute{'s' if v != 1 else ''}"


def _aware(dt: datetime) -> datetime:
    """Ensure a datetime is UTC-aware (Motor can return naive datetimes)."""
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=timezone.utc)


# ---------- background job ----------

async def check_giveaway_deadlines(context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Runs every minute via JobQueue. Closes participation on any giveaway
    whose deadline has passed. Winners can still be drawn after this —
    participation just stops accepting new entries.
    """
    giveaway = await get_active_giveaway()
    if giveaway is None or giveaway.get("participation_closed"):
        return

    deadline = giveaway.get("deadline")
    if deadline is None:
        return

    if datetime.now(timezone.utc) < _aware(deadline):
        return

    await close_giveaway_participation(giveaway["ticket"])

    participant_count = len(giveaway.get("participants", []))
    announcement = (
        "⏰ <b>Giveaway participation is now closed!</b>\n\n"
        f"🎟 Ticket: <code>{giveaway['ticket']}</code>\n"
        f"👥 Total participants: <b>{participant_count}</b>\n\n"
        "🏆 Winners will be announced shortly. Stay tuned!"
    )
    for chat_id in (GROUP_CHAT_ID, CHANNEL_CHAT_ID):
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=announcement, parse_mode="HTML"
            )
        except Exception:
            pass


# ---------- /giveaway ----------

@super_admin_only
async def giveaway_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /giveaway <number_of_winners> <duration>
    Duration examples: 30m, 2h, 1d
    """
    message = update.message
    if message is None:
        return

    usage = (
        "❌ Usage: `/giveaway <winners> <duration>`\n\n"
        "Examples:\n"
        "`/giveaway 3 2h` — 3 winners, 2 hour entry window\n"
        "`/giveaway 1 30m` — 1 winner, 30 minute entry window\n"
        "`/giveaway 5 1d` — 5 winners, 1 day entry window\n\n"
        "Duration units: `m` = minutes, `h` = hours, `d` = days"
    )

    if len(context.args or []) < 2:
        await message.reply_text(usage, parse_mode="Markdown")
        return

    if not context.args[0].isdigit() or int(context.args[0]) < 1:
        await message.reply_text(usage, parse_mode="Markdown")
        return

    total_winners = int(context.args[0])
    duration = _parse_duration(context.args[1])
    if duration is None:
        await message.reply_text(usage, parse_mode="Markdown")
        return

    existing = await get_active_giveaway()
    if existing:
        deadline = existing.get("deadline")
        deadline_str = _format_deadline(_aware(deadline)) if deadline else "unknown"
        await message.reply_text(
            f"⚠️ There's already an active giveaway!\n\n"
            f"🎟 Ticket: `{existing['ticket']}`\n"
            f"⏰ Deadline: {deadline_str}\n"
            f"👥 Participants so far: {len(existing.get('participants', []))}\n\n"
            "Close it first before starting a new one.",
            parse_mode="Markdown",
        )
        return

    ticket = _generate_ticket()
    deadline = datetime.now(timezone.utc) + duration
    await create_giveaway(ticket=ticket, total_winners=total_winners, deadline=deadline)

    duration_str = _format_duration(duration)
    deadline_str = _format_deadline(deadline)

    announcement = (
        "🎉 <b>GIVEAWAY TIME!</b> 🎉\n\n"
        f"🏆 Winners: <b>{total_winners}</b>\n"
        f"🎟 Ticket Code: <code>{ticket}</code>\n"
        f"⏰ Participation closes in: <b>{duration_str}</b>\n"
        f"🕐 Deadline: <b>{deadline_str}</b>\n\n"
        "📩 <b>How to participate:</b>\n"
        "1️⃣ Make sure you've joined both the group and channel\n"
        "2️⃣ Open the bot in DM\n"
        f"3️⃣ Send: <code>/participate {ticket}</code>\n\n"
        "Good luck to everyone! 🍀"
    )

    for chat_id in (GROUP_CHAT_ID, CHANNEL_CHAT_ID):
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=announcement, parse_mode="HTML"
            )
        except Exception:
            pass

    await message.reply_text(
        f"✅ Giveaway created!\n\n"
        f"🎟 Ticket: `{ticket}`\n"
        f"🏆 Winners: {total_winners}\n"
        f"⏰ Duration: {duration_str}\n"
        f"🕐 Deadline: {deadline_str}\n\n"
        f"Use `/select 1` through `/select {total_winners}` to draw each winner.\n"
        f"Use `/cancelwinner <number>` to cancel a drawn slot and re-draw.",
        parse_mode="Markdown",
    )


# ---------- /participate ----------

async def participate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /participate <ticket>
    DM only. Registers the user if deadline hasn't passed and they're in
    both the group and channel.
    """
    message = update.message
    user = update.effective_user
    if message is None or user is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type != "private":
        await message.reply_text("📩 Please use this command in my DM only.")
        return

    if not context.args:
        await message.reply_text(
            "❌ Please include the ticket code.\n"
            "Example: `/participate ABC12345`",
            parse_mode="Markdown",
        )
        return

    ticket = context.args[0].strip().upper()

    giveaway = await get_active_giveaway()
    if giveaway is None:
        await message.reply_text("😶 There's no active giveaway right now.")
        return

    if giveaway["ticket"] != ticket:
        await message.reply_text(
            "❌ That ticket code is invalid.\n"
            "Double-check the code posted in the group/channel."
        )
        return

    # Deadline check
    if giveaway.get("participation_closed"):
        await message.reply_text(
            "⏰ Sorry, participation for this giveaway is now <b>closed</b>.\n"
            "Winners will be announced shortly!",
            parse_mode="HTML",
        )
        return

    deadline = giveaway.get("deadline")
    if deadline and datetime.now(timezone.utc) > _aware(deadline):
        await close_giveaway_participation(ticket)
        await message.reply_text(
            "⏰ Sorry, the participation deadline has passed!\n"
            "Winners will be announced shortly."
        )
        return

    in_group, in_channel = await check_membership(context.bot, user.id)
    if not in_group or not in_channel:
        await message.reply_text(
            "🚫 You need to be a member of both our group and channel to participate.\n\n"
            "Please join both, then try again."
        )
        return

    display_name = (
        user.full_name
        or (f"@{user.username}" if user.username else f"User{user.id}")
    )
    result = await add_giveaway_participant(
        ticket=ticket, user_id=user.id, display_name=display_name
    )

    deadline_str = _format_deadline(_aware(deadline)) if deadline else "soon"

    if result == "already_joined":
        await message.reply_text(
            "✅ You're already registered in this giveaway! Good luck 🍀\n\n"
            f"⏰ Participation closes: <b>{deadline_str}</b>",
            parse_mode="HTML",
        )
        return

    if result == "not_found":
        await message.reply_text("😶 There's no active giveaway with that ticket.")
        return

    await message.reply_text(
        f"🎉 You're in! Good luck, <b>{display_name}</b>! 🍀\n\n"
        f"🎟 Ticket: <code>{ticket}</code>\n"
        f"⏰ Participation closes: <b>{deadline_str}</b>\n\n"
        "We'll announce the winners when the giveaway ends.",
        parse_mode="HTML",
    )


# ---------- shared draw logic ----------

async def _draw_slot(bot, giveaway: dict, slot: int) -> dict | None:
    """
    Picks a random eligible participant for `slot` and records them.
    Returns the winner dict, or None if no eligible participants remain.
    Eligible = participated + not already holding another slot.
    """
    participants = await get_giveaway_participants(giveaway["ticket"])
    drawn_slots = await get_giveaway_drawn_slots(giveaway["ticket"])

    already_won_ids = {v["user_id"] for k, v in drawn_slots.items() if k != slot}
    eligible = [p for p in participants if p["user_id"] not in already_won_ids]

    if not eligible:
        return None

    winner = random.choice(eligible)
    await mark_giveaway_slot_drawn(
        ticket=giveaway["ticket"],
        slot=slot,
        user_id=winner["user_id"],
        display_name=winner["display_name"],
    )
    return winner


# ---------- /select ----------

@super_admin_only
async def select_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /select <number>
    Draws one winner slot. Each slot can only be drawn once (use
    /cancelwinner to redo a slot). Winner is chosen randomly from
    participants who don't already hold another slot.
    """
    message = update.message
    if message is None:
        return

    if not context.args or not context.args[0].isdigit():
        await message.reply_text(
            "❌ Usage: `/select <number>`\n"
            "Example: `/select 1` to draw the 1st winner.",
            parse_mode="Markdown",
        )
        return

    slot = int(context.args[0])

    giveaway = await get_active_giveaway()
    if giveaway is None:
        await message.reply_text("😶 There's no active giveaway right now.")
        return

    total_winners = giveaway["total_winners"]

    if slot < 1 or slot > total_winners:
        await message.reply_text(
            f"❌ Invalid number. This giveaway has {total_winners} winner(s).\n"
            f"Use a number between 1 and {total_winners}.",
        )
        return

    drawn_slots = await get_giveaway_drawn_slots(giveaway["ticket"])

    if slot in drawn_slots:
        already = drawn_slots[slot]
        await message.reply_text(
            f"⚠️ Slot {slot} was already drawn.\n"
            f"Winner: <b>{already['display_name']}</b>\n\n"
            f"Use `/cancelwinner {slot}` to cancel and re-draw this slot.",
            parse_mode="HTML",
        )
        return

    participants = await get_giveaway_participants(giveaway["ticket"])
    if not participants:
        await message.reply_text("😶 No one has participated in this giveaway yet.")
        return

    winner = await _draw_slot(context.bot, giveaway, slot)
    if winner is None:
        await message.reply_text(
            "⚠️ All participants have already won a slot!\n"
            "There aren't enough unique participants to fill all winner slots."
        )
        return

    updated_drawn = await get_giveaway_drawn_slots(giveaway["ticket"])
    all_slots_filled = len(updated_drawn) >= total_winners
    slot_label = _ordinal(slot)

    announcement = (
        f"🏆 <b>{slot_label} Winner!</b>\n\n"
        f"🎉 Congratulations to <b>{winner['display_name']}</b>!\n\n"
        f"🎟 Giveaway Ticket: <code>{giveaway['ticket']}</code>"
    )
    if all_slots_filled:
        await close_giveaway(giveaway["ticket"])
        announcement += "\n\n🔒 <b>All winners drawn! Giveaway is now closed.</b>"

    for chat_id in (GROUP_CHAT_ID, CHANNEL_CHAT_ID):
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=announcement, parse_mode="HTML"
            )
        except Exception:
            pass

    # DM the winner
    try:
        await context.bot.send_message(
            chat_id=winner["user_id"],
            text=(
                f"🎉 <b>Congratulations! You won the giveaway!</b>\n\n"
                f"🏆 You are the <b>{slot_label}</b> winner!\n"
                f"🎟 Ticket: <code>{giveaway['ticket']}</code>\n\n"
                "Please coordinate with an admin to claim your prize. 🎁"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    remaining = [s for s in range(1, total_winners + 1) if s not in updated_drawn]
    if remaining:
        remaining_str = ", ".join(f"`/select {s}`" for s in remaining)
        await message.reply_text(
            f"✅ {slot_label} winner drawn: <b>{winner['display_name']}</b>\n\n"
            f"Remaining slots: {remaining_str}",
            parse_mode="HTML",
        )
    else:
        await message.reply_text(
            f"✅ {slot_label} winner drawn: <b>{winner['display_name']}</b>\n\n"
            "🔒 All winners drawn. Giveaway closed!",
            parse_mode="HTML",
        )


# ---------- /cancelwinner ----------

@super_admin_only
async def cancel_winner_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    /cancelwinner <number>
    Cancels the winner in slot <number> and immediately re-draws a new
    one from the remaining eligible participants. The cancelled winner is
    DM'd to let them know, and the new winner is announced in the group
    and channel just like a normal draw.
    """
    message = update.message
    if message is None:
        return

    if not context.args or not context.args[0].isdigit():
        await message.reply_text(
            "❌ Usage: `/cancelwinner <number>`\n"
            "Example: `/cancelwinner 2` to cancel and re-draw the 2nd winner slot.",
            parse_mode="Markdown",
        )
        return

    slot = int(context.args[0])

    giveaway = await get_active_giveaway()
    if giveaway is None:
        await message.reply_text("😶 There's no active giveaway right now.")
        return

    total_winners = giveaway["total_winners"]

    if slot < 1 or slot > total_winners:
        await message.reply_text(
            f"❌ Invalid number. This giveaway has {total_winners} winner(s).\n"
            f"Use a number between 1 and {total_winners}.",
        )
        return

    drawn_slots = await get_giveaway_drawn_slots(giveaway["ticket"])

    if slot not in drawn_slots:
        await message.reply_text(
            f"❌ Slot {slot} hasn't been drawn yet.\n"
            f"Use `/select {slot}` to draw it first.",
            parse_mode="Markdown",
        )
        return

    cancelled_winner = drawn_slots[slot]

    # Remove this slot so _draw_slot can re-pick it
    await cancel_giveaway_slot(ticket=giveaway["ticket"], slot=slot)

    # Notify the cancelled winner in DM
    try:
        await context.bot.send_message(
            chat_id=cancelled_winner["user_id"],
            text=(
                f"ℹ️ Your win in the giveaway (<code>{giveaway['ticket']}</code>) "
                f"for slot <b>{_ordinal(slot)}</b> has been <b>cancelled</b> by an admin.\n\n"
                "Sorry about that — please reach out to an admin if you have questions."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    # Re-draw — fetch fresh giveaway state after the cancel
    giveaway = await get_active_giveaway()
    if giveaway is None:
        await message.reply_text(
            "⚠️ Slot cancelled, but the giveaway closed in the meantime."
        )
        return

    new_winner = await _draw_slot(context.bot, giveaway, slot)

    if new_winner is None:
        await message.reply_text(
            f"↩️ Cancelled <b>{cancelled_winner['display_name']}</b>'s win for slot {slot}.\n\n"
            "⚠️ No eligible participants left to re-draw from.\n"
            f"Use `/select {slot}` again once new participants are available.",
            parse_mode="HTML",
        )
        return

    slot_label = _ordinal(slot)
    announcement = (
        f"🔄 <b>Winner Re-drawn — {slot_label} Place!</b>\n\n"
        f"🎉 Congratulations to <b>{new_winner['display_name']}</b>!\n\n"
        f"🎟 Giveaway Ticket: <code>{giveaway['ticket']}</code>"
    )

    # Check if all slots are now filled
    updated_drawn = await get_giveaway_drawn_slots(giveaway["ticket"])
    all_slots_filled = len(updated_drawn) >= total_winners
    if all_slots_filled:
        await close_giveaway(giveaway["ticket"])
        announcement += "\n\n🔒 <b>All winners drawn! Giveaway is now closed.</b>"

    for chat_id in (GROUP_CHAT_ID, CHANNEL_CHAT_ID):
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=announcement, parse_mode="HTML"
            )
        except Exception:
            pass

    # DM the new winner
    try:
        await context.bot.send_message(
            chat_id=new_winner["user_id"],
            text=(
                f"🎉 <b>Congratulations! You won the giveaway!</b>\n\n"
                f"🏆 You are the <b>{slot_label}</b> winner!\n"
                f"🎟 Ticket: <code>{giveaway['ticket']}</code>\n\n"
                "Please coordinate with an admin to claim your prize. 🎁"
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    await message.reply_text(
        f"↩️ Cancelled: <b>{cancelled_winner['display_name']}</b>\n"
        f"✅ New {slot_label} winner: <b>{new_winner['display_name']}</b>",
        parse_mode="HTML",
    )


# ---------- registration ----------

def register_giveaway_handlers(app: Application) -> None:
    app.add_handler(CommandHandler("giveaway", giveaway_command))
    app.add_handler(CommandHandler("participate", participate_command))
    app.add_handler(CommandHandler("select", select_command))
    app.add_handler(CommandHandler("cancelwinner", cancel_winner_command))
