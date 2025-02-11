import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.filters import CommandStart
from aiogram.types import Message, KeyboardButton, ReplyKeyboardMarkup
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from mistralai import Mistral
from datetime import datetime


# Настройки API
API_KEY = os.getenv("API_KEY")
MODEL_NAME = "codestral-latest"


# Настройки Telegram-бота
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Хранилище состояния пользователей
user_requests = {}

# Максимальное количество запросов в день
MAX_REQUESTS_PER_DAY = 10


# Функция для взаимодействия с Mistral AI
async def get_ai_response(content, prompt):
    try:
        client = Mistral(api_key=API_KEY)

        response = await client.chat.stream_async(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": content},
            ],
        )
        result = ""
        async for chunk in response:
            delta_content = chunk.data.choices[0].delta.content
            if delta_content:
                result += delta_content
        return result or "Ошибка: Пустой ответ от модели."
    except Exception as e:
        return f"Произошла ошибка: {e}"


# Создаем экземпляры бота и диспетчера ,session=session
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode='HTML'))
dp = Dispatcher()


# Проверка лимита запросов
def check_request_limit(user_id):
    today = datetime.now().date()

    if user_id not in user_requests:
        user_requests[user_id] = {"count": 0, "date": today}

    # Если дата изменилась, сбрасываем счётчик запросов
    if user_requests[user_id]["date"] != today:
        user_requests[user_id] = {"count": 0, "date": today}

    remaining_requests = MAX_REQUESTS_PER_DAY - user_requests[user_id]["count"]

    if remaining_requests <= 0:
        return "Лимит запросов на сегодня исчерпан.\n\n Попробуйте снова завтра. 👋🏻", False
    return (
        f"Вы можете сделать ещё <b>{remaining_requests} запросов</b> сегодня.\n\n"
        f"<b>Выберите нужный пункт меню, чтобы продолжить 👇🏻</b>",
        True,
    )

# Обновление счётчика запросов
def update_request_count(user_id):
    if user_id in user_requests:
        user_requests[user_id]["count"] += 1


# Создаем главное меню
def create_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="Проверка орфографии 🖍"),
                KeyboardButton(text="Сгенерировать e-mail 📩"),
            ],
            [
                KeyboardButton(text="Получить план эссе 🔍"),
                KeyboardButton(text="Пригласить друга 🌟"),
            ],
        ],
        resize_keyboard=True,
    )


# Определяем состояния для FSM
class EmailStates(StatesGroup):
    waiting_for_email_topic = State()
    waiting_for_email_tone = State()
    waiting_for_additional_details= State()


class EssayStates(StatesGroup):
    waiting_for_essay_topic = State()


class SpellCheckStates(StatesGroup):
    waiting_for_text_to_check = State()


# Команда /start
@dp.message(CommandStart())
async def start_command(message: Message):
    await message.answer(
        "Приветствую тебя! 🇬🇧\n\nМеня зовут <b>Lingvo</b>, и я твой личный помощник в изучении английского языка с функцией ИИ.\n\n"
        "Я накопил обширные знания, изучая лучшие методики преподавания.\n\n➡️ Каждый день я помогаю"
        " школьникам - <b>повысить успеваемость</b>, а взрослым студентам - <b>достигать успеха в работе</b>.\n\n"
        "С моей помощью ты сможешь раскрыть свой потенциал, повысить свои профессиональные навыки и добиться успеха в учебе. 🌟\n\n"
        "<b>Выберите нужный пункт меню, чтобы продолжить 👇🏻</b>",
        reply_markup=create_reply_menu(),
    )


# Обработчик команды "Проверка орфографии 🖍"
@dp.message(F.text == "Проверка орфографии 🖍")
async def spell_checker(message: Message, state: FSMContext):
    await state.set_state(SpellCheckStates.waiting_for_text_to_check)
    await message.answer(
        "Рад помочь!\n\nПожалуйста, отправьте текст <b>на английском языке</b>, который вы хотите проверить на орфографию.\n\n"
        " Я исправлю ошибки и объясню изменения 👇🏻",
        reply_markup=create_reply_menu(),
    )


# Обработчик текста для проверки орфографии
@dp.message(SpellCheckStates.waiting_for_text_to_check)
async def handle_spell_check(message: Message, state: FSMContext):
    prompt = (
        "Ты учительница английского языка и помощник для проверки орфографии на английском языке."
        "Исправь ошибки в тексте пользователя и коротко объясни изменения."
        "Ответ отправляй в формате: <b>Исправленный текст:</b>, <b>Ошибки:</b>"
        "Объясняй ошибки на русском языке."
        "Ты умеешь исправлять ошибки только в английском языке."
        "Общайся в уважительном, дружеском стиле на Вы, подбадривая."
    )

    await state.clear()
    await handle_request(message, prompt)


