from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import os
from datetime import datetime

app = Flask(__name__)
CORS(app)

# ==========================================
# ПУТИ
# ==========================================

BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(BACKEND_DIR)

DB_PATH = os.path.join(PROJECT_DIR, "ratings.db")
FRONTEND_DIR = os.path.join(PROJECT_DIR, "frontend")


# ==========================================
# СОЗДАНИЕ БАЗЫ
# ==========================================

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

    print("База данных готова:")
    print(DB_PATH)


# ==========================================
# ГЛАВНАЯ СТРАНИЦА
# ==========================================

@app.route("/")
def home():
    return send_from_directory(
        FRONTEND_DIR,
        "index.html"
    )


# ==========================================
# ПОЛУЧЕНИЕ ОЦЕНКИ
# ==========================================

@app.route("/api/rating", methods=["POST"])
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

    # Проверка пункта пропуска

    if not checkpoint:

        return jsonify({
            "success": False,
            "message": "Не указан пункт пропуска"
        }), 400

    # Проверка ФИО

    if not employee:

        return jsonify({
            "success": False,
            "message": "Не указано ФИО сотрудника"
        }), 400

    # Проверка оценки

    if rating < 1 or rating > 5:

        return jsonify({
            "success": False,
            "message": "Оценка должна быть от 1 до 5"
        }), 400

    # Время

    created_at = datetime.now().strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    # Сохранение

    connection = sqlite3.connect(DB_PATH)

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

    # Вывод

    print()
    print("==============================")
    print("НОВАЯ ОЦЕНКА")
    print("==============================")
    print("ID:", rating_id)
    print("Пункт пропуска:", checkpoint)
    print("ФИО:", employee)
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


# ==========================================
# ПОЛУЧЕНИЕ ВСЕХ ОЦЕНОК
# ==========================================

@app.route("/api/ratings", methods=["GET"])
def get_ratings():

    connection = sqlite3.connect(DB_PATH)

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
            "id": row["id"],
            "checkpoint": row["checkpoint"],
            "employee": row["employee"],
            "rating": row["rating"],
            "comment": row["comment"],
            "created_at": row["created_at"]
        })

    return jsonify({
        "success": True,
        "count": len(ratings),
        "ratings": ratings
    })


# ==========================================
# ЗАПУСК
# ==========================================

init_database()


if __name__ == "__main__":

    print("==============================")
    print("СЕРВЕР ОЦЕНКИ СОТРУДНИКОВ")
    print("==============================")
    print("База:", DB_PATH)
    print("Сайт:", "http://127.0.0.1:5000")
    print("==============================")

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=True
    )
