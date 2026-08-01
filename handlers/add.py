from dataclasses import asdict

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters,
)

from utils import check_membership, admin_only
from db import (
    create_pending_submission,
    get_pending_submission,
    delete_pending_submission,
    create_auction,
    get_auction,
    place_bid,
    admin_cancel_highest_bid,
    get_due_auction_ids,
    claim_auction_for_closing,
)
from utils.addutils import (
    escape_html,
    get_add_choice_keyboard,
    get_verification_keyboard,
    get_bid_keyboard,
    build_rarity_notice,
    build_success_message,
    build_wrong_type_message,
    build_wrong_rarity_message,
    build_parse_failed_message,
    build_price_prompt_message,
    build_invalid_price_message,
    build_pending_verification_message,
    build_log_caption,
    build_log_decision_suffix,
    build_user_verified_message,
    build_user_rejected_message,
    build_public_post_caption,
    build_bid_placed_message,
    build_bid_too_low_message,
    build_outbid_notice,
    build_user_mention,
    build_mention,
    build_mention_from_id,
    get_display_name,
    build_bid_dm_prompt,
    build_cannot_bid_own_card_message,
    build_auction_ended_public_caption,
    build_auction_won_announcement,
    build_auction_no_bids_announcement,
    build_winner_dm_message,
    build_seller_sold_dm_message,
    build_seller_no_bids_dm_message,
    build_end_auction_usage_message,
    build_end_auction_not_found_message,
    build_cancel_bid_usage_message,
    build_cancel_bid_no_bid_message,
    build_cancel_bid_conflict_message,
    build_bid_cancelled_admin_confirmation,
    build_bid_cancelled_bidder_notice,
    build_bid_reinstated_notice,
    calculate_cancellation_charge,
    parse_card_caption,
    parse_price,
    is_allowed_rarity,
    CALLBACK_TO_TYPE,
    TYPE_LABEL,
    CB_VERIFY_PREFIX,
    CB_REJECT_PREFIX,
    CB_BID_PREFIX,
    AUCTION_DURATION_SECONDS,
    LOG_GROUP_ID,
    CHANNEL_CHAT_ID,
    GROUP_CHAT_ID,
    ParsedCard,
)


# ---------- /add command ----------
async def add_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type != "private":
        await message.reply_text(
            "❌ This command can only be used in my DM, not in groups."
        )
        return

    if context.user_data is not None:
        context.user_data.pop("add_type", None)
        context.user_data.pop("awaiting_price", None)
        context.user_data.pop("pending_card", None)
        context.user_data.pop("pending_photo", None)

    await message.reply_text(
        "Choose what you want to add:",
        reply_markup=get_add_choice_keyboard(),
    )


# ---------- Callback handler for the choice buttons ----------
async def add_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.data is None:
        return

    await query.answer()

    add_type = CALLBACK_TO_TYPE.get(query.data)
    if add_type is None:
        return

    if context.user_data is not None:
        context.user_data["add_type"] = add_type
        context.user_data.pop("awaiting_price", None)
        context.user_data.pop("pending_card", None)
        context.user_data.pop("pending_photo", None)

    kind_label = TYPE_LABEL[add_type]

    await query.edit_message_text(
        build_rarity_notice(kind_label),
        parse_mode="Markdown",
    )


