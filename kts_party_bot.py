import os
import json
import re
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
    ConversationHandler,
)

# =============================
#        НАСТРОЙКИ
# =============================
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
if not TOKEN:
    raise RuntimeError("Не найден TELEGRAM_BOT_TOKEN в переменных окружения.")

# Админы
ADMIN_IDS = {455103834}

# Файл хранения данных
DATA_FILE = "party_data.json"

# =============================
#      ГЛОБАЛЬНОЕ СОСТОЯНИЕ
# =============================

# users: {
#   user_id: {
#       "name": str,
#       "points": int,
#       "mode": "offline"|"online",
#       "games": {
#            "truth_game": bool,
#            "binary_game": bool,
#            "headline_game": bool,
#            "emoji_game": bool
#       }
#   }
# }
users = {}

# tg_to_user: {tg_id: user_id}
tg_to_user = {}

next_uid = 1

# =============================
#     ЗАГРУЗКА / СОХРАНЕНИЕ
# =============================

def load_data():
    global users, tg_to_user, next_uid
    if not os.path.exists(DATA_FILE):
        return
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        users = data.get("users", {})
        tg_to_user = {int(k): v for k, v in data.get("tg_to_user", {}).items()}
        next_uid = data.get("next_uid", 1)
    except:
        users = {}
        tg_to_user = {}
        next_uid = 1

def save_data():
    data = {
        "users": users,
        "tg_to_user": tg_to_user,
        "next_uid": next_uid,
    }
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# =============================
#   СОСТОЯНИЯ ДЛЯ МЕНЮ/ИГР
# =============================
(
    CHOOSING_LOCATION,
    MAIN_MENU,
    REG_NAME,
    CHECK_POINTS_ID,
    ADMIN_ADD_ID,
    ADMIN_ADD_VALUE,

    # Игры
    GAME_TRUTH_Q,
    GAME_BINARY_Q,
    GAME_HEADLINE_Q,
    GAME_EMOJI_Q,
) = range(10)

# =============================
#      КЛАВИАТУРЫ
# =============================

def start_keyboard():
    return ReplyKeyboardMarkup(
        [["Я на вечеринке"], ["Я на удаленке"]],
        resize_keyboard=True
    )

# --- МЕНЮ ДЛЯ ОФФЛАЙН ---

def offline_menu_unregistered():
    # Только регистрация, пока нет ID
    return ReplyKeyboardMarkup(
        [
            ["✍️ Регистрация"],
            ["🔙 В меню"],
        ],
        resize_keyboard=True
    )

def offline_menu():
    # Меню для уже зарегистрированных офлайн-гостей (без кнопки регистрации)
    return ReplyKeyboardMarkup(
        [
            ["👁 Играть"],
            ["🧮 Мои баллы", "🏆 Турнирная таблица"],
            ["➕ Добавить баллы", "ℹ️ Правила игры"],
        ],
        resize_keyboard=True
    )

# --- МЕНЮ ДЛЯ ОНЛАЙН ---

def online_menu_unregistered():
    # Только регистрация и назад
    return ReplyKeyboardMarkup(
        [
            ["✍️ Регистрация"],
            ["🔙 В меню"],
        ],
        resize_keyboard=True
    )

def online_menu():
    # Меню для зарегистрированных онлайн-участников (без регистрации)
    return ReplyKeyboardMarkup(
        [
            ["Играть"],
            ["Мои баллы", "Турнирная таблица"],
            ["🔙 В меню"],
        ],
        resize_keyboard=True
    )

def online_games_menu():
    return ReplyKeyboardMarkup(
        [
            ["Где правда?"],
            ["Расшифруй код"],
            ["Правда или ложь"],
            ["Угадай мелодию"],
            ["🔙 В меню"]
        ],
        resize_keyboard=True
    )

# =============================
#     ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =============================

