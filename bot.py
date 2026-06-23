"""
Бот-администратор для ВКонтакте
Python 3.11+
Функции: кик, бан, разбан, управление никами, админами
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

OWNER_IDS: list[int] = [
    724970995,
]

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
            
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS bot_admins (
                    chat_id BIGINT NOT NULL,
                    user_id BIGINT NOT NULL,
                    added_by BIGINT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW(),
                    PRIMARY KEY (chat_id, user_id)
                )
            """)
        print("✅ База данных готова")
    except Exception as e:
        print(f"❌ Ошибка БД: {e}")
        exit(1)


# ====== НИКИ ======

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


# ====== АДМИНЫ ======

async def add_admin(chat_id: int, user_id: int, added_by: int):
    async with db_pool.acquire() as conn:
        await conn.execute("""
            INSERT INTO bot_admins (chat_id, user_id, added_by, created_at)
            VALUES ($1, $2, $3, NOW())
            ON CONFLICT (chat_id, user_id) DO NOTHING
        """, chat_id, user_id, added_by)


async def remove_admin(chat_id: int, user_id: int):
    async with db_pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM bot_admins WHERE chat_id = $1 AND user_id = $2",
            chat_id, user_id
        )
        return result != "DELETE 0"


async def is_bot_admin(chat_id: int, user_id: int) -> bool:
    if user_id in OWNER_IDS:
        return True
    async with db_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT 1 FROM bot_admins WHERE chat_id = $1 AND user_id = $2",
            chat_id, user_id
        )
        return row is not None


async def get_all_admins(chat_id: int):
    async with db_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id, added_by, created_at FROM bot_admins WHERE chat_id = $1 ORDER BY created_at",
            chat_id
        )
        return rows


# ====== ВСПОМОГАТЕЛЬНЫЕ ======

async def is_chat_admin(api: API, chat_id: int, user_id: int) -> bool:
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


async def is_admin(api: API, chat_id: int, user_id: int) -> bool:
    if user_id in OWNER_IDS:
        return True
    if await is_bot_admin(chat_id, user_id):
        return True
    if await is_chat_admin(api, chat_id, user_id):
        return True
    return False


async def check_admin(message: Message, chat_id: int) -> bool:
    if await is_admin(bot.api, chat_id, message.from_id):
        return True
    await message.answer("❌ У вас нет прав")
    return False


def get_chat_id(message: Message) -> int:
    return message.peer_id - 2000000000


async def get_display_name(api: API, chat_id: int, user_id: int) -> str:
    """Получить отображаемое имя: ник если есть, иначе имя из ВК"""
    nick = await get_nick(chat_id, user_id)
    if nick:
        return nick
    
    try:
        user_info = await api.users.get(user_ids=[user_id])
        if user_info:
            return f"{user_info[0].first_name} {user_info[0].last_name}"
    except:
        pass
    return f"id{user_id}"


async def get_user_name(api: API, user_id: int) -> str:
    """Получить реальное имя из ВК"""
    try:
        user_info = await api.users.get(user_ids=[user_id])
        if user_info:
            return f"{user_info[0].first_name} {user_info[0].last_name}"
    except:
        pass
    return f"id{user_id}"


def user_link(user_id: int, name: str) -> str:
    return f"@id{user_id}({name})"


async def resolve_user(api: API, text: str) -> int:
    text = text.strip()
    
    if text.isdigit():
        return int(text)
    
    match = re.search(r'\[id(\d+)\|', text)
    if match:
        return int(match.group(1))
    
    match = re.search(r'vk\.com/id(\d+)', text)
    if match:
        return int(match.group(1))
    
    match = re.search(r'(?:vk\.com/|@)([a-zA-Z0-9_.]+)', text)
    if match:
        screen_name = match.group(1)
        if screen_name not in ['id', 'club', 'public']:
            try:
                result = await api.utils.resolve_screen_name(screen_name=screen_name)
                if result and result.type == 'user':
                    return result.object_id
            except:
                pass
    
    return 0


def get_target(message: Message, user_arg: str = None) -> int:
    if message.reply_message:
        return message.reply_message.from_id
    elif user_arg:
        return 0
    return 0


# ====== КОМАНДЫ ======

@bot.on.message(text=["/help"])
async def help_handler(message: Message):
    await message.answer("""
🤖 Команды бота:

👮 Управление:
/kick @user — кикнуть
/ban @user — забанить
/unban @user — разбанить

📛 Ники:
/snick @user Ник — установить ник
/rnick @user — удалить ник
/gnick @user — узнать ник
/nlist — список всех ников

👑 Админы:
/addadmin @user — дать доступ
/deladmin @user — забрать доступ
/adminlist — список админов бота

💡 Можно: @user, vk.com/user, vk.com/id123, ID
""")


# ====== KICK ======

