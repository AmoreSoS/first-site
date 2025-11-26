import json
import os
from telegram import (
    Update,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    ContextTypes,
    filters,
)

# ---------- НАСТРОЙКИ ----------
# Токен берём из переменной окружения TELEGRAM_BOT_TOKEN
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

if not TOKEN:
    raise RuntimeError(
        "Не задан TELEGRAM_BOT_TOKEN. "
        "Установи переменную окружения TELEGRAM_BOT_TOKEN с токеном бота."
    )

# Telegram ID организаторов, которые могут добавлять баллы (офлайн/онлайн по желанию)
ADMIN_IDS = {
    # Пример: 123456789,
    # Добавь сюда реальные telegram ID организаторов
}

DATA_FILE = "party_data.json"

# ---------- СОСТОЯНИЯ ДЛЯ CONVERSATION ----------
(
    CHOOSING_LOCATION,
    MAIN_MENU,
    REGISTRATION_NAME,
    CHECK_POINTS_QUERY,
    ADD_POINTS_ID_OR_NAME,
    ADD_POINTS_AMOUNT,
) = range(6)

# ---------- "БАЗА ДАННЫХ" В ПАМЯТИ ----------
# users_by_id: {id: {"name": str, "points": int, "mode": "offline"|"online"}}
users_by_id: dict[int, dict] = {}
# user_ids_by_tg: {telegram_user_id: id}
user_ids_by_tg: dict[int, int] = {}
next_user_id: int = 1


# ---------- ФУНКЦИИ ХРАНЕНИЯ ДАННЫХ ----------

def load_data():
    """Загрузка данных из JSON при старте."""
    global users_by_id, user_ids_by_tg, next_user_id

    if not os.path.exists(DATA_FILE):
        return

    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)

        users_by_id_raw = data.get("users_by_id", {})
        users_by_id.clear()
        for uid_str, info in users_by_id_raw.items():
            uid = int(uid_str)
            # для старых записей по умолчанию считаем офлайновым режимом
            if "mode" not in info:
                info["mode"] = "offline"
            users_by_id[uid] = info

        user_ids_by_tg_raw = data.get("user_ids_by_tg", {})
        user_ids_by_tg.clear()
        for tg_str, uid in user_ids_by_tg_raw.items():
            user_ids_by_tg[int(tg_str)] = int(uid)

        next_user_id = int(data.get("next_user_id", 1))
        print(f"Данные загружены. Игроков: {len(users_by_id)}")

    except Exception as e:
        print(f"Ошибка загрузки данных: {e}")


def save_data():
    """Сохранение данных в JSON при изменениях."""
    try:
        data = {
            "users_by_id": {str(uid): info for uid, info in users_by_id.items()},
            "user_ids_by_tg": {
                str(tg): int(uid) for tg, uid in user_ids_by_tg.items()
            },
            "next_user_id": next_user_id,
        }
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Ошибка сохранения данных: {e}")


# ---------- КЛАВИАТУРЫ ----------

def start_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["Я на вечеринке"],
            ["Я на удаленке"],
        ],
        resize_keyboard=True,
    )


def offline_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["👁 Играть", "✍️ Регистрация"],
            ["🧮 Мои баллы", "🏆 Турнирная таблица"],
            ["➕ Добавить баллы", "ℹ️ Правила игры"],
        ],
        resize_keyboard=True,
    )


def online_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        [
            ["Регистрация", "Играть"],
            ["Мои баллы", "Турнирная таблица"],
            ["🔙 В меню"],
        ],
        resize_keyboard=True,
    )


def get_current_menu_keyboard(context: ContextTypes.DEFAULT_TYPE) -> ReplyKeyboardMarkup:
    mode_menu = context.user_data.get("mode_menu", "offline")
    if mode_menu == "online":
        return online_main_menu_keyboard()
    return offline_main_menu_keyboard()


