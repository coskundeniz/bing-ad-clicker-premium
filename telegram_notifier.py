import asyncio
import os
from pathlib import Path
from typing import Optional

import telegram
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler
from telegram.constants import ParseMode

from logger import logger
from stats import SearchStats


TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")

bot = telegram.Bot(token=TELEGRAM_TOKEN)

telegram_chat_id_file = Path(".TELEGRAM_CHAT_ID")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command

    :type update: Update
    :param update: Incoming update object
    :type context: ContextTypes
    :param context: Callback context
    """

    with open(telegram_chat_id_file, mode="w", encoding="utf-8") as chat_id_file:
        logger.info(f"Chat ID: {update.effective_chat.id}")
        chat_id_file.write(str(update.effective_chat.id))

    response = "Started Ad Clicker Premium Notifier! Please end the script with CTRL+C"

    await context.bot.send_message(chat_id=update.effective_chat.id, text=response)

    logger.info("Please end the script with CTRL+C")


async def send_message(chat_id: str, message: str) -> None:
    """Send message to user with the given chat id

    Limit the message length with maximum of 2048 characters.

    :type chat_id: str
    :param chat_id: Chat ID of the user
    :type message: str
    :param message: Message to send
    """

    async with bot:
        if len(message) > 2048:
            message = message[:2048]

            if "</pre>" not in message:
                message += "</pre>\n"

        await bot.send_message(chat_id=chat_id, text=message, parse_mode=ParseMode.HTML)


def notify_matching_ads(query: str, links: list, stats: Optional[SearchStats] = None) -> None:
    """Notify matching ads via Telegram

    :type query: str
    :param query: Query used for search
    :type links: AllLinks
    :param links: List of (ad, ad_link, ad_title) tuples
    :type stats: SearchStats
    :param stats: Search statistics data
    """

    if not telegram_chat_id_file.exists():
        logger.info("Please start the messaging with bot to get a chat ID!")
        raise SystemExit()

    with open(telegram_chat_id_file, encoding="utf-8") as chat_id_file:
        chat_id = chat_id_file.read().strip()

    if not links:
        message = f"{stats.to_pre_text()}\n" if stats else ""
        message += f"<b>No matching ads found in the search results for query:</b> {query}\n"

        asyncio.run(send_message(chat_id=chat_id, message=message))
        return

    if stats:
        message = f"{stats.to_pre_text()}\n<b>Query:</b> {query}\n"
    else:
        message = f"<b>Query:</b> {query}\n"

    for link in links:
        link_url = link[1]
        original_ad_title = link[2].replace("\n", " ")

        ad_title = original_ad_title.replace("<", "&lt;").replace(">", "&gt;").replace("&", "&amp;")

        message += f"<b>Ad Title:</b> {ad_title}\n"

        logger.debug(f"Notification was added for [{original_ad_title}]({link_url})")

    try:
        logger.info("Sending Telegram notification...")
        asyncio.run(send_message(chat_id=chat_id, message=message))

    except Exception as exp:
        logger.debug(exp)
        logger.error("Failed to send notification!")
        logger.debug(f"Message: {message}")


def start_bot() -> None:
    """Start polling updates to get /start command"""

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()

    start_handler = CommandHandler("start", start)
    application.add_handler(start_handler)

    logger.info("Waiting for /start command...")
    application.run_polling()
