import os
import sqlite3
import threading
import time
from datetime import datetime

import requests
import telebot
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS


# =========================================================
# НАСТРОЙКИ
# =========================================================

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "ratings.db")

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

PORT = int(os.getenv("PORT", 5000))


# =========================================================
# TELEGRAM
# =========================================================

bot = None

if BOT_TOKEN:
    bot = telebot.TeleBot(BOT_TOKEN)
else:
    print("⚠️ BOT_TOKEN не установлен")

if not CHAT_ID:
    print("⚠️ CHAT_ID не установлен")
else:
    try:
        CHAT_ID = int(CHAT_ID)
    except ValueError:
        print("⚠️ CHAT_ID должен быть числом")
        CHAT_ID = None


# =========================================================
# БАЗА ДАННЫХ
# =========================================================

def get_connection():

    connection = sqlite3.connect(
        DB_PATH,
        timeout=30
    )

    connection.row_factory = sqlite3.Row

    return connection


def init_database():

    connection = get_connection()

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

    print("✅ База данных готова:")
    print(DB_PATH)


# =========================================================
# ГЛАВНАЯ СТРАНИЦА
# =========================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# =========================================================
# СОЗДАНИЕ ОЦЕНКИ
# =========================================================

@app.route(
    "/api/rating",
    methods=["POST"]
)
def receive_rating():

    try:

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

        except (
            TypeError,
            ValueError
        ):

            return jsonify({
                "success": False,
                "message": "Некорректная оценка"
            }), 400


        # -------------------------------------------------
        # ПРОВЕРКА
        # -------------------------------------------------

        if not checkpoint:

            return jsonify({
                "success": False,
                "message": "Не указан пункт пропуска"
            }), 400


        if not employee:

            return jsonify({
                "success": False,
                "message": "Не указано ФИО сотрудника"
            }), 400


        if rating < 1 or rating > 5:

            return jsonify({
                "success": False,
                "message": "Оценка должна быть от 1 до 5"
            }), 400


        # -------------------------------------------------
        # ВРЕМЯ
        # -------------------------------------------------

        created_at = datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )


        # -------------------------------------------------
        # СОХРАНЕНИЕ
        # -------------------------------------------------

        connection = get_connection()

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


        print()
        print("==============================")
        print("📝 НОВАЯ ОЦЕНКА")
        print("==============================")
        print("ID:", rating_id)
        print("Пункт:", checkpoint)
        print("Сотрудник:", employee)
        print("Оценка:", rating)
        print("Комментарий:", comment)
        print("Дата:", created_at)
        print("==============================")


        return jsonify({

            "success": True,

            "message": "Оценка сохранена",

            "id": rating_id,

            "created_at": created_at

        })


    except Exception as error:

        print(
            "❌ Ошибка сохранения:",
            error
        )

        return jsonify({

            "success": False,

            "message": "Ошибка сервера"

        }), 500


# =========================================================
# ПОЛУЧЕНИЕ ВСЕХ ОЦЕНОК
# =========================================================

@app.route(
    "/api/ratings",
    methods=["GET"]
)
def get_ratings():

    try:

        connection = get_connection()

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

                "id": row["id"],

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

            "count": len(ratings),

            "ratings": ratings

        })


    except Exception as error:

        print(
            "❌ Ошибка получения оценок:",
            error
        )

        return jsonify({

            "success": False,

            "message": "Ошибка сервера"

        }), 500


# =========================================================
# ФОРМАТ TELEGRAM-СООБЩЕНИЯ
# =========================================================