def validate_name(fullname: str) -> bool:
    """
    Имя + фамилия, только буквы (рус/лат), минимум 2 слова.
    """
    parts = fullname.strip().split()
    if len(parts) < 2:
        return False
    for p in parts:
        if not re.match(r"^[A-Za-zА-Яа-яЁё]+$", p):
            return False
    return True

def require_registered(func):
    """
    Декоратор — запрещает выполнять действия, если игрок не зарегистрирован.
    """
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        tg_id = update.effective_user.id
        if tg_id not in tg_to_user:
            await update.message.reply_text(
                "Сначала зарегистрируйтесь 🙂\n"
                "Нажмите «✍️ Регистрация»."
            )
            return MAIN_MENU
        return await func(update, context)
    return wrapper

def get_user_by_tg(update: Update):
    tg_id = update.effective_user.id
    if tg_id not in tg_to_user:
        return None, None
    uid = tg_to_user[tg_id]
    return users.get(uid), uid

# =============================
#          СТАРТ
# =============================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖 Привет! Это бот вечеринки KTS.\n"
        "Для начала выберите, где вы играете:",
        reply_markup=start_keyboard()
    )
    return CHOOSING_LOCATION

async def choose_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    tg_id = update.effective_user.id

    if text == "Я на вечеринке":
        context.user_data["mode"] = "offline"

        # Если уже зарегистрирован — сразу нормальное меню без регистрации
        if tg_id in tg_to_user and users.get(tg_to_user[tg_id], {}).get("mode") == "offline":
            kb = offline_menu()
        else:
            kb = offline_menu_unregistered()

        await update.message.reply_text(
            "Отлично! Добро пожаловать на вечеринку 🎉",
            reply_markup=kb,
        )
        return MAIN_MENU

    if text == "Я на удаленке":
        context.user_data["mode"] = "online"

        if tg_id in tg_to_user and users.get(tg_to_user[tg_id], {}).get("mode") == "online":
            kb = online_menu()
        else:
            kb = online_menu_unregistered()

        await update.message.reply_text(
            "Привет, онлайн-герой ⚡️",
            reply_markup=kb,
        )
        return MAIN_MENU

    await update.message.reply_text(
        "Пожалуйста, выберите один из вариантов.",
        reply_markup=start_keyboard(),
    )
    return CHOOSING_LOCATION

# =============================
#         РЕГИСТРАЦИЯ
# =============================

async def registration(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Введите ваше имя и фамилию:",
        reply_markup=ReplyKeyboardRemove()
    )
    return REG_NAME

async def save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global next_uid

    name = update.message.text.strip()
    if not validate_name(name):
        await update.message.reply_text(
            "Имя должно содержать минимум 2 слова и только буквы.\n"
            "Например: «Иван Петров»."
        )
        return REG_NAME

    mode = context.user_data.get("mode")
    if not mode:
        await update.message.reply_text(
            "Ошибка: не выбран режим (онлайн/офлайн)."
        )
        return MAIN_MENU

    tg_id = update.effective_user.id

    if tg_id in tg_to_user:
        uid = tg_to_user[tg_id]
        users[uid]["name"] = name
        users[uid]["mode"] = mode
    else:
        uid = next_uid
        next_uid += 1
        users[uid] = {
            "name": name,
            "points": 0,
            "mode": mode,
            "games": {
                "truth_game": False,
                "binary_game": False,
                "headline_game": False,
                "emoji_game": False
            }
        }
        tg_to_user[tg_id] = uid

    save_data()

    await update.message.reply_text(
        f"Готово! Вы зарегистрированы как {name}.\n"
        f"Ваш ID: #{uid}",
        reply_markup=online_menu() if mode == "online" else offline_menu()
    )
    return MAIN_MENU

# =============================
#    ПРОСМОТР БАЛЛОВ
# =============================

@require_registered
async def my_points(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)
    await update.message.reply_text(
        f"Ваши баллы: {user['points']}",
    )
    return MAIN_MENU

