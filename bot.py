"""
Бот-администратор для ВКонтакте
Python 3.11+
Функции: кик, бан, разбан, установка ника
"""

import os
import re
from vkbottle import Bot
from vkbottle.bot import Message
from vkbottle.api import API

# Токен из переменной окружения хостинга
TOKEN: str | None = os.environ.get("VK_TOKEN")

if not TOKEN:
    print("❌ Ошибка: Не указан VK_TOKEN!")
    print("Добавьте переменную окружения VK_TOKEN в настройках хостинга")
    exit(1)

bot = Bot(token=TOKEN)

# ID администраторов (кто имеет доступ к командам в любой беседе)
ADMIN_IDS: list[int] = [
    # Добавьте свои ID ВК
    # Например: 123456789,
]


async def get_user_id(api: API, mention_or_id: str) -> int:
    """Получает числовой ID пользователя из разных форматов"""
    if mention_or_id.isdigit():
        return int(mention_or_id)
    
    match = re.search(r'\[id(\d+)\|', mention_or_id)
    if match:
        return int(match.group(1))
    
    match = re.search(r'vk\.com/id(\d+)', mention_or_id)
    if match:
        return int(match.group(1))
    
    match = re.search(r'vk\.com/([a-zA-Z0-9_.]+)', mention_or_id)
    if match:
        screen_name = match.group(1)
        if screen_name not in ['id', 'club', 'public']:
            try:
                user = await api.utils.resolve_screen_name(screen_name=screen_name)
                if user and user.type == 'user':
                    return user.object_id
            except Exception:
                pass
    
    return 0


async def is_admin(api: API, chat_id: int, user_id: int) -> bool:
    """Проверяет, является ли пользователь администратором беседы"""
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
    """Проверяет права и отправляет сообщение об ошибке"""
    if message.from_id in ADMIN_IDS:
        return True
    
    if await is_admin(bot.api, chat_id, message.from_id):
        return True
    
    await message.answer("❌ У вас нет прав администратора")
    return False


# ========== КОМАНДЫ ==========

@bot.on.message(command="кик")
async def kick_handler(message: Message):
    """Кикнуть пользователя из беседы"""
    chat_id = message.peer_id - 2000000000
    
    if not await check_admin(message, chat_id):
        return
    
    if message.peer_id < 2000000000:
        return await message.answer("❌ Эта команда работает только в беседе")
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя, которого хотите кикнуть")
    
    target_id = message.reply_message.from_id
    
    if target_id == message.from_id:
        return await message.answer("❌ Вы не можете кикнуть самого себя")
    
    try:
        await bot.api.messages.remove_chat_user(
            chat_id=chat_id,
            member_id=target_id
        )
        await message.answer("✅ Пользователь исключен из беседы")
    except Exception as e:
        await message.answer(f"❌ Ошибка при кике: {str(e)}")


@bot.on.message(command="бан")
async def ban_handler(message: Message):
    """Забанить пользователя (кик + бан в сообществе)"""
    chat_id = message.peer_id - 2000000000
    
    if not await check_admin(message, chat_id):
        return
    
    if message.peer_id < 2000000000:
        return await message.answer("❌ Эта команда работает только в беседе")
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя, которого хотите забанить")
    
    target_id = message.reply_message.from_id
    
    if target_id == message.from_id:
        return await message.answer("❌ Вы не можете забанить самого себя")
    
    try:
        await bot.api.messages.remove_chat_user(
            chat_id=chat_id,
            member_id=target_id
        )
        
        await bot.api.groups.ban(
            group_id=message.group_id,
            owner_id=target_id
        )
        
        await message.answer(
            f"✅ Пользователь заблокирован в сообществе\n"
            f"Чтобы разбанить: /разбан @id{target_id}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка при бане: {str(e)}")


