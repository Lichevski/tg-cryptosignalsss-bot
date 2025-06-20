import asyncio
import requests
from os import getenv
from telegram import Bot, KeyboardButton, ReplyKeyboardMarkup, Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from dotenv import load_dotenv

# === Загрузка переменных окружения ===
load_dotenv()
TELEGRAM_BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")

if not TELEGRAM_BOT_TOKEN:
    print("❌ Убедитесь, что .env содержит TELEGRAM_BOT_TOKEN")
    exit()

# === Инициализация бота ===
bot = Bot(token=TELEGRAM_BOT_TOKEN)

# === Глобальные переменные ===
STABLE_COIN = "USDT"
LOOKBACK_MINUTES = 5
PRICE_CHANGE_THRESHOLD = 0.10  # 10%

# Для многопользовательской поддержки:
analysis_tasks = {}           # chat_id: asyncio.Task
send_messages_flags = {}      # chat_id: bool

# === Интерфейс клавиатуры ===
def get_keyboard(start=True):
    button_text = "Запустить анализ" if start else "Остановить анализ"
    keyboard = [[KeyboardButton(button_text)]]
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)

# === Команда /start ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Привет! 👋 Я бот, анализирующий крипторынок на MEXC. "
        "Если цена актива изменилась более чем на 10%, я пришлю сигнал. 🚀",
        reply_markup=get_keyboard(start=True)
    )

# === Обработка запуска анализа ===
async def run_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if analysis_tasks.get(chat_id) and not analysis_tasks[chat_id].done():
        await update.message.reply_text("Анализ уже запущен, брат 🙂")
        return

    send_messages_flags[chat_id] = True
    await update.message.reply_text(
        "✅ Анализ запущен! Нажмите 'Остановить анализ' для остановки.",
        reply_markup=get_keyboard(start=False)
    )

    analysis_tasks[chat_id] = asyncio.create_task(analyze_loop(chat_id))

# === Обработка остановки анализа ===
async def stop_script(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    send_messages_flags[chat_id] = False
    task = analysis_tasks.get(chat_id)

    if task:
        task.cancel()
        analysis_tasks[chat_id] = None

    await update.message.reply_text(
        "⛔️ Анализ остановлен.",
        reply_markup=get_keyboard(start=True)
    )

# === Получить все торговые пары с USDT ===
async def get_all_symbols():
    url = "https://api.mexc.com/api/v3/exchangeInfo"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return [s['symbol'] for s in data['symbols'] if s['quoteAsset'] == STABLE_COIN]
    except Exception as e:
        print(f"[Ошибка получения символов] {e}")
        return []

# === Исторические цены закрытия ===
def get_historical_closes(symbol, interval="1m", limit=LOOKBACK_MINUTES):
    url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return [float(kline[4]) for kline in data]
    except Exception as e:
        print(f"[Ошибка истории {symbol}] {e}")
        return None

# === Текущая цена ===
def get_current_price(symbol):
    url = f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return round(float(resp.json()['price']), 4)
    except Exception as e:
        print(f"[Ошибка цены {symbol}] {e}")
        return None

# === Анализ изменения цены и отправка сигнала ===
async def analyze_and_alert(symbol, chat_id):
    closes = get_historical_closes(symbol)
    if not closes or len(closes) < 2:
        return

    start_price = closes[0]
    current_price = get_current_price(symbol)
    if not current_price:
        return

    change = (current_price - start_price) / start_price
    percent = change * 100

    if abs(change) >= PRICE_CHANGE_THRESHOLD:
        trend = "📈 LONG" if change > 0 else "📉 SHORT"
        msg = (
            f"{trend} сигнал для {symbol}\n"
            f"Цена: {current_price} ({percent:.2f}%) за {LOOKBACK_MINUTES} мин."
        )
        await send_alert(msg, chat_id)

# === Цикл анализа для конкретного пользователя ===
async def analyze_loop(chat_id):
    symbols = await get_all_symbols()
    try:
        while send_messages_flags.get(chat_id, False):
            for symbol in symbols:
                await analyze_and_alert(symbol, chat_id)
                await asyncio.sleep(0.5)  # Пауза между отправками
            await asyncio.sleep(60)  # Пауза между полными циклами анализа
    except asyncio.CancelledError:
        print(f"[Анализ остановлен для {chat_id}]")

# === Отправка сообщения конкретному пользователю ===
async def send_alert(text, chat_id):
    try:
        await bot.send_message(chat_id=chat_id, text=text)
        print(f"[Отправлено {chat_id}] {text}")
    except Exception as e:
        print(f"[Ошибка отправки {chat_id}] {e}")

# === Запуск приложения ===
async def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Запустить анализ$"), run_script))
    app.add_handler(MessageHandler(filters.TEXT & filters.Regex("^Остановить анализ$"), stop_script))

    print("🤖 Бот запущен. Ожидаю команды.")
    await app.run_polling()

# === Точка входа ===
if __name__ == "__main__":
    import nest_asyncio
    nest_asyncio.apply()
    asyncio.get_event_loop().run_until_complete(main())