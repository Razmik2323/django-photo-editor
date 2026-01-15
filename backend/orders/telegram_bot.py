import logging
import os
import sys
import django

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, MenuButtonWebApp
from telegram.ext import Application, CommandHandler, ContextTypes

logger = logging.getLogger('orders')

WEB_APP_URL = os.getenv('TELEGRAM_WEB_APP_URL', '')


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик команды /start"""
    keyboard = [
        [InlineKeyboardButton(
            "Открыть помощника",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    await update.message.reply_text(
        "Нажмите кнопку ниже, чтобы открыть помощник.",
        reply_markup=reply_markup
    )


async def setup_bot_menu(application):
    bot = application.bot
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(
            text="Открыть помощника",
            web_app=WebAppInfo(url=WEB_APP_URL)
        )
    )


async def post_init(application):
    await setup_bot_menu(application)


def run_bot():
    """Запуск Telegram бота"""
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not bot_token:
        logger.error("TELEGRAM_BOT_TOKEN not set in environment variables")
        logger.error("Please set TELEGRAM_BOT_TOKEN environment variable")
        return
    
    application = Application.builder().token(bot_token).post_init(post_init).build()
    
    application.add_handler(CommandHandler("start", start_command))
    
    logger.info("Starting Telegram bot...")
    try:
        application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Error running bot: {str(e)}", exc_info=True)
        raise


if __name__ == "__main__":
    run_bot()

