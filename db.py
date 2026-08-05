import re
from datetime import datetime, timedelta, timezone

import certifi
from motor.motor_asyncio import AsyncIOMotorClient
from pymongo import ReturnDocument

from config import MONGO_URI, MONGO_DB_NAME, SUPER_ADMIN_ID

client = AsyncIOMotorClient(MONGO_URI, tlsCAFile=certifi.where())
db = client[MONGO_DB_NAME]

settings_col = db["settings"]
admins_col = db["admins"]
users_col = db["users"]
bans_col = db["bans"]
auctions_col = db["auctions"]
pending_submissions_col = db["pending_submissions"]


async def init_db() -> None:
    """Ensure indexes exist and the super admin is present. Call once at startup."""
    await admins_col.create_index("user_id", unique=True)
    await users_col.create_index("user_id", unique=True)
    await bans_col.create_index("user_id", unique=True)
    await auctions_col.create_index("submission_id", unique=True)
    await auctions_col.create_index([("status", 1), ("end_time", 1)])
    await pending_submissions_col.create_index("submission_id", unique=True)
    await db["giveaways"].create_index("ticket", unique=True)
    await db["giveaways"].create_index([("status", 1)])

    if SUPER_ADMIN_ID:
        await admins_col.update_one(
            {"user_id": SUPER_ADMIN_ID},
            {"$set": {"user_id": SUPER_ADMIN_ID, "role": "super_admin"}},
            upsert=True,
        )


# ---- Start image / caption ----

async def set_start_image(file_id: str, caption: str) -> None:
    await settings_col.update_one(
        {"key": "start_image"},
        {"$set": {"file_id": file_id, "caption": caption}},
        upsert=True,
    )


async def get_start_image() -> tuple[str | None, str | None]:
    """Returns (file_id, caption). Either may be None if never set."""
    doc = await settings_col.find_one({"key": "start_image"})
    if not doc:
        return None, None
    return doc.get("file_id"), doc.get("caption")


# ---- Admins ----

async def is_admin(user_id: int) -> bool:
    if user_id == SUPER_ADMIN_ID:
        return True
    doc = await admins_col.find_one({"user_id": user_id})
    return doc is not None


async def add_admin(user_id: int) -> bool:
    """Returns True if newly added, False if already an admin."""
    existing = await admins_col.find_one({"user_id": user_id})
    if existing:
        return False
    await admins_col.insert_one({"user_id": user_id, "role": "admin"})
    return True


async def remove_admin(user_id: int) -> bool:
    """
    Returns True if the user was an admin and got removed, False if they
    weren't an admin to begin with. The super admin can never be removed
    this way — protects against locking everyone out of admin commands.
    """
    if user_id == SUPER_ADMIN_ID:
        return False

    result = await admins_col.delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def get_all_admins() -> list[int]:
    cursor = admins_col.find({})
    return [doc["user_id"] async for doc in cursor]


# ---- Users (everyone who has started the bot) ----

async def upsert_user(user_id: int, username: str | None, first_name: str | None) -> bool:
    """
    Records/updates a user. Returns True if this is a brand-new user
    (first time ever starting the bot), False if they already existed.
    """
    existing = await users_col.find_one({"user_id": user_id})

    await users_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "username": username,
                "first_name": first_name,
                "last_started_at": datetime.now(timezone.utc),
            },
            "$setOnInsert": {"first_started_at": datetime.now(timezone.utc)},
        },
        upsert=True,
    )

    return existing is None


async def get_user_count() -> int:
    return await users_col.count_documents({})


async def get_user_by_username(username: str) -> int | None:
    """
    Looks up a stored user's id by their @username (case-insensitive),
    among users who have started the bot at least once. Telegram's Bot API
    has no general "resolve @username to id" call, so this only works for
    users already recorded in `users_col` — reply-to-message or a raw
    numeric id always work regardless.
    """
    doc = await users_col.find_one(
        {"username": {"$regex": f"^{re.escape(username)}$", "$options": "i"}}
    )
    return doc["user_id"] if doc else None


# ---- Global bans ----

