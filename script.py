import asyncio
from os import getenv

import requests
from dotenv import load_dotenv
from telegram import Bot, KeyboardButton, ReplyKeyboardMarkup

load_dotenv()

TELEGRAM_BOT_TOKEN = getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = getenv("TELEGRAM_CHAT_ID")

if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
    print("Ошибка: Задайте TELEGRAM_BOT_TOKEN и TELEGRAM_CHAT_ID в .env файле")
    exit()

bot = Bot(token=TELEGRAM_BOT_TOKEN)

# Константы
STABLE_COIN = "USDT"
LOOKBACK_MINUTES = 5
PRICE_CHANGE_THRESHOLD = 0.10

# Глобальные переменные для управления задачей
analysis_task = None
send_messages = False


def show_start_button(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    button = KeyboardButton("Запустить скрипт")
    markup.add(button)
    bot.send_message(message.chat.id, "Нажмите кнопку для запуска скрипта:", reply_markup=markup)


def show_stop_button(message):
    markup = ReplyKeyboardMarkup(resize_keyboard=True)
    button = KeyboardButton("Остановить сообщения")
    markup.add(button)
    bot.send_message(message.chat.id, "Теперь вы можете остановить сообщения:", reply_markup=markup)


@bot.message_handler(commands=['start'])
def start(message):
    show_start_button(message)


@bot.message_handler(func=lambda message: message.text == "Запустить скрипт")
def run_script(message):
    global send_messages, analysis_task

    if analysis_task and not analysis_task.done():
        bot.send_message(message.chat.id, "Скрипт уже запущен!")
        return

    send_messages = True
    bot.send_message(message.chat.id, "Скрипт запущен! Нажмите 'Остановить сообщения' для его остановки.")
    show_stop_button(message)

    # Запуск асинхронной задачи
    analysis_task = asyncio.create_task(main())


@bot.message_handler(func=lambda message: message.text == "Остановить сообщения")
def stop_messages(message):
    global send_messages, analysis_task
    send_messages = False
    if analysis_task:
        analysis_task.cancel()
        analysis_task = None
    bot.send_message(message.chat.id, "Сообщения остановлены.")
    show_start_button(message)


async def get_all_symbols():
    url = "https://api.mexc.com/api/v3/exchangeInfo"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        symbols = [s['symbol'] for s in data['symbols'] if s['quoteAsset'] == STABLE_COIN]
        return symbols
    except Exception as e:
        print(f"Ошибка получения списка символов: {e}")
        return []


def get_historical_close_prices(symbol, interval="1m", limit=LOOKBACK_MINUTES):
    url = f"https://api.mexc.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        closes = [float(kline[4]) for kline in data]
        return closes
    except Exception as e:
        print(f"Ошибка получения исторических данных для {symbol}: {e}")
        return None


def get_current_price(symbol):
    url = f"https://api.mexc.com/api/v3/ticker/price?symbol={symbol}"
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        return round(float(data['price']), 4)
    except Exception as e:
        print(f"Ошибка получения текущей цены для {symbol}: {e}")
        return None


async def analyze_and_send_signal(symbol):
    closes = get_historical_close_prices(symbol)
    if not closes or len(closes) < 2:
        print(f"[{symbol}] Нет данных для анализа")
        return

    oldest_price = closes[0]
    current_price = get_current_price(symbol)
    if not current_price:
        print(f"[{symbol}] Не удалось получить текущую цену")
        return

    price_change = (current_price - oldest_price) / oldest_price
    percent_change = price_change * 100

    print(f"[{symbol}] Старое: {oldest_price:.4f}, Текущее: {current_price:.4f}, Изменение: {percent_change:.2f}%")

    if abs(price_change) >= PRICE_CHANGE_THRESHOLD:
        if price_change > 0:
            message = f"📊 LONG для {symbol}! Текущая цена {current_price}. Рост на {percent_change:.2f}% за последние {LOOKBACK_MINUTES} минут."
        else:
            message = f"📊 SHORT для {symbol}! Текущая цена {current_price}. Понижение на {abs(percent_change):.2f}% за последние {LOOKBACK_MINUTES} минут."

        await send_message(message)


async def main():
    global send_messages
    symbols = await get_all_symbols()
    try:
        while send_messages:
            for symbol in symbols:
                await analyze_and_send_signal(symbol)
            await asyncio.sleep(60)
    except asyncio.CancelledError:
        print("Задача анализа отменена.")


async def send_message(message):
    try:
        await bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        print(f"Отправлено: {message}")
    except Exception as e:
        print(f"Ошибка отправки сообщения в Telegram: {e}")


# Асинхронный цикл для запуска бота
async def run_bot():
    while True:
        try:
            await bot.polling(none_stop=True)
        except Exception as e:
            print(f"Ошибка в polling: {e}")
            await asyncio.sleep(5)


def run():
    pass


if __name__ == "__main__":
    # Запускаем оба асинхронных процесса: бот и задачу анализа
    asyncio.run(run())


async def run():
    # Создаём таск для бота
    bot_task = asyncio.create_task(run_bot())
    # Основной цикл
    while True:
        await asyncio.sleep(1)