# =============================
#     ТУРНИРНЫЕ ТАБЛИЦЫ
# =============================

async def build_leaderboard(mode: str):
    data = [
        (uid, info["name"], info["points"])
        for uid, info in users.items()
        if info["mode"] == mode
    ]
    data.sort(key=lambda x: x[2], reverse=True)

    if not data:
        return "Пока нет игроков в этом режиме."

    top = data[:10]
    out = [f"Текущий ТОП-10 ({mode}):"]
    for i, (uid, name, pts) in enumerate(top, start=1):
        out.append(f"{i}. {name} — {pts}")
    return "\n".join(out)

@require_registered
async def leaderboard(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)
    mode = user["mode"]
    text = await build_leaderboard(mode)
    await update.message.reply_text(text)
    return MAIN_MENU
# =============================
#      ОНЛАЙН-ИГРА №1
#       «ГДЕ ПРАВДА?»
# =============================

TRUTH_GAME_QUESTIONS = [
    ("image 2114.png", "left"),
    ("image 2115.png", "left"),
    ("image 2116.png", "right"),
    ("image 2117.png", "left"),
    ("image 2118.png", "left"),
    ("image 2119.png", "right"),
    ("image 2120.png", "left"),
    ("image 2121.png", "left"),
]

@require_registered
async def game_truth_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)

    # уже проходил
    if user["games"]["truth_game"]:
        await update.message.reply_text(
            "Вы уже проходили игру «Где правда?». Баллы начислены ранее.",
            reply_markup=online_games_menu()
        )
        return MAIN_MENU

    context.user_data["truth_index"] = 0
    await update.message.reply_text(
        "Игра «Где правда?»\n"
        "Выберите, какая картинка — реальность.\n"
        "Всего 8 заданий.",
    )
    return await send_truth_question(update, context)

async def send_truth_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("truth_index", 0)

    if idx >= len(TRUTH_GAME_QUESTIONS):
        # игра завершена
        user, uid = get_user_by_tg(update)
        user["games"]["truth_game"] = True
        save_data()
        await update.message.reply_text(
            "Игра завершена! Баллы были начислены при прохождении.",
            reply_markup=online_games_menu()
        )
        return MAIN_MENU

    img, correct = TRUTH_GAME_QUESTIONS[idx]
    path = os.path.join(os.path.dirname(__file__), img)

    with open(path, "rb") as ph:
        await update.message.reply_photo(
            ph,
            caption=f"Задание {idx+1}/8\nГде правда?",
            reply_markup=ReplyKeyboardMarkup(
                [["Слева", "Справа"], ["🔙 В меню"]],
                resize_keyboard=True
            )
        )
    return GAME_TRUTH_Q

@require_registered
async def game_truth_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.lower()

    if text == "🔙 в меню".lower():
        await update.message.reply_text("Меню игр:", reply_markup=online_games_menu())
        return MAIN_MENU

    if text not in ("слева", "справа"):
        await update.message.reply_text("Выберите «Слева» или «Справа».")
        return GAME_TRUTH_Q

    idx = context.user_data.get("truth_index", 0)
    img, correct = TRUTH_GAME_QUESTIONS[idx]

    user, uid = get_user_by_tg(update)

    # "left" или "right"
    user_choice = "left" if text == "слева" else "right"

    if user_choice == correct:
        user["points"] += 1
        save_data()
        await update.message.reply_text("Верно! +1 балл ✨")
    else:
        await update.message.reply_text("Неверно 😅")

    context.user_data["truth_index"] = idx + 1
    return await send_truth_question(update, context)

# =============================
#      ОНЛАЙН-ИГРА №2
#   «РАСШИФРУЙ БИНАРНЫЙ КОД»
# =============================

BINARY_GAME_QUESTIONS = [
    ("01.png", "дедлайн"),
    ("02.png", "созвон"),
    ("03.png", "легенда"),
    ("04.png", "девопс"),
    ("05.png", "корпорат"),
]