async def ban_user(user_id: int, banned_by: int, reason: str | None = None) -> bool:
    """
    Globally bans a user. Returns True if newly banned, False if they were
    already banned (their reason/banned_by get updated regardless).
    """
    existing = await bans_col.find_one({"user_id": user_id})
    await bans_col.update_one(
        {"user_id": user_id},
        {
            "$set": {
                "user_id": user_id,
                "banned_by": banned_by,
                "banned_at": datetime.now(timezone.utc),
                "reason": reason,
            }
        },
        upsert=True,
    )
    return existing is None


async def unban_user(user_id: int) -> bool:
    """Returns True if the user was banned and got unbanned, False otherwise."""
    result = await bans_col.delete_one({"user_id": user_id})
    return result.deleted_count > 0


async def is_banned(user_id: int) -> bool:
    doc = await bans_col.find_one({"user_id": user_id})
    return doc is not None


# ---- Pending submissions (awaiting admin verify/reject) ----

async def create_pending_submission(
    submission_id: str,
    card: dict,
    price: int,
    user_id: int | None,
    caption: str,
    photo_file_id: str,
    submitted_by: str,
) -> None:
    await pending_submissions_col.insert_one(
        {
            "submission_id": submission_id,
            "card": card,
            "price": price,
            "user_id": user_id,
            "caption": caption,
            "photo_file_id": photo_file_id,
            "submitted_by": submitted_by,
            "created_at": datetime.now(timezone.utc),
        }
    )


async def get_pending_submission(submission_id: str) -> dict | None:
    return await pending_submissions_col.find_one({"submission_id": submission_id})


async def delete_pending_submission(submission_id: str) -> None:
    await pending_submissions_col.delete_one({"submission_id": submission_id})


# ---- Auctions ----
#
# bid_history keeps every accepted bid in order (each entry:
# {bidder_id, bidder_name, amount}). This is what makes /cancelbid possible
# — cancelling pops the current highest bid off the end of the list and
# reverts highest_bid/highest_bidder back to whatever the previous entry
# was (or to "no bids" if the cancelled bid was the only one).

async def create_auction(
    submission_id: str,
    card: dict,
    price: int,
    submitted_by: str,
    owner_id: int | None,
    channel_message_id: int,
    group_message_id: int,
    duration_seconds: int,
) -> None:
    end_time = datetime.now(timezone.utc) + timedelta(seconds=duration_seconds)
    await auctions_col.insert_one(
        {
            "submission_id": submission_id,
            "status": "active",
            "card": card,
            "price": price,
            "submitted_by": submitted_by,
            "owner_id": owner_id,
            "highest_bid": None,
            "highest_bidder_id": None,
            "highest_bidder_name": None,
            "bid_history": [],
            "channel_message_id": channel_message_id,
            "group_message_id": group_message_id,
            "end_time": end_time,
        }
    )


async def get_auction(submission_id: str) -> dict | None:
    return await auctions_col.find_one({"submission_id": submission_id, "status": "active"})


async def get_active_auctions() -> list[dict]:
    cursor = auctions_col.find({"status": "active"})
    return [doc async for doc in cursor]


async def place_bid(submission_id: str, amount: int, bidder_id: int, bidder_name: str) -> dict:
    """
    Atomically raises the highest bid, but only if `amount` still beats the
    current highest (or base price) at the moment of the write — this closes
    the race window where two people bid at nearly the same instant. Also
    appends the accepted bid to bid_history so it can be reverted to later
    via admin_cancel_highest_bid.

    Returns one of:
      {"status": "ok", "previous_bidder_id": <id or None>}
      {"status": "too_low", "current_amount": <int>}
      {"status": "not_found"}
    """
    doc = await auctions_col.find_one_and_update(
        {
            "submission_id": submission_id,
            "status": "active",
            "$or": [{"highest_bid": None}, {"highest_bid": {"$lt": amount}}],
        },
        {
            "$set": {
                "highest_bid": amount,
                "highest_bidder_id": bidder_id,
                "highest_bidder_name": bidder_name,
            },
            "$push": {
                "bid_history": {
                    "bidder_id": bidder_id,
                    "bidder_name": bidder_name,
                    "amount": amount,
                }
            },
        },
        return_document=ReturnDocument.BEFORE,
    )
    if doc is not None:
        return {"status": "ok", "previous_bidder_id": doc.get("highest_bidder_id")}

    existing = await auctions_col.find_one({"submission_id": submission_id})
    if existing is None or existing.get("status") != "active":
        return {"status": "not_found"}
    current_amount = existing.get("highest_bid")
    if current_amount is None:
        current_amount = existing.get("price")
    return {"status": "too_low", "current_amount": current_amount}