# ---------- Handler for the actual card submission (photo + caption) ----------
async def add_card_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type != "private":
        return

    user_data = context.user_data or {}
    add_type = user_data.get("add_type")

    if add_type is None:
        await message.reply_text(
            "ℹ️ Please use /add first and choose Husbando or Waifu before sending a card."
        )
        return

    caption = message.caption or ""
    parsed = parse_card_caption(caption)

    if parsed is None:
        await message.reply_text(build_parse_failed_message(), parse_mode="Markdown")
        return

    if parsed.card_type != add_type:
        await message.reply_text(
            build_wrong_type_message(add_type, parsed.card_type),
            parse_mode="Markdown",
        )
        return

    if not is_allowed_rarity(parsed.rarity):
        await message.reply_text(
            build_wrong_rarity_message(parsed.rarity),
            parse_mode="Markdown",
        )
        return

    if not message.photo:
        # Shouldn't happen given the filters.PHOTO handler filter, but guard anyway.
        await message.reply_text(build_parse_failed_message(), parse_mode="Markdown")
        return

    if context.user_data is not None:
        context.user_data.pop("add_type", None)
        context.user_data["awaiting_price"] = True
        context.user_data["pending_card"] = parsed
        context.user_data["pending_photo"] = message.photo[-1].file_id

    await message.reply_text(
        build_price_prompt_message(parsed),
        parse_mode="Markdown",
    )


# ---------- Handler for the base price reply ----------
async def add_price_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type != "private":
        return

    user_data = context.user_data or {}
    if not user_data.get("awaiting_price"):
        return

    parsed = user_data.get("pending_card")
    photo_file_id = user_data.get("pending_photo")
    if parsed is None or not photo_file_id:
        if context.user_data is not None:
            context.user_data.pop("awaiting_price", None)
            context.user_data.pop("pending_card", None)
            context.user_data.pop("pending_photo", None)
        await message.reply_text(
            "⚠️ Something went wrong with your submission. Please start again with /add."
        )
        return

    price = parse_price(message.text or "")
    if price is None:
        await message.reply_text(build_invalid_price_message(), parse_mode="Markdown")
        return

    user = update.effective_user
    submitted_by = f"@{user.username}" if user and user.username else (user.full_name if user else parsed.username)

    log_message = await context.bot.send_photo(
        chat_id=LOG_GROUP_ID,
        photo=photo_file_id,
        caption=build_log_caption(parsed, price, submitted_by),
        parse_mode="Markdown",
    )

    submission_id = str(log_message.message_id)
    final_log_caption = build_log_caption(parsed, price, submitted_by, submission_id)
    await context.bot.edit_message_caption(
        chat_id=LOG_GROUP_ID,
        message_id=log_message.message_id,
        caption=final_log_caption,
        parse_mode="Markdown",
        reply_markup=get_verification_keyboard(submission_id),
    )

    # Persisted so this submission survives a restart before an admin
    # taps Verified/Rejected — not just kept in an in-memory dict.
    await create_pending_submission(
        submission_id=submission_id,
        card=asdict(parsed),
        price=price,
        user_id=user.id if user else None,
        caption=final_log_caption,
        photo_file_id=photo_file_id,
        submitted_by=submitted_by,
    )

    await message.reply_text(
        build_pending_verification_message(parsed, price),
        parse_mode="Markdown",
    )

    if context.user_data is not None:
        context.user_data.pop("awaiting_price", None)
        context.user_data.pop("pending_card", None)
        context.user_data.pop("pending_photo", None)