@require_registered
async def game_binary_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)

    if user["games"]["binary_game"]:
        await update.message.reply_text(
            "Вы уже проходили игру «Расшифруй код». Баллы начислены ранее.",
            reply_markup=online_games_menu()
        )
        return MAIN_MENU

    context.user_data["binary_index"] = 0
    await update.message.reply_text(
        "Игра «Расшифруй бинарный код».\n"
        "Вводите ответы текстом. Всего 5 заданий."
    )
    return await send_binary_question(update, context)

async def send_binary_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("binary_index", 0)
    if idx >= len(BINARY_GAME_QUESTIONS):
        user, uid = get_user_by_tg(update)
        user["games"]["binary_game"] = True
        save_data()
        await update.message.reply_text(
            "Игра завершена!",
            reply_markup=online_games_menu()
        )
        return MAIN_MENU

    img, ans = BINARY_GAME_QUESTIONS[idx]
    path = os.path.join(os.path.dirname(__file__), img)

    with open(path, "rb") as ph:
        await update.message.reply_photo(
            ph,
            caption=f"Задание {idx+1}/5\nВведите ответ текстом:",
            reply_markup=ReplyKeyboardMarkup(
                [["🔙 В меню"]],
                resize_keyboard=True
            )
        )

    return GAME_BINARY_Q

@require_registered
async def game_binary_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()

    if text == "🔙 в меню".lower():
        await update.message.reply_text("Меню игр:", reply_markup=online_games_menu())
        return MAIN_MENU

    idx = context.user_data.get("binary_index", 0)
    img, ans = BINARY_GAME_QUESTIONS[idx]

    user, uid = get_user_by_tg(update)

    if text == ans.lower():
        user["points"] += 1
        save_data()
        await update.message.reply_text(f"Верно! «{ans}» +1 балл ✨")
    else:
        await update.message.reply_text(f"Неверно. Правильный ответ: {ans}")

    context.user_data["binary_index"] = idx + 1
    return await send_binary_question(update, context)

# =============================
#       ОНЛАЙН-ИГРЫ МЕНЮ
# =============================

@require_registered
async def online_play(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)
    if user["mode"] != "online":
        await update.message.reply_text(
            "Эти игры доступны только для онлайн-участников."
        )
        return MAIN_MENU

    await update.message.reply_text(
        "Выберите игру:",
        reply_markup=online_games_menu()
    )
    return MAIN_MENU
# =============================
#      ОНЛАЙН-ИГРА №3
#      «ПРАВДА ИЛИ ЛОЖЬ?»
# =============================

HEADLINE_GAME_QUESTIONS = [
    ("true11.png", True),
    ("true12.png", True),
    ("true3.png", True),
    ("true4.png", True),
    ("false1.png", False),
    ("false2.png", False),
    ("false3.png", False),
    ("false4.png", False),
]

@require_registered
async def game_headline_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)
    if user["mode"] != "online":
        await update.message.reply_text("Игра доступна только онлайн-участникам.")
        return MAIN_MENU

    if user["games"]["headline_game"]:
        await update.message.reply_text(
            "Вы уже проходили игру «Правда или ложь». Баллы начислены ранее.",
            reply_markup=online_games_menu()
        )
        return MAIN_MENU

    context.user_data["headline_index"] = 0
    await update.message.reply_text(
        "Игра «Угадай реальность заголовка».\n"
        "Выберите: правда или ложь.",
    )
    return await send_headline_question(update, context)

