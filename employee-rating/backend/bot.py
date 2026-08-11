import time
import requests
import telebot

# =========================================================
# НАСТРОЙКИ
# =========================================================

BOT_TOKEN = "8606610454:AAG6wYBzLBI0ETLojTWx7dORnbRTRUBUQOo"

API_URL = "https://employee-rating-1.onrender.com/api/ratings"

# =========================================================
# ПРОВЕРКА ТОКЕНА
# =========================================================

if not BOT_TOKEN or BOT_TOKEN == "ВСТАВЬ_СЮДА_НОВЫЙ_ТОКЕН_БОТА":
    raise RuntimeError(
        "Укажи BOT_TOKEN в файле backend/bot.py"
    )

bot = telebot.TeleBot(BOT_TOKEN)

# Chat ID получателя
CHAT_ID = None

# Последний обработанный ID
last_rating_id = 0


# =========================================================
# ПОЛУЧЕНИЕ ОЦЕНОК С RENDER
# =========================================================

def get_ratings():

    try:

        response = requests.get(
            API_URL,
            timeout=30
        )

        print(
            "API статус:",
            response.status_code
        )

        response.raise_for_status()

        data = response.json()

        if not data.get("success"):
            print("API вернуло success=False")
            return []

        ratings = data.get(
            "ratings",
            []
        )

        print(
            "Получено оценок:",
            len(ratings)
        )

        return ratings

    except Exception as error:

        print(
            "❌ Ошибка получения данных:",
            error
        )

        return []


# =========================================================
# ФОРМАТИРОВАНИЕ ОЦЕНКИ
# =========================================================

def format_rating(item):

    rating = int(
        item.get("rating", 0)
    )

    stars = "⭐" * rating

    checkpoint = item.get(
        "checkpoint",
        "Не указан"
    )

    employee = item.get(
        "employee",
        "Не указан"
    )

    comment = item.get(
        "comment"
    ) or "Без комментария"

    created_at = item.get(
        "created_at",
        "Не указано"
    )

    rating_id = item.get(
        "id",
        "?"
    )

    text = (
        "📝 НОВАЯ ОЦЕНКА\n"
        "\n"
        f"🆔 ID: {rating_id}\n"
        "\n"
        f"📍 Пункт пропуска:\n"
        f"{checkpoint}\n"
        "\n"
        f"👤 Сотрудник:\n"
        f"{employee}\n"
        "\n"
        f"⭐ Оценка:\n"
        f"{stars} ({rating}/5)\n"
        "\n"
        f"💬 Комментарий:\n"
        f"{comment}\n"
        "\n"
        f"🕐 Дата:\n"
        f"{created_at}"
    )

    return text


# =========================================================
# /start
# =========================================================

@bot.message_handler(
    commands=["start"]
)
def start(message):

    global CHAT_ID

    CHAT_ID = message.chat.id

    bot.send_message(
        message.chat.id,

        "🤖 Система оценки сотрудников\n"
        "\n"
        "Бот подключён.\n"
        "\n"
        "Доступные команды:\n"
        "\n"
        "/report — общий отчёт\n"
        "/last — последние оценки\n"
        "/chatid — показать Chat ID\n"
        "/test — проверить Telegram"
    )

    print(
        "CHAT_ID:",
        CHAT_ID
    )


# =========================================================
# /chatid
# =========================================================

@bot.message_handler(
    commands=["chatid"]
)
def chat_id(message):

    global CHAT_ID

    CHAT_ID = message.chat.id

    bot.send_message(
        message.chat.id,

        "🆔 Ваш Chat ID:\n\n"
        f"{message.chat.id}"
    )

    print(
        "CHAT_ID сохранён:",
        CHAT_ID
    )


# =========================================================
# /test
# =========================================================

@bot.message_handler(
    commands=["test"]
)
def test(message):

    bot.send_message(
        message.chat.id,

        "✅ Telegram-бот работает!\n\n"
        "Связь с ботом исправна."
    )


# =========================================================
# /report
# =========================================================

