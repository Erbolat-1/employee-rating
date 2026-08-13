import io
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
from flask import Flask, jsonify, render_template, request
from flask_cors import CORS
import pandas as pd

app = Flask(__name__)
CORS(app)  # Разрешает запросы из Telegram Mini App

DATABASE = "ratings.db"

# Ключевые слова для анализа тональности
POSITIVE_WORDS = {
    "отлично", "замечательно", "быстро", "вежливо", "профессионально",
    "качественно", "спасибо", "благодарность", "корректно", "чисто",
    "удобно", "прекрасно", "хорошо", "компетентно", "оперативно", "молодец",
    "вежливый", "быстрый", "отличный", "профессионал", "вежливость", "образцово"
}

NEGATIVE_WORDS = {
    "плохо", "медленно", "грубо", "ужасно", "хамство", "ошибка",
    "очередь", "долго", "невнимательно", "превышение", "халатность",
    "претензия", "задержка", "проблема", "бардак", "грязь", "отвратительно",
    "грубый", "медлительный", "хам", "ужасный", "плохой", "грубость"
}


def analyze_text(text: str) -> dict:
    """Расчет оценки от 1 до 5 по содержанию ключевых слов."""
    if not text or not text.strip():
        return {"score": 3, "sentiment": "Нейтральный", "word_count": 0}

    clean_text = text.lower()
    words = re.findall(r'\b[а-яа-яa-z0-9]+\b', clean_text)

    pos_count = sum(1 for w in words if w in POSITIVE_WORDS)
    neg_count = sum(1 for w in words if w in NEGATIVE_WORDS)

    if pos_count > neg_count:
        sentiment = "Положительный"
        score = 5 if (pos_count - neg_count) >= 2 else 4
    elif neg_count > pos_count:
        sentiment = "Отрицательный"
        score = 1 if (neg_count - pos_count) >= 2 else 2
    else:
        sentiment = "Нейтральный"
        score = 3

    return {"score": score, "sentiment": sentiment, "word_count": len(words)}


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


def send_telegram_document(chat_id: str, file_bytes: bytes, filename: str, caption: str = "") -> bool:
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return False

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    boundary = "----WebKitFormBoundary7MA44QEldjy1Yb0e"
    
    body = []
    body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"chat_id\"\r\n\r\n{chat_id}\r\n".encode("utf-8"))
    
    if caption:
        body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"caption\"\r\n\r\n{caption}\r\n".encode("utf-8"))
        body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"parse_mode\"\r\n\r\nHTML\r\n".encode("utf-8"))
        
    body.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{filename}\"\r\nContent-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n".encode("utf-8"))
    body.append(file_bytes)
    body.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    
    payload = b"".join(body)
    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}

    try:
        req = urllib.request.Request(url, data=payload, headers=headers)
        with urllib.request.urlopen(req, timeout=10) as response:
            return response.status == 200
    except Exception as e:
        print(f"Error sending document: {e}")
        return False


def send_telegram_webapp_button(chat_id: str, webapp_url: str):
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": "📊 <b>Нажмите кнопку ниже для просмотра отчета в формате Mini App:</b>",
        "parse_mode": "HTML",
        "reply_markup": {
            "inline_keyboard": [[
                {
                    "text": "📈 Открыть интерактивный отчет",
                    "web_app": {"url": webapp_url}
                }
            ]]
        }
    }).encode("utf-8")

    headers = {"Content-Type": "application/json"}
    try:
        req = urllib.request.Request(url, data=payload, headers=headers)
        urllib.request.urlopen(req, timeout=5)
    except Exception as e:
        print(f"Error sending Web App button: {e}")


