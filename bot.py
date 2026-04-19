import sqlite3, logging, re, os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")

# --- База данных ---
def init_db():
    conn = sqlite3.connect("finance.db")
    conn.execute("""CREATE TABLE IF NOT EXISTS transactions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        type TEXT, amount REAL, category TEXT, date TEXT DEFAULT (date('now')))""")
    conn.commit(); conn.close()

def add_transaction(type_, amount, category):
    conn = sqlite3.connect("finance.db")
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
    conn = sqlite3.connect("finance.db")
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

        await update.message.reply_text(f"🎤 Услышал: {text}")

        numbers = re.findall(r'\d+', text)
        if not numbers:
            await update.message.reply_text("❌ Не нашёл сумму. Скажи например: кофе 300 сом")
            return

        amount = float(numbers[0])
        category = re.sub(r'\d+', '', text).replace('сом', '').strip() or "прочее"

        add_transaction("расход", amount, category)
        await update.message.reply_text(f"✅ Записал расход: {amount:.0f} сом — {category}")

    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

async def today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect("finance.db")
    расходы = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='расход' AND date=date('now')").fetchone()[0] or 0
    rows = conn.execute("SELECT amount, category FROM transactions WHERE type='расход' AND date=date('now')").fetchall()
    conn.close()
    
    if not rows:
        await update.message.reply_text("📭 Сегодня расходов нет!")
        return
    
    detail = "\n".join([f"  • {r[1]} — {r[0]:.0f} сом" for r in rows])
    await update.message.reply_text(
        f"📅 Расходы за сегодня:\n\n{detail}\n\n💸 Итого: {расходы:.0f} сом")
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