# ---------- Callback handler for Verified / Rejected buttons in the log group ----------
async def add_verification_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    if query is None or query.data is None:
        return

    if query.data.startswith(CB_VERIFY_PREFIX):
        status = "verified"
        submission_id = query.data[len(CB_VERIFY_PREFIX):]
    elif query.data.startswith(CB_REJECT_PREFIX):
        status = "rejected"
        submission_id = query.data[len(CB_REJECT_PREFIX):]
    else:
        return

    submission = await get_pending_submission(submission_id)
    if submission is None:
        await query.answer("This submission is no longer available.", show_alert=True)
        return

    await query.answer("Verified ✅" if status == "verified" else "Rejected ❌")

    admin = update.effective_user
    decided_by = f"@{admin.username}" if admin and admin.username else (admin.full_name if admin else "an admin")

    new_caption = submission["caption"] + build_log_decision_suffix(status, decided_by)
    await query.edit_message_caption(caption=new_caption, parse_mode="Markdown", reply_markup=None)

    card = ParsedCard(**submission["card"])
    price = submission["price"]

    if status == "verified":
        photo_file_id = submission.get("photo_file_id")
        submitted_by = submission.get("submitted_by") or card.username

        if not photo_file_id:
            # Data integrity problem — shouldn't normally happen, but bail
            # out cleanly instead of crashing send_photo with None.
            await context.bot.send_message(
                chat_id=LOG_GROUP_ID,
                text=f"⚠️ Submission `{submission_id}` is missing its photo and couldn't be posted publicly.",
                parse_mode="Markdown",
            )
        else:
            public_caption = build_public_post_caption(card, price, submitted_by)
            bot_username = context.bot.username
            bid_keyboard = get_bid_keyboard(submission_id, bot_username)

            channel_message = await context.bot.send_photo(
                chat_id=CHANNEL_CHAT_ID,
                photo=photo_file_id,
                caption=public_caption,
                parse_mode="Markdown",
                reply_markup=bid_keyboard,
            )
            group_message = await context.bot.send_photo(
                chat_id=GROUP_CHAT_ID,
                photo=photo_file_id,
                caption=public_caption,
                parse_mode="Markdown",
                reply_markup=bid_keyboard,
            )

            try:
                await context.bot.pin_chat_message(
                    chat_id=GROUP_CHAT_ID,
                    message_id=group_message.message_id,
                    disable_notification=True,
                )
            except Exception:
                pass

            seller_id = submission.get("user_id")

            # Persisted to MongoDB so the auction's 2-day end_time, bid state,
            # and message ids all survive a Render restart/redeploy — a
            # repeating check (see close_due_auctions) picks this up when
            # end_time passes, instead of relying on a single in-memory timer
            # living uninterrupted for the full 2 days.
            await create_auction(
                submission_id=submission_id,
                card=asdict(card),
                price=price,
                submitted_by=submitted_by,
                owner_id=seller_id,
                channel_message_id=channel_message.message_id,
                group_message_id=group_message.message_id,
                duration_seconds=AUCTION_DURATION_SECONDS,
            )

    user_id = submission.get("user_id")
    if user_id is not None:
        try:
            if status == "verified":
                await context.bot.send_message(
                    chat_id=user_id,
                    text=build_user_verified_message(card, price),
                    parse_mode="Markdown",
                )
            else:
                await context.bot.send_message(
                    chat_id=user_id,
                    text=build_user_rejected_message(card),
                    parse_mode="Markdown",
                )
        except Exception:
            pass

    await delete_pending_submission(submission_id)


# ---------- Bid deep-link handling ----------
async def try_handle_bid_deeplink(update: Update, context: ContextTypes.DEFAULT_TYPE, payload: str) -> bool:
    """
    The public 'Place Bid' button is a t.me deep link that opens the user's
    DM with a /start payload of "bid_<submission_id>". This project's actual
    /start handler lives elsewhere (it does the join-gate check first), so
    that handler should call this helper with the raw payload string before
    falling back to its normal welcome message.

    Returns True if the payload was a bid link and has been fully handled.
    Returns False if this isn't a bid payload at all.
    """
    if not payload or not payload.startswith(CB_BID_PREFIX):
        return False

    user = update.effective_user
    if user is None:
        return True

    in_group, in_channel = await check_membership(context.bot, user.id)
    if not (in_group and in_channel):
        await context.bot.send_message(
            chat_id=user.id,
            text="🚫 You need to join our group and channel before you can bid. "
            "Please join both, then tap the bid button again.",
        )
        return True

    submission_id = payload[len(CB_BID_PREFIX):]
    post = await get_auction(submission_id)
    if post is None:
        await context.bot.send_message(
            chat_id=user.id, text="❌ That card isn't available for bidding."
        )
        return True

    if post.get("owner_id") == user.id:
        await context.bot.send_message(
            chat_id=user.id, text=build_cannot_bid_own_card_message()
        )
        return True

    current_amount = post["highest_bid"] if post["highest_bid"] is not None else post["price"]
    card = ParsedCard(**post["card"])

    if context.user_data is not None:
        context.user_data["awaiting_bid_for"] = submission_id

    await context.bot.send_message(
        chat_id=user.id,
        text=build_bid_dm_prompt(card, current_amount),
        parse_mode="Markdown",
    )
    return True