def process_telegram_command(command: str, chat_id: str):
    token = os.environ.get("BOT_TOKEN")
    if not token:
        return

    if command == "/start":
        text = (
            "👋 <b>Система оценки сотрудников</b>\n\n"
            "Доступные команды:\n"
            "/app или /view — Открыть интерактивный отчет (Mini App)\n"
            "/excel — Скачать выгрузку всех данных в формате Excel\n"
            "/report — Краткая сводка оценок\n"
            "/last — Последние 10 отзывов\n"
            "/delete_last — Удалить последний отзыв\n"
            "/reset_all — Полностью очистить базу данных\n"
            "/chatid — Узнать ID этого чата"
        )
        send_telegram_message(text)

    elif command in ["/app", "/view"]:
        server_url = os.environ.get("SERVER_URL", "https://your-domain.onrender.com")
        webapp_url = f"{server_url}/webapp/report"
        send_telegram_webapp_button(chat_id, webapp_url)

    elif command in ["/excel", "/export"]:
        with get_db() as conn:
            df = pd.read_sql_query(
                """
                SELECT 
                    id AS 'ID',
                    created_at AS 'Дата и время',
                    checkpoint AS 'Пункт пропуска',
                    employee_name AS 'Сотрудник',
                    comment AS 'Текст отзыва',
                    rating AS 'Оценка',
                    sentiment AS 'Тональность',
                    word_count AS 'Слов'
                FROM ratings
                ORDER BY id DESC
                """, 
                conn
            )

        if df.empty:
            send_telegram_message("ℹ️ База данных пуста. Записей для Excel нет.")
            return

        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Отчет')
        
        excel_bytes = output.getvalue()
        send_telegram_document(
            chat_id, 
            excel_bytes, 
            "Отчет_по_оценкам.xlsx", 
            f"📊 <b>Выгрузка в Excel готова!</b>\nВсего отзывов в базе: <b>{len(df)}</b>"
        )

    elif command == "/delete_last":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id FROM ratings ORDER BY id DESC LIMIT 1")
            row = cursor.fetchone()
            if row:
                conn.execute("DELETE FROM ratings WHERE id = ?", (row["id"],))
                conn.commit()
                text = f"🗑️ <b>Запись №{row['id']} была удалена.</b>"
            else:
                text = "ℹ️ База данных уже пуста."
        send_telegram_message(text)

    elif command == "/reset_all":
        with get_db() as conn:
            conn.execute("DELETE FROM ratings")
            conn.execute("DELETE FROM sqlite_sequence WHERE name='ratings'")
            conn.commit()
        send_telegram_message("🔥 <b>База данных успешно очищена!</b>")

    elif command == "/report":
        with get_db() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), AVG(rating) FROM ratings")
            count, avg_rating = cursor.fetchone()

        avg_val = round(avg_rating, 2) if avg_rating else 0.0
        text = (
            f"📊 <b>Общая статистика:</b>\n\n"
            f"• Всего отзывов: <b>{count}</b>\n"
            f"• Средний балл: <b>{avg_val} / 5 ⭐</b>"
        )
        send_telegram_message(text)

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
                    f"⭐ <b>Оценка:</b> {stars} ({r['rating']}/5)\n"
                    f"🎭 <b>Тональность:</b> {r['sentiment']}\n"
                    f"🕒 <b>Дата:</b> {r['created_at']}\n"
                    f"------------------------------\n"
                )
        send_telegram_message(text)

    elif command == "/chatid":
        send_telegram_message(f"🆔 <b>ID чата:</b> <code>{chat_id}</code>")


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/webapp/report")
def webapp_report():
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, checkpoint, employee_name, comment, rating, sentiment, created_at 
            FROM ratings 
            ORDER BY id DESC
            """
        )
        ratings = cursor.fetchall()
    return render_template("report_webapp.html", ratings=ratings)


@app.route("/api/rate", methods=["POST"])
def add_rating():
    data = request.get_json() or {}

    checkpoint = data.get("checkpoint", "").strip()
    employee_name = data.get("employee_name", "").strip()
    comment = data.get("comment", "").strip()

    if not checkpoint or not employee_name or not comment:
        return jsonify({"success": False, "message": "Заполните все обязательные поля!"}), 400

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

    stars_str = "⭐" * rating

    if rating <= 2:
        msg_text = (
            f"🚨🚨🚨 <b>ВНИМАНИЕ! НЕГАТИВНЫЙ ОТЗЫВ</b> 🚨🚨🚨\n"
            f"<code>══════════════════════════════════</code>\n\n"
            f"📍 <b>Пункт пропуска:</b> {checkpoint}\n"
            f"👤 <b>Сотрудник:</b> {employee_name}\n"
            f"💬 <b>Отзыв:</b> <i>«{comment}»</i>\n\n"
            f"📊 <b>Анализ:</b>\n"
            f"🔴 <b>Оценка:</b> {stars_str} ({rating}/5)\n"
            f"🎭 <b>Тональность:</b> {sentiment}\n\n"
            f"<code>⚠️ ТРЕБУЕТСЯ РЕАГИРОВАНИЕ РУКОВОДСТВА!</code>\n"
            f"<code>══════════════════════════════════</code>"
        )
    else:
        msg_text = (
            f"📝 <b>Новый отзыв о сотруднике</b>\n\n"
            f"📍 <b>Пункт пропуска:</b> {checkpoint}\n"
            f"👤 <b>Сотрудник:</b> {employee_name}\n"
            f"💬 <b>Отзыв:</b> <i>«{comment}»</i>\n\n"
            f"📊 <b>Анализ текста:</b>\n"
            f"⭐ <b>Авто-оценка:</b> {stars_str} ({rating}/5)\n"
            f"🎭 <b>Тональность:</b> {sentiment}"
        )

    send_telegram_message(msg_text)

    return jsonify({
        "success": True,
        "message": "Оценка успешно отправлена!",
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