def format_rating(item):

    rating = int(
        item["rating"]
    )

    stars = "⭐" * rating

    comment = (
        item.get("comment")
        or "Без комментария"
    )

    return (

        "📝 НОВАЯ ОЦЕНКА\n\n"

        f"🆔 ID: {item['id']}\n\n"

        f"📍 Пункт пропуска:\n"
        f"{item['checkpoint']}\n\n"

        f"👤 Сотрудник:\n"
        f"{item['employee']}\n\n"

        f"⭐ Оценка:\n"
        f"{stars} ({rating}/5)\n\n"

        f"💬 Комментарий:\n"
        f"{comment}\n\n"

        f"🕐 Дата:\n"
        f"{item['created_at']}"

    )


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

            "Бот подключён.\n\n"

            "/report — общий отчёт\n"
            "/last — последние оценки\n"
            "/chatid — узнать Chat ID\n"
            "/test — проверить бота"

        )


    @bot.message_handler(
        commands=["chatid"]
    )
    def chatid(message):

        bot.send_message(

            message.chat.id,

            f"🆔 Ваш Chat ID:\n\n"
            f"{message.chat.id}"

        )


    @bot.message_handler(
        commands=["test"]
    )
    def test(message):

        bot.send_message(

            message.chat.id,

            "✅ Telegram-бот работает!"

        )


    @bot.message_handler(
        commands=["report"]
    )
    def report(message):

        ratings = get_ratings().json

        if not ratings.get("ratings"):

            bot.send_message(
                message.chat.id,
                "📊 Оценок пока нет."
            )

            return


        items = ratings["ratings"]

        total = len(items)

        average = sum(
            int(item["rating"])
            for item in items
        ) / total


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
    def last(message):

        data = get_ratings().json

        items = data.get(
            "ratings",
            []
        )[:10]


        if not items:

            bot.send_message(
                message.chat.id,
                "📊 Оценок пока нет."
            )

            return


        text = "📋 ПОСЛЕДНИЕ ОЦЕНКИ\n\n"


        for item in items:

            rating = int(
                item["rating"]
            )

            stars = "⭐" * rating

            text += (

                f"📍 {item['checkpoint']}\n"

                f"👤 {item['employee']}\n"

                f"{stars} "
                f"({rating}/5)\n"

                f"💬 "
                f"{item.get('comment') or 'Без комментария'}\n"

                f"🕐 {item['created_at']}\n"

                "────────────────\n"

            )


        bot.send_message(
            message.chat.id,
            text
        )


# =========================================================
# АВТОМАТИЧЕСКАЯ ОТПРАВКА НОВЫХ ОЦЕНОК
# =========================================================

last_rating_id = 0


def telegram_monitor():

    global last_rating_id

    print(
        "🤖 Telegram-монитор запущен"
    )


    while True:

        try:

            if not bot or not CHAT_ID:

                time.sleep(10)

                continue


            connection = get_connection()

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

                WHERE id > ?

                ORDER BY id ASC
            """, (
                last_rating_id,
            ))


            rows = cursor.fetchall()

            connection.close()


            for row in rows:

                item = {

                    "id": row["id"],

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

                }


                bot.send_message(

                    CHAT_ID,

                    format_rating(item)

                )


                last_rating_id = row["id"]


                print(
                    "✅ Отправлено в Telegram:",
                    row["id"]
                )


        except Exception as error:

            print(
                "❌ Telegram error:",
                error
            )


        time.sleep(10)


# =========================================================
# TELEGRAM POLLING
# =========================================================

def telegram_polling():

    if not bot:

        print(
            "⚠️ Telegram отключён: "
            "BOT_TOKEN не установлен"
        )

        return


    print(
        "🤖 Telegram polling запущен"
    )


    while True:

        try:

            bot.infinity_polling(
                skip_pending=True,
                timeout=30,
                long_polling_timeout=30
            )

        except Exception as error:

            print(
                "❌ Telegram polling:",
                error
            )

            time.sleep(10)


# =========================================================
# ЗАПУСК
# =========================================================

init_database()


if bot:

    threading.Thread(
        target=telegram_polling,
        daemon=True
    ).start()


    threading.Thread(
        target=telegram_monitor,
        daemon=True
    ).start()


print("==============================")
print("СИСТЕМА ОЦЕНКИ СОТРУДНИКОВ")
print("==============================")
print("PORT:", PORT)
print("DATABASE:", DB_PATH)
print("==============================")


if __name__ == "__main__":

    app.run(
        host="0.0.0.0",
        port=PORT,
        debug=False
    )