async def admin_cancel_highest_bid(submission_id: str) -> dict:
    """
    Admin-only action: cancels whichever bid is currently highest on an
    item, regardless of who placed it — unlike a self-service cancel, this
    doesn't check who's calling; that check belongs in the handler via the
    @admin_only decorator. Reverts highest_bid/highest_bidder back to the
    previous entry in bid_history (or to "no bids" if the cancelled bid
    was the only one).

    Returns one of:
      {"status": "ok", "cancelled_bidder_id": <int>, "cancelled_amount": <int>,
       "new_highest_bid": <int or None>,
       "new_highest_bidder_id": <int or None>,
       "new_highest_bidder_name": <str or None>}
      {"status": "not_found"}
      {"status": "no_bid"}
      {"status": "conflict"}   # a new bid landed between read and write — retry
    """
    doc = await auctions_col.find_one({"submission_id": submission_id, "status": "active"})
    if doc is None:
        return {"status": "not_found"}

    history = doc.get("bid_history", [])
    if not history:
        return {"status": "no_bid"}

    cancelled_entry = history[-1]
    new_history = history[:-1]

    if new_history:
        prev = new_history[-1]
        new_highest_bid = prev["amount"]
        new_highest_bidder_id = prev["bidder_id"]
        new_highest_bidder_name = prev["bidder_name"]
    else:
        new_highest_bid = None
        new_highest_bidder_id = None
        new_highest_bidder_name = None

    result = await auctions_col.find_one_and_update(
        {
            "submission_id": submission_id,
            "status": "active",
            "highest_bid": doc.get("highest_bid"),
            "highest_bidder_id": doc.get("highest_bidder_id"),
        },
        {
            "$set": {
                "highest_bid": new_highest_bid,
                "highest_bidder_id": new_highest_bidder_id,
                "highest_bidder_name": new_highest_bidder_name,
                "bid_history": new_history,
            }
        },
        return_document=ReturnDocument.AFTER,
    )

    if result is None:
        return {"status": "conflict"}

    return {
        "status": "ok",
        "cancelled_bidder_id": cancelled_entry["bidder_id"],
        "cancelled_amount": cancelled_entry["amount"],
        "new_highest_bid": new_highest_bid,
        "new_highest_bidder_id": new_highest_bidder_id,
        "new_highest_bidder_name": new_highest_bidder_name,
    }


async def get_due_auction_ids(limit: int = 100) -> list[str]:
    """Submission ids of active auctions whose end_time has already passed."""
    now = datetime.now(timezone.utc)
    cursor = auctions_col.find(
        {"status": "active", "end_time": {"$lte": now}},
        {"submission_id": 1},
    ).limit(limit)
    return [doc["submission_id"] async for doc in cursor]


async def claim_auction_for_closing(submission_id: str) -> dict | None:
    """
    Atomically flips an active auction to 'closed' and returns its data.
    Returns None if it was already closed/doesn't exist — protects against
    double-processing if /endauction and the periodic check ever overlap.
    """
    return await auctions_col.find_one_and_update(
        {"submission_id": submission_id, "status": "active"},
        {"$set": {"status": "closed"}},
    )


# ---- Giveaways ----
#
# Collection: giveaways
# Schema per document:
# {
#     "ticket":               str,       # unique 8-char code
#     "total_winners":        int,       # how many slots to fill
#     "status":               str,       # "active" | "closed"
#     "participation_closed": bool,      # True once deadline passes
#     "deadline":             datetime,  # UTC, when entries stop
#     "participants":         list[{user_id, display_name}],
#     "drawn_slots":          dict,      # {"1": {user_id, display_name}, ...}
#                                        # keys are STRINGS (MongoDB requirement)
#     "created_at":           datetime,
# }