@bot.message_handler(
    commands=["report"]
)
def report(message):

    ratings = get_ratings()

    if not ratings:

        bot.send_message(
            message.chat.id,

            "📊 Оценок пока нет."
        )

        return

    total = len(ratings)

    total_score = sum(
        int(item.get("rating", 0))
        for item in ratings
    )

    average = total_score / total

    five = sum(
        1
        for item in ratings
        if int(item.get("rating", 0)) == 5
    )

    four = sum(
        1
        for item in ratings
        if int(item.get("rating", 0)) == 4
    )

    three = sum(
        1
        for item in ratings
        if int(item.get("rating", 0)) == 3
    )

    two = sum(
        1
        for item in ratings
        if int(item.get("rating", 0)) == 2
    )

    one = sum(
        1
        for item in ratings
        if int(item.get("rating", 0)) == 1
    )

    text = (
        "📊 ОБЩИЙ ОТЧЁТ\n"
        "\n"
        f"📝 Всего оценок: {total}\n"
        "\n"
        f"⭐ Средняя оценка: {average:.2f} / 5\n"
        "\n"
        "РАСПРЕДЕЛЕНИЕ:\n"
        "\n"
        f"⭐⭐⭐⭐⭐ 5 — {five}\n"
        f"⭐⭐⭐⭐ 4 — {four}\n"
        f"⭐⭐⭐ 3 — {three}\n"
        f"⭐⭐ 2 — {two}\n"
        f"⭐ 1 — {one}"
    )

    bot.send_message(
        message.chat.id,
        text
    )


# =========================================================
# /last
# =========================================================

@bot.message_handler(
    commands=["last"]
)
def last_ratings(message):

    ratings = get_ratings()

    if not ratings:

        bot.send_message(
            message.chat.id,

            "📊 Оценок пока нет."
        )

        return

    ratings = ratings[:10]

    text = "📋 ПОСЛЕДНИЕ ОЦЕНКИ\n\n"

    for item in ratings:

        rating = int(
            item.get("rating", 0)
        )

        stars = "⭐" * rating

        checkpoint = item.get(
            "checkpoint",
            "Не указан"
        )

        employee = item.get(
            "employee",
            "Не указан"
        )

        comment = item.get(
            "comment"
        ) or "Без комментария"

        created_at = item.get(
            "created_at",
            "Не указано"
        )

        text += (
            f"📍 {checkpoint}\n"
            f"👤 {employee}\n"
            f"{stars} ({rating}/5)\n"
            f"💬 {comment}\n"
            f"🕐 {created_at}\n"
            "────────────────\n"
        )

    bot.send_message(
        message.chat.id,
        text
    )


# =========================================================
# ПРОВЕРКА НОВЫХ ОЦЕНОК
# =========================================================

def check_new_ratings():

    global last_rating_id

    if CHAT_ID is None:
        return

    ratings = get_ratings()

    if not ratings:
        return

    # API отдаёт новые оценки первыми
    ratings = sorted(
        ratings,
        key=lambda x: int(x["id"])
    )

    for item in ratings:

        item_id = int(
            item["id"]
        )

        if item_id <= last_rating_id:
            continue

        text = format_rating(
            item
        )

        try:

            bot.send_message(
                CHAT_ID,
                text
            )

            print(
                "✅ Отправлено в Telegram:",
                item_id
            )

            last_rating_id = item_id

        except Exception as error:

            print(
                "❌ Ошибка отправки:",
                error
            )


# =========================================================
# ПРОВЕРКА API ПРИ ЗАПУСКЕ
# =========================================================

print(
    "=============================="
)

print(
    "TELEGRAM-БОТ ЗАПУЩЕН"
)

print(
    "=============================="
)

print(
    "API:",
    API_URL
)

print(
    "=============================="
)


# =========================================================
# ОСНОВНОЙ ЦИКЛ
# =========================================================

def main():

    global CHAT_ID
    global last_rating_id

    # Сначала проверяем API

    ratings = get_ratings()

    if ratings:

        last_rating_id = max(
            int(item["id"])
            for item in ratings
        )

        print(
            "Последний ID:",
            last_rating_id
        )

    else:

        print(
            "Оценок в базе пока нет."
        )

    print(
        "Ожидание Telegram..."
    )

    while True:

        try:

            check_new_ratings()

            time.sleep(10)

        except Exception as error:

            print(
                "❌ Ошибка:",
                error
            )

            time.sleep(10)


# =========================================================
# ЗАПУСК
# =========================================================

if __name__ == "__main__":

    # Запускаем Telegram polling
    #
    # ВАЖНО:
    # polling должен работать отдельно от
    # проверки новых оценок.

    import threading

    telegram_thread = threading.Thread(
        target=lambda: bot.infinity_polling(
            skip_pending=True
        ),
        daemon=True
    )

    telegram_thread.start()

    main()