@bot.on.message(command="разбан")
async def unban_handler(message: Message):
    """Разбанить пользователя в сообществе"""
    chat_id = message.peer_id - 2000000000
    
    if not await check_admin(message, chat_id):
        return
    
    args = message.text.split()
    
    if len(args) < 2:
        return await message.answer(
            "❌ Укажите пользователя:\n"
            "/разбан @user\n"
            "/разбан vk.com/id123\n"
            "/разбан 123456789"
        )
    
    target_text = args[1]
    target_id = await get_user_id(bot.api, target_text)
    
    if not target_id:
        return await message.answer(
            "❌ Пользователь не найден. Укажите:\n"
            "• Ссылку на профиль\n"
            "• Упоминание\n"
            "• ID пользователя"
        )
    
    try:
        await bot.api.groups.unban(
            group_id=message.group_id,
            owner_id=target_id
        )
        await message.answer("✅ Пользователь разбанен в сообществе")
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            await message.answer("❌ Пользователь не забанен или уже разбанен")
        else:
            await message.answer(f"❌ Ошибка при разбане: {error_msg}")


@bot.on.message(command="ник")
async def nick_handler(message: Message):
    """Установить никнейм пользователю в беседе"""
    chat_id = message.peer_id - 2000000000
    
    if not await check_admin(message, chat_id):
        return
    
    if not message.reply_message:
        return await message.answer("❌ Ответьте на сообщение пользователя, которому хотите дать ник")
    
    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        return await message.answer(
            "❌ Укажите никнейм:\n"
            "/ник НовыйНик"
        )
    
    new_nick = args[1].strip()
    
    if len(new_nick) > 50:
        return await message.answer("❌ Никнейм должен быть короче 50 символов")
    
    if len(new_nick) < 2:
        return await message.answer("❌ Никнейм должен быть длиннее 2 символов")
    
    if re.search(r'[<>{}()\[\]\\\/]', new_nick):
        return await message.answer("❌ Никнейм содержит запрещенные символы")
    
    target_id = message.reply_message.from_id
    
    try:
        user_info = await bot.api.users.get(user_ids=[target_id])
        if user_info:
            real_name = f"{user_info[0].first_name} {user_info[0].last_name}"
        else:
            real_name = f"id{target_id}"
        
        await message.answer(
            f"✅ Пользователю {real_name} установлен никнейм\n"
            f"📛 Новый ник: {new_nick}"
        )
    except Exception as e:
        await message.answer(f"❌ Ошибка: {str(e)}")


@bot.on.message(command=["команды", "help", "начать", "start"])
async def help_handler(message: Message):
    """Показать список всех команд"""
    help_text = """
🤖 **Админ-бот | Список команд**

⚡ **/кик** — исключить из беседы
⛔ **/бан** — забанить в сообществе
🔓 **/разбан @user** — разблокировать
✏️ **/ник Имя** — установить ник

📋 **Доступные форматы:**
• `/разбан @durov`
• `/разбан vk.com/id1`
• `/разбан 1`

📌 **Команды работают:**
• Только в беседах
• Для администраторов чата
• Отвечать на сообщение цели

👨‍💻 **GitHub:** https://github.com/your/vk-admin-bot
    """
    await message.answer(help_text)


@bot.on.message()
async def any_message(message: Message):
    """Отвечает на любое сообщение"""
    if message.peer_id < 2000000000:
        await message.answer(
            "👋 Привет! Я бот-администратор.\n"
            "Добавь меня в беседу и дай права администратора.\n\n"
            "Напиши /команды для списка команд"
        )


# ========== ЗАПУСК ==========

if __name__ == "__main__":
    print("=" * 50)
    print("🤖 Бот-администратор ВКонтакте")
    print("🐍 Python 3.11+")
    print("=" * 50)
    print("✅ Бот запущен и готов к работе!")
    print("📋 Команды: /кик, /бан, /разбан, /ник, /команды")
    print("-" * 50)
    
    try:
        bot.run_forever()
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        print(f"❌ Критическая ошибка: {e}")
