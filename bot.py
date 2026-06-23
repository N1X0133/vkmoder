"""
Бот-администратор для ВКонтакте
Python 3.11+
Функции: кик, бан, разбан, управление никами
База данных: PostgreSQL
"""

import os
import re
import asyncio
import asyncpg
from vkbottle import Bot
from vkbottle.bot import Message
from vkbottle.api import API

# ====== НАСТРОЙКИ ======

# Токен ВК
TOKEN: str | None = os.environ.get("VK_TOKEN")
if not TOKEN:
    print("❌ Ошибка: Не указан VK_TOKEN!")
    exit(1)

# База данных
DATABASE_URL: str | None = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "postgresql://bothost_db_c28f080200a2:VKQO5ZU113LDy3icJRRwwndTgaBNNp2KALyme49zAzU@node1.pghost.ru:15807/bothost_db_c28f080200a2"

# ID администраторов
ADMIN_IDS: list[int] = [
    # 123456789,  # ваш ID
]

bot = Bot(token=TOKEN)
db_pool: asyncpg.Pool | None = None


# ====== РАБОТА С БАЗОЙ ДАННЫХ ======

async def init_db():
    """Инициализация базы данных"""
    global db_pool
    
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS nicks (
                    id SERIAL PRIMARY KEY,
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    nick VARCHAR(100) NOT NULL,
                    set_by BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    UNIQUE(chat_id, user_id)
                )
            """)
            
            await conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_nicks_chat_user 
                ON nicks(chat_id, user_id)
            """)
        
        print("✅ База данных подключена")
    except Exception as e:
        print(f"❌ Ошибка подключения к БД: {e}")
        exit(1)


async def set_nick(chat_id: int, user_id: int, nick: str, set_by: int):
    """Установить ник"""
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO nicks (chat_id, user_id, nick, set_by)
            VALUES ($1, $2, $3, $4)
            ON CONFLICT (chat_id, user_id)
            DO UPDATE SET nick = $3, set_by = $4, created_at = NOW()
        """, chat_id, user_id, nick, set_by)


async def remove_nick(chat_id: int, user_id: int) -> str | None:
    """Удалить ник. Возвращает старый ник или None"""
    async with db_pool.acquire() as conn:
        old_nick = await conn.fetchval(
            "DELETE FROM nicks WHERE chat_id = $1 AND user_id = $2 RETURNING nick",
            chat_id, user_id
        )
        return old_nick


async def get_nick(chat_id: int, user_id: int) -> str | None:
    """Получить ник пользователя"""
    async with db_pool.acquire() as conn:
        nick = await conn.fetchval(
            "SELECT nick FROM nicks WHERE chat_id = $1 AND user_id = $2",
            chat_id, user_id
        )
        return nick


async def get_all_nicks(chat_id: int) -> list:
    """Получить все ники в чате"""
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, nick FROM nicks WHERE chat_id = $1 ORDER BY nick",
            chat_id
        )
        return rows


# ====== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ======

async def is_admin(api: API, chat_id: int, user_id: int) -> bool:
    """Проверка прав администратора"""
    if user_id in ADMIN_IDS:
        return True
    try:
        members = await api.messages.get_conversation_members(
            peer_id=2000000000 + chat_id
        )
        for member in members.items:
            if member.member_id == user_id:
                return bool(member.is_admin or member.is_owner)
    except Exception:
        pass
    return False


async def check_admin(message: Message, chat_id: int) -> bool:
    """Проверка прав с выводом ошибки"""
    if await is_admin(bot.api, chat_id, message.from_id):
        return True
    await message.answer("❌ У вас нет прав администратора")
    return False


def get_chat_id(message: Message) -> int:
    """Получить ID чата"""
    return message.peer_id - 2000000000


async def get_user_name(api: API, user_id: int) -> str:
    """Получить имя пользователя"""
    try:
        user_info = await api.users.get(user_ids=[user_id])
        if user_info:
            return f"{user_info[0].first_name} {user_info[0].last_name}"
    except:
        pass
    return f"id{user_id}"


# ====== КОМАНДЫ ======

@bot.on.message(command=["help", "хелп", "помощь", "команды", "start", "начать"])
async def help_handler(message: Message):
    """Список всех команд"""
    help_text = """
🤖 **Админ-бот | Список команд**

⛔ **/kick** — кикнуть (ответом)
🔨 **/ban** — забанить (ответом)
🔓 **/unban @user** — разбанить

✏️ **Никнеймы:**
📛 **/snick Ник** — установить ник (ответом)
🗑️ **/rnick** — удалить ник (ответом)
🔍 **/gnick** — узнать ник (ответом или /gnick @user)
📋 **/nicks** — список всех ников в чате