async def create_giveaway(
    ticket: str,
    total_winners: int,
    deadline: datetime,
) -> None:
    """Create a fresh giveaway. Called by /giveaway."""
    await db["giveaways"].insert_one(
        {
            "ticket": ticket,
            "total_winners": total_winners,
            "status": "active",
            "participation_closed": False,
            "deadline": deadline,
            "participants": [],
            "drawn_slots": {},
            "created_at": datetime.now(timezone.utc),
        }
    )


async def get_active_giveaway() -> dict | None:
    """Returns the single active giveaway document, or None."""
    return await db["giveaways"].find_one({"status": "active"})


async def add_giveaway_participant(
    ticket: str,
    user_id: int,
    display_name: str,
) -> str:
    """
    Register a user in the active giveaway.

    Returns:
      "ok"             — successfully added
      "already_joined" — user already entered
      "not_found"      — no active giveaway with that ticket
    """
    giveaway = await db["giveaways"].find_one({"ticket": ticket, "status": "active"})
    if giveaway is None:
        return "not_found"

    if any(p["user_id"] == user_id for p in giveaway.get("participants", [])):
        return "already_joined"

    await db["giveaways"].update_one(
        {"ticket": ticket, "status": "active"},
        {
            "$push": {
                "participants": {
                    "user_id": user_id,
                    "display_name": display_name,
                }
            }
        },
    )
    return "ok"


async def get_giveaway_participants(ticket: str) -> list[dict]:
    """Returns the full participants list for a giveaway ticket."""
    giveaway = await db["giveaways"].find_one({"ticket": ticket})
    if giveaway is None:
        return []
    return giveaway.get("participants", [])


async def mark_giveaway_slot_drawn(
    ticket: str,
    slot: int,
    user_id: int,
    display_name: str,
) -> None:
    """
    Records a winner for a specific slot.
    Slot number is stored as a string key (MongoDB doesn't allow int dict keys).
    Called by /select and internally by /cancelwinner after the re-draw.
    """
    await db["giveaways"].update_one(
        {"ticket": ticket},
        {
            "$set": {
                f"drawn_slots.{slot}": {
                    "user_id": user_id,
                    "display_name": display_name,
                }
            }
        },
    )


async def get_giveaway_drawn_slots(ticket: str) -> dict:
    """
    Returns drawn slots as {int_slot: {user_id, display_name}}.
    String keys from MongoDB are cast back to int for easy comparison
    in the handler (e.g. `if slot in drawn_slots`).
    """
    giveaway = await db["giveaways"].find_one({"ticket": ticket})
    if giveaway is None:
        return {}
    return {int(k): v for k, v in giveaway.get("drawn_slots", {}).items()}


async def cancel_giveaway_slot(ticket: str, slot: int) -> None:
    """
    Removes a drawn slot so it becomes empty and can be re-drawn.
    Called by /cancelwinner before picking a new winner for that slot.
    Uses $unset so the key is fully removed from the drawn_slots dict.
    """
    await db["giveaways"].update_one(
        {"ticket": ticket},
        {"$unset": {f"drawn_slots.{slot}": ""}},
    )


async def close_giveaway_participation(ticket: str) -> None:
    """
    Marks participation as closed once the deadline passes.
    The giveaway itself stays "active" so winners can still be drawn —
    this only stops new /participate entries from being accepted.
    Called by the background job and as a fallback in /participate.
    """
    await db["giveaways"].update_one(
        {"ticket": ticket},
        {"$set": {"participation_closed": True}},
    )


async def close_giveaway(ticket: str) -> None:
    """
    Fully closes the giveaway (status → "closed") once all winner
    slots have been filled. After this, get_active_giveaway() returns
    None, allowing a new giveaway to be started.
    """
    await db["giveaways"].update_one(
        {"ticket": ticket},
        {"$set": {"status": "closed"}},
    )
