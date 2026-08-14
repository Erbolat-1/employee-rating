import io
import json
import os
import re
import sqlite3
import urllib.parse
import urllib.request
import urllib.error
import html
from datetime import datetime, timezone

import pandas as pd
from flask import Flask, jsonify, request, render_template_string
from flask_cors import CORS


# =========================================================
# CONFIGURATION
# =========================================================

app = Flask(__name__)
CORS(app)

DATABASE = os.environ.get("DATABASE_PATH", "ratings.db")

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

# On Render, RENDER_EXTERNAL_URL is supplied automatically.
SERVER_URL = (
    os.environ.get("SERVER_URL", "").strip().rstrip("/")
    or os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
)

WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()

# If true, the application tries to register the Telegram webhook at startup.
AUTO_SET_WEBHOOK = os.environ.get("AUTO_SET_WEBHOOK", "true").lower() in {
    "1", "true", "yes", "on"
}


# =========================================================
# TEXT ANALYSIS
# =========================================================

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
    if not text or not text.strip():
        return {
            "score": 3,
            "sentiment": "Нейтральный",
            "word_count": 0
        }

    clean_text = text.lower()
    words = re.findall(r"[а-яёa-z0-9]+", clean_text)

    pos_count = sum(1 for word in words if word in POSITIVE_WORDS)
    neg_count = sum(1 for word in words if word in NEGATIVE_WORDS)

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


# =========================================================
# DATABASE
# =========================================================

