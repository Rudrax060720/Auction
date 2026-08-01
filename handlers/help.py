from telegram import Update
from telegram.ext import ContextTypes


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.message
    if message is None:
        return

    await message.reply_text(
        "Available commands:\n"
        "/start - Welcome message\n"
        "/help - Show this help message"
    )