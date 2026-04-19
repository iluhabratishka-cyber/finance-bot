import sqlite3, logging, re, os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")

# --- База данных ---
def init_db():
    conn = sqlite3.connect("/app/data/finance.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT, amount REAL, category TEXT, date TEXT DEFAULT (date('now', '+6 hours')))""")
    conn.commit(); conn.close()

def add_transaction(type_, amount, category):
    conn = sqlite3.connect("/app/data/finance.db")
    conn.execute("INSERT INTO transactions (type, amount, category) VALUES (?,?,?)", (type_, amount, category))
    conn.commit(); conn.close()

# --- Команды ---
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я веду твои финансы.\n\n"
        "/income 5000 зарплата\n"
        "/expense 300 кофе\n"
        "/stats\n"
        "🎤 Или отправь голосовое: кофе 300 сом")

async def доход(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(ctx.args[0])
        category = " ".join(ctx.args[1:]) or "прочее"
        add_transaction("доход", amount, category)
        await update.message.reply_text(f"✅ Доход {amount} сом ({category}) записан!")
    except:
        await update.message.reply_text("❌ Формат: /income 5000 зарплата")

async def расход(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(ctx.args[0])
        category = " ".join(ctx.args[1:]) or "прочее"
        add_transaction("расход", amount, category)
        await update.message.reply_text(f"✅ Расход {amount} сом ({category}) записан!")
    except:
        await update.message.reply_text("❌ Формат: /expense 300 кофе")

async def статистика(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("/app/data/finance.db")
    доходы = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='доход' AND strftime('%Y-%m', date)=strftime('%Y-%m','now')").fetchone()[0] or 0
    расходы = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='расход' AND strftime('%Y-%m', date)=strftime('%Y-%m','now')").fetchone()[0] or 0
    conn.close()
    await update.message.reply_text(
        f"📊 Статистика за этот месяц:\n\n"
        f"💚 Доходы:  {доходы:.0f} сом\n"
        f"🔴 Расходы: {расходы:.0f} сом\n"
        f"💰 Баланс:  {доходы - расходы:.0f} сом")

async def voice(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        file = await ctx.bot.get_file(update.message.voice.file_id)
        path = "/tmp/voice.ogg"
        await file.download_to_drive(path)

        client = Groq(api_key=GROQ_KEY)
        with open(path, "rb") as f:
            text = client.audio.transcriptions.create(
                model="whisper-large-v3", file=f, language="ru"
            ).text.lower()

        numbers = re.findall(r'\d+', text)
        if not numbers:
            await update.message.reply_text("❌ Не нашёл сумму. Скажи например: кофе 300 сом")
            return

        amount = float(numbers[0])
        category = re.sub(r'\d+', '', text).replace('сом', '').strip() or "прочее"

        # Определяем тип — доход или расход
        income_words = ['доход', 'зарплата', 'получил', 'заработал', 'пришло', 'перевод', 'фриланс']
        type_ = "доход" if any(w in text for w in income_words) else "расход"
        emoji = "💚" if type_ == "доход" else "🔴"

        add_transaction(type_, amount, category)
        await update.message.reply_text(f"✅ Записал {type_}: {emoji} {amount:.0f} сом — {category}")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("/app/data/finance.db")
    расходы_сумма = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='расход' AND date=date('now')").fetchone()[0] or 0
    доходы_сумма = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='доход' AND date=date('now')").fetchone()[0] or 0
    расходы_rows = conn.execute("SELECT amount, category FROM transactions WHERE type='расход' AND date=date('now')").fetchall()
    доходы_rows = conn.execute("SELECT amount, category FROM transactions WHERE type='доход' AND date=date('now')").fetchall()
    conn.close()

    if not расходы_rows and not доходы_rows:
        await update.message.reply_text("📭 Сегодня записей нет!")
        return

    msg = "📅 Сегодня:\n"

    if доходы_rows:
        msg += "\n💚 Доходы:\n"
        msg += "\n".join([f"  • {r[1]} — {r[0]:.0f} сом" for r in доходы_rows])
        msg += f"\n  Итого: {доходы_сумма:.0f} сом\n"

    if расходы_rows:
        msg += "\n🔴 Расходы:\n"
        msg += "\n".join([f"  • {r[1]} — {r[0]:.0f} сом" for r in расходы_rows])
        msg += f"\n  Итого: {расходы_сумма:.0f} сом\n"

    msg += f"\n💰 Баланс: {доходы_сумма - расходы_сумма:.0f} сом"

    await update.message.reply_text(msg)
# --- Запуск ---
logging.basicConfig(level=logging.INFO)
init_db()
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("income", доход))
app.add_handler(CommandHandler("expense", расход))
app.add_handler(CommandHandler("stats", статистика))
app.add_handler(MessageHandler(filters.VOICE, voice))
app.add_handler(CommandHandler("today", today))
print("Бот запущен!")
app.run_polling()