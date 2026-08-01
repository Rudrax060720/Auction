import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from telegram import Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

from config import BOT_TOKEN
from db import init_db
from handlers.start import start
from handlers.help import help_command, rules_command
from handlers.admin import set_image, add_admin_command, remove_admin_command
from handlers.verify import check_join_callback
from handlers.add import register_add_handlers, close_due_auctions
from handlers.ban import register_ban_handlers
from handlers.ban_guard import BOT_COMMANDS, global_ban_check_message, global_ban_check_callback
from handlers.itemlist import (
    itemlist_command,
    itemlist_callback,
    myitem_command,
    myitem_callback,
)

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------- tiny HTTP server so Render + UptimeRobot have something to ping ----------
class PingHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, format, *args):
        pass  # silence default request logging spam


def run_ping_server():
    port = int(os.environ.get("PORT", 8080))  # Render sets PORT automatically
    server = HTTPServer(("0.0.0.0", port), PingHandler)
    logger.info(f"Ping server listening on port {port}")
    server.serve_forever()


# ---------- startup ----------
async def on_startup(app: Application) -> None:
    await init_db()
    logger.info("Database initialized.")
    # Catch anything that expired while the bot was asleep/restarted
    await close_due_auctions(app.bot)

    if app.job_queue is None:
        # Means python-telegram-bot[job-queue] isn't installed — the auction
        # auto-close check below would silently never run without this.
        raise RuntimeError(
            "JobQueue is not available. Install with: "
            'pip install "python-telegram-bot[job-queue]"'
        )

    # Recheck every 5 minutes — self-heals across Render restarts, since
    # "what's due" is recomputed from the DB each tick instead of relying
    # on a single in-memory timer surviving the full 2-day auction window.
    app.job_queue.run_repeating(
        lambda ctx: close_due_auctions(ctx.bot),
        interval=300,
        first=300,
    )


def main() -> None:
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN environment variable is not set")

    threading.Thread(target=run_ping_server, daemon=True).start()

    app = Application.builder().token(BOT_TOKEN).post_init(on_startup).build()

    # Regular commands
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("addadmin", add_admin_command))
    app.add_handler(CommandHandler("setimage", set_image))
    app.add_handler(CommandHandler("removeadmin", remove_admin_command))
    app.add_handler(CommandHandler(BOT_COMMANDS, global_ban_check_message), group=-1)
    app.add_handler(CallbackQueryHandler(global_ban_check_callback, pattern=".*"), group=-1)
    app.add_handler(CommandHandler("rules", rules_command))
    register_ban_handlers(app)
    register_add_handlers(app)

    # /itemlist and /myitem
    app.add_handler(CommandHandler("itemlist", itemlist_command))
    app.add_handler(CommandHandler("myitem", myitem_command))
    app.add_handler(CallbackQueryHandler(itemlist_callback, pattern="^(il_)"))
    app.add_handler(CallbackQueryHandler(myitem_callback, pattern="^(mi_)"))

    # "✅ I've Joined" button on the join-prompt message
    app.add_handler(CallbackQueryHandler(check_join_callback, pattern="^check_join$"))

    logger.info("Bot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
