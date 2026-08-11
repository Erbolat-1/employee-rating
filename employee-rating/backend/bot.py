import telebot
import sqlite3
import os


# ==============================
# НАСТРОЙКИ
# ==============================

BOT_TOKEN = "8606610454:AAG6wYBzLBI0ETLojTWx7dORnbRTRUBUQOo"


# ==============================
# БАЗА ДАННЫХ
# ==============================

BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.abspath(__file__)
    )
)

DB_PATH = os.path.join(
    BASE_DIR,
    "ratings.db"
)


bot = telebot.TeleBot(
    BOT_TOKEN
)


# ==============================
# /start
# ==============================

@bot.message_handler(
    commands=["start"]
)
def start(message):

    bot.send_message(
        message.chat.id,

        "🤖 Система оценки сотрудников\n\n"
        "Доступные команды:\n\n"
        "/report — общий отчёт\n"
        "/last — последние оценки"
    )


# ==============================
# ОБЩИЙ ОТЧЁТ
# ==============================

@bot.message_handler(
    commands=["report"]
)
def report(message):

    connection = sqlite3.connect(
        DB_PATH
    )

    cursor = connection.cursor()


    cursor.execute("""
        SELECT
            COUNT(*),
            AVG(rating)
        FROM ratings
    """)

    total, average = cursor.fetchone()


    connection.close()


    if total == 0:

        bot.send_message(
            message.chat.id,
            "📊 Оценок пока нет."
        )

        return


    text = (
        "📊 ОТЧЁТ ПО ОЦЕНКАМ\n\n"

        f"📝 Всего оценок: {total}\n"

        f"⭐ Средняя оценка: "
        f"{average:.2f} / 5"
    )


    bot.send_message(
        message.chat.id,
        text
    )


# ==============================
# ПОСЛЕДНИЕ ОЦЕНКИ
# ==============================

@bot.message_handler(
    commands=["last"]
)
def last_ratings(message):

    connection = sqlite3.connect(
        DB_PATH
    )

    cursor = connection.cursor()


    cursor.execute("""
        SELECT
            checkpoint,
            employee,
            rating,
            comment,
            created_at

        FROM ratings

        ORDER BY id DESC

        LIMIT 10
    """)

    rows = cursor.fetchall()


    connection.close()


    if not rows:

        bot.send_message(
            message.chat.id,
            "📊 Оценок пока нет."
        )

        return


    text = "📋 ПОСЛЕДНИЕ ОЦЕНКИ\n\n"


    for row in rows:

        checkpoint = row[0]
        employee = row[1]
        rating = row[2]
        comment = row[3]
        created_at = row[4]


        stars = "⭐" * rating


        text += (
            f"📍 {checkpoint}\n"
            f"👤 {employee}\n"
            f"{stars} ({rating}/5)\n"
            f"💬 {comment or 'Без комментария'}\n"
            f"🕐 {created_at}\n"
            f"──────────────\n"
        )


    bot.send_message(
        message.chat.id,
        text
    )


# ==============================
# ЗАПУСК
# ==============================
@bot.message_handler(commands=["chatid"])
def get_chat_id(message):

    bot.send_message(
        message.chat.id,
        f"Ваш Chat ID:\n{message.chat.id}"
    )
print("==============================")
print("TELEGRAM-БОТ ЗАПУЩЕН")
print("==============================")

bot.infinity_polling()