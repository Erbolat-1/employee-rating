import io
import json
import os
import re
import sqlite3
import urllib.request
import html
from datetime import datetime, timezone

import pandas as pd
from flask import Flask, jsonify, request, send_from_directory, render_template
from flask_cors import CORS


# ============================================================
# EMPLOYEE RATING — RENDER + TELEGRAM MINI APP
# UPDATED:
# - Jinja render_template for report_webapp.html
# - report selection
# - single delete with confirmation
# - bulk delete
# - Telegram report list + delete/confirm buttons
# - Telegram admin protection for destructive commands
# ============================================================

app = Flask(__name__)
CORS(app)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

DATABASE = os.environ.get(
    "DATABASE_PATH",
    os.path.join(BASE_DIR, "ratings.db")
)

BOT_TOKEN = os.environ.get("BOT_TOKEN", "").strip()
CHAT_ID = os.environ.get("CHAT_ID", "").strip()

SERVER_URL = (
    os.environ.get("SERVER_URL", "").strip().rstrip("/")
    or os.environ.get("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
)

WEBHOOK_SECRET = os.environ.get("TELEGRAM_WEBHOOK_SECRET", "").strip()

# Optional comma-separated Telegram user IDs allowed to delete reports.
# Example: ADMIN_TELEGRAM_IDS=123456789,987654321
# If empty, destructive Telegram commands are allowed only in CHAT_ID.
ADMIN_TELEGRAM_IDS = {
    x.strip()
    for x in os.environ.get("ADMIN_TELEGRAM_IDS", "").split(",")
    if x.strip()
}


# ============================================================
# DATABASE
# ============================================================

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


# ============================================================
# TEXT ANALYSIS
# ============================================================

POSITIVE_WORDS = {
    "отлично", "замечательно", "быстро", "вежливо", "профессионально",
    "качественно", "спасибо", "благодарность", "корректно", "чисто",
    "удобно", "прекрасно", "хорошо", "компетентно", "оперативно",
    "молодец", "вежливый", "быстрый", "отличный", "профессионал",
    "вежливость", "образцово",
    "жақсы", "өте", "тамаша", "рахмет", "жылдам", "сыпайы",
    "кәсіби", "сапалы", "дұрыс", "ыңғайлы"
}

NEGATIVE_WORDS = {
    "плохо", "медленно", "грубо", "ужасно", "хамство", "ошибка",
    "очередь", "долго", "невнимательно", "превышение", "халатность",
    "претензия", "задержка", "проблема", "бардак", "грязь",
    "отвратительно", "грубый", "медлительный", "хам", "ужасный",
    "плохой", "грубость",
    "жаман", "баяу", "дөрекі", "қате", "мәселе", "кезек", "ұзақ",
    "назарсыз", "шағым", "кешігу"
}


def analyze_text(text):
    words = re.findall(
        r"[а-яёa-zәіңғүұқөһ0-9]+",
        (text or "").lower()
    )

    positive = sum(word in POSITIVE_WORDS for word in words)
    negative = sum(word in NEGATIVE_WORDS for word in words)

    if positive > negative:
        sentiment = "Положительный"
        auto_score = 5 if positive - negative >= 2 else 4
    elif negative > positive:
        sentiment = "Отрицательный"
        auto_score = 1 if negative - positive >= 2 else 2
    else:
        sentiment = "Нейтральный"
        auto_score = 3

    return {
        "sentiment": sentiment,
        "word_count": len(words),
        "auto_score": auto_score
    }


# ============================================================
# HELPERS
# ============================================================

def escape_telegram(value):
    return html.escape(str(value), quote=False)


def get_server_url():
    return SERVER_URL or "http://127.0.0.1:5000"


def is_telegram_admin(user_id=None, chat_id=None):
    user_id = str(user_id or "")
    chat_id = str(chat_id or "")

    if ADMIN_TELEGRAM_IDS:
        return user_id in ADMIN_TELEGRAM_IDS

    return bool(CHAT_ID and chat_id == CHAT_ID)


def format_rating_stars(rating):
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        rating = 0
    return "⭐" * max(0, min(rating, 5))


def get_rating_by_id(rating_id):
    with get_db() as conn:
        row = conn.execute("""
            SELECT id, checkpoint, employee_name, comment,
                   rating, sentiment, word_count, created_at
            FROM ratings
            WHERE id = ?
        """, (rating_id,)).fetchone()
    return dict(row) if row else None


# ============================================================
# TELEGRAM API
# ============================================================

def telegram_request(method, payload, timeout=10):
    if not BOT_TOKEN:
        return False, {"description": "BOT_TOKEN is not configured"}

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"

    body = json.dumps(
        payload,
        ensure_ascii=False
    ).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            data = json.loads(
                response.read().decode("utf-8")
            )
            return bool(data.get("ok")), data
    except Exception as exc:
        print(f"[Telegram] {method}: {exc}")
        return False, {"description": str(exc)}


def telegram_message(text, chat_id=None, reply_markup=None):
    target = chat_id or CHAT_ID

    if not BOT_TOKEN or not target:
        print("[Telegram] BOT_TOKEN/CHAT_ID not configured")
        return False

    payload = {
        "chat_id": target,
        "text": text,
        "parse_mode": "HTML"
    }

    if reply_markup:
        payload["reply_markup"] = reply_markup

    ok, result = telegram_request(
        "sendMessage",
        payload
    )

    if not ok:
        print("[Telegram] sendMessage failed:", result)

    return ok


def telegram_edit_message(chat_id, message_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    ok, result = telegram_request(
        "editMessageText",
        payload
    )

    if not ok:
        print("[Telegram] editMessageText failed:", result)

    return ok


def telegram_delete_message(chat_id, message_id):
    ok, result = telegram_request(
        "deleteMessage",
        {
            "chat_id": chat_id,
            "message_id": message_id
        }
    )

    if not ok:
        print("[Telegram] deleteMessage failed:", result)

    return ok


# ============================================================
# TELEGRAM KEYBOARDS
# ============================================================

def main_keyboard():
    app_url = f"{get_server_url()}/webapp/report"

    return {
        "inline_keyboard": [
            [
                {
                    "text": "📊 Открыть Mini App",
                    "web_app": {
                        "url": app_url
                    }
                }
            ],
            [
                {
                    "text": "📈 Статистика",
                    "callback_data": "report"
                },
                {
                    "text": "📋 Последние",
                    "callback_data": "last"
                }
            ],
            [
                {
                    "text": "🗑 Управление отчётами",
                    "callback_data": "reports"
                }
            ],
            [
                {
                    "text": "📥 Excel",
                    "callback_data": "excel"
                }
            ]
        ]
    }


def reports_keyboard(rows):
    buttons = []

    for row in rows:
        rating_id = row["id"]
        employee = escape_telegram(row["employee_name"])
        rating = int(row["rating"])

        buttons.append([
            {
                "text": f"🗑 №{rating_id} — {employee[:24]} — {rating}/5",
                "callback_data": f"delete_report:{rating_id}"
            }
        ])

    buttons.append([
        {
            "text": "🔄 Обновить",
            "callback_data": "reports"
        }
    ])

    return {"inline_keyboard": buttons}


def confirm_delete_keyboard(rating_id):
    return {
        "inline_keyboard": [
            [
                {
                    "text": "🗑 Да, удалить",
                    "callback_data": f"confirm_delete:{rating_id}"
                },
                {
                    "text": "❌ Отмена",
                    "callback_data": "cancel_delete"
                }
            ]
        ]
    }


# ============================================================
# TELEGRAM REPORTS
# ============================================================

def send_report(chat_id):
    with get_db() as conn:
        count, avg = conn.execute(
            "SELECT COUNT(*), AVG(rating) FROM ratings"
        ).fetchone()

    telegram_message(
        "📊 <b>Статистика</b>\n\n"
        f"📝 Отзывов: <b>{count}</b>\n"
        f"⭐ Средняя оценка: "
        f"<b>{round(avg, 2) if avg else 0}/5</b>",
        chat_id
    )


def send_last(chat_id):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT checkpoint, employee_name, comment,
                   rating, sentiment, created_at
            FROM ratings
            ORDER BY id DESC
            LIMIT 10
        """).fetchall()

    if not rows:
        telegram_message(
            "ℹ️ Отзывов пока нет.",
            chat_id
        )
        return

    result = ["📋 <b>Последние отзывы</b>\n"]

    for row in rows:
        result.append(
            f"📍 <b>КПП:</b> "
            f"{escape_telegram(row['checkpoint'])}\n"
            f"👤 <b>Сотрудник:</b> "
            f"{escape_telegram(row['employee_name'])}\n"
            f"⭐ <b>Оценка:</b> "
            f"{format_rating_stars(row['rating'])} "
            f"({row['rating']}/5)\n"
            f"🎭 <b>Тональность:</b> "
            f"{escape_telegram(row['sentiment'])}\n"
            f"💬 {escape_telegram(row['comment'])}\n"
            f"🕒 {escape_telegram(row['created_at'])}\n"
            "──────────────────"
        )

    telegram_message(
        "\n".join(result),
        chat_id
    )


def send_reports_manager(chat_id):
    with get_db() as conn:
        rows = conn.execute("""
            SELECT id, checkpoint, employee_name,
                   rating, created_at
            FROM ratings
            ORDER BY id DESC
            LIMIT 20
        """).fetchall()

    if not rows:
        telegram_message(
            "📊 <b>Отчёты</b>\n\nℹ️ Записей пока нет.",
            chat_id
        )
        return

    lines = [
        "🗑 <b>УПРАВЛЕНИЕ ОТЧЁТАМИ</b>",
        "",
        f"Показаны последние {len(rows)} записей.",
        "Нажмите кнопку нужного отчёта для удаления."
    ]

    for row in rows:
        lines.append(
            f"№{row['id']} • "
            f"{escape_telegram(row['employee_name'])} • "
            f"{row['rating']}/5"
        )

    telegram_message(
        "\n".join(lines),
        chat_id,
        reports_keyboard(rows)
    )


def send_delete_confirmation(chat_id, rating_id):
    row = get_rating_by_id(rating_id)

    if not row:
        telegram_message(
            f"❌ Отчёт №{rating_id} уже не существует.",
            chat_id
        )
        return

    text = (
        "⚠️ <b>ПОДТВЕРЖДЕНИЕ УДАЛЕНИЯ</b>\n\n"
        f"🆔 Отчёт №<b>{row['id']}</b>\n"
        f"📍 <b>КПП:</b> "
        f"{escape_telegram(row['checkpoint'])}\n"
        f"👤 <b>Сотрудник:</b> "
        f"{escape_telegram(row['employee_name'])}\n"
        f"⭐ <b>Оценка:</b> "
        f"{format_rating_stars(row['rating'])} "
        f"({row['rating']}/5)\n"
        f"💬 <b>Отзыв:</b> "
        f"{escape_telegram(row['comment'])}\n"
        f"🕒 <b>Дата:</b> "
        f"{escape_telegram(row['created_at'])}\n\n"
        "Удалить эту запись?"
    )

    telegram_message(
        text,
        chat_id,
        confirm_delete_keyboard(rating_id)
    )


def delete_rating_from_db(rating_id):
    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM ratings WHERE id = ?",
            (rating_id,)
        )
        conn.commit()

    return cursor.rowcount > 0


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


def reset_database():
    with get_db() as conn:
        conn.execute("DELETE FROM ratings")
        conn.commit()


# ============================================================
# EXCEL
# ============================================================

def send_excel(chat_id):
    with get_db() as conn:
        df = pd.read_sql_query("""
            SELECT
                id AS 'ID',
                created_at AS 'Дата',
                checkpoint AS 'Пункт пропуска',
                employee_name AS 'Сотрудник',
                comment AS 'Отзыв',
                rating AS 'Оценка',
                sentiment AS 'Тональность',
                word_count AS 'Слов'
            FROM ratings
            ORDER BY id DESC
        """, conn)

    if df.empty:
        telegram_message(
            "ℹ️ В базе пока нет отзывов.",
            chat_id
        )
        return

    output = io.BytesIO()

    with pd.ExcelWriter(
        output,
        engine="openpyxl"
    ) as writer:
        df.to_excel(
            writer,
            index=False,
            sheet_name="Отзывы"
        )

    output.seek(0)

    boundary = "----EmployeeRatingBoundary"
    parts = []

    def add_field(name, value):
        parts.append(
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
            f"{value}\r\n".encode("utf-8")
        )

    add_field("chat_id", chat_id)
    add_field(
        "caption",
        f"📊 <b>Отчёт по оценкам</b>\nЗаписей: {len(df)}"
    )
    add_field("parse_mode", "HTML")

    parts.append(
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="document"; '
        f'filename="Отчет_по_оценкам.xlsx"\r\n'
        f"Content-Type: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet\r\n\r\n"
        .encode("utf-8")
    )

    parts.append(output.getvalue())
    parts.append(
        f"\r\n--{boundary}--\r\n".encode("utf-8")
    )

    payload = b"".join(parts)

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{BOT_TOKEN}/sendDocument",
        data=payload,
        headers={
            "Content-Type":
                f"multipart/form-data; boundary={boundary}"
        },
        method="POST"
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            response.read()
    except Exception as exc:
        print("[Telegram] Excel error:", exc)


# ============================================================
# TELEGRAM UPDATE PROCESSING
# ============================================================

def process_update(update):
    message = update.get("message")

    if message:
        chat_id = str(
            message.get("chat", {}).get("id", "")
        )

        from_user = message.get("from", {})
        user_id = str(from_user.get("id", ""))

        text = message.get("text", "").strip()

        if text.startswith("/"):
            command = text.split()[0].lower().split("@")[0]

            if command == "/start":
                telegram_message(
                    "👋 <b>Система оценки сотрудников</b>\n\n"
                    "Выберите действие:",
                    chat_id,
                    main_keyboard()
                )

            elif command in ("/app", "/view"):
                telegram_message(
                    "📊 <b>Открыть интерактивное приложение:</b>",
                    chat_id,
                    main_keyboard()
                )

            elif command in ("/report", "/stats"):
                send_report(chat_id)

            elif command in ("/last", "/latest"):
                send_last(chat_id)

            elif command in ("/reports", "/delete_report"):
                if not is_telegram_admin(user_id, chat_id):
                    telegram_message(
                        "⛔ <b>Недостаточно прав.</b>\n"
                        "Управление отчётами доступно только администратору.",
                        chat_id
                    )
                else:
                    send_reports_manager(chat_id)

            elif command in ("/excel", "/export"):
                send_excel(chat_id)

            elif command == "/delete_last":
                if not is_telegram_admin(user_id, chat_id):
                    telegram_message(
                        "⛔ Недостаточно прав.",
                        chat_id
                    )
                else:
                    deleted = delete_last()

                    telegram_message(
                        "🗑️ Последняя запись удалена."
                        if deleted
                        else "ℹ️ Записей нет.",
                        chat_id
                    )

            elif command == "/reset_all":
                if not is_telegram_admin(user_id, chat_id):
                    telegram_message(
                        "⛔ Недостаточно прав.",
                        chat_id
                    )
                else:
                    reset_database()

                    telegram_message(
                        "🧹 <b>База отзывов полностью очищена.</b>",
                        chat_id
                    )

            elif command == "/chatid":
                telegram_message(
                    f"🆔 ID чата: "
                    f"<code>{escape_telegram(chat_id)}</code>",
                    chat_id
                )

    callback = update.get("callback_query")

    if callback:
        callback_id = callback.get("id")
        data = callback.get("data", "")

        callback_message = callback.get("message", {})
        chat_id = str(
            callback_message.get("chat", {}).get("id", "")
        )
        message_id = callback_message.get("message_id")

        from_user = callback.get("from", {})
        user_id = str(from_user.get("id", ""))

        if callback_id:
            telegram_request(
                "answerCallbackQuery",
                {
                    "callback_query_id": callback_id
                },
                timeout=5
            )

        if data == "report":
            send_report(chat_id)

        elif data == "last":
            send_last(chat_id)

        elif data == "reports":
            if not is_telegram_admin(user_id, chat_id):
                telegram_message(
                    "⛔ Недостаточно прав.",
                    chat_id
                )
            else:
                send_reports_manager(chat_id)

        elif data == "excel":
            send_excel(chat_id)

        elif data.startswith("delete_report:"):
            if not is_telegram_admin(user_id, chat_id):
                telegram_message(
                    "⛔ Недостаточно прав.",
                    chat_id
                )
            else:
                try:
                    rating_id = int(data.split(":", 1)[1])
                except (ValueError, IndexError):
                    rating_id = 0

                if rating_id:
                    send_delete_confirmation(
                        chat_id,
                        rating_id
                    )

        elif data.startswith("confirm_delete:"):
            if not is_telegram_admin(user_id, chat_id):
                telegram_message(
                    "⛔ Недостаточно прав.",
                    chat_id
                )
                return

            try:
                rating_id = int(data.split(":", 1)[1])
            except (ValueError, IndexError):
                rating_id = 0

            if not rating_id:
                return

            deleted = delete_rating_from_db(rating_id)

            if deleted:
                text = (
                    f"✅ <b>Отчёт №{rating_id} удалён.</b>\n\n"
                    "Данные удалены из базы."
                )
            else:
                text = (
                    f"ℹ️ Отчёт №{rating_id} уже отсутствует."
                )

            telegram_edit_message(
                chat_id,
                message_id,
                text,
                {
                    "inline_keyboard": [
                        [
                            {
                                "text": "📊 К списку отчётов",
                                "callback_data": "reports"
                            }
                        ]
                    ]
                }
            )

        elif data == "cancel_delete":
            telegram_edit_message(
                chat_id,
                message_id,
                "❌ <b>Удаление отменено.</b>"
            )


# ============================================================
# WEBHOOK
# ============================================================

def set_webhook():
    if not BOT_TOKEN:
        print("[Webhook] BOT_TOKEN missing")
        return False

    if not SERVER_URL:
        print("[Webhook] SERVER_URL/RENDER_EXTERNAL_URL missing")
        return False

    payload = {
        "url": f"{SERVER_URL}/webhook"
    }

    if WEBHOOK_SECRET:
        payload["secret_token"] = WEBHOOK_SECRET

    ok, result = telegram_request(
        "setWebhook",
        payload
    )

    print(
        "[Webhook]",
        "OK" if ok else "ERROR",
        result
    )

    return ok


# ============================================================
# HTML
# ============================================================

ORIGINAL_HTML_CANDIDATES = [
    "employee_rating_final_ru_kk_en_kz_ornament_logo.html",
    "index.html",
    "index_demo.html",
    "index_demo_manual_checkpoint.html"
]


def find_original_html():
    for filename in ORIGINAL_HTML_CANDIDATES:
        path = os.path.join(
            TEMPLATES_DIR,
            filename
        )

        if os.path.isfile(path):
            return filename

    return None


# ============================================================
# ROUTES
# ============================================================

@app.route("/")
def index():
    filename = find_original_html()

    if not filename:
        return jsonify({
            "success": False,
            "error": "HTML_NOT_FOUND",
            "message": (
                "Оригинальный HTML не найден. "
                "Помести HTML в папку templates."
            )
        }), 500

    return send_from_directory(
        TEMPLATES_DIR,
        filename
    )


@app.route("/webapp/report")
def webapp_report():
    report_path = os.path.join(
        TEMPLATES_DIR,
        "report_webapp.html"
    )

    if not os.path.isfile(report_path):
        return jsonify({
            "success": False,
            "error": "REPORT_HTML_NOT_FOUND",
            "message": "Файл report_webapp.html не найден."
        }), 404

    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                id,
                checkpoint,
                employee_name,
                comment,
                rating,
                sentiment,
                word_count,
                created_at
            FROM ratings
            ORDER BY id DESC
        """).fetchall()

        avg = conn.execute(
            "SELECT AVG(rating) FROM ratings"
        ).fetchone()[0]

    ratings = [dict(row) for row in rows]

    return render_template(
        "report_webapp.html",
        ratings=ratings,
        average=round(avg, 2) if avg else 0
    )


# ============================================================
# API
# ============================================================

@app.route("/api/rating", methods=["POST"])
@app.route("/api/rate", methods=["POST"])
def add_rating():
    data = request.get_json(silent=True) or {}

    checkpoint = str(
        data.get("checkpoint", "")
    ).strip()

    employee = str(
        data.get("employee", "")
        or data.get("employee_name", "")
    ).strip()

    comment = str(
        data.get("comment", "")
    ).strip()

    try:
        rating = int(data.get("rating", 0))
    except (TypeError, ValueError):
        rating = 0

    if not checkpoint:
        return jsonify({
            "success": False,
            "message": "Введите пункт пропуска."
        }), 400

    if not employee:
        return jsonify({
            "success": False,
            "message": "Введите ФИО сотрудника."
        }), 400

    if rating not in (1, 2, 3, 4, 5):
        return jsonify({
            "success": False,
            "message": "Выберите оценку от 1 до 5."
        }), 400

    if len(comment) > 5000:
        return jsonify({
            "success": False,
            "message": "Комментарий слишком длинный."
        }), 400

    analysis = analyze_text(comment)

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
            employee,
            comment,
            rating,
            sentiment,
            word_count
        ))

        rating_id = cursor.lastrowid
        conn.commit()

    stars = format_rating_stars(rating)

    if rating <= 2:
        telegram_text = (
            "🚨 <b>ВНИМАНИЕ! НЕГАТИВНЫЙ ОТЗЫВ</b>\n"
            "════════════════════════\n\n"
            f"📍 <b>Пункт пропуска:</b> "
            f"{escape_telegram(checkpoint)}\n"
            f"👤 <b>Сотрудник:</b> "
            f"{escape_telegram(employee)}\n"
            f"💬 <b>Отзыв:</b> "
            f"<i>«{escape_telegram(comment)}»</i>\n\n"
            f"🔴 <b>Оценка:</b> {stars} ({rating}/5)\n"
            f"🎭 <b>Тональность:</b> "
            f"{escape_telegram(sentiment)}\n\n"
            "⚠️ <b>ТРЕБУЕТСЯ РЕАГИРОВАНИЕ "
            "РУКОВОДСТВА!</b>"
        )
    else:
        telegram_text = (
            "📝 <b>Новый отзыв о сотруднике</b>\n\n"
            f"📍 <b>Пункт пропуска:</b> "
            f"{escape_telegram(checkpoint)}\n"
            f"👤 <b>Сотрудник:</b> "
            f"{escape_telegram(employee)}\n"
            f"💬 <b>Отзыв:</b> "
            f"<i>«{escape_telegram(comment)}»</i>\n\n"
            f"⭐ <b>Оценка:</b> {stars} ({rating}/5)\n"
            f"🎭 <b>Тональность:</b> "
            f"{escape_telegram(sentiment)}"
        )

    telegram_message(telegram_text)

    return jsonify({
        "success": True,
        "message": "Оценка успешно сохранена!",
        "id": rating_id,
        "rating": rating,
        "sentiment": sentiment
    })