async def send_headline_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("headline_index", 0)
    if idx >= len(HEADLINE_GAME_QUESTIONS):
        user, uid = get_user_by_tg(update)
        user["games"]["headline_game"] = True
        save_data()
        await update.message.reply_text(
            "Игра завершена!",
            reply_markup=online_games_menu()
        )
        return MAIN_MENU

    img, is_true = HEADLINE_GAME_QUESTIONS[idx]
    path = os.path.join(os.path.dirname(__file__), img)

    with open(path, "rb") as ph:
        await update.message.reply_photo(
            ph,
            caption=f"Задание {idx+1}/8\nПравда или ложь?",
            reply_markup=ReplyKeyboardMarkup(
                [["Правда", "Ложь"], ["🔙 В меню"]],
                resize_keyboard=True
            )
        )
    return GAME_HEADLINE_Q

@require_registered
async def game_headline_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip().lower()

    if text == "🔙 в меню".lower():
        await update.message.reply_text("Меню игр:", reply_markup=online_games_menu())
        return MAIN_MENU

    if text not in ("правда", "ложь"):
        await update.message.reply_text("Пожалуйста, выберите «Правда» или «Ложь».")
        return GAME_HEADLINE_Q

    idx = context.user_data.get("headline_index", 0)
    img, is_true = HEADLINE_GAME_QUESTIONS[idx]
    user, uid = get_user_by_tg(update)

    user_choice = (text == "правда")
    if user_choice == is_true:
        user["points"] += 1
        save_data()
        await update.message.reply_text("Верно! +1 балл ✨")
    else:
        await update.message.reply_text("Неверно 😅")

    context.user_data["headline_index"] = idx + 1
    return await send_headline_question(update, context)

# =============================
#      ОНЛАЙН-ИГРА №4
#   «УГАДАЙ МЕЛОДИЮ ПО ЭМОДЗИ»
# =============================

EMOJI_GAME_QUESTIONS = [
    ("💯 🏃‍➡️⬅️", "сто шагов назад"),
    ("☔️🔫", "дожди пистолеты"),
    ("👐🌞", "солнышко в руках"),
    ("🍫🐰", "шоколадный заяц"),
    ("⚪️🌃⬇️☁️", "белая ночь"),
]

def normalize_answer(text: str) -> str:
    # привести к нижнему регистру, убрать лишние пробелы
    t = text.strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t

@require_registered
async def game_emoji_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)
    if user["mode"] != "online":
        await update.message.reply_text("Игра доступна только онлайн-участникам.")
        return MAIN_MENU

    if user["games"]["emoji_game"]:
        await update.message.reply_text(
            "Вы уже проходили игру «Угадай мелодию». Баллы начислены ранее.",
            reply_markup=online_games_menu()
        )
        return MAIN_MENU

    context.user_data["emoji_index"] = 0
    await update.message.reply_text(
        "Игра «Угадай мелодию по эмодзи».\n"
        "Вводите название песни текстом.\n"
        "За правильный ответ: +2 балла."
    )
    return await send_emoji_question(update, context)

async def send_emoji_question(update: Update, context: ContextTypes.DEFAULT_TYPE):
    idx = context.user_data.get("emoji_index", 0)
    if idx >= len(EMOJI_GAME_QUESTIONS):
        user, uid = get_user_by_tg(update)
        user["games"]["emoji_game"] = True
        save_data()
        await update.message.reply_text(
            "Игра завершена!",
            reply_markup=online_games_menu()
        )
        return MAIN_MENU

    emoji_str, ans = EMOJI_GAME_QUESTIONS[idx]
    await update.message.reply_text(
        f"Задание {idx+1}/{len(EMOJI_GAME_QUESTIONS)}\n"
        f"{emoji_str}\n\n"
        f"Напишите название песни:",
        reply_markup=ReplyKeyboardMarkup(
            [["🔙 В меню"]],
            resize_keyboard=True
        )
    )
    return GAME_EMOJI_Q

