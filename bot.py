import sqlite3, logging, re, os
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")
DB = "/app/data/finance.db"

MY_ID = 1359837942  # замени на свой Telegram ID

KEYBOARD = ReplyKeyboardMarkup(
    [
        ["📅 Сегодня", "📊 Статистика"],
        ["🗑️ Сбросить всё", "❓ Помощь"]
    ],
    resize_keyboard=True
)

async def check_user(update: Update) -> bool:
    if update.effective_user.id != MY_ID:
        await update.message.reply_text("⛔ Нет доступа.")
        return False
    return True

def init_db():
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT, amount REAL, category TEXT, date TEXT DEFAULT (date('now', '+6 hours')))""")
    conn.commit(); conn.close()

def add_transaction(type_, amount, category):
    conn = sqlite3.connect(DB)
    conn.execute("INSERT INTO transactions (type, amount, category) VALUES (?,?,?)", (type_, amount, category))
    conn.commit(); conn.close()

def parse_and_save(text):
    text = re.sub(r'(\d+)\s*(тысяч|тысячи|тыщ|тыс)\b', lambda m: str(int(m.group(1)) * 1000), text)
    text = re.sub(r'(\d+)\s*(миллион|миллиона|млн)\b', lambda m: str(int(m.group(1)) * 1000000), text)
    numbers = re.findall(r'\d+', text)
    if not numbers:
        return None, None, None
    amount = float(numbers[0])
    category = re.sub(r'\d+', '', text).replace('сом', '').replace('тысяч', '').replace('тыс', '').replace('миллион', '').replace('млн', '').strip() or "прочее"
    income_words = ['доход', 'зарплата', 'получил', 'заработал', 'пришло', 'перевод', 'фриланс']
    type_ = "доход" if any(w in text for w in income_words) else "расход"
    add_transaction(type_, amount, category)
    return type_, amount, category

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    await update.message.reply_text(
        "👋 Привет! Я веду твои финансы.\n\n"
        "Просто напиши:\n"
        "  кофе 300\n"
        "  зарплата 50000\n\n"
        "Или отправь голосовое 🎤",
        reply_markup=KEYBOARD)

async def show_today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    conn = sqlite3.connect(DB)
    today_date = "date('now', '+6 hours')"
    д_сумма = conn.execute(f"SELECT SUM(amount) FROM transactions WHERE type='доход' AND date={today_date}").fetchone()[0] or 0
    р_сумма = conn.execute(f"SELECT SUM(amount) FROM transactions WHERE type='расход' AND date={today_date}").fetchone()[0] or 0
    д_rows = conn.execute(f"SELECT amount, category FROM transactions WHERE type='доход' AND date={today_date}").fetchall()
    р_rows = conn.execute(f"SELECT amount, category FROM transactions WHERE type='расход' AND date={today_date}").fetchall()
    conn.close()
    if not д_rows and not р_rows:
        await update.message.reply_text("📭 Сегодня записей нет!", reply_markup=KEYBOARD)
        return
    msg = "📅 Сегодня:\n"
    if д_rows:
        msg += "\n💚 Доходы:\n" + "\n".join([f"  • {r[1]} — {r[0]:.0f} сом" for r in д_rows])
        msg += f"\n  Итого: {д_сумма:.0f} сом\n"
    if р_rows:
        msg += "\n🔴 Расходы:\n" + "\n".join([f"  • {r[1]} — {r[0]:.0f} сом" for r in р_rows])
        msg += f"\n  Итого: {р_сумма:.0f} сом\n"
    msg += f"\n💰 Баланс: {д_сумма - р_сумма:.0f} сом"
    await update.message.reply_text(msg, reply_markup=KEYBOARD)

async def show_stats(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    conn = sqlite3.connect(DB)
    д = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='доход' AND strftime('%Y-%m', date)=strftime('%Y-%m', date('now', '+6 hours'))").fetchone()[0] or 0
    р = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='расход' AND strftime('%Y-%m', date)=strftime('%Y-%m', date('now', '+6 hours'))").fetchone()[0] or 0
    conn.close()
    await update.message.reply_text(
        f"📊 Статистика за месяц:\n\n💚 Доходы:  {д:.0f} сом\n🔴 Расходы: {р:.0f} сом\n💰 Баланс:  {д-р:.0f} сом",
        reply_markup=KEYBOARD)

async def reset(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    conn = sqlite3.connect(DB)
    conn.execute("DELETE FROM transactions")
    conn.commit(); conn.close()
    await update.message.reply_text("🗑️ Все записи удалены! Начинаем с нуля.", reply_markup=KEYBOARD)

async def help_cmd(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    await update.message.reply_text(
        "❓ Как пользоваться:\n\n"
        "Просто напиши текстом:\n"
        "  кофе 300\n"
        "  зарплата 50000\n"
        "  фриланс 10 тысяч\n\n"
        "Или отправь голосовое 🎤\n\n"
        "Кнопки внизу:\n"
        "  📅 Сегодня — записи за сегодня\n"
        "  📊 Статистика — итоги за месяц\n"
        "  🗑️ Сбросить всё — удалить все записи",
        reply_markup=KEYBOARD)

async def text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    text = update.message.text.lower()

    if "сегодня" in text:
        await show_today(update, ctx); return
    if "статистика" in text:
        await show_stats(update, ctx); return
    if "сбросить" in text:
        await reset(update, ctx); return
    if "помощь" in text:
        await help_cmd(update, ctx); return

    type_, amount, category = parse_and_save(text)
    if type_ is None:
        return
    emoji = "💚" if type_ == "доход" else "🔴"
    await update.message.reply_text(
        f"✅ Записал {type_}: {emoji} {amount:.0f} сом — {category}",
        reply_markup=KEYBOARD)

async def voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if not await check_user(update): return
    try:
        file = await ctx.bot.get_file(update.message.voice.file_id)
        path = "/tmp/voice.ogg"
        await file.download_to_drive(path)
        client = Groq(api_key=GROQ_KEY)
        with open(path, "rb") as f:
            text = client.audio.transcriptions.create(
                model="whisper-large-v3", file=f, language="ru"
            ).text.lower()
        await update.message.reply_text(f"🎤 Услышал: {text}")
        type_, amount, category = parse_and_save(text)
        if type_ is None:
            await update.message.reply_text("❌ Не нашёл сумму. Скажи например: кофе 300 сом", reply_markup=KEYBOARD)
            return
        emoji = "💚" if type_ == "доход" else "🔴"
        await update.message.reply_text(
            f"✅ Записал {type_}: {emoji} {amount:.0f} сом — {category}",
            reply_markup=KEYBOARD)
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}", reply_markup=KEYBOARD)

logging.basicConfig(level=logging.INFO)
init_db()
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("today", show_today))
app.add_handler(CommandHandler("stats", show_stats))
app.add_handler(CommandHandler("reset", reset))
app.add_handler(CommandHandler("help", help_cmd))
app.add_handler(MessageHandler(filters.VOICE, voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input))
print("Бот запущен!")
app.run_polling()