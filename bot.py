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

TOKEN: str | None = os.environ.get("VK_TOKEN")
if not TOKEN:
    TOKEN = "vk1.a.FaMM2CswZcJsSZ9ZlbZp5SEwDfTM2Adt1bYPYIFk4z1Ai6F0mHfB1mNFfMOlHJexidIbbj8Jlyt13mykczzVTduOncPtVY70K7m4ewYilUrnIJSlDOe-n_piKr_8LvsI6PwM1HD4v_44_kuKpB0oVP9MTQ05ucy5kAfn1YPOBnVO8_uze_5TdgdcVJct73gDxgiLAS1eOSgZ-mBUsOML1w"

if not TOKEN:
    print("❌ Ошибка: Не указан VK_TOKEN!")
    exit(1)

DATABASE_URL: str | None = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "postgresql://bothost_db_c28f080200a2:VKQO5ZU113LDy3icJRRwwndTgaBNNp2KALyme49zAzU@node1.pghost.ru:15807/bothost_db_c28f080200a2"

ADMIN_IDS: list[int] = []

print("✅ Конфигурация загружена!")

bot = Bot(token=TOKEN)
db_pool: asyncpg.Pool | None = None


# ====== БАЗА ДАННЫХ ======

async def init_db():
    global db_pool
    try:
        db_pool = await asyncpg.create_pool(DATABASE_URL)
        async with db_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS nicks (
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    nick VARCHAR(100) NOT NULL,
                    set_by BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
        print("✅ База данных готова")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        exit(1)


async def set_nick(chat_id: int, user_id: int, nick: str, set_by: int):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO nicks (chat_id, user_id, nick, set_by, created_at)
            VALUES ($1, $2, $3, $4, NOW())
            ON CONFLICT (chat_id, user_id)
            DO UPDATE SET nick = $3, set_by = $4, created_at = NOW()
        """, chat_id, user_id, nick, set_by)


async def remove_nick(chat_id: int, user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "DELETE FROM nicks WHERE chat_id = $1 AND user_id = $2 RETURNING nick",
            chat_id, user_id
        )
        return row['nick'] if row else None


async def get_nick(chat_id: int, user_id: int):
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT nick FROM nicks WHERE chat_id = $1 AND user_id = $2",
            chat_id, user_id
        )
        return row['nick'] if row else None


async def get_all_nicks(chat_id: int):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, nick FROM nicks WHERE chat_id = $1 ORDER BY nick",
            chat_id
        )
        return rows


# ====== ВСПОМОГАТЕЛЬНЫЕ ======

async def is_admin(api: API, chat_id: int, user_id: int) -> bool:
    if user_id in ADMIN_IDS:
        return True
    try:
        members = await api.messages.get_conversation_members(
            peer_id=2000000000 + chat_id
        )
        for member in members.items:
            if member.member_id == user_id:
                return bool(member.is_admin or member.is_owner)
    except:
        pass
    return False


async def check_admin(message: Message, chat_id: int) -> bool:
    if await is_admin(bot.api, chat_id, message.from_id):
        return True
    await message.answer("❌ У вас нет прав администратора")
    return False


def get_chat_id(message: Message) -> int:
    return message.peer_id - 2000000000


async def get_user_name(api: API, user_id: int) -> str:
    try:
        user_info = await api.users.get(user_ids=[user_id])
        if user_info:
            return f"{user_info[0].first_name} {user_info[0].last_name}"
    except:
        pass
    return f"id{user_id}"


def extract_id(text: str) -> int:
    if text.isdigit():
        return int(text)
    
    match = re.search(r'\[id(\d+)\|', text)
    if match:
        return int(match.group(1))
    
    match = re.search(r'vk\.com/id(\d+)', text)
    if match:
        return int(match.group(1))
    
    return 0


# ====== КОМАНДЫ ======

@bot.on.message(text=["/help"])
async def help_handler(message: Message):
    await message.answer("""
🤖 Команды:

/kick — кикнуть (ответом)
/ban — забанить (ответом)
/unban @user — разбанить
/snick Ник — установить ник (ответом)
/rnick — удалить ник (ответом)
/gnick — узнать ник (ответом или /gnick @user)
/nicks — список ников в чате
""")


@bot.on.message(text=["/kick"])
async def kick_handler(message: Message):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
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


@bot.on.message(text=["/ban"])
async def ban_handler(message: Message):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
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
        await message.answer(f"✅ Пользователь забанен\n/unban @id{target_id}")
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@bot.on.message(text=["/unban", "/unban <user>"])
async def unban_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    if not user:
        return await message.answer("❌ Укажите: /unban @user или /unban ID")
    
    target_id = extract_id(user)
    
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


@bot.on.message(text=["/snick", "/snick <nick>"])
async def snick_handler(message: Message, nick: str = None):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя")
    
    if not nick:
        return await message.answer("❌ Укажите ник: /snick НовыйНик")
    
    new_nick = nick.strip()
    
    if len(new_nick) > 100:
        return await message.answer("❌ Ник должен быть короче 100 символов")
    
    if len(new_nick) < 2:
        return await message.answer("❌ Ник должен быть длиннее 2 символов")
    
    if re.search(r'[<>{}()\[\]\\\/]', new_nick):
        return await message.answer("❌ Ник содержит запрещённые символы")
    
    target_id = message.reply_message.from_id
    target_name = await get_user_name(bot.api, target_id)
    
    await set_nick(chat_id, target_id, new_nick, message.from_id)
    await message.answer(f"✅ {target_name} теперь {new_nick}")


@bot.on.message(text=["/rnick"])
async def rnick_handler(message: Message):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя")
    
    target_id = message.reply_message.from_id
    target_name = await get_user_name(bot.api, target_id)
    
    old_nick = await remove_nick(chat_id, target_id)
    
    if old_nick:
        await message.answer(f"🗑️ У {target_name} удалён ник {old_nick}")
    else:
        await message.answer(f"❌ У {target_name} нет ника")


@bot.on.message(text=["/gnick", "/gnick <user>"])
async def gnick_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    target_id = 0
    
    if message.reply_message:
        target_id = message.reply_message.from_id
    elif user:
        target_id = extract_id(user)
    
    if not target_id:
        return await message.answer("❌ Ответьте на сообщение или /gnick @user")
    
    target_name = await get_user_name(bot.api, target_id)
    nick = await get_nick(chat_id, target_id)
    
    if nick:
        await message.answer(f"🔍 {target_name} — {nick}")
    else:
        await message.answer(f"🔍 У {target_name} нет ника")


@bot.on.message(text=["/nicks"])
async def nicks_handler(message: Message):
    chat_id = get_chat_id(message)
    
    all_nicks = await get_all_nicks(chat_id)
    
    if not all_nicks:
        return await message.answer("📋 В этом чате нет ников")
    
    text = "📋 Ники в этом чате:\n\n"
    for row in all_nicks:
        user_name = await get_user_name(bot.api, row['user_id'])
        text += f"• {user_name} — {row['nick']}\n"
    
    await message.answer(text)


# ====== ЗАПУСК ======

async def main():
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