@require_registered
async def game_emoji_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text.strip().lower() == "🔙 в меню".lower():
        await update.message.reply_text("Меню игр:", reply_markup=online_games_menu())
        return MAIN_MENU

    idx = context.user_data.get("emoji_index", 0)
    emoji_str, ans = EMOJI_GAME_QUESTIONS[idx]
    user, uid = get_user_by_tg(update)

    if normalize_answer(text) == normalize_answer(ans):
        user["points"] += 2
        save_data()
        await update.message.reply_text("Правильно! Держи + 2 балла 🎶✨")
        context.user_data["emoji_index"] = idx + 1
        return await send_emoji_question(update, context)
    else:
        await update.message.reply_text(
            "Кажется, это не та песня, попробуй ещё раз 🙂"
        )
        return GAME_EMOJI_Q

# =============================
#      ОФФЛАЙН «ИГРАТЬ»
# =============================

@require_registered
async def play_offline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)
    if user["mode"] != "offline":
        await update.message.reply_text(
            "Эта часть игры для гостей на самой вечеринке 🙂"
        )
        return MAIN_MENU

    await update.message.reply_text(
        "Вот список активностей, за которые можно получить баллы:\n"
        "— Расшифровать бинарный код ✔️ (2 этаж)\n"
        "— Найти все 6 QR-кодов 🔍 (везде)\n"
        "— Угадать что ИИ, а что реальность 🎭 (3 этаж)\n"
        "— Отличить настоящие новости от выдуманных ⚡ (3 этаж)\n"
        "— Попасть в кольцо 💍 (3 этаж)\n"
        "— Поиграть в алкошахматы 🍷♟ (2 этаж)\n\n"
        "После выполнения подходите к волонтёрам — они начислят баллы.",
        reply_markup=offline_menu()
    )
    return MAIN_MENU

# =============================
#       ПРАВИЛА (ОФФЛАЙН)
# =============================

@require_registered
async def rules_offline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user, uid = get_user_by_tg(update)
    if user["mode"] != "offline":
        await update.message.reply_text(
            "Эти правила относятся к офлайн-игре на вечеринке."
        )
        return MAIN_MENU

    await update.message.reply_text(
        "Правила офлайн-игры:\n\n"
        "— Выполняй задания и активности\n"
        "— Проси волонтёров начислить баллы\n"
        "— Следи за турнирной таблицей\n"
        "— В конце вечера объявим победителей 🏆",
        reply_markup=offline_menu()
    )
    return MAIN_MENU

# =============================
#       АДМИН: ДОБАВИТЬ БАЛЛЫ
# =============================

async def admin_add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    if tg_id not in ADMIN_IDS:
        await update.message.reply_text("Эта функция доступна только организаторам.")
        return MAIN_MENU

    await update.message.reply_text(
        "Введите ID офлайн-игрока (например: 3 или #3):",
        reply_markup=ReplyKeyboardRemove()
    )
    return ADMIN_ADD_ID

async def admin_add_get_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if text.startswith("#"):
        text = text[1:]

    if not text.isdigit():
        await update.message.reply_text(
            "Нужно число (ID игрока). Попробуйте ещё раз."
        )
        return ADMIN_ADD_ID

    uid = int(text)
    if uid not in users:
        await update.message.reply_text("Игрок с таким ID не найден.")
        return ADMIN_ADD_ID

    if users[uid]["mode"] != "offline":
        await update.message.reply_text(
            "Этот игрок не относится к офлайн-режиму (нужен офлайн-игрок)."
        )
        return ADMIN_ADD_ID

    context.user_data["admin_target_uid"] = uid
    await update.message.reply_text(
        f"Выбрали: {users[uid]['name']} (ID #{uid}).\n"
        "Введите, сколько баллов начислить (можно отрицательное число):"
    )
    return ADMIN_ADD_VALUE