@app.route("/api/ratings", methods=["GET"])
def get_ratings():
    with get_db() as conn:
        rows = conn.execute("""
            SELECT
                id,
                checkpoint,
                employee_name,
                comment,
                rating,
                sentiment,
                word_count,
                created_at
            FROM ratings
            ORDER BY id DESC
        """).fetchall()

        avg = conn.execute(
            "SELECT AVG(rating) FROM ratings"
        ).fetchone()[0]

    return jsonify({
        "success": True,
        "count": len(rows),
        "average": round(avg, 2) if avg else 0,
        "ratings": [dict(row) for row in rows]
    })


@app.route("/api/ratings/<int:rating_id>", methods=["DELETE"])
def delete_rating(rating_id):
    if not get_rating_by_id(rating_id):
        return jsonify({
            "success": False,
            "message": "Запись не найдена."
        }), 404

    with get_db() as conn:
        cursor = conn.execute(
            "DELETE FROM ratings WHERE id = ?",
            (rating_id,)
        )
        conn.commit()

    return jsonify({
        "success": True,
        "message": f"Запись №{rating_id} удалена.",
        "id": rating_id
    })


@app.route("/api/ratings/bulk-delete", methods=["POST"])
def bulk_delete_ratings():
    data = request.get_json(silent=True) or {}
    ids = data.get("ids", [])

    if not isinstance(ids, list):
        return jsonify({
            "success": False,
            "message": "ids должен быть массивом."
        }), 400

    clean_ids = []

    for value in ids:
        try:
            number = int(value)
            if number > 0:
                clean_ids.append(number)
        except (TypeError, ValueError):
            pass

    clean_ids = list(dict.fromkeys(clean_ids))

    if not clean_ids:
        return jsonify({
            "success": False,
            "message": "Не выбраны отчёты."
        }), 400

    placeholders = ",".join("?" for _ in clean_ids)

    with get_db() as conn:
        cursor = conn.execute(
            f"DELETE FROM ratings WHERE id IN ({placeholders})",
            clean_ids
        )
        conn.commit()

    return jsonify({
        "success": True,
        "deleted": cursor.rowcount,
        "ids": clean_ids,
        "message": f"Удалено записей: {cursor.rowcount}."
    })


