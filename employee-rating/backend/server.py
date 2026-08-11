from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS

import sqlite3
import os
import requests

from datetime import datetime
from dotenv import load_dotenv


# ==============================
# НАСТРОЙКИ
# ==============================

load_dotenv()

app = Flask(__name__)
CORS(app)


# ==============================
# ПУТЬ К ПРОЕКТУ
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


# ==============================
# TELEGRAM
# ==============================

TELEGRAM_BOT_TOKEN = os.getenv(
    "8606610454:AAG6wYBzLBI0ETLojTWx7dORnbRTRUBUQOo"
)

TELEGRAM_CHAT_ID = os.getenv(
    "7421182406"
)

# ==============================
# СОЗДАНИЕ БАЗЫ
# ==============================

def init_database():

    connection = sqlite3.connect(
        DB_PATH
    )

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


# ==============================
# TELEGRAM
# ==============================

def send_telegram_message(text):

    # Проверяем настройки

    if not TELEGRAM_BOT_TOKEN:

        print(
            "8606610454:AAG6wYBzLBI0ETLojTWx7dORnbRTRUBUQOo"
        )

        return False

    if not TELEGRAM_CHAT_ID:

        print(
            "7421182406"
        )

        return False


    url = (
        "https://api.telegram.org/bot"
        + TELEGRAM_BOT_TOKEN
        + "/sendMessage"
    )


    payload = {

        "chat_id":
            TELEGRAM_CHAT_ID,

        "text":
            text
    }


    try:

        response = requests.post(

            url,

            json=payload,

            timeout=10

        )


        if response.ok:

            print(
                "✅ Telegram: сообщение отправлено"
            )

            return True


        print(
            "❌ Telegram ошибка:",
            response.text
        )

        return False


    except Exception as error:

        print(
            "❌ Ошибка соединения с Telegram:",
            error
        )

        return False


# ==============================
# ГЛАВНАЯ СТРАНИЦА
# ==============================

@app.route("/")
def home():

    return send_from_directory(
        BASE_DIR,
        "index.html"
    )


# ==============================
# ПОЛУЧЕНИЕ ОЦЕНКИ
# ==============================

@app.route(
    "/api/rating",
    methods=["POST"]
)
def receive_rating():

    data = request.get_json()


    if not data:

        return jsonify({

            "success": False,

            "message":
                "Нет данных"

        }), 400


    checkpoint = str(
        data.get(
            "checkpoint",
            ""
        )
    ).strip()


    employee = str(
        data.get(
            "employee",
            ""
        )
    ).strip()


    comment = str(
        data.get(
            "comment",
            ""
        )
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

            "message":
                "Некорректная оценка"

        }), 400


    # ==============================
    # ПРОВЕРКА
    # ==============================

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


    # ==============================
    # ВРЕМЯ
    # ==============================

    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )


    # ==============================
    # СОХРАНЕНИЕ
    # ==============================

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


    # ==============================
    # ТЕРМИНАЛ
    # ==============================

    print()

    print(
        "=============================="
    )

    print(
        "НОВАЯ ОЦЕНКА СОХРАНЕНА"
    )

    print(
        "=============================="
    )

    print(
        "ID:",
        rating_id
    )

    print(
        "Пункт пропуска:",
        checkpoint
    )

    print(
        "ФИО:",
        employee
    )

    print(
        "Оценка:",
        rating
    )

    print(
        "Комментарий:",
        comment
    )

    print(
        "Дата:",
        created_at
    )

    print(
        "=============================="
    )


    # ==============================
    # TELEGRAM
    # ==============================

    stars = "⭐" * rating


    telegram_text = (

        "🔔 НОВАЯ ОЦЕНКА\n\n"

        f"📍 Пункт пропуска:\n"
        f"{checkpoint}\n\n"

        f"👤 Сотрудник:\n"
        f"{employee}\n\n"

        f"⭐ Оценка:\n"
        f"{stars} ({rating}/5)\n\n"

        f"💬 Комментарий:\n"
        f"{comment or 'Без комментария'}\n\n"

        f"🕐 Время:\n"
        f"{created_at}\n\n"

        f"🆔 ID оценки: {rating_id}"
    )


    send_telegram_message(
        telegram_text
    )


    # ==============================
    # ОТВЕТ САЙТУ
    # ==============================

    return jsonify({

        "success": True,

        "message":
            "Оценка сохранена",

        "id":
            rating_id,

        "created_at":
            created_at

    })


# ==============================
# ПОЛУЧЕНИЕ ВСЕХ ОЦЕНОК
# ==============================

@app.route(
    "/api/ratings",
    methods=["GET"]
)
def get_ratings():

    connection = sqlite3.connect(
        DB_PATH
    )

    connection.row_factory = (
        sqlite3.Row
    )

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

        "success":
            True,

        "count":
            len(ratings),

        "ratings":
            ratings

    })


# ==============================
# ЗАПУСК
# ==============================

if __name__ == "__main__":

    init_database()


    print(
        "=============================="
    )

    print(
        "СЕРВЕР ОЦЕНКИ СОТРУДНИКОВ"
    )

    print(
        "=============================="
    )

    print(
        "База:",
        DB_PATH
    )

    print(
        "Сайт:",
        "http://127.0.0.1:5000"
    )

    print(
        "=============================="
    )


    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True

    )
