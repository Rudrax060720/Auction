import os

BOT_TOKEN = os.environ.get("BOT_TOKEN")

# Your numeric Telegram user ID — bootstrapped as the permanent super admin.
# Other admins (added later via /addadmin) are stored in MongoDB.
SUPER_ADMIN_ID = int(os.environ.get("SUPER_ADMIN_ID", "0"))

# Fallback caption used only if nothing has been set in the database yet
DEFAULT_CAPTION_TEXT = os.environ.get(
    "DEFAULT_CAPTION_TEXT", "👋 Welcome!\n\nJoin our community below."
)

GROUP_URL = os.environ.get("GROUP_URL", "")
CHANNEL_URL = os.environ.get("CHANNEL_URL", "")

# Chat IDs used for membership verification.
GROUP_CHAT_ID = int(os.environ.get("GROUP_CHAT_ID", "0"))
CHANNEL_CHAT_ID = os.environ.get("CHANNEL_CHAT_ID", "")  # numeric id or "@username"

# Chat ID of a private log channel/group where new /start events get posted.
LOG_CHAT_ID = int(os.environ.get("LOG_CHAT_ID", "0"))

# MongoDB connection string — MongoDB Atlas free tier.
MONGO_URI = os.environ.get("MONGO_URI")
MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "telegram_bot")