def get_db():
    conn = sqlite3.connect(DATABASE, timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
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
        """)
        conn.commit()


init_db()


# =========================================================
# HELPERS
# =========================================================

def esc(value) -> str:
    """Safe text for Telegram HTML."""
    return html.escape(str(value), quote=False)


def get_public_url() -> str:
    return SERVER_URL or "http://127.0.0.1:5000"


def telegram_request(method: str, payload: dict, timeout: int = 10):
    if not BOT_TOKEN:
        return False, {"description": "BOT_TOKEN is not configured"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            body = response.read().decode("utf-8")
            parsed = json.loads(body)
            return response.status == 200 and parsed.get("ok", False), parsed
    except Exception as exc:
        print(f"[Telegram] {method} error: {exc}")
        return False, {"description": str(exc)}


def send_telegram_message(text: str, chat_id: str = None, reply_markup=None) -> bool:
    target_chat_id = chat_id or CHAT_ID

    if not BOT_TOKEN or not target_chat_id:
        print("[Telegram] BOT_TOKEN or CHAT_ID is missing")
        return False

    payload = {
        "chat_id": target_chat_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    ok, result = telegram_request("sendMessage", payload)
    if not ok:
        print(f"[Telegram] sendMessage failed: {result}")
    return ok


def send_telegram_document(chat_id: str, file_bytes: bytes,
                           filename: str, caption: str = "") -> bool:
    if not BOT_TOKEN:
        return False

    boundary = "----PythonTelegramBoundary7MA44QEldjy1Yb0e"

    body = []

    body.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="chat_id"\r\n\r\n'
        f"{chat_id}\r\n"
    )

    if caption:
        body.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="caption"\r\n\r\n'
            f"{caption}\r\n"
        )
        body.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="parse_mode"\r\n\r\n'
            f"HTML\r\n"
        )

    body.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; '
        f'filename="{filename}"\r\n'
        f"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
    )

    raw_body = b"".join(
        part.encode("utf-8") if isinstance(part, str) else part
        for part in body
    )

    raw_body += file_bytes
    raw_body += f"\r\n--{boundary}--\r\n".encode("utf-8")

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument"

    req = urllib.request.Request(
        url,
        data=raw_body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status == 200
    except Exception as exc:
        print(f"[Telegram] sendDocument error: {exc}")
        return False


def make_main_keyboard():
    return {
        "inline_keyboard": [
            [
                {
                    "text": "📊 Открыть Mini App",
                    "web_app": {
                        "url": f"{get_public_url()}/webapp/report"
                    }
                }
            ],
            [
                {"text": "📈 Статистика", "callback_data": "report"},
                {"text": "📋 Последние отзывы", "callback_data": "last"}
            ],
            [
                {"text": "📥 Excel", "callback_data": "excel"}
            ]
        ]
    }


# =========================================================
# TELEGRAM BOT
# =========================================================

def send_start_menu(chat_id: str):
    text = (
        "👋 <b>Система оценки сотрудников</b>\n\n"
        "Выберите действие:"
    )

    send_telegram_message(
        text,
        chat_id=chat_id,
        reply_markup=make_main_keyboard()
    )


def send_report(chat_id: str):
    with get_db() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*), AVG(rating) FROM ratings")
        count, avg_rating = cursor.fetchone()

    avg_val = round(avg_rating, 2) if avg_rating else 0.0

    text = (
        "📊 <b>Общая статистика</b>\n\n"
        f"• Всего отзывов: <b>{count}</b>\n"
        f"• Средний балл: <b>{avg_val} / 5 ⭐</b>"
    )

    send_telegram_message(text, chat_id=chat_id)


def send_last(chat_id: str):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT checkpoint, employee_name, comment,
                   rating, sentiment, created_at
            FROM ratings
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

    if not rows:
        send_telegram_message(
            "ℹ️ <b>Отзывов пока нет.</b>",
            chat_id=chat_id
        )
        return

    parts = ["📋 <b>Последние 10 отзывов</b>\n"]

    for row in rows:
        stars = "⭐" * int(row["rating"])

        parts.append(
            f"📍 <b>Пункт:</b> {esc(row['checkpoint'])}\n"
            f"👤 <b>Сотрудник:</b> {esc(row['employee_name'])}\n"
            f"💬 <b>Отзыв:</b> «{esc(row['comment'])}»\n"
            f"⭐ <b>Оценка:</b> {stars} ({row['rating']}/5)\n"
            f"🎭 <b>Тональность:</b> {esc(row['sentiment'])}\n"
            f"🕒 <b>Дата:</b> {esc(row['created_at'])}\n"
            "────────────────────"
        )

    send_telegram_message("\n".join(parts), chat_id=chat_id)


def send_excel(chat_id: str):
    with get_db() as conn:
        df = pd.read_sql_query("""
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
        """, conn)

    if df.empty:
        send_telegram_message(
            "ℹ️ База данных пуста. Записей для Excel нет.",
            chat_id=chat_id
        )
        return

    output = io.BytesIO()

    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Отчет")

    output.seek(0)

    caption = (
        "📊 <b>Выгрузка в Excel готова!</b>\n"
        f"Всего отзывов: <b>{len(df)}</b>"
    )

    send_telegram_document(
        chat_id,
        output.getvalue(),
        "Отчет_по_оценкам.xlsx",
        caption
    )


def delete_last():
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM ratings ORDER BY id DESC LIMIT 1"
        ).fetchone()

        if not row:
            return None

        conn.execute(
            "DELETE FROM ratings WHERE id = ?",
            (row["id"],)
        )
        conn.commit()

        return row["id"]


def reset_all():
    with get_db() as conn:
        conn.execute("DELETE FROM ratings")
        conn.execute(
            "DELETE FROM sqlite_sequence WHERE name='ratings'"
        )
        conn.commit()


def process_telegram_command(command: str, chat_id: str):
    command = command.lower().split("@")[0]

    if command == "/start":
        send_start_menu(chat_id)

    elif command in ("/app", "/view"):
        send_telegram_message(
            "📊 <b>Открыть интерактивный отчет:</b>",
            chat_id=chat_id,
            reply_markup=make_main_keyboard()
        )

    elif command in ("/excel", "/export"):
        send_excel(chat_id)

    elif command == "/report":
        send_report(chat_id)

    elif command == "/last":
        send_last(chat_id)

    elif command == "/delete_last":
        deleted_id = delete_last()

        if deleted_id is None:
            text = "ℹ️ База данных уже пуста."
        else:
            text = f"🗑️ <b>Запись №{deleted_id} удалена.</b>"

        send_telegram_message(text, chat_id=chat_id)

    elif command == "/reset_all":
        reset_all()
        send_telegram_message(
            "🧹 <b>Все отзывы удалены.</b>",
            chat_id=chat_id
        )

    elif command == "/chatid":
        send_telegram_message(
            f"🆔 <b>ID чата:</b> <code>{esc(chat_id)}</code>",
            chat_id=chat_id
        )

    else:
        send_telegram_message(
            "❓ Неизвестная команда.\n\n"
            "Используйте /start для открытия меню.",
            chat_id=chat_id
        )


def process_telegram_update(data: dict):
    message = data.get("message")

    if message:
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))
        text = message.get("text", "")

        if chat_id and text.startswith("/"):
            process_telegram_command(text.split()[0], chat_id)

    callback = data.get("callback_query")

    if callback:
        callback_id = callback.get("id")
        callback_data = callback.get("data", "")
        message = callback.get("message", {})
        chat = message.get("chat", {})
        chat_id = str(chat.get("id", ""))

        if BOT_TOKEN and callback_id:
            telegram_request(
                "answerCallbackQuery",
                {"callback_query_id": callback_id},
                timeout=5
            )

        if callback_data == "report":
            send_report(chat_id)
        elif callback_data == "last":
            send_last(chat_id)
        elif callback_data == "excel":
            send_excel(chat_id)


def set_telegram_webhook() -> bool:
    if not BOT_TOKEN:
        print("[Webhook] BOT_TOKEN is not configured")
        return False

    if not SERVER_URL:
        print("[Webhook] SERVER_URL/RENDER_EXTERNAL_URL is not configured")
        return False

    webhook_url = f"{SERVER_URL}/webhook"

    payload = {
        "url": webhook_url
    }

    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET

    ok, result = telegram_request("setWebhook", payload)

    if ok:
        print(f"[Webhook] Telegram webhook configured: {webhook_url}")
    else:
        print(f"[Webhook] Failed: {result}")

    return ok


# =========================================================
# MINI APP HTML
# =========================================================

INDEX_HTML = """
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Система оценки сотрудников</title>
<style>
*{box-sizing:border-box}
body{
    margin:0;
    min-height:100vh;
    font-family:Arial,sans-serif;
    background:#06152f;
    color:#fff;
    display:flex;
    align-items:center;
    justify-content:center;
    padding:20px;
}
.card{
    width:100%;
    max-width:650px;
    background:#0c2347;
    border:1px solid rgba(255,255,255,.12);
    border-radius:24px;
    padding:28px;
    box-shadow:0 20px 60px rgba(0,0,0,.35);
}
h1{margin:0 0 10px;font-size:28px}
p{color:#b9c8df}
label{display:block;margin:18px 0 7px;font-weight:bold}
input,textarea{
    width:100%;
    border:1px solid #35537e;
    background:#071a38;
    color:white;
    border-radius:13px;
    padding:14px;
    font-size:16px;
}
textarea{min-height:130px;resize:vertical}
button{
    width:100%;
    margin-top:22px;
    border:0;
    border-radius:14px;
    padding:15px;
    font-size:17px;
    font-weight:bold;
    cursor:pointer;
    background:#fff;
    color:#08204a;
}
button:disabled{opacity:.6}
#result{margin-top:18px;padding:14px;border-radius:12px;display:none}
.success{background:#123f2a}
.error{background:#5a1e29}
</style>
</head>
<body>
<div class="card">
    <h1>⭐ Оценка сотрудника</h1>
    <p>Заполните данные и отправьте отзыв.</p>

    <form id="ratingForm">
        <label>Пункт пропуска</label>
        <input id="checkpoint" required placeholder="Например: Атамекен">

        <label>Сотрудник</label>
        <input id="employee_name" required placeholder="ФИО сотрудника">

        <label>Ваш отзыв</label>
        <textarea id="comment" required placeholder="Напишите отзыв..."></textarea>

        <button id="submitBtn" type="submit">Отправить оценку</button>
    </form>

    <div id="result"></div>
</div>

<script>
const form = document.getElementById("ratingForm");
const result = document.getElementById("result");
const button = document.getElementById("submitBtn");

form.addEventListener("submit", async (event) => {
    event.preventDefault();

    button.disabled = true;
    result.style.display = "none";

    const payload = {
        checkpoint: document.getElementById("checkpoint").value.trim(),
        employee_name: document.getElementById("employee_name").value.trim(),
        comment: document.getElementById("comment").value.trim()
    };

    try {
        const response = await fetch("/api/rate", {
            method: "POST",
            headers: {"Content-Type": "application/json"},
            body: JSON.stringify(payload)
        });

        const data = await response.json();

        result.style.display = "block";

        if (data.success) {
            result.className = "success";
            result.innerHTML =
                "✅ " + data.message +
                "<br>⭐ Авто-оценка: " + data.rating + "/5" +
                "<br>🎭 Тональность: " + data.sentiment;

            form.reset();
        } else {
            result.className = "error";
            result.textContent = data.message || "Ошибка отправки.";
        }
    } catch (error) {
        result.style.display = "block";
        result.className = "error";
        result.textContent = "Ошибка соединения с сервером.";
    } finally {
        button.disabled = false;
    }
});
</script>
</body>
</html>
"""


REPORT_HTML = """
<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Интерактивный отчет</title>
<style>
*{box-sizing:border-box}
body{
    margin:0;
    font-family:Arial,sans-serif;
    background:#06152f;
    color:#fff;
}
header{
    padding:22px;
    background:#0c2347;
    position:sticky;
    top:0;
    z-index:5;
}
h1{margin:0 0 5px}
.stats{
    display:grid;
    grid-template-columns:repeat(2,1fr);
    gap:12px;
    padding:16px;
}
.stat{
    background:#0c2347;
    border-radius:16px;
    padding:18px;
}
.value{font-size:26px;font-weight:bold;margin-top:7px}
.container{padding:0 16px 30px}
.item{
    background:#0c2347;
    border-radius:17px;
    padding:17px;
    margin-bottom:12px;
}
.row{margin:6px 0}
.comment{color:#cbd7e9;margin-top:10px}
.badge{
    display:inline-block;
    padding:5px 9px;
    border-radius:10px;
    background:#173a68;
}
.empty{
    text-align:center;
    padding:50px 20px;
    color:#aebed5;
}
@media(max-width:500px){
    .stats{grid-template-columns:1fr}
}
</style>
</head>
<body>
<header>
    <h1>📊 Отчет по оценкам</h1>
    <div>Данные обновлены: {{ now }}</div>
</header>

<div class="stats">
    <div class="stat">
        <div>Всего отзывов</div>
        <div class="value">{{ ratings|length }}</div>
    </div>
    <div class="stat">
        <div>Средняя оценка</div>
        <div class="value">{{ average }} / 5 ⭐</div>
    </div>
</div>

<div class="container">
{% if ratings %}
    {% for r in ratings %}
    <div class="item">
        <div class="row">📍 <b>Пункт:</b> {{ r["checkpoint"] }}</div>
        <div class="row">👤 <b>Сотрудник:</b> {{ r["employee_name"] }}</div>
        <div class="row">
            ⭐ <b>Оценка:</b>
            <span class="badge">{{ "⭐" * r["rating"] }} ({{ r["rating"] }}/5)</span>
        </div>
        <div class="row">🎭 <b>Тональность:</b> {{ r["sentiment"] }}</div>
        <div class="comment">💬 {{ r["comment"] }}</div>
        <div class="row">🕒 {{ r["created_at"] }}</div>
    </div>
    {% endfor %}
{% else %}
    <div class="empty">Отзывов пока нет.</div>
{% endif %}
</div>
</body>
</html>
"""


# =========================================================
# ROUTES
# =========================================================

@app.route("/")
def index():
    return render_template_string(INDEX_HTML)


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "service": "employee-rating",
        "server_url": get_public_url(),
        "telegram_configured": bool(BOT_TOKEN),
        "chat_configured": bool(CHAT_ID),
        "webhook_configured": bool(BOT_TOKEN and SERVER_URL),
        "time_utc": datetime.now(timezone.utc).isoformat()
    })


@app.route("/webapp/report")
def webapp_report():
    with get_db() as conn:
        ratings = conn.execute("""
            SELECT id, checkpoint, employee_name, comment,
                   rating, sentiment, created_at
            FROM ratings
            ORDER BY id DESC
        """).fetchall()

        avg = conn.execute(
            "SELECT AVG(rating) FROM ratings"
        ).fetchone()[0]

    average = round(avg, 2) if avg else 0

    return render_template_string(
        REPORT_HTML,
        ratings=ratings,
        average=average,
        now=datetime.now().strftime("%d.%m.%Y %H:%M")
    )


@app.route("/api/rate", methods=["POST"])
def add_rating():
    data = request.get_json(silent=True) or {}

    checkpoint = str(data.get("checkpoint", "")).strip()
    employee_name = str(data.get("employee_name", "")).strip()
    comment = str(data.get("comment", "")).strip()

    if not checkpoint or not employee_name or not comment:
        return jsonify({
            "success": False,
            "message": "Заполните все обязательные поля!"
        }), 400

    if len(checkpoint) > 200:
        return jsonify({
            "success": False,
            "message": "Название пункта слишком длинное."
        }), 400

    if len(employee_name) > 200:
        return jsonify({
            "success": False,
            "message": "ФИО сотрудника слишком длинное."
        }), 400

    if len(comment) > 5000:
        return jsonify({
            "success": False,
            "message": "Отзыв слишком длинный."
        }), 400

    analysis = analyze_text(comment)

    rating = analysis["score"]
    sentiment = analysis["sentiment"]
    word_count = analysis["word_count"]

    with get_db() as conn:
        cursor = conn.execute("""
            INSERT INTO ratings (
                checkpoint,
                employee_name,
                comment,
                rating,
                sentiment,
                word_count
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            checkpoint,
            employee_name,
            comment,
            rating,
            sentiment,
            word_count
        ))

        rating_id = cursor.lastrowid
        conn.commit()

    stars = "⭐" * rating

    if rating <= 2:
        msg_text = (
            "🚨 <b>НЕГАТИВНЫЙ ОТЗЫВ</b>\n\n"
            f"📍 <b>Пункт:</b> {esc(checkpoint)}\n"
            f"👤 <b>Сотрудник:</b> {esc(employee_name)}\n"
            f"💬 <b>Отзыв:</b> «{esc(comment)}»\n\n"
            f"🔴 <b>Оценка:</b> {stars} ({rating}/5)\n"
            f"🎭 <b>Тональность:</b> {esc(sentiment)}\n\n"
            "⚠️ <b>Требуется внимание руководства.</b>"
        )
    else:
        msg_text = (
            "📝 <b>Новый отзыв о сотруднике</b>\n\n"
            f"📍 <b>Пункт:</b> {esc(checkpoint)}\n"
            f"👤 <b>Сотрудник:</b> {esc(employee_name)}\n"
            f"💬 <b>Отзыв:</b> «{esc(comment)}»\n\n"
            f"⭐ <b>Авто-оценка:</b> {stars} ({rating}/5)\n"
            f"🎭 <b>Тональность:</b> {esc(sentiment)}"
        )

    # Notify the configured administrator chat.
    send_telegram_message(msg_text)

    return jsonify({
        "success": True,
        "message": "Оценка успешно отправлена!",
        "id": rating_id,
        "rating": rating,
        "sentiment": sentiment,
        "word_count": word_count
    })


@app.route("/api/ratings", methods=["GET"])
def get_ratings():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, checkpoint, employee_name, comment,
                   rating, sentiment, word_count, created_at
            FROM ratings
            ORDER BY id DESC
        """).fetchall()

    return jsonify({
        "success": True,
        "count": len(rows),
        "ratings": [dict(row) for row in rows]
    })


@app.route("/api/ratings/<int:rating_id>", methods=["DELETE"])
def delete_rating(rating_id):
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM ratings WHERE id = ?",
            (rating_id,)
        )
        conn.commit()

    if cursor.rowcount == 0:
        return jsonify({
            "success": False,
            "message": "Запись не найдена."
        }), 404

    return jsonify({
        "success": True,
        "message": f"Запись №{rating_id} удалена."
    })


@app.route("/api/reset", methods=["POST"])
def api_reset():
    reset_all()

    return jsonify({
        "success": True,
        "message": "База данных очищена."
    })


@app.route("/webhook", methods=["POST"])
def telegram_webhook():
    # Optional protection with Telegram secret token.
    if WEBHOOK_SECRET:
        received_secret = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token",
            ""
        )

        if received_secret != WEBHOOK_SECRET:
            return jsonify({
                "success": False,
                "message": "Forbidden"
            }), 403

    data = request.get_json(silent=True)

    if not isinstance(data, dict):
        return jsonify({"ok": True})

    try:
        process_telegram_update(data)
    except Exception as exc:
        print(f"[Webhook] processing error: {exc}")

    return jsonify({"ok": True})


@app.route("/setup-webhook", methods=["GET"])
def setup_webhook():
    if not BOT_TOKEN:
        return jsonify({
            "success": False,
            "message": "BOT_TOKEN не задан."
        }), 500

    if not SERVER_URL:
        return jsonify({
            "success": False,
            "message": "SERVER_URL не задан и RENDER_EXTERNAL_URL не найден."
        }), 500

    ok = set_telegram_webhook()

    return jsonify({
        "success": ok,
        "webhook_url": f"{SERVER_URL}/webhook",
        "message": (
            "Webhook установлен."
            if ok else
            "Не удалось установить webhook. Проверь BOT_TOKEN."
        )
    })


@app.route("/telegram-info", methods=["GET"])
def telegram_info():
    if not BOT_TOKEN:
        return jsonify({
            "success": False,
            "message": "BOT_TOKEN не настроен."
        }), 500

    ok, result = telegram_request("getWebhookInfo", {})

    return jsonify({
        "success": ok,
        "result": result
    })


# =========================================================
# ERROR HANDLERS
# =========================================================

@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "404",
        "message": "Страница или API-маршрут не найден.",
        "available_routes": [
            "/",
            "/health",
            "/webapp/report",
            "/api/rate",
            "/api/ratings",
            "/webhook",
            "/setup-webhook",
            "/telegram-info"
        ]
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "500",
        "message": "Внутренняя ошибка сервера."
    }), 500


# =========================================================
# STARTUP
# =========================================================

def startup():
    print("=" * 60)
    print("EMPLOYEE RATING SERVER")
    print("=" * 60)
    print(f"DATABASE: {DATABASE}")
    print(f"SERVER_URL: {get_public_url()}")
    print(f"BOT_TOKEN: {'configured' if BOT_TOKEN else 'NOT CONFIGURED'}")
    print(f"CHAT_ID: {'configured' if CHAT_ID else 'NOT CONFIGURED'}")
    print(f"WEBHOOK_SECRET: {'configured' if WEBHOOK_SECRET else 'not configured'}")
    print("=" * 60)

    if AUTO_SET_WEBHOOK and BOT_TOKEN and SERVER_URL:
        set_telegram_webhook()


startup()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))
    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
