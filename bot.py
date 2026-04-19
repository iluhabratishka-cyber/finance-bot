import sqlite3, logging, re, os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters
from groq import Groq

BOT_TOKEN = os.environ.get("BOT_TOKEN")
GROQ_KEY = os.environ.get("GROQ_KEY")
DB = "/app/data/finance.db"

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
    numbers = re.findall(r'\d+', text)
    if not numbers:
        return None, None, None
    amount = float(numbers[0])
    category = re.sub(r'\d+', '', text).replace('сом', '').strip() or "прочее"
    income_words = ['доход', 'зарплата', 'получил', 'заработал', 'пришло', 'перевод', 'фриланс']
    type_ = "доход" if any(w in text for w in income_words) else "расход"
    add_transaction(type_, amount, category)
    return type_, amount, category

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Привет! Я веду твои финансы.\n\n"
        "Просто напиши:\n"
        "  кофе 300\n"
        "  зарплата 50000\n\n"
        "Или отправь голосовое 🎤\n\n"
        "Команды:\n"
        "/today — расходы за сегодня\n"
        "/stats — статистика за месяц")

async def доход(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(ctx.args[0])
        category = " ".join(ctx.args[1:]) or "прочее"
        add_transaction("доход", amount, category)
        await update.message.reply_text(f"✅ Доход {amount:.0f} сом ({category}) записан!")
    except:
        await update.message.reply_text("❌ Формат: /income 5000 зарплата")

async def расход(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    try:
        amount = float(ctx.args[0])
        category = " ".join(ctx.args[1:]) or "прочее"
        add_transaction("расход", amount, category)
        await update.message.reply_text(f"✅ Расход {amount:.0f} сом ({category}) записан!")
    except:
        await update.message.reply_text("❌ Формат: /expense 300 кофе")

async def статистика(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB)
    д = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='доход' AND strftime('%Y-%m', date)=strftime('%Y-%m', date('now', '+6 hours'))").fetchone()[0] or 0
    р = conn.execute("SELECT SUM(amount) FROM transactions WHERE type='расход' AND strftime('%Y-%m', date)=strftime('%Y-%m', date('now', '+6 hours'))").fetchone()[0] or 0
    conn.close()
    await update.message.reply_text(f"📊 Статистика за месяц:\n\n💚 Доходы:  {д:.0f} сом\n🔴 Расходы: {р:.0f} сом\n💰 Баланс:  {д-р:.0f} сом")

async def today(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    conn = sqlite3.connect(DB)
    today_date = "date('now', '+6 hours')"
    д_сумма = conn.execute(f"SELECT SUM(amount) FROM transactions WHERE type='доход' AND date={today_date}").fetchone()[0] or 0
    р_сумма = conn.execute(f"SELECT SUM(amount) FROM transactions WHERE type='расход' AND date={today_date}").fetchone()[0] or 0
    д_rows = conn.execute(f"SELECT amount, category FROM transactions WHERE type='доход' AND date={today_date}").fetchall()
    р_rows = conn.execute(f"SELECT amount, category FROM transactions WHERE type='расход' AND date={today_date}").fetchall()
    conn.close()
    if not д_rows and not р_rows:
        await update.message.reply_text("📭 Сегодня записей нет!")
        return
    msg = "📅 Сегодня:\n"
    if д_rows:
        msg += "\n💚 Доходы:\n" + "\n".join([f"  • {r[1]} — {r[0]:.0f} сом" for r in д_rows])
        msg += f"\n  Итого: {д_сумма:.0f} сом\n"
    if р_rows:
        msg += "\n🔴 Расходы:\n" + "\n".join([f"  • {r[1]} — {r[0]:.0f} сом" for r in р_rows])
        msg += f"\n  Итого: {р_сумма:.0f} сом\n"
    msg += f"\n💰 Баланс: {д_сумма - р_сумма:.0f} сом"
    await update.message.reply_text(msg)

async def text_input(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()
    type_, amount, category = parse_and_save(text)
    if type_ is None:
        return
    emoji = "💚" if type_ == "доход" else "🔴"
    await update.message.reply_text(f"✅ Записал {type_}: {emoji} {amount:.0f} сом — {category}")

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
        type_, amount, category = parse_and_save(text)
        if type_ is None:
            await update.message.reply_text("❌ Не нашёл сумму. Скажи например: кофе 300 сом")
            return
        emoji = "📊" if type_ == "доход" else "🔴"
        await update.message.reply_text(f"✅ Записал {type_}: {emoji} {amount:.0f} сом — {category}")
    except Exception as e:
        await update.message.reply_text(f"❌ Ошибка: {e}")

logging.basicConfig(level=logging.INFO)
init_db()
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("income", доход))
app.add_handler(CommandHandler("expense", расход))
app.add_handler(CommandHandler("stats", статистика))
app.add_handler(CommandHandler("today", today))
app.add_handler(MessageHandler(filters.VOICE, voice))
app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_input))
print("Бот запущен!")
app.run_polling()