# ---------- Handler for a bid amount typed in the DM ----------
async def add_bid_amount_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    chat = update.effective_chat
    if chat is None or chat.type != "private":
        return

    user = update.effective_user
    if user is None:
        # No identifiable user to attribute this bid to — nothing safe to do.
        return

    user_data = context.user_data or {}
    submission_id = user_data.get("awaiting_bid_for")
    if not submission_id:
        return

    post = await get_auction(submission_id)
    if post is None:
        if context.user_data is not None:
            context.user_data.pop("awaiting_bid_for", None)
        await message.reply_text("❌ That card isn't available for bidding anymore.")
        return

    if post.get("owner_id") == user.id:
        if context.user_data is not None:
            context.user_data.pop("awaiting_bid_for", None)
        await message.reply_text(build_cannot_bid_own_card_message())
        return

    in_group, in_channel = await check_membership(context.bot, user.id)
    if not (in_group and in_channel):
        if context.user_data is not None:
            context.user_data.pop("awaiting_bid_for", None)
        await message.reply_text(
            "🚫 You need to be joined to our group and channel to place a bid. "
            "Please join both, then tap the bid button again."
        )
        return

    amount = parse_price(message.text or "")
    if amount is None:
        await message.reply_text(build_invalid_price_message(), parse_mode="Markdown")
        return

    card = ParsedCard(**post["card"])
    bidder_name = get_display_name(user)

    result = await place_bid(submission_id, amount, user.id, bidder_name)

    if result["status"] == "not_found":
        if context.user_data is not None:
            context.user_data.pop("awaiting_bid_for", None)
        await message.reply_text("❌ That card isn't available for bidding anymore.")
        return

    if result["status"] == "too_low":
        await message.reply_text(
            build_bid_too_low_message(result["current_amount"]), parse_mode="Markdown"
        )
        return  # keep awaiting_bid_for so they can retry

    previous_bidder_id = result.get("previous_bidder_id")
    bidder_label = build_mention_from_id(user.id, bidder_name)

    new_caption = build_public_post_caption(
        card, post["price"], post["submitted_by"], amount, bidder_label
    )
    bot_username = context.bot.username
    new_keyboard = get_bid_keyboard(submission_id, bot_username, amount)

    for chat_id, message_id in (
        (CHANNEL_CHAT_ID, post.get("channel_message_id")),
        (GROUP_CHAT_ID, post.get("group_message_id")),
    ):
        if message_id is None:
            continue
        try:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=new_caption,
                parse_mode="Markdown",
                reply_markup=new_keyboard,
            )
        except Exception:
            pass

    if context.user_data is not None:
        context.user_data.pop("awaiting_bid_for", None)

    await message.reply_text(
        build_bid_placed_message(card, amount), parse_mode="Markdown"
    )

    if previous_bidder_id is not None and previous_bidder_id != user.id:
        try:
            await context.bot.send_message(
                chat_id=previous_bidder_id,
                text=build_outbid_notice(card, amount),
                parse_mode="Markdown",
            )
        except Exception:
            pass