@app.route("/api/reset", methods=["POST"])
def reset_api():
    reset_database()

    return jsonify({
        "success": True,
        "message": "Все отзывы удалены."
    })


# ============================================================
# TELEGRAM WEBHOOK ROUTES
# ============================================================

@app.route("/webhook", methods=["POST"])
def webhook():
    if WEBHOOK_SECRET:
        received = request.headers.get(
            "X-Telegram-Bot-Api-Secret-Token",
            ""
        )

        if received != WEBHOOK_SECRET:
            return jsonify({
                "ok": False,
                "message": "Forbidden"
            }), 403

    update = request.get_json(silent=True)

    if isinstance(update, dict):
        try:
            process_update(update)
        except Exception as exc:
            print("[Webhook] processing error:", exc)

    return jsonify({"ok": True})


@app.route("/setup-webhook")
def setup_webhook_route():
    ok = set_webhook()

    return jsonify({
        "success": ok,
        "webhook": (
            f"{get_server_url()}/webhook"
            if SERVER_URL
            else None
        )
    })


@app.route("/telegram-info")
def telegram_info():
    ok, result = telegram_request(
        "getWebhookInfo",
        {}
    )

    return jsonify({
        "success": ok,
        "result": result
    })


# ============================================================
# HEALTH
# ============================================================