async def admin_add_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "admin_target_uid" not in context.user_data:
        await update.message.reply_text("Цель не выбрана, начните заново.")
        return MAIN_MENU

    try:
        delta = int(text)
    except ValueError:
        await update.message.reply_text("Нужно целое число. Попробуйте ещё раз.")
        return ADMIN_ADD_VALUE

    uid = context.user_data["admin_target_uid"]
    if uid not in users:
        await update.message.reply_text("Игрок с таким ID пропал. Начните заново.")
        return MAIN_MENU

    users[uid]["points"] += delta
    save_data()

    await update.message.reply_text(
        f"Готово! {users[uid]['name']} (ID #{uid}) теперь имеет {users[uid]['points']} баллов.",
        reply_markup=offline_menu() if users[uid]["mode"] == "offline" else online_menu()
    )
    context.user_data.pop("admin_target_uid", None)
    return MAIN_MENU

# =============================
#      ВОЗВРАТ В МЕНЮ
# =============================

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Сначала пытаемся понять режим из сохранённых данных
    user, uid = get_user_by_tg(update)
    if user:
        if user["mode"] == "online":
            await update.message.reply_text("Меню онлайн-игры:", reply_markup=online_menu())
        else:
            await update.message.reply_text("Меню:", reply_markup=offline_menu())
        return MAIN_MENU

    # Если ещё не зарегистрирован
    await update.message.reply_text(
        "Сначала выберите, где вы играете:",
        reply_markup=start_keyboard()
    )
    return CHOOSING_LOCATION

# =============================
#          FALLBACK
# =============================

async def fallback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Я вас не совсем понял. Пожалуйста, используйте кнопки меню."
    )
    return MAIN_MENU

# =============================
#            MAIN
# =============================

def main():
    load_data()
    app = Application.builder().token(TOKEN).build()

    conv = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            CHOOSING_LOCATION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, choose_location),
            ],
            MAIN_MENU: [
                # Выбор режима
                MessageHandler(filters.Regex("^Я на вечеринке$"), choose_location),
                MessageHandler(filters.Regex("^Я на удаленке$"), choose_location),

                # Регистрация
                MessageHandler(filters.Regex("^✍️ Регистрация$"), registration),

                # Офлайн
                MessageHandler(filters.Regex("^👁 Играть$"), play_offline),
                MessageHandler(filters.Regex("^ℹ️ Правила игры$"), rules_offline),

                # Онлайн общее
                MessageHandler(filters.Regex("^Играть$"), online_play),
                MessageHandler(filters.Regex("^Мои баллы$"), my_points),
                MessageHandler(filters.Regex("^🧮 Мои баллы$"), my_points),
                MessageHandler(filters.Regex("^Турнирная таблица$"), leaderboard),
                MessageHandler(filters.Regex("^🏆 Турнирная таблица$"), leaderboard),

                # Онлайн игры
                MessageHandler(filters.Regex("^Где правда\\?$"), game_truth_start),
                MessageHandler(filters.Regex("^Расшифруй код$"), game_binary_start),
                MessageHandler(filters.Regex("^Правда или ложь$"), game_headline_start),
                MessageHandler(filters.Regex("^Угадай мелодию$"), game_emoji_start),

                # Админ
                MessageHandler(filters.Regex("^➕ Добавить баллы$"), admin_add_start),

                # Назад
                MessageHandler(filters.Regex("^🔙 В меню$"), back_to_menu),
            ],
            REG_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, save_name),
            ],
            GAME_TRUTH_Q: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, game_truth_answer),
            ],
            GAME_BINARY_Q: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, game_binary_answer),
            ],
            GAME_HEADLINE_Q: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, game_headline_answer),
            ],
            GAME_EMOJI_Q: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, game_emoji_answer),
            ],
            ADMIN_ADD_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_get_id),
            ],
            ADMIN_ADD_VALUE: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, admin_add_get_value),
            ],
        },
        fallbacks=[MessageHandler(filters.ALL & ~filters.COMMAND, fallback)],
    )

    app.add_handler(conv)

    print("Бот запущен...")
    app.run_polling()

if __name__ == "__main__":
    main()