📌 Команды для администраторов беседы
    """
    await message.answer(help_text)


# ====== KICK ======

@bot.on.message(command="kick")
async def kick_handler(message: Message):
    """Кикнуть пользователя"""
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    if message.peer_id < 2000000000:
        return await message.answer("❌ Команда только для бесед")
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя")
    
    target_id = message.reply_message.from_id
    
    if target_id == message.from_id:
        return await message.answer("❌ Нельзя кикнуть самого себя")
    
    try:
        await bot.api.messages.remove_chat_user(
            chat_id=chat_id,
            member_id=target_id
        )
        await message.answer("✅ Пользователь кикнут")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ====== BAN ======

@bot.on.message(command="ban")
async def ban_handler(message: Message):
    """Забанить пользователя"""
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    if message.peer_id < 2000000000:
        return await message.answer("❌ Команда только для бесед")
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя")
    
    target_id = message.reply_message.from_id
    
    if target_id == message.from_id:
        return await message.answer("❌ Нельзя забанить самого себя")
    
    try:
        await bot.api.messages.remove_chat_user(
            chat_id=chat_id,
            member_id=target_id
        )
        await bot.api.groups.ban(
            group_id=message.group_id,
            owner_id=target_id
        )
        await message.answer(f"✅ Пользователь забанен\nРазбанить: /unban @id{target_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ====== UNBAN ======

@bot.on.message(command="unban")
async def unban_handler(message: Message):
    """Разбанить пользователя"""
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    args = message.text.split()
    if len(args) < 2:
        return await message.answer("❌ Укажите: /unban @user или /unban ID")
    
    target_text = args[1]
    target_id = 0
    
    if target_text.isdigit():
        target_id = int(target_text)
    else:
        match = re.search(r'\[id(\d+)\|', target_text)
        if match:
            target_id = int(match.group(1))
        else:
            match = re.search(r'vk\.com/id(\d+)', target_text)
            if match:
                target_id = int(match.group(1))
    
    if not target_id:
        return await message.answer("❌ Пользователь не найден")
    
    try:
        await bot.api.groups.unban(
            group_id=message.group_id,
            owner_id=target_id
        )
        await message.answer("✅ Пользователь разбанен")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ====== SNICK (установить ник) ======

@bot.on.message(command="snick")
async def snick_handler(message: Message):
    """Установить никнейм"""
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя")
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer("❌ Укажите ник: /snick НовыйНик")
    
    new_nick = args[1].strip()
    
    if len(new_nick) > 100:
        return await message.answer("❌ Ник должен быть короче 100 символов")
    
    if len(new_nick) < 2:
        return await message.answer("❌ Ник должен быть длиннее 2 символов")
    
    if re.search(r'[<>{}()\[\]\\\/]', new_nick):
        return await message.answer("❌ Ник содержит запрещённые символы")
    
    target_id = message.reply_message.from_id
    target_name = await get_user_name(bot.api, target_id)
    
    await set_nick(chat_id, target_id, new_nick, message.from_id)
    
    await message.answer(f"✅ {target_name} теперь **{new_nick}**")


# ====== RNICK (удалить ник) ======

@bot.on.message(command="rnick")
async def rnick_handler(message: Message):
    """Удалить никнейм"""
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя")
    
    target_id = message.reply_message.from_id
    target_name = await get_user_name(bot.api, target_id)
    
    old_nick = await remove_nick(chat_id, target_id)
    
    if old_nick:
        await message.answer(f"🗑️ У {target_name} удалён ник **{old_nick}**")
    else:
        await message.answer(f"❌ У {target_name} нет ника")


# ====== GNICK (узнать ник) ======

@bot.on.message(command="gnick")
async def gnick_handler(message: Message):
    """Узнать ник пользователя"""
    chat_id = get_chat_id(message)
    target_id = 0
    
    if message.reply_message:
        target_id = message.reply_message.from_id
    else:
        args = message.text.split()
        if len(args) >= 2:
            target_text = args[1]
            
            if target_text.isdigit():
                target_id = int(target_text)
            else:
                match = re.search(r'\[id(\d+)\|', target_text)
                if match:
                    target_id = int(match.group(1))
                else:
                    match = re.search(r'vk\.com/id(\d+)', target_text)
                    if match:
                        target_id = int(match.group(1))
    
    if not target_id:
        return await message.answer("❌ Ответьте на сообщение или укажите: /gnick @user")
    
    target_name = await get_user_name(bot.api, target_id)
    nick = await get_nick(chat_id, target_id)
    
    if nick:
        await message.answer(f"🔍 {target_name} — **{nick}**")
    else:
        await message.answer(f"🔍 У {target_name} нет ника")


# ====== NICKS (список всех ников) ======

@bot.on.message(command="nicks")
async def nicks_handler(message: Message):
    """Показать все ники в чате"""
    chat_id = get_chat_id(message)
    
    all_nicks = await get_all_nicks(chat_id)
    
    if not all_nicks:
        return await message.answer("📋 В этом чате нет ников")
    
    text = "📋 **Ники в этом чате:**\n\n"
    for row in all_nicks:
        user_name = await get_user_name(bot.api, row['user_id'])
        text += f"• {user_name} — **{row['nick']}**\n"
    
    await message.answer(text)


# ====== ОБЫЧНЫЕ СООБЩЕНИЯ ======

@bot.on.message()
async def any_message(message: Message):
    """Ответ в личных сообщениях"""
    if message.peer_id < 2000000000:
        await message.answer(
            "👋 Привет! Я админ-бот.\n"
            "Добавь меня в беседу и дай права администратора.\n\n"
            "Напиши /help для списка команд"
        )


# ====== ЗАПУСК ======

async def main():
    """Главная функция"""
    print("=" * 50)
    print("🤖 Админ-бот ВКонтакте")
    print("🗄️ База данных: PostgreSQL")
    print("=" * 50)
    
    await init_db()
    
    print("📋 Команды: /help, /kick, /ban, /unban")
    print("📛 Ники: /snick, /rnick, /gnick, /nicks")
    print("-" * 50)
    print("✅ Бот запущен!")
    
    try:
        await bot.run_polling()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    finally:
        if db_pool:
            await db_pool.close()
            print("🔌 База данных отключена")


if __name__ == "__main__":
    asyncio.run(main())
