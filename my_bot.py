import os
import logging
from datetime import datetime
from telegram import Update, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes,
    MessageHandler, filters, ConversationHandler
)
from apscheduler.schedulers.background import BackgroundScheduler
import openai
import traceback
import os

openai.api_key = os.getenv("OPENAI_API_KEY")
TOKEN = os.getenv("TELEGRAM_TOKEN")

logging.basicConfig(level=logging.INFO)

subscribers = set()
user_zodiac_signs = {}
user_send_times = {}
user_birth_data = {}

MONTHS_RU = {
    "January": "января", "February": "февраля", "March": "марта", "April": "апреля",
    "May": "мая", "June": "июня", "July": "июля", "August": "августа",
    "September": "сентября", "October": "октября", "November": "ноября", "December": "декабря"
}

HOROSCOPE_SIGNS = [
    "Овен", "Телец", "Близнецы", "Рак", "Лев", "Дева",
    "Весы", "Скорпион", "Стрелец", "Козерог", "Водолей", "Рыбы"
]

NATAL_DATE, NATAL_TIME, NATAL_PLACE = range(3)

def get_horoscope(sign, date):
    file_path = f"horoscopes/{sign}.txt"
    if not os.path.exists(file_path):
        return f"Извините, гороскоп для {sign} не найден."
    with open(file_path, 'r', encoding='utf-8') as file:
        for line in file:
            if line.startswith(date):
                return line.strip().split(': ', 1)[1]
    return f"Извините, гороскоп на {date} для {sign} не найден."

from telegram.constants import ParseMode

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    subscribers.add(user_id)

    keyboard = [[KeyboardButton(sign) for sign in HOROSCOPE_SIGNS[i:i+3]] for i in range(0, 12, 3)]
    reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=True)

    welcome_text = (
        "<b>✨ Добро пожаловать в гороскоп-бот Lunari! ✨</b>\n\n"
        "Здесь ты найдёшь:\n"
        "🔮 Ежедневные гороскопы по твоему знаку\n"
        "🌌 Натальные карты по дате, времени и месту рождения\n"
        "🪐 Астрологические подсказки и мотивации\n\n"
        "<b>Команды:</b>\n"
        "/start — Подписаться и выбрать знак зодиака\n"
        "/today — Гороскоп на сегодня\n"
        "/unsubscribe — Отписаться от рассылки\n"
        "/settime — Время получения гороскопа\n"
        "/natal — Натальная карта\n"
        "/help — Помощь по командам\n\n"
        "Сначала выбери свой знак зодиака:"
    )

    try:
        with open("welcome.png", "rb") as photo:
            await context.bot.send_photo(chat_id=user_id, photo=photo, caption=welcome_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    except Exception as e:
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)


async def handle_zodiac_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    sign = update.message.text.strip()
    if sign in HOROSCOPE_SIGNS:
        user_zodiac_signs[user_id] = sign
        await update.message.reply_text(f"Твой знак зодиака — {sign}! Используй /today для гороскопа ✨")
    else:
        await update.message.reply_text("Пожалуйста, выбери знак с клавиатуры.")

async def today(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    sign = user_zodiac_signs.get(user_id)
    if not sign:
        await update.message.reply_text("Сначала выбери знак зодиака через /start")
        return

    now = datetime.now()
    today_date = now.strftime('%Y-%m-%d')
    day = now.strftime('%-d') if os.name != 'nt' else now.strftime('%#d')
    month_ru = MONTHS_RU.get(now.strftime('%B'), now.strftime('%B'))
    formatted_date = f"{day} {month_ru}"
    horoscope = get_horoscope(sign, today_date)

    await update.message.reply_text(f"🔮 Гороскоп для {sign} на {formatted_date}:\n\n{horoscope}")

async def unsubscribe(update: Update, context: ContextTypes.DEFAULT_TYPE):
    subscribers.discard(update.effective_chat.id)
    await update.message.reply_text("Ты отписан от ежедневной рассылки 💫")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "/start — Выбрать знак зодиака ✨\n"
        "/today — Гороскоп на сегодня 🔮\n"
        "/unsubscribe — Отписаться 💫\n"
        "/settime — Время рассылки 🕒\n"
        "/natal — Натальная карта 🌌"
    )

