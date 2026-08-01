from telegram import Update
from telegram.ext import ContextTypes

from db import set_start_image, add_admin, remove_admin
from utils import super_admin_only


@super_admin_only
async def set_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: reply to a photo with /setimage
    Only updates the photo — caption is managed via DEFAULT_CAPTION_TEXT in config.py.
    Super-admin-only.
    """
    message = update.message
    if message is None:
        return

    replied = message.reply_to_message
    if replied is None or not replied.photo:
        await message.reply_text(
            "Please reply to a photo with /setimage to set the welcome image."
        )
        return

    # Telegram sends multiple sizes; the last one is the highest resolution
    file_id = replied.photo[-1].file_id

    await set_start_image(file_id, "")
    await message.reply_text("✅ Start image updated.")


@super_admin_only
async def add_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /addadmin <telegram_user_id>
    Only the super admin can add new admins.
    """
    message = update.message
    if message is None:
        return

    if not context.args:
        await message.reply_text("Usage: /addadmin <telegram_user_id>")
        return

    try:
        new_admin_id = int(context.args[0])
    except ValueError:
        await message.reply_text("That doesn't look like a valid numeric Telegram ID.")
        return

    added = await add_admin(new_admin_id)
    if added:
        await message.reply_text(f"✅ User {new_admin_id} added as admin.")
    else:
        await message.reply_text(f"User {new_admin_id} is already an admin.")


@super_admin_only
async def remove_admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Usage: /removeadmin <telegram_user_id>
    Only the super admin can remove admins.
    """
    message = update.message
    if message is None:
        return

    if not context.args:
        await message.reply_text("Usage: /removeadmin <telegram_user_id>")
        return

    try:
        target_admin_id = int(context.args[0])
    except ValueError:
        await message.reply_text("That doesn't look like a valid numeric Telegram ID.")
        return

    removed = await remove_admin(target_admin_id)
    if removed:
        await message.reply_text(f"✅ User {target_admin_id} removed as admin.")
    else:
        await message.reply_text(f"User {target_admin_id} isn't an admin.")