# Общий обработчик запросов
async def handle_request(message: Message, prompt):
    user_id = message.from_user.id
    limit_message, within_limit = check_request_limit(user_id)

    if not within_limit:
        await message.answer(limit_message)
        return

    if len(message.text) > 200:
        await message.answer("Ваше сообщение слишком длинное! Пожалуйста, сократите текст до 200 символов.")
        return

    # Обновляем счётчик перед отправкой запроса к модели
    update_request_count(user_id)

    response = await get_ai_response(message.text, prompt)
    await message.answer(response, reply_markup=create_reply_menu())

    # После ответа больше не обновляем счётчик
    limit_message, _ = check_request_limit(user_id)
    await message.answer(limit_message, reply_markup=create_reply_menu())


# Команда "Сгенерировать e-mail 📩"
@dp.message(F.text == "Сгенерировать e-mail 📩")
async def write_email(message: Message, state: FSMContext):
    await state.set_state(EmailStates.waiting_for_email_topic)
    await message.answer(
        "С удовольствием помогу!\n\nПожалуйста, опишите, о чем вы бы хотели рассказать в письме, "
        "и я напишу его <b>на английском языке</b> для вас.\n\n"
        "Опишите кратко его тему (например, письмо в университет, жалоба, деловое предложение и т. д.) 👇🏻",
        reply_markup=create_reply_menu()
    )

# Получаем тему письма и спрашиваем о стиле письма (инлайн-кнопки)
@dp.message(EmailStates.waiting_for_email_topic)
async def ask_email_tone(message: Message, state: FSMContext):
    await state.update_data(email_topic=message.text)
    await state.set_state(EmailStates.waiting_for_email_tone)

    # Создаем инлайн-клавиатуру с вариантами стиля письма
    tone_keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 Официальный", callback_data="tone_official")],
        [InlineKeyboardButton(text="😊 Дружеский", callback_data="tone_friendly")],
    ])

    await message.answer(
        "Какой стиль письма вам нужен?\n\n"
        "Выберите один из предложенных или напишите свой вариант 👇🏻",
        reply_markup=tone_keyboard
    )

# Обработка выбора стиля письма через инлайн-кнопки
@dp.callback_query(F.data.startswith("tone_"))
async def handle_email_tone(callback: CallbackQuery, state: FSMContext):
    tone_mapping = {
        "tone_official": "Официальный",
        "tone_friendly": "Дружеский"
    }

    chosen_tone = tone_mapping.get(callback.data, "Неизвестный стиль")
    await state.update_data(email_tone=chosen_tone)

    await callback.message.answer(
        f"Вы выбрали стиль письма: *{chosen_tone}*\n\n"
        "Хотите добавить что-то особенное в письмо? Например, ключевые моменты, длина текста или количество абзацев?"
        "\n\nЕсли ничего не нужно, просто напишите 'Нет'.",
        parse_mode="Markdown"
    )

    await state.set_state(EmailStates.waiting_for_additional_details)
    await callback.answer()  # Закрываем уведомление о нажатии

# Получаем дополнительные детали и передаем данные для генерации email
@dp.message(EmailStates.waiting_for_additional_details)
async def generate_email(message: Message, state: FSMContext):
    user_data = await state.get_data()
    email_topic = user_data.get("email_topic", "")
    email_tone = user_data.get("email_tone", "")
    additional_details = message.text if message.text.lower() != "нет" else ""

    # Формируем запрос для генерации письма
    prompt = (
        "Ты учительница английского языка и профессиональный помощник для написания e-mail. "
        f"Напиши {email_tone.lower()} письмо на английском языке на тему '{email_topic}'. "
        "Убедись, что оно звучит профессионально и естественно."
    )

    if additional_details:
        prompt += f" Дополнительные пожелания: {additional_details}."


    await handle_request(message, prompt)

    # Завершаем FSM
    await state.clear()

# Команда "Получить план эссе 🔍"
@dp.message(F.text == "Получить план эссе 🔍")
async def essay_plan(message: Message, state: FSMContext):
    await state.set_state(EssayStates.waiting_for_essay_topic)
    await message.answer("Отлично!\n\nДавайте составим план эссе.\n\n Пожалуйста, напишите тему вашего эссе 👇🏻", reply_markup=create_reply_menu())

@dp.message(EssayStates.waiting_for_essay_topic)
async def handle_essay_plan(message: Message, state: FSMContext):
    # Формируем запрос для генерации плана эссе
    prompt = (
        "You are an expert in writing essays in English. Create a detailed essay plan in English based on the user's topic. "
        "The plan must include three sections: <b>Introduction</b>, <b>Main Body</b>, and <b>Conclusion</b>. "
        "Each section should contain 2-3 key points or ideas. "
        "Write the plan in English and use clear, structured language. "
        "Here is the user's topic: {user_topic}"
    ).format(user_topic=message.text)

    await state.clear()
    await handle_request(message, prompt)


@dp.message(F.text == "Пригласить друга 🌟")
async def invite_friends(message: Message):
    await message.answer(
        "Очень рада, что тебе здесь нравится!\n\n"
        "Пригласите друга по этой ссылке: https://t.me/myligvoacademy_bot 🌟",
        reply_markup=create_reply_menu()
    )

# Обработчик для сообщений вне меню
@dp.message()
async def handle_unknown_message(message: Message):
    await message.answer("Не понял вас.\n\n Пожалуйста, выберите пункт в меню ниже 👇🏻", reply_markup=create_reply_menu())

# Основной запуск
async def main():
    print("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())