# ---------- Admin command: /cancelbid <item_id> — cancel the current highest bid ----------
@admin_only
async def cancel_bid_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    if not context.args:
        await message.reply_text(build_cancel_bid_usage_message(), parse_mode="Markdown")
        return

    submission_id = context.args[0].strip()

    # Fetch the auction first — admin_cancel_highest_bid only returns the
    # bid-state change (cancelled amount, new highest, etc.), not the card,
    # price, submitted_by, or message ids needed to update the public posts
    # and notify people. Those live on the auction document itself.
    auction = await get_auction(submission_id)
    if auction is None:
        await message.reply_text(build_end_auction_not_found_message())
        return

    card = ParsedCard(**auction["card"])
    price = auction["price"]
    submitted_by = auction.get("submitted_by")
    channel_message_id = auction.get("channel_message_id")
    group_message_id = auction.get("group_message_id")

    result = await admin_cancel_highest_bid(submission_id)

    if result["status"] == "not_found":
        # Auction got closed (e.g. by the periodic check) between our
        # get_auction call and this one — treat it the same as "not found".
        await message.reply_text(build_end_auction_not_found_message())
        return

    if result["status"] == "no_bid":
        await message.reply_text(build_cancel_bid_no_bid_message())
        return

    if result["status"] == "conflict":
        # A new bid landed between our read and the cancel write — bail
        # out rather than risk cancelling a bid the admin didn't see.
        await message.reply_text(build_cancel_bid_conflict_message())
        return

    # status == "ok"
    cancelled_amount = result["cancelled_amount"]
    cancelled_bidder_id = result.get("cancelled_bidder_id")
    charge = calculate_cancellation_charge(cancelled_amount)

    new_highest_bid = result.get("new_highest_bid")
    new_highest_bidder_id = result.get("new_highest_bidder_id")
    new_highest_bidder_name = result.get("new_highest_bidder_name")

    new_bidder_label = (
        build_mention_from_id(new_highest_bidder_id, new_highest_bidder_name)
        if new_highest_bidder_id is not None
        else None
    )

    # Reflect the reverted bid state on the public posts, same as a normal bid update.
    new_caption = build_public_post_caption(
        card, price, submitted_by, new_highest_bid, new_bidder_label
    )
    bot_username = context.bot.username
    new_keyboard = get_bid_keyboard(submission_id, bot_username, new_highest_bid)

    for chat_id, message_id in (
        (CHANNEL_CHAT_ID, channel_message_id),
        (GROUP_CHAT_ID, group_message_id),
    ):
        if message_id is None:
            continue
        try:
            await context.bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=new_caption,
                parse_mode="Markdown",
                reply_markup=new_keyboard,
            )
        except Exception:
            pass

    await message.reply_text(
        build_bid_cancelled_admin_confirmation(card, cancelled_amount, charge),
        parse_mode="Markdown",
    )

    if cancelled_bidder_id is not None:
        try:
            await context.bot.send_message(
                chat_id=cancelled_bidder_id,
                text=build_bid_cancelled_bidder_notice(card, cancelled_amount, charge),
                parse_mode="Markdown",
            )
        except Exception:
            pass

    if new_highest_bidder_id is not None:
        try:
            await context.bot.send_message(
                chat_id=new_highest_bidder_id,
                text=build_bid_reinstated_notice(card, new_highest_bid),
                parse_mode="Markdown",
            )
        except Exception:
            pass