async def set_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    if len(context.args) != 1:
        await update.message.reply_text("Укажи время в формате HH:MM, например 08:30")
        return
    try:
        datetime.strptime(context.args[0], '%H:%M')
        user_send_times[user_id] = context.args[0]
        await update.message.reply_text(f"✅ Время установлено на {context.args[0]}")
    except ValueError:
        await update.message.reply_text("⛔ Неверный формат. Пример: 08:30")

def check_and_send_horoscopes(application):
    now = datetime.now()
    current_time = now.strftime('%H:%M')
    today_date = now.strftime('%Y-%m-%d')
    day = now.strftime('%-d') if os.name != 'nt' else now.strftime('%#d')
    month_ru = MONTHS_RU.get(now.strftime('%B'), now.strftime('%B'))
    formatted_date = f"{day} {month_ru}"

    for user_id in subscribers:
        if user_send_times.get(user_id) == current_time:
            sign = user_zodiac_signs.get(user_id)
            if sign:
                horoscope = get_horoscope(sign, today_date)
                application.bot.send_message(
                    chat_id=user_id,
                    text=f"✨ Новое предсказание прибыло!\n\n🔮 Гороскоп для {sign} на {formatted_date}:\n\n{horoscope}"
                )

async def natal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🌌 Введите дату рождения в формате ДД.ММ.ГГГГ")
    return NATAL_DATE

async def natal_date(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_birth_data[user_id] = {"date": update.message.text.strip()}
    await update.message.reply_text("🕒 Введите время рождения в формате ЧЧ:ММ")
    return NATAL_TIME

async def natal_time(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_birth_data[user_id]["time"] = update.message.text.strip()
    await update.message.reply_text("🌍 Введите город рождения")
    return NATAL_PLACE

async def natal_place(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_chat.id
    user_birth_data[user_id]["place"] = update.message.text.strip()
    data = user_birth_data[user_id]

    prompt = (
        f"Составь подробное, красивое, вдохновляющее описание натальной карты для:\n"
        f"Дата рождения: {data['date']}\n"
        f"Время рождения: {data['time']}\n"
        f"Место рождения: {data['place']}\n\n"
        f"Опиши важные аспекты личности, призвание, чувства, сильные и слабые стороны. На русском языке. Без сложных терминов."
    )

    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "user", "content": prompt}
            ],
            temperature=0.8,
            max_tokens=1000
        )
        result = response.choices[0].message.content
        await update.message.reply_text(f"🌌 Вот описание твоей натальной карты:\n\n{result}")

    except Exception as e:
        await update.message.reply_text(f"⛔ Ошибка при генерации карты:\n{e}")
        print("OpenAI error:", e)
        import traceback
        traceback.print_exc()



    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Окей, отмена ✨")
    return ConversationHandler.END

async def main():
    app = ApplicationBuilder().token(TOKEN).build()

    natal_conv = ConversationHandler(
        entry_points=[CommandHandler("natal", natal_command)],
        states={
            NATAL_DATE: [MessageHandler(filters.TEXT & ~filters.COMMAND, natal_date)],
            NATAL_TIME: [MessageHandler(filters.TEXT & ~filters.COMMAND, natal_time)],
            NATAL_PLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, natal_place)],
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    app.add_handler(natal_conv)

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("today", today))
    app.add_handler(CommandHandler("unsubscribe", unsubscribe))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("settime", set_time))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_zodiac_choice))

    scheduler = BackgroundScheduler()
    scheduler.add_job(check_and_send_horoscopes, "cron", minute="*", args=[app])
    scheduler.start()

    print("Бот запущен!")
    await app.run_polling()

if __name__ == "__main__":
    import nest_asyncio
    import asyncio
    nest_asyncio.apply()
    asyncio.run(main())

























