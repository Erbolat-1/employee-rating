import os
import sqlite3
import urllib.parse
import urllib.request
from flask import Flask, jsonify, render_template, request
from text_evaluator import analyze_text

app = Flask(__name__)
DATABASE = "ratings.db"


def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ratings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                checkpoint TEXT NOT NULL,
                employee_name TEXT NOT NULL,
                rating INTEGER NOT NULL,
                comment TEXT,
                sentiment TEXT,
                word_count INTEGER,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        conn.commit()


init_db()


def send_telegram_message(text: str) -> bool:
    token = os.environ.get("BOT_TOKEN")
    chat_id = os.environ.get("CHAT_ID")

    if not token or not chat_id:
        print("Telegram BOT_TOKEN or CHAT_ID is not configured.")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")

    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return response.status == 200
    except Exception as e:
        print(f"Error sending Telegram message: {e}")
        return False


def process_telegram_command(command: str, chat_id: str):
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return

    if command == "/start":
        text = (
            "👋 <b>Добро пожаловать в систему оценки сотрудников!</b>\n\n"
            "Доступные команды:\n"
            "/report — итоговая статистика\n"
            "/last — последние 10 оценок\n"
            "/chatid — узнать ID текущего чата"
        )
    elif command == "/chatid":
        text = f"🆔 <b>ID этого чата:</b> <code>{chat_id}</code>"
    elif command == "/report":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), AVG(rating) FROM ratings")
            count, avg_rating = cursor.fetchone()

        avg_val = round(avg_rating, 2) if avg_rating else 0.0
        text = (
            f"📊 <b>Отчет по оценкам:</b>\n\n"
            f"• Всего оценок: <b>{count}</b>\n"
            f"• Средняя оценка: <b>{avg_val} / 5 ⭐</b>"
        )
    elif command == "/last":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT checkpoint, employee_name, rating, comment, sentiment, created_at FROM ratings ORDER BY id DESC LIMIT 10"
            )
            rows = cursor.fetchall()

        if not rows:
            text = "ℹ️ Оценок пока нет."
        else:
            text = "📋 <b>Последние 10 оценок:</b>\n\n"
            for r in rows:
                stars = "⭐" * r["rating"]
                sentiment_str = f"\n🎭 <b>Тональность:</b> {r['sentiment']}" if r["sentiment"] else ""
                comment_str = f"\n💬 <i>«{r['comment']}»</i>" if r["comment"] else ""
                text += (
                    f"📍 <b>Пункт:</b> {r['checkpoint']}\n"
                    f"👤 <b>Сотрудник:</b> {r['employee_name']}\n"
                    f"⭐ <b>Оценка:</b> {stars} ({r['rating']}/5){sentiment_str}{comment_str}\n"
                    f"🕒 <b>Дата:</b> {r['created_at']}\n"
                    f"------------------------------\n"
                )
    else:
        text = "❓ Неизвестная команда. Используйте /start."

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML"}).encode("utf-8")
    try:
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Error answering Telegram command: {e}")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/rate", methods=["POST"])
def add_rating():
    data = request.get_json() or {}

    checkpoint = data.get("checkpoint", "").strip()
    employee_name = data.get("employee_name", "").strip()
    rating = data.get("rating")
    comment = data.get("comment", "").strip()

    if not checkpoint or not employee_name or not rating:
        return jsonify({"success": False, "message": "Заполните все обязательные поля!"}), 400

    try:
        rating = int(rating)
        if rating < 1 or rating > 5:
            raise ValueError()
    except ValueError:
        return jsonify({"success": False, "message": "Оценка должна быть от 1 до 5."}), 400

    # Текстовый анализ отзыва
    analysis = analyze_text(comment)
    sentiment = analysis["sentiment"]
    word_count = analysis["word_count"]

    with get_db() as conn:
        conn.execute(
            """INSERT INTO ratings (checkpoint, employee_name, rating, comment, sentiment, word_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (checkpoint, employee_name, rating, comment, sentiment, word_count),
        )
        conn.commit()

    # Отправка в Telegram
    stars_str = "⭐" * rating
    msg_text = (
        f"🚨 <b>Новая оценка сотрудника!</b>\n\n"
        f"📍 <b>Пункт пропуска:</b> {checkpoint}\n"
        f"👤 <b>Сотрудник:</b> {employee_name}\n"
        f"⭐ <b>Оценка:</b> {stars_str} ({rating}/5)\n"
    )
    if comment:
        msg_text += f"💬 <b>Комментарий:</b> {comment}\n"
        msg_text += f"🎭 <b>Анализ текста:</b> {sentiment} ({word_count} слов)"

    send_telegram_message(msg_text)

    return jsonify({
        "success": True,
        "message": "Спасибо за оценку! Ваша оценка успешно отправлена.",
        "analysis": analysis
    })


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    data = request.get_json() or {}
    if "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")
        if text.startswith("/"):
            command = text.split()[0]
            process_telegram_command(command, chat_id)
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