# ---------- Auction closing (shared by the periodic check and /endauction) ----------
async def _finalize_auction(bot, submission_id: str) -> bool:
    """
    Closes a single auction: edits the public posts to show the result,
    announces the winner + seller (or "no bids") in the group, DMs the
    winner and seller, and marks it closed in the DB.

    Returns True if an auction was actually closed here, False if it was
    already gone — e.g. a race between the periodic check and an admin
    running /endauction at nearly the same moment.
    """
    post = await claim_auction_for_closing(submission_id)
    if post is None:
        return False

    card = ParsedCard(**post["card"])
    price = post["price"]
    final_bid = post.get("highest_bid")
    winner_id = post.get("highest_bidder_id")
    winner_name = post.get("highest_bidder_name") or "Someone"
    winner_mention = build_mention(winner_id, winner_name) if winner_id is not None else None
    seller_id = post.get("owner_id")
    submitted_by = post.get("submitted_by") or "the seller"
    seller_mention = (
        build_mention(seller_id, submitted_by)
        if seller_id is not None
        else escape_html(submitted_by)
    )

    ended_caption = build_auction_ended_public_caption(card, price, final_bid, winner_mention)
    for chat_id, message_id in (
        (CHANNEL_CHAT_ID, post.get("channel_message_id")),
        (GROUP_CHAT_ID, post.get("group_message_id")),
    ):
        if message_id is None:
            continue
        try:
            await bot.edit_message_caption(
                chat_id=chat_id,
                message_id=message_id,
                caption=ended_caption,
                parse_mode="HTML",
                reply_markup=None,
            )
        except Exception:
            pass

    group_message_id = post.get("group_message_id")
    if group_message_id is not None:
        try:
            await bot.unpin_chat_message(chat_id=GROUP_CHAT_ID, message_id=group_message_id)
        except Exception:
            pass

    if final_bid is not None and winner_mention is not None:
        announcement = build_auction_won_announcement(card, seller_mention, winner_mention, final_bid)
    else:
        announcement = build_auction_no_bids_announcement(card, seller_mention)

    try:
        await bot.send_message(chat_id=GROUP_CHAT_ID, text=announcement, parse_mode="HTML")
    except Exception:
        pass

    if final_bid is not None and winner_mention is not None:
        if winner_id is not None:
            try:
                await bot.send_message(
                    chat_id=winner_id,
                    text=build_winner_dm_message(card, final_bid, seller_mention),
                    parse_mode="HTML",
                )
            except Exception:
                pass
        if seller_id is not None:
            try:
                await bot.send_message(
                    chat_id=seller_id,
                    text=build_seller_sold_dm_message(card, final_bid, winner_mention),
                    parse_mode="HTML",
                )
            except Exception:
                pass
    else:
        if seller_id is not None:
            try:
                await bot.send_message(
                    chat_id=seller_id,
                    text=build_seller_no_bids_dm_message(card),
                    parse_mode="HTML",
                )
            except Exception:
                pass

    return True


async def close_due_auctions(bot) -> None:
    """
    Finds every active auction whose end_time has passed and closes it.

    Called once on bot startup (to catch anything that expired while the
    bot was down) and then repeatedly every few minutes via JobQueue in
    main.py. Because "what's due" is recomputed fresh from the DB each
    time, this is resilient to restarts — unlike a single run_once job
    that has to survive the full 2 days in memory uninterrupted.
    """
    submission_ids = await get_due_auction_ids()
    for submission_id in submission_ids:
        await _finalize_auction(bot, submission_id)


# ---------- Admin command: /endauction <item_id> — end an auction early ----------
@admin_only
async def end_auction_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if message is None:
        return

    if not context.args:
        await message.reply_text(build_end_auction_usage_message(), parse_mode="Markdown")
        return

    submission_id = context.args[0].strip()
    auction = await get_auction(submission_id)
    if auction is None:
        await message.reply_text(build_end_auction_not_found_message())
        return

    closed = await _finalize_auction(context.bot, submission_id)
    if closed:
        await message.reply_text(f"✅ Auction `{submission_id}` has been ended early.", parse_mode="Markdown")
    else:
        await message.reply_text(build_end_auction_not_found_message())



# ---------- Router for private-chat text messages (price reply vs. bid reply) ----------
async def add_private_text_router(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_data = context.user_data or {}
    if user_data.get("awaiting_price"):
        await add_price_message(update, context)
    elif user_data.get("awaiting_bid_for"):
        await add_bid_amount_message(update, context)


# ---------- Registration ----------
def register_add_handlers(app: Application):
    app.add_handler(CommandHandler("add", add_command))
    app.add_handler(
        CallbackQueryHandler(add_choice_callback, pattern="^add_(husbando|waifu)$")
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.PHOTO & filters.CAPTION,
            add_card_submission,
        )
    )
    app.add_handler(
        MessageHandler(
            filters.ChatType.PRIVATE & filters.TEXT & ~filters.COMMAND,
            add_private_text_router,
        )
    )
    app.add_handler(
        CallbackQueryHandler(
            add_verification_callback, pattern="^(verify_|reject_)"
        )
    )
    app.add_handler(CommandHandler("endauction", end_auction_command))
    app.add_handler(CommandHandler("cancelbid", cancel_bid_command))
