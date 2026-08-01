import functools

from telegram import Update
from telegram.ext import ContextTypes

from config import SUPER_ADMIN_ID
from db import is_admin


def admin_only(func):
    """Decorator: blocks the command unless the sender is an admin (or super admin)."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        user = update.effective_user
        if message is None or user is None:
            return
        if not await is_admin(user.id):
            await message.reply_text("You're not authorized to use this command.")
            return
        return await func(update, context)
    return wrapper


def super_admin_only(func):
    """Decorator: blocks the command unless the sender is the super admin."""
    @functools.wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        message = update.message
        user = update.effective_user
        if message is None or user is None:
            return
        if user.id != SUPER_ADMIN_ID:
            await message.reply_text("Only the super admin can use this command.")
            return
        return await func(update, context)
    return wrapper