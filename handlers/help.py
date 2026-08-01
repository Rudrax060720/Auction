from telegram import Update
from telegram.ext import ContextTypes


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    await message.reply_text(
        "<b>📖 Available Commands:</b>\n\n"
        "/start - Welcome message\n"
        "/help - Show this help message\n"
        "/add - Add a Waifu/Husbando to auction\n"
        "/itemlist - Browse all cards currently up for auction\n"
        "/myitem - View the cards you've submitted\n"
        "/rules - Read the auction rules before you bid",
        parse_mode="HTML",
    )


async def rules_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    await message.reply_text(
        "<b>📜 Auction Rules:</b>\n\n"
        "1️⃣ After adding a <b>Waifu/Husbando</b> to auction, it will be sent for approval.\n\n"
        "2️⃣ You can only add cards from these rarities: 🟡 <b>Legendary</b> (Chibis) [👶], "
        "🔮 <b>Limiteds</b>, and 🎐 <b>Celestials</b>.\n\n"
        "3️⃣ A card is approved only if its <b>base price is valid</b> — submissions with an "
        "invalid base price will be <b>rejected</b>.\n\n"
        "4️⃣ The <b>seller remains hidden</b> until the end of the auction.\n\n"
        "5️⃣ The <b>auction automatically ends after 2 days</b> once approved.\n\n"
        "6️⃣ <b>Bid only if you can afford</b> — bids <b>cannot be cancelled</b> by you once placed.\n\n"
        "7️⃣ If an admin cancels a bid or auction, it costs <b>10% of the current bid</b> — this "
        "charge must be <b>paid to the admin first</b>.\n\n"
        "8️⃣ Bidding from <b>alternate accounts</b> or placing <b>fake bids</b> will lead to a "
        "<b>permanent ban</b> from using the bot.\n\n"
        "9️⃣ Do not send the <b>same Waifu/Husbando</b> for approval if it's already in auction.\n\n"
        "🔟 The <b>winner</b> will receive the Waifu/Husbando from the seller "
        "<b>after paying the final bid amount</b> to the seller.",
        parse_mode="HTML",
    )
