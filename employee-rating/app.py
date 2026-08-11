import os
import sqlite3
import threading
import time

import requests
import telebot

from flask import Flask, request, jsonify, render_template_string
from flask_cors import CORS


# =========================================================
# НАСТРОЙКИ
# =========================================================

app = Flask(__name__)
CORS(app)

BOT_TOKEN = os.getenv(
    "BOT_TOKEN",
    "8606610454:AAG6wYBzLBI0ETLojTWx7dORnbRTRUBUQOo"
)

# На Render лучше указывать переменную окружения API_URL
API_URL = os.getenv(
    "API_URL",
    "https://employee-rating-1.onrender.com/api/ratings"
)

CHAT_ID = os.getenv("CHAT_ID")

BASE_DIR = os.path.dirname(
    os.path.abspath(__file__)
)

DB_PATH = os.path.join(
    BASE_DIR,
    "ratings.db"
)


# =========================================================
# TELEGRAM
# =========================================================

bot = None

if BOT_TOKEN and BOT_TOKEN != "8606610454:AAG6wYBzLBI0ETLojTWx7dORnbRTRUBUQOo":
    bot = telebot.TeleBot(BOT_TOKEN)


# =========================================================
# БАЗА ДАННЫХ
# =========================================================

def init_database():

    connection = sqlite3.connect(DB_PATH)

    cursor = connection.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ratings (

            id INTEGER PRIMARY KEY AUTOINCREMENT,

            checkpoint TEXT NOT NULL,

            employee TEXT NOT NULL,

            rating INTEGER NOT NULL,

            comment TEXT,

            created_at TEXT NOT NULL

        )
    """)

    connection.commit()
    connection.close()



@app.route("/")
def home():

    return render_template_string(HTML)


# =========================================================
# СОХРАНЕНИЕ ОЦЕНКИ
# =========================================================

@app.route(
    "/api/rating",
    methods=["POST"]
)
def receive_rating():

    data = request.get_json()

    if not data:

        return jsonify({
            "success": False,
            "message": "Нет данных"
        }), 400


    checkpoint = str(
        data.get("checkpoint", "")
    ).strip()


    employee = str(
        data.get("employee", "")
    ).strip()


    comment = str(
        data.get("comment", "")
    ).strip()


    try:

        rating = int(
            data.get("rating")
        )

    except (TypeError, ValueError):

        return jsonify({
            "success": False,
            "message": "Некорректная оценка"
        }), 400


    if not checkpoint:

        return jsonify({
            "success": False,
            "message":
                "Не указан пункт пропуска"
        }), 400


    if not employee:

        return jsonify({
            "success": False,
            "message":
                "Не указано ФИО"
        }), 400


    if rating < 1 or rating > 5:

        return jsonify({
            "success": False,
            "message":
                "Оценка должна быть от 1 до 5"
        }), 400


    from datetime import datetime

    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    connection = sqlite3.connect(
        DB_PATH
    )

    cursor = connection.cursor()


    cursor.execute("""
        INSERT INTO ratings
        (
            checkpoint,
            employee,
            rating,
            comment,
            created_at
        )

        VALUES (?, ?, ?, ?, ?)
    """, (
        checkpoint,
        employee,
        rating,
        comment,
        created_at
    ))


    rating_id = cursor.lastrowid

    connection.commit()

    connection.close()


    print(
        "Новая оценка:",
        rating_id
    )


    # Отправляем новую оценку в Telegram
    send_rating_to_telegram(
        rating_id,
        checkpoint,
        employee,
        rating,
        comment,
        created_at
    )


    return jsonify({

        "success": True,

        "message":
            "Оценка сохранена",

        "id":
            rating_id,

        "created_at":
            created_at

    })


# =========================================================
# TELEGRAM — ОТПРАВКА НОВОЙ ОЦЕНКИ
# =========================================================

def send_rating_to_telegram(
    rating_id,
    checkpoint,
    employee,
    rating,
    comment,
    created_at
):

    if not bot:

        print(
            "Telegram бот не настроен"
        )

        return


    if not CHAT_ID:

        print(
            "CHAT_ID не настроен"
        )

        return


    stars = "⭐" * rating


    text = (

        "📝 НОВАЯ ОЦЕНКА\n\n"

        f"🆔 ID: {rating_id}\n\n"

        f"📍 Пункт пропуска:\n"
        f"{checkpoint}\n\n"

        f"👤 Сотрудник:\n"
        f"{employee}\n\n"

        f"⭐ Оценка:\n"
        f"{stars} ({rating}/5)\n\n"

        f"💬 Комментарий:\n"
        f"{comment or 'Без комментария'}\n\n"

        f"🕐 Дата:\n"
        f"{created_at}"

    )


    try:

        bot.send_message(
            int(CHAT_ID),
            text
        )

        print(
            "Оценка отправлена в Telegram"
        )

    except Exception as error:

        print(
            "Ошибка Telegram:",
            error
        )


# =========================================================
# API — ВСЕ ОЦЕНКИ
# =========================================================

@app.route(
    "/api/ratings",
    methods=["GET"]
)
def get_ratings():

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.row_factory = sqlite3.Row

    cursor = connection.cursor()


    cursor.execute("""
        SELECT
            id,
            checkpoint,
            employee,
            rating,
            comment,
            created_at

        FROM ratings

        ORDER BY id DESC
    """)


    rows = cursor.fetchall()

    connection.close()


    ratings = []


    for row in rows:

        ratings.append({

            "id":
                row["id"],

            "checkpoint":
                row["checkpoint"],

            "employee":
                row["employee"],

            "rating":
                row["rating"],

            "comment":
                row["comment"],

            "created_at":
                row["created_at"]

        })


    return jsonify({

        "success": True,

        "count":
            len(ratings),

        "ratings":
            ratings

    })


# =========================================================
# TELEGRAM КОМАНДЫ
# =========================================================

if bot:

    @bot.message_handler(
        commands=["start"]
    )
    def start(message):

        bot.send_message(

            message.chat.id,

            "🤖 Система оценки сотрудников\n\n"

            "/report — общий отчёт\n"
            "/last — последние оценки\n"
            "/chatid — узнать Chat ID"

        )


    @bot.message_handler(
        commands=["chatid"]
    )
    def chatid(message):

        bot.send_message(

            message.chat.id,

            f"🆔 Ваш Chat ID:\n"
            f"{message.chat.id}"

        )


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

            "📊 ОБЩИЙ ОТЧЁТ\n\n"

            f"📝 Всего оценок: "
            f"{total}\n\n"

            f"⭐ Средняя оценка: "
            f"{average:.2f} / 5"

        )


        bot.send_message(
            message.chat.id,
            text
        )


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


        text = (
            "📋 ПОСЛЕДНИЕ ОЦЕНКИ\n\n"
        )


        for row in rows:

            checkpoint = row[0]
            employee = row[1]
            rating = row[2]
            comment = row[3]
            created_at = row[4]


            text += (

                f"📍 {checkpoint}\n"

                f"👤 {employee}\n"

                f"⭐ {rating}/5\n"

                f"💬 "
                f"{comment or 'Без комментария'}\n"

                f"🕐 {created_at}\n"

                "──────────────\n"

            )


        bot.send_message(
            message.chat.id,
            text
        )


# =========================================================
# TELEGRAM POLLING
# =========================================================

def start_telegram():

    if not bot:

        print(
            "Telegram отключен: "
            "BOT_TOKEN не задан"
        )

        return


    print(
        "Telegram бот запущен"
    )


    try:

        bot.infinity_polling(
            skip_pending=True
        )

    except Exception as error:

        print(
            "Ошибка Telegram:",
            error
        )


# =========================================================
# ЗАПУСК
# =========================================================

init_database()


if __name__ == "__main__":

    if bot:

        telegram_thread = threading.Thread(
            target=start_telegram,
            daemon=True
        )

        telegram_thread.start()


    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )


    print(
        "=============================="
    )

    print(
        "СИСТЕМА ОЦЕНКИ СОТРУДНИКОВ"
    )

    print(
        "=============================="
    )

    print(
        "Порт:",
        port
    )

    print(
        "=============================="
    )


    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
