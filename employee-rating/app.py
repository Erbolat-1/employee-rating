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


# =========================================================
# HTML
# =========================================================

HTML = """
<!DOCTYPE html>

<html lang="ru">

<head>

<meta charset="UTF-8">

<meta name="viewport"
      content="width=device-width, initial-scale=1.0">

<title>Оценка сотрудника</title>

<style>

* {
    box-sizing: border-box;
}

body {

    margin: 0;

    min-height: 100vh;

    font-family: Arial, sans-serif;

    background:
        linear-gradient(
            135deg,
            #03152d,
            #0865c5
        );

    display: flex;

    align-items: center;

    justify-content: center;

    padding: 20px;
}

.card {

    width: 100%;

    max-width: 520px;

    background: white;

    border-radius: 24px;

    padding: 30px;

    box-shadow:
        0 20px 60px rgba(0,0,0,.35);
}

.logo {

    width: 75px;

    height: 75px;

    margin: 0 auto 15px;

    border-radius: 50%;

    background: #0865c5;

    color: white;

    display: flex;

    align-items: center;

    justify-content: center;

    font-size: 35px;
}

h1 {

    text-align: center;

    color: #073b75;

    margin: 0;
}

.subtitle {

    text-align: center;

    color: #777;

    margin: 8px 0 25px;
}

label {

    display: block;

    font-weight: bold;

    margin-top: 18px;

    margin-bottom: 7px;

    color: #333;
}

input,
textarea {

    width: 100%;

    padding: 14px;

    border: 1px solid #ccc;

    border-radius: 12px;

    font-size: 16px;

    outline: none;
}

input:focus,
textarea:focus {

    border-color: #0865c5;
}

textarea {

    min-height: 110px;

    resize: vertical;
}

.stars {

    display: flex;

    flex-direction: row-reverse;

    justify-content: center;

    gap: 5px;

    margin: 10px 0 20px;
}

.stars input {

    display: none;
}

.stars label {

    margin: 0;

    font-size: 45px;

    color: #ccc;

    cursor: pointer;
}

.stars label:hover,
.stars label:hover ~ label,
.stars input:checked ~ label {

    color: #ffc107;
}

button {

    width: 100%;

    border: none;

    border-radius: 12px;

    background: #0865c5;

    color: white;

    padding: 16px;

    margin-top: 20px;

    font-size: 17px;

    font-weight: bold;

    cursor: pointer;
}

button:hover {

    background: #064d98;
}

.success {

    display: none;

    text-align: center;

    padding: 20px;
}

.success-icon {

    font-size: 65px;
}

.success h2 {

    color: #16833b;
}

.footer {

    text-align: center;

    color: #999;

    font-size: 12px;

    margin-top: 18px;
}

</style>

</head>

<body>

<div class="card">

<div id="formBlock">

<div class="logo">
★
</div>

<h1>
Оценка сотрудника
</h1>

<div class="subtitle">
Оцените качество обслуживания
</div>


<label for="checkpoint">
📍 Пункт пропуска
</label>

<input
    type="text"
    id="checkpoint"
    placeholder="Введите пункт пропуска"
>


<label for="employee">
👤 ФИО сотрудника
</label>

<input
    type="text"
    id="employee"
    placeholder="Введите ФИО сотрудника"
>


<label>
⭐ Оценка работы
</label>

<div class="stars">

<input
    type="radio"
    name="rating"
    id="star5"
    value="5"
>

<label for="star5">★</label>


<input
    type="radio"
    name="rating"
    id="star4"
    value="4"
>

<label for="star4">★</label>


<input
    type="radio"
    name="rating"
    id="star3"
    value="3"
>

<label for="star3">★</label>


<input
    type="radio"
    name="rating"
    id="star2"
    value="2"
>

<label for="star2">★</label>


<input
    type="radio"
    name="rating"
    id="star1"
    value="1"
>

<label for="star1">★</label>

</div>


<label for="comment">
💬 Комментарий
</label>

<textarea
    id="comment"
    placeholder="Напишите отзыв или замечание..."
></textarea>


<button onclick="sendRating()">
Отправить оценку
</button>


<div class="footer">

Ваш отзыв помогает улучшать качество обслуживания

</div>

</div>


<div
    class="success"
    id="successBlock"
>

<div class="success-icon">
✅
</div>

<h2>
Спасибо за оценку!
</h2>

<p>
Ваша оценка успешно отправлена.
</p>

<button onclick="location.reload()">
Новая оценка
</button>

</div>

</div>


<script>

async function sendRating() {

    const checkpoint =
        document.getElementById("checkpoint")
        .value.trim();

    const employee =
        document.getElementById("employee")
        .value.trim();

    const comment =
        document.getElementById("comment")
        .value.trim();

    const ratingElement =
        document.querySelector(
            'input[name="rating"]:checked'
        );


    if (!checkpoint) {

        alert(
            "Введите пункт пропуска."
        );

        return;
    }


    if (!employee) {

        alert(
            "Введите ФИО сотрудника."
        );

        return;
    }


    if (!ratingElement) {

        alert(
            "Поставьте оценку от 1 до 5."
        );

        return;
    }


    const rating =
        Number(ratingElement.value);


    const data = {

        checkpoint: checkpoint,

        employee: employee,

        rating: rating,

        comment: comment

    };


    try {

        const response =
            await fetch(
                "/api/rating",
                {

                    method: "POST",

                    headers: {
                        "Content-Type":
                            "application/json"
                    },

                    body:
                        JSON.stringify(data)

                }
            );


        const result =
            await response.json();


        if (!response.ok ||
            !result.success) {

            throw new Error(
                result.message ||
                "Ошибка сервера"
            );
        }


        document
            .getElementById(
                "formBlock"
            )
            .style.display = "none";


        document
            .getElementById(
                "successBlock"
            )
            .style.display = "block";


    } catch (error) {

        console.error(error);

        alert(
            "❌ Не удалось отправить оценку.\\n\\n" +
            error.message
        );

    }

}

</script>

</body>

</html>
"""


# =========================================================
# ГЛАВНАЯ
# =========================================================

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