# ---------- ОБРАБОТЧИКИ СТАРТА И ВЫБОРА РЕЖИМА ----------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🤖\nПривет! ✨\n"
        "Это бот вечеринки KTS.\n"
        "Я буду считать твои баллы и показывать, какое место ты занимаешь в рейтинге гостей.\n"
        "Выполняй задания, получай баллы, а за первые 3 места мы вручим подарки 🎁\n\n"
        "Выбери действие:",
        reply_markup=start_keyboard(),
    )
    return CHOOSING_LOCATION


async def choose_location(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text

    if text == "Я на вечеринке":
        context.user_data["mode_menu"] = "offline"
        await update.message.reply_text(
            "🔥 Отлично! Добро пожаловать на вечеринку KTS!\n"
            "Выбирай действие:",
            reply_markup=offline_main_menu_keyboard(),
        )
        return MAIN_MENU

    elif text == "Я на удаленке":
        context.user_data["mode_menu"] = "online"
        await update.message.reply_text(
            "Привет, онлайн-герой KTS! ⚡️\n\n"
            "Для тебя тоже есть игра — онлайн-челленджи, квизы, задания в чате.\n"
            "Ты можешь участвовать прямо из дома и набирать баллы так же, как гости на месте.\n"
            "Топ-3 дистанционных участников тоже получат подарки 🎁\n\n"
            "Меню:",
            reply_markup=online_main_menu_keyboard(),
        )
        return MAIN_MENU

    else:
        await update.message.reply_text(
            "Пожалуйста, выбери один из вариантов на клавиатуре.",
            reply_markup=start_keyboard(),
        )
        return CHOOSING_LOCATION


# ---------- РЕГИСТРАЦИЯ (ОФФЛАЙН / ОНЛАЙН) ----------

async def registration_entry_offline(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data["reg_mode"] = "offline"
    await update.message.reply_text(
        "✍️ РЕГИСТРАЦИЯ\n\n"
        "Чтобы зарегистрироваться в игре, отправь своё имя или ник,\n"
        "который будет отображаться в таблице.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REGISTRATION_NAME


async def registration_entry_online(
    update: Update, context: ContextTypes.DEFAULT_TYPE
):
    context.user_data["reg_mode"] = "online"
    await update.message.reply_text(
        "✍️ РЕГИСТРАЦИЯ (онлайн)\n\n"
        "Чтобы зарегистрироваться в игре, отправь своё имя или ник,\n"
        "который будет отображаться в таблице.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return REGISTRATION_NAME


async def registration_save_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global next_user_id

    name = update.message.text.strip()
    tg_id = update.effective_user.id
    mode = context.user_data.get("reg_mode", "offline")

    # если пользователь уже есть — обновим имя и режим
    if tg_id in user_ids_by_tg:
        user_id = user_ids_by_tg[tg_id]
        users_by_id[user_id]["name"] = name
        users_by_id[user_id]["mode"] = mode
    else:
        user_id = next_user_id
        next_user_id += 1
        users_by_id[user_id] = {"name": name, "points": 0, "mode": mode}
        user_ids_by_tg[tg_id] = user_id

    save_data()

    if mode == "offline":
        keyboard = ReplyKeyboardMarkup(
            [["👁 Играть", "🔙 В меню"]],
            resize_keyboard=True,
        )
    else:
        keyboard = ReplyKeyboardMarkup(
            [
                ["👁 Играть"],
                ["🧮 Мои баллы", "🏆 Турнирная таблица"],
                ["🔙 В меню"],
            ],
            resize_keyboard=True,
        )

    await update.message.reply_text(
        f"Отлично, ты зарегистрирован как {name} ✨\n"
        f"Твой игровой ID: #{user_id}\n\n"
        f"Теперь можешь играть и собирать баллы!",
        reply_markup=keyboard,
    )
    return MAIN_MENU


# ---------- ИГРАТЬ (ОФФЛАЙН) ----------

async def play_offline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👁 ИГРАТЬ (офлайн)\n\n"
        "Вот список активностей, за которые можно получить баллы:\n"
        "— Расшифровать бинарный код ✔️ (2 этаж)\n"
        "— Найти все 6 QR кодов и стать избранным 🔍 (везде)\n"
        "— Угадать что ИИ, а что реальность 🎭 (3 этаж)\n"
        "— Отличить настоящие новости от выдуманных ⚡ (3 этаж)\n"
        "— Попасть в кольцо 💍 (3 этаж)\n"
        "— Поиграть в алкошахматы 🍷♟ (2 этаж)\n\n"
        "Когда ты что-то выполняешь, подойди к волонтёру — он начислит тебе баллы.",
        reply_markup=ReplyKeyboardMarkup(
            [["🧮 Мои баллы", "🏆 Турнирная таблица"], ["🔙 В меню"]],
            resize_keyboard=True,
        ),
    )
    return MAIN_MENU


# ---------- ИГРАТЬ (ОНЛАЙН) ----------

async def play_online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Пока только меню игр. Квизы и автонНачисление баллов добавим, когда принесёшь задания.
    await update.message.reply_text(
        "👁 ИГРАТЬ (онлайн)\n\n"
        "Выбери игру:\n"
        "— Расшифруй бинарный код ✔️\n"
        "— Угадай что ИИ, а что реальность 🎭\n"
        "— Отличи настоящие новости от выдуманных ⚡\n"
        "— Угадай мелодию по эмодзи 🎵\n"
        "— 3 вопроса про KTS за 10 лет 🎂\n\n"
        "Скоро здесь будут полноценные квизы с автонНачислением баллов ✨",
        reply_markup=ReplyKeyboardMarkup(
            [
                ["🧮 Мои баллы", "🏆 Турнирная таблица"],
                ["🔙 В меню"],
            ],
            resize_keyboard=True,
        ),
    )
    return MAIN_MENU


# ---------- ПОИСК ИГРОКА ----------

def find_user(query: str):
    """Поиск игрока по ID или имени (без учёта регистра)."""
    query = query.strip()
    # Попытка интерпретировать как ID
    if query.startswith("#"):
        query = query[1:]
    if query.isdigit():
        uid = int(query)
        return users_by_id.get(uid), uid

    # Иначе ищем по имени
    lower_query = query.lower()
    for uid, info in users_by_id.items():
        if info["name"].lower() == lower_query:
            return info, uid

    return None, None


# ---------- МОИ БАЛЛЫ ----------

async def my_points_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "🧮 МОИ БАЛЛЫ\n\n"
        "Введи свой ID (например: 3 или #3) или имя, чтобы я нашёл твой счёт.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return CHECK_POINTS_QUERY


async def my_points_show(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    user, uid = find_user(query)

    if not user:
        await update.message.reply_text(
            "Я не нашёл игрока с таким именем или ID 😔\n"
            "Попробуй ещё раз или зарегистрируйся.",
            reply_markup=get_current_menu_keyboard(context),
        )
        return MAIN_MENU

    mode_menu = context.user_data.get("mode_menu", "offline")
    if mode_menu == "online":
        keyboard = ReplyKeyboardMarkup(
            [
                ["Турнирная таблица", "👁 Играть"],
                ["🔙 В меню"],
            ],
            resize_keyboard=True,
        )
    else:
        keyboard = ReplyKeyboardMarkup(
            [
                ["🏆 Турнирная таблица", "👁 Играть"],
                ["🔙 В меню"],
            ],
            resize_keyboard=True,
        )

    await update.message.reply_text(
        f"У тебя сейчас {user['points']} баллов ✨\n"
        f"Имя: {user['name']}\n"
        f"ID: #{uid}\n\n"
        f"Продолжай в том же духе!",
        reply_markup=keyboard,
    )
    return MAIN_MENU


# ---------- ПРАВИЛА ИГРЫ (ОФФЛАЙН) ----------

async def rules_offline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "ℹ️ ПРАВИЛА ИГРЫ (офлайн)\n\n"
        "Правила простые:\n"
        "— Выполняй задания и активности\n"
        "— Получай баллы от волонтёров (не забывай просить их начислить)\n"
        "— Следи за турнирной таблицей\n"
        "— В 22:40 объявим победителей 🏆\n\n"
        "Хочешь начать?",
        reply_markup=ReplyKeyboardMarkup(
            [["👁 Играть", "🔙 В меню"]],
            resize_keyboard=True,
        ),
    )
    return MAIN_MENU


# ---------- ТУРНИРНЫЕ ТАБЛИЦЫ ----------

def get_leaderboard_text(mode: str, current_user_id: int | None):
    """
    mode: "offline" или "online".
    Строим отдельные рейтинги.
    """
    filtered = [
        (uid, info)
        for uid, info in users_by_id.items()
        if info.get("mode", "offline") == mode
    ]

    if not filtered:
        if mode == "offline":
            return "Пока ещё никто не зарегистрировался или не набрал баллы в офлайн-игре 🤔"
        else:
            return "Пока ещё никто не зарегистрировался или не набрал баллы в онлайн-игре 🤔"

    sorted_users = sorted(
        filtered,
        key=lambda item: item[1]["points"],
        reverse=True,
    )

    if mode == "offline":
        header = "ТЕКУЩИЙ ТОП-10 ГОСТЕЙ (офлайн):\n"
    else:
        header = "ТЕКУЩИЙ ТОП-10 ГОСТЕЙ (онлайн):\n"

    lines = [header]
    for idx, (uid, info) in enumerate(sorted_users[:10], start=1):
        lines.append(f"{idx}. {info['name']} — {info['points']}")

    if current_user_id is not None:
        # найдём позицию именно этого игрока
        for pos, (uid, info) in enumerate(sorted_users, start=1):
            if uid == current_user_id:
                lines.append(
                    "\nТвои результаты:\n"
                    f"{info['name']} — {info['points']} баллов, {pos}-е место."
                )
                break

    return "\n".join(lines)


async def leaderboard_offline(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    current_user_id = user_ids_by_tg.get(tg_id)

    text = get_leaderboard_text("offline", current_user_id)

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(
            [["🎯 Мои баллы", "🔙 В меню"]],
            resize_keyboard=True,
        ),
    )
    return MAIN_MENU


async def leaderboard_online(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tg_id = update.effective_user.id
    current_user_id = user_ids_by_tg.get(tg_id)

    text = get_leaderboard_text("online", current_user_id)

    await update.message.reply_text(
        text,
        reply_markup=ReplyKeyboardMarkup(
            [["🎯 Мои баллы", "🔙 В меню"]],
            resize_keyboard=True,
        ),
    )
    return MAIN_MENU


# ---------- ДОБАВЛЕНИЕ БАЛЛОВ (ОРГАНИЗАТОРЫ) ----------

async def add_points_entry(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text(
            "Эта функция только для организаторов 🙅‍♂️",
            reply_markup=get_current_menu_keyboard(context),
        )
        return MAIN_MENU

    await update.message.reply_text(
        "➕ ДОБАВИТЬ БАЛЛЫ\n\n"
        "Отправь ID (например: 3 или #3) или имя игрока, которому нужно начислить баллы.",
        reply_markup=ReplyKeyboardRemove(),
    )
    return ADD_POINTS_ID_OR_NAME


async def add_points_get_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.message.text
    user, uid = find_user(query)

    if not user:
        await update.message.reply_text(
            "Не нашёл такого игрока. Проверь ID/имя или попроси гостя зарегистрироваться.",
            reply_markup=get_current_menu_keyboard(context),
        )
        return MAIN_MENU

    context.user_data["target_user_id"] = uid
    await update.message.reply_text(
        f"Игрок: {user['name']} (ID #{uid}, режим: {user.get('mode', 'offline')})\n"
        "Сколько баллов начислить? Введи число (можно отрицательное, чтобы снять баллы).",
    )
    return ADD_POINTS_AMOUNT


async def add_points_set_amount(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if "target_user_id" not in context.user_data:
        await update.message.reply_text(
            "Что-то пошло не так, попробуй ещё раз.",
            reply_markup=get_current_menu_keyboard(context),
        )
        return MAIN_MENU

    try:
        delta = int(text)
    except ValueError:
        await update.message.reply_text(
            "Нужно отправить именно число (например: 5 или -3). Попробуй ещё раз.",
        )
        return ADD_POINTS_AMOUNT

    uid = context.user_data["target_user_id"]
    user = users_by_id.get(uid)
    if not user:
        await update.message.reply_text(
            "Игрок куда-то пропал из базы. Попробуй выбрать его заново.",
            reply_markup=get_current_menu_keyboard(context),
        )
        return MAIN_MENU

    user["points"] += delta
    save_data()

    await update.message.reply_text(
        f"Готово ✅\n"
        f"{user['name']} (ID #{uid}, режим: {user.get('mode', 'offline')}) "
        f"теперь имеет {user['points']} баллов.",
        reply_markup=get_current_menu_keyboard(context),
    )
    context.user_data.pop("target_user_id", None)
    return MAIN_MENU


# ---------- ОБЩИЙ "В МЕНЮ" И FALLBACK ----------

async def back_to_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Главное меню:",
        reply_markup=get_current_menu_keyboard(context),
    )
    return MAIN_MENU


async def fallback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Не совсем понял 🤔\n"
        "Пожалуйста, воспользуйся кнопками на клавиатуре.",
        reply_markup=get_current_menu_keyboard(context),
    )
    return MAIN_MENU


# ---------- MAIN ----------

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
                # офлайн кнопки
                MessageHandler(filters.Regex("^✍️ Регистрация$"), registration_entry_offline),
                MessageHandler(filters.Regex("^👁 Играть$"), play_offline),
                MessageHandler(filters.Regex("^🧮 Мои баллы$"), my_points_entry),
                MessageHandler(filters.Regex("^ℹ️ Правила игры$"), rules_offline),
                MessageHandler(filters.Regex("^🏆 Турнирная таблица$"), leaderboard_offline),
                MessageHandler(filters.Regex("^➕ Добавить баллы$"), add_points_entry),

                # онлайн кнопки
                MessageHandler(filters.Regex("^Регистрация$"), registration_entry_online),
                MessageHandler(filters.Regex("^Играть$"), play_online),
                MessageHandler(filters.Regex("^Мои баллы$"), my_points_entry),
                MessageHandler(filters.Regex("^Турнирная таблица$"), leaderboard_online),

                # общий "назад"
                MessageHandler(filters.Regex("^🔙 В меню$"), back_to_menu),

                # вдруг снова выбрали режим
                MessageHandler(filters.Regex("^Я на вечеринке$"), choose_location),
                MessageHandler(filters.Regex("^Я на удаленке$"), choose_location),
            ],
            REGISTRATION_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, registration_save_name),
            ],
            CHECK_POINTS_QUERY: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, my_points_show),
            ],
            ADD_POINTS_ID_OR_NAME: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_points_get_user),
            ],
            ADD_POINTS_AMOUNT: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, add_points_set_amount),
            ],
        },
        fallbacks=[
            MessageHandler(filters.Regex("^🔙 В меню$"), back_to_menu),
            MessageHandler(filters.ALL & ~filters.COMMAND, fallback_handler),
        ],
    )

    app.add_handler(conv)

    print("Бот запущен...")
    app.run_polling()


if __name__ == "__main__":
    main()