@app.route("/health")
def health():
    with get_db() as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM ratings"
        ).fetchone()[0]

    return jsonify({
        "status": "ok",
        "service": "employee-rating",
        "server_url": get_server_url(),
        "telegram_configured": bool(BOT_TOKEN),
        "chat_configured": bool(CHAT_ID),
        "admin_ids_configured": bool(ADMIN_TELEGRAM_IDS),
        "html_found": bool(find_original_html()),
        "report_html_found": os.path.isfile(
            os.path.join(TEMPLATES_DIR, "report_webapp.html")
        ),
        "ratings_count": count,
        "time_utc": datetime.now(
            timezone.utc
        ).isoformat()
    })


# ============================================================
# 404
# ============================================================

@app.errorhandler(404)
def error_404(error):
    return jsonify({
        "success": False,
        "error": "404",
        "message": "Маршрут не найден.",
        "routes": [
            "/",
            "/webapp/report",
            "/api/rating",
            "/api/ratings",
            "/api/ratings/<id>",
            "/api/ratings/bulk-delete",
            "/webhook",
            "/setup-webhook",
            "/telegram-info",
            "/health"
        ]
    }), 404


# ============================================================
# START
# ============================================================

def startup():
    print("=" * 60)
    print("EMPLOYEE RATING SERVER")
    print("=" * 60)
    print("SERVER_URL:", get_server_url())
    print("BOT_TOKEN:", "OK" if BOT_TOKEN else "MISSING")
    print("CHAT_ID:", "OK" if CHAT_ID else "MISSING")
    print(
        "ADMIN_TELEGRAM_IDS:",
        "OK" if ADMIN_TELEGRAM_IDS else "NOT SET"
    )
    print(
        "ORIGINAL HTML:",
        find_original_html() or "NOT FOUND"
    )
    print(
        "REPORT HTML:",
        "FOUND"
        if os.path.isfile(
            os.path.join(TEMPLATES_DIR, "report_webapp.html")
        )
        else "NOT FOUND"
    )
    print("DATABASE:", DATABASE)
    print("=" * 60)

    if BOT_TOKEN and SERVER_URL:
        set_webhook()


startup()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "5000"))

    app.run(
        host="0.0.0.0",
        port=port,
        debug=False
    )
