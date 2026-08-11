import os
import time
import requests
import telebot
from dotenv import load_dotenv

load_dotenv()

# ==========================================
# НАСТРОЙКИ
# ==========================================

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

API_URL = "https://employee-rating-1.onrender.com/api/ratings"

if not BOT_TOKEN:
    raise RuntimeError("Не указан BOT_TOKEN")

if not CHAT_ID:
    raise RuntimeError("Не указан CHAT_ID")

bot = telebot.TeleBot(BOT_TOKEN)


# ==========================================
# /start
# ==========================================

@bot.message_handler(commands=["start"])
def start(message):

    bot.send_message(
        message.chat.id,
        "🤖 Бот оценки сотрудников запущен.\n\n"
        "Команды:\n"
        "/report — получить отчет\n"
        "/help — помощь"
    )


# ==========================================
# /help
# ==========================================

@bot.message_handler(commands=["help"])
def help_command(message):

    bot.send_message(
        message.chat.id,
        "📋 Доступные команды:\n\n"
        "/start — запуск\n"
        "/report — последний отчет\n"
        "/help — помощь"
    )


# ==========================================
# ФОРМАТ ОЦЕНКИ
# ==========================================

def format_rating(item):

    stars = "⭐" * int(item["rating"])

    comment = item.get("comment") or "Без комментария"

    return (
        "📝 НОВАЯ ОЦЕНКА\n\n"
        f"🆔 ID: {item['id']}\n"
        f"📍 Пункт пропуска: {item['checkpoint']}\n"
        f"👤 Сотрудник: {item['employee']}\n"
        f"⭐ Оценка: {stars} ({item['rating']}/5)\n"
        f"💬 Комментарий: {comment}\n"
        f"🕐 Дата: {item['created_at']}"
    )


# ==========================================
# ПОЛУЧЕНИЕ ДАННЫХ
# ==========================================

def get_ratings():

    try:

        response = requests.get(
            API_URL,
            timeout=20
        )

        response.raise_for_status()

        data = response.json()

        if not data.get("success"):
            return []

        return data.get("ratings", [])

    except Exception as error:

        print(
            "Ошибка получения оценок:",
            error
        )

        return []


# ==========================================
# /report
# ==========================================

@bot.message_handler(commands=["report"])
def report(message):

    ratings = get_ratings()

    if not ratings:

        bot.send_message(
            message.chat.id,
            "📊 Оценок пока нет."
        )

        return

    # Последние 10 оценок

    ratings = ratings[:10]

    text = "📊 ПОСЛЕДНИЕ ОЦЕНКИ\n\n"

    for item in ratings:

        text += (
            f"🆔 {item['id']}\n"
            f"📍 {item['checkpoint']}\n"
            f"👤 {item['employee']}\n"
            f"⭐ {item['rating']}/5\n"
            f"💬 {item.get('comment') or 'Без комментария'}\n"
            f"🕐 {item['created_at']}\n"
            "━━━━━━━━━━━━━━\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )


# ==========================================
# МОНИТОРИНГ НОВЫХ ОЦЕНОК
# ==========================================

last_id = 0


def check_new_ratings():

    global last_id

    ratings = get_ratings()

    if not ratings:
        return

    # API отдаёт новые записи первыми

    newest = ratings[0]

    newest_id = int(
        newest["id"]
    )

    # Первый запуск

    if last_id == 0:

        last_id = newest_id

        return

    # Есть новая оценка

    if newest_id > last_id:

        new_items = []

        for item in reversed(ratings):

            item_id = int(item["id"])

            if item_id > last_id:
                new_items.append(item)

        for item in new_items:

            try:

                bot.send_message(
                    CHAT_ID,
                    format_rating(item)
                )

            except Exception as error:

                print(
                    "Ошибка Telegram:",
                    error
                )

        last_id = newest_id


# ==========================================
# ЗАПУСК
# ==========================================

print("==============================")
print("TELEGRAM-БОТ ЗАПУЩЕН")
print("==============================")

while True:

    try:

        check_new_ratings()

    except Exception as error:

        print(
            "Ошибка:",
            error
        )

    time.sleep(10)