@bot.on.message(text=["/kick", "/kick <user>"])
async def kick_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    target_id = get_target(message, user)
    
    if not target_id and user:
        target_id = await resolve_user(bot.api, user)
    
    if not target_id:
        return await message.answer("❌ Укажите пользователя: /kick @user")
    
    if target_id == message.from_id:
        return await message.answer("❌ Нельзя кикнуть самого себя")
    
    try:
        await bot.api.messages.remove_chat_user(chat_id=chat_id, member_id=target_id)
        
        admin_display = await get_display_name(bot.api, chat_id, message.from_id)
        target_display = await get_display_name(bot.api, chat_id, target_id)
        
        await message.answer(
            f"✅ {user_link(message.from_id, admin_display)} кикнул {user_link(target_id, target_display)}.",
            disable_mentions=0
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ====== BAN ======

@bot.on.message(text=["/ban", "/ban <user>"])
async def ban_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    target_id = get_target(message, user)
    
    if not target_id and user:
        target_id = await resolve_user(bot.api, user)
    
    if not target_id:
        return await message.answer("❌ Укажите пользователя: /ban @user")
    
    if target_id == message.from_id:
        return await message.answer("❌ Нельзя забанить самого себя")
    
    try:
        await bot.api.messages.remove_chat_user(chat_id=chat_id, member_id=target_id)
        await bot.api.groups.ban(group_id=message.group_id, owner_id=target_id)
        
        admin_display = await get_display_name(bot.api, chat_id, message.from_id)
        target_display = await get_display_name(bot.api, chat_id, target_id)
        
        await message.answer(
            f"✅ {user_link(message.from_id, admin_display)} забанил {user_link(target_id, target_display)}.",
            disable_mentions=0
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ====== UNBAN ======

@bot.on.message(text=["/unban", "/unban <user>"])
async def unban_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    if not user:
        return await message.answer("❌ Укажите: /unban @user")
    
    target_id = await resolve_user(bot.api, user)
    
    if not target_id:
        return await message.answer("❌ Пользователь не найден")
    
    try:
        await bot.api.groups.unban(group_id=message.group_id, owner_id=target_id)
        
        admin_display = await get_display_name(bot.api, chat_id, message.from_id)
        target_display = await get_display_name(bot.api, chat_id, target_id)
        
        await message.answer(
            f"✅ {user_link(message.from_id, admin_display)} разбанил {user_link(target_id, target_display)}.",
            disable_mentions=0
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


# ====== SNICK ======

@bot.on.message(text=["/snick", "/snick <user>", "/snick <user> <nick>"])
async def snick_handler(message: Message, user: str = None, nick: str = None):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    target_id = get_target(message, user)
    
    if not target_id and user:
        target_id = await resolve_user(bot.api, user)
    
    if not target_id:
        return await message.answer("❌ Укажите пользователя: /snick @user Ник")
    
    if not nick:
        parts = message.text.split()
        if len(parts) >= 3:
            nick = " ".join(parts[2:])
    
    if not nick:
        return await message.answer("❌ Укажите ник: /snick @user НовыйНик")
    
    new_nick = nick.strip()
    
    if len(new_nick) > 100:
        return await message.answer("❌ Ник должен быть короче 100 символов")
    
    if len(new_nick) < 2:
        return await message.answer("❌ Ник должен быть длиннее 2 символов")
    
    if re.search(r'[<>{}()\[\]\\\/]', new_nick):
        return await message.answer("❌ Ник содержит запрещённые символы")
    
    target_name = await get_user_name(bot.api, target_id)
    admin_display = await get_display_name(bot.api, chat_id, message.from_id)
    
    await set_nick(chat_id, target_id, new_nick, message.from_id)
    
    await message.answer(
        f"✅ {user_link(message.from_id, admin_display)} поставил никнейм '{new_nick}' {user_link(target_id, target_name)}.",
        disable_mentions=0
    )


# ====== RNICK ======

@bot.on.message(text=["/rnick", "/rnick <user>"])
async def rnick_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    target_id = get_target(message, user)
    
    if not target_id and user:
        target_id = await resolve_user(bot.api, user)
    
    if not target_id:
        return await message.answer("❌ Укажите пользователя: /rnick @user")
    
    admin_display = await get_display_name(bot.api, chat_id, message.from_id)
    target_name = await get_user_name(bot.api, target_id)
    
    old_nick = await remove_nick(chat_id, target_id)
    
    if old_nick:
        await message.answer(
            f"🗑️ {user_link(message.from_id, admin_display)} удалил никнейм {user_link(target_id, target_name)}.",
            disable_mentions=0
        )
    else:
        await message.answer(
            f"❌ У {user_link(target_id, target_name)} нет ника.",
            disable_mentions=0
        )


# ====== GNICK ======

@bot.on.message(text=["/gnick", "/gnick <user>"])
async def gnick_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    target_id = get_target(message, user)
    
    if not target_id and user:
        target_id = await resolve_user(bot.api, user)
    
    if not target_id:
        return await message.answer("❌ Укажите пользователя: /gnick @user")
    
    target_display = await get_display_name(bot.api, chat_id, target_id)
    nick = await get_nick(chat_id, target_id)
    
    if nick:
        await message.answer(
            f"🔍 Никнейм {user_link(target_id, target_display)} — '{nick}'.",
            disable_mentions=0
        )
    else:
        await message.answer(
            f"🔍 У {user_link(target_id, target_display)} нет ника.",
            disable_mentions=0
        )


# ====== NLIST ======

@bot.on.message(text=["/nlist"])
async def nlist_handler(message: Message):
    chat_id = get_chat_id(message)
    
    all_nicks = await get_all_nicks(chat_id)
    
    if not all_nicks:
        return await message.answer("📋 В этом чате нет ников")
    
    text = "📋 Список пользователей с ником:\n\n"
    for i, row in enumerate(all_nicks, 1):
        user_name = await get_user_name(bot.api, row['user_id'])
        text += f"{i}. {user_link(row['user_id'], user_name)} — {row['nick']}\n"
    
    await message.answer(text, disable_mentions=0)


# ====== ADDADMIN ======

@bot.on.message(text=["/addadmin", "/addadmin <user>"])
async def addadmin_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    
    if message.from_id not in OWNER_IDS:
        if not await is_chat_admin(bot.api, chat_id, message.from_id):
            return await message.answer("❌ У вас нет прав")
    
    target_id = get_target(message, user)
    
    if not target_id and user:
        target_id = await resolve_user(bot.api, user)
    
    if not target_id:
        return await message.answer("❌ Укажите пользователя: /addadmin @user")
    
    target_name = await get_user_name(bot.api, target_id)
    admin_display = await get_display_name(bot.api, chat_id, message.from_id)
    
    await add_admin(chat_id, target_id, message.from_id)
    
    await message.answer(
        f"✅ {user_link(message.from_id, admin_display)} выдал права админа {user_link(target_id, target_name)}.",
        disable_mentions=0
    )


# ====== DELADMIN ======

@bot.on.message(text=["/deladmin", "/deladmin <user>"])
async def deladmin_handler(message: Message, user: str = None):
    chat_id = get_chat_id(message)
    
    if message.from_id not in OWNER_IDS:
        if not await is_chat_admin(bot.api, chat_id, message.from_id):
            return await message.answer("❌ У вас нет прав")
    
    target_id = get_target(message, user)
    
    if not target_id and user:
        target_id = await resolve_user(bot.api, user)
    
    if not target_id:
        return await message.answer("❌ Укажите пользователя: /deladmin @user")
    
    if target_id in OWNER_IDS:
        return await message.answer("❌ Нельзя удалить владельца")
    
    target_name = await get_user_name(bot.api, target_id)
    admin_display = await get_display_name(bot.api, chat_id, message.from_id)
    
    removed = await remove_admin(chat_id, target_id)
    
    if removed:
        await message.answer(
            f"✅ {user_link(message.from_id, admin_display)} забрал права админа у {user_link(target_id, target_name)}.",
            disable_mentions=0
        )
    else:
        await message.answer(
            f"❌ {user_link(target_id, target_name)} не был админом.",
            disable_mentions=0
        )


# ====== ADMINLIST ======

@bot.on.message(text=["/adminlist"])
async def adminlist_handler(message: Message):
    chat_id = get_chat_id(message)
    
    if not await check_admin(message, chat_id):
        return
    
    admins = await get_all_admins(chat_id)
    
    text = "👑 Админы бота:\n\n"
    
    for owner_id in OWNER_IDS:
        owner_display = await get_display_name(bot.api, chat_id, owner_id)
        text += f"• {user_link(owner_id, owner_display)} — 👑 владелец\n"
    
    for row in admins:
        admin_display = await get_display_name(bot.api, chat_id, row['user_id'])
        added_by_display = await get_display_name(bot.api, chat_id, row['added_by'])
        text += f"• {user_link(row['user_id'], admin_display)} — назначил {user_link(row['added_by'], added_by_display)}\n"
    
    await message.answer(text, disable_mentions=0)


# ====== ЗАПУСК ======

async def main():
    print("=" * 50)
    print("🤖 Админ-бот ВКонтакте")
    print("🗄️ База данных: PostgreSQL")
    print("=" * 50)
    
    await init_db()
    
    print("📋 Команды: /help, /kick, /ban, /unban")
    print("📛 Ники: /snick, /rnick, /gnick, /nlist")
    print("👑 Админы: /addadmin, /deladmin, /adminlist")
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
