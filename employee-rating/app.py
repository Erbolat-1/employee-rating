import os
import re
import sqlite3
import urllib.parse
import urllib.request
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)
DATABASE = "ratings.db"

# Словари ключевых слов для текстового анализа
POSITIVE_WORDS = {
    "отлично", "замечательно", "быстро", "вежливо", "профессионально",
    "качественно", "спасибо", "благодарность", "корректно", "чисто",
    "удобно", "прекрасно", "хорошо", "компетентно", "оперативно", "молодец",
    "вежливый", "быстрый", "отличный", "профессионал", "вежливость"
}

NEGATIVE_WORDS = {
    "плохо", "медленно", "грубо", "ужасно", "хамство", "ошибка",
    "очередь", "долго", "невнимательно", "превышение", "халатность",
    "претензия", "задержка", "проблема", "бардак", "грязь", "отвратительно",
    "грубый", "медлительный", "хам", "ужасный", "плохой"
}


def analyze_text(text: str) -> dict:
    """Анализирует текст и возвращает тональность, число слов и балл от 1 до 5."""
    if not text or not text.strip():
        return {
            "score": 3,
            "sentiment": "Нейтральный",
            "word_count": 0
        }

    clean_text = text.lower()
    words = re.findall(r'\b[а-яа-яa-z0-9]+\b', clean_text)
    
    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)

    # Расчет тональности и оценки от 1 до 5
    if pos_count > neg_count:
        sentiment = "Положительный"
        score = 5 if (pos_count - neg_count) >= 2 else 4
    elif neg_count > pos_count:
        sentiment = "Отрицательный"
        score = 1 if (neg_count - pos_count) >= 2 else 2
    else:
        sentiment = "Нейтральный"
        score = 3

    return {
        "score": score,
        "sentiment": sentiment,
        "word_count": len(words)
    }


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
                comment TEXT NOT NULL,
                rating INTEGER NOT NULL,
                sentiment TEXT NOT NULL,
                word_count INTEGER NOT NULL,
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
        print("BOT_TOKEN or CHAT_ID is not configured.")
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
            "👋 <b>Добро пожаловать в систему автоматической оценки сотрудников!</b>\n\n"
            "Доступные команды:\n"
            "/report — отчет по оценкам\n"
            "/last — последние 10 отзывов\n"
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
            f"📊 <b>Отчет по оценкам отзывов:</b>\n\n"
            f"• Всего отзывов проанализировано: <b>{count}</b>\n"
            f"• Средний балл: <b>{avg_val} / 5 ⭐</b>"
        )
    elif command == "/last":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT checkpoint, employee_name, comment, rating, sentiment, created_at FROM ratings ORDER BY id DESC LIMIT 10"
            )
            rows = cursor.fetchall()

        if not rows:
            text = "ℹ️ Отзывов пока нет."
        else:
            text = "📋 <b>Последние 10 отзывов:</b>\n\n"
            for r in rows:
                stars = "⭐" * r["rating"]
                text += (
                    f"📍 <b>Пункт:</b> {r['checkpoint']}\n"
                    f"👤 <b>Сотрудник:</b> {r['employee_name']}\n"
                    f"💬 <b>Текст:</b> <i>«{r['comment']}»</i>\n"
                    f"⭐ <b>Рассчитанная оценка:</b> {stars} ({r['rating']}/5)\n"
                    f"🎭 <b>Тональность:</b> {r['sentiment']}\n"
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
    comment = data.get("comment", "").strip()

    if not checkpoint or not employee_name or not comment:
        return jsonify({"success": False, "message": "Заполните все поля, включая текст отзыва!"}), 400

    # Автоматическая оценка текста
    analysis = analyze_text(comment)
    rating = analysis["score"]
    sentiment = analysis["sentiment"]
    word_count = analysis["word_count"]

    with get_db() as conn:
        conn.execute(
            """INSERT INTO ratings (checkpoint, employee_name, comment, rating, sentiment, word_count)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (checkpoint, employee_name, comment, rating, sentiment, word_count),
        )
        conn.commit()

    # Отправка в Telegram
    stars_str = "⭐" * rating
    msg_text = (
        f"📝 <b>Новая текстовая оценка сотрудника!</b>\n\n"
        f"📍 <b>Пункт пропуска:</b> {checkpoint}\n"
        f"👤 <b>Сотрудник:</b> {employee_name}\n"
        f"💬 <b>Текст отзыва:</b> <i>«{comment}»</i>\n\n"
        f"📊 <b>Результат анализа:</b>\n"
        f"⭐ <b>Рассчитанный балл:</b> {stars_str} ({rating}/5)\n"
        f"🎭 <b>Тональность:</b> {sentiment}\n"
        f"📏 <b>Слов в тексте:</b> {word_count}"
    )

    send_telegram_message(msg_text)

    return jsonify({
        "success": True,
        "message": "Спасибо! Ваш отзыв проанализирован и оценка сохранена.",
        "rating": rating,
        "sentiment": sentiment,
        "word_count": word_count
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
