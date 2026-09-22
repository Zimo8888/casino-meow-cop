import os
import re
import html
import time
import sqlite3
import threading

import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions


# =========================================================
# تنظیمات اصلی
# =========================================================

TOKEN = os.getenv("BOT_TOKEN")

if not TOKEN:
    raise RuntimeError("BOT_TOKEN در Railway تنظیم نشده است.")

ALLOWED_GROUP = -1004410278746
MAIN_OWNER = 7105951313

WELCOME_PHOTO_URL = (
    "AgACAgIAAxkBAAEvBV5qsVbqOFe9mgvyTCSP52TSuQ0mtwACWyJrGwmZYUlchxeM79golgEAAwIAA3kAAz0E"
)

BOT_USERNAME = "@casinomeowibot"

BAD_WORDS = [
    "کیر", "بیناموس", "بیناموص", "مادرجنده", "حرومزاده",
    "خارکصدع", "خارکصده", "خارکسده", "خارکسدع",
    "گوه نخور", "گوه بخور", "گوه", "کونی", "کص", "پیوی",
    "کصننت", "کسننت", "کص بیبیت", "کس بیبیت",
    "کصبیبیت", "کسبیبیت", "کس بی بیت", "کص بی بیت",
    "کص بی بی", "کس بی بی", "کص بیبی", "کس بیبی",
    "کسبیبی", "کصبیبی", "کس ننت", "کص ننت",
    "کص ننه", "کس ننه", "کصننه", "کسننه",
    "کسکش", "کصکش", "پدرسگ", "پدرصگ", "پدر سگ",
    "پدر صگ", "مادرسگ", "مادرصگ", "مادر سگ",
    "مادر صگ", "مادرکونی", "مادر کونی",
    "ولد زنا", "زنا زاده", "عمه ننه"
]


# =========================================================
# ربات و دیتابیس
# =========================================================

bot = telebot.TeleBot(TOKEN)
db_lock = threading.RLock()

conn = sqlite3.connect(
    "casino_meowi.db",
    check_same_thread=False
)


# =========================================================
# ساخت جداول
# =========================================================

with db_lock:
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            name TEXT,
            username TEXT,
            role INTEGER DEFAULT 0,
            status TEXT DEFAULT 'normal',
            reason TEXT DEFAULT 'ندارد',
            warnings INTEGER DEFAULT 0,
            msg_count INTEGER DEFAULT 0,
            action_date TEXT DEFAULT '-'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            chat_id INTEGER PRIMARY KEY,
            lock_links INTEGER DEFAULT 0,
            lock_forwards INTEGER DEFAULT 0,
            lock_words INTEGER DEFAULT 0,
            lock_photo INTEGER DEFAULT 0,
            lock_voice INTEGER DEFAULT 0,
            lock_chat INTEGER DEFAULT 0,
            lock_video INTEGER DEFAULT 0,
            lock_doc INTEGER DEFAULT 0,
            lock_sticker INTEGER DEFAULT 0,
            lock_gif INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS group_stats (
            chat_id INTEGER PRIMARY KEY,
            total_msg INTEGER DEFAULT 0,
            total_photo INTEGER DEFAULT 0,
            total_video INTEGER DEFAULT 0,
            total_sticker INTEGER DEFAULT 0,
            total_gif INTEGER DEFAULT 0,
            total_voice INTEGER DEFAULT 0
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS auto_responses (
            word TEXT PRIMARY KEY,
            reply TEXT
        )
    """)

    conn.commit()


# =========================================================
# اضافه کردن ستون‌های قدیمی در صورت نیاز
# =========================================================

def add_column(table, column, col_type):
    with db_lock:
        try:
            conn.execute(
                f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"
            )
            conn.commit()
        except sqlite3.OperationalError:
            pass


add_column("users", "warnings", "INTEGER DEFAULT 0")
add_column("users", "msg_count", "INTEGER DEFAULT 0")
add_column("users", "action_date", "TEXT DEFAULT '-'")

add_column("settings", "lock_photo", "INTEGER DEFAULT 0")
add_column("settings", "lock_voice", "INTEGER DEFAULT 0")
add_column("settings", "lock_chat", "INTEGER DEFAULT 0")
add_column("settings", "lock_video", "INTEGER DEFAULT 0")
add_column("settings", "lock_doc", "INTEGER DEFAULT 0")
add_column("settings", "lock_sticker", "INTEGER DEFAULT 0")
add_column("settings", "lock_gif", "INTEGER DEFAULT 0")


# =========================================================
# ابزارهای دیتابیس
# =========================================================

def get_settings():
    with db_lock:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                lock_links,
                lock_forwards,
                lock_words,
                lock_photo,
                lock_voice,
                lock_chat,
                lock_video,
                lock_doc,
                lock_sticker,
                lock_gif
            FROM settings
            WHERE chat_id = ?
        """, (ALLOWED_GROUP,))

        result = cur.fetchone()

        if not result:
            cur.execute(
                "INSERT INTO settings (chat_id) VALUES (?)",
                (ALLOWED_GROUP,)
            )
            conn.commit()

            return (0, 0, 0, 0, 0, 0, 0, 0, 0, 0)

        return result


def update_setting(setting_name, value):
    allowed = {
        "lock_links",
        "lock_forwards",
        "lock_words",
        "lock_photo",
        "lock_voice",
        "lock_chat",
        "lock_video",
        "lock_doc",
        "lock_sticker",
        "lock_gif"
    }

    if setting_name not in allowed:
        return

    with db_lock:
        conn.execute(
            f"""
            UPDATE settings
            SET {setting_name} = ?
            WHERE chat_id = ?
            """,
            (value, ALLOWED_GROUP)
        )
        conn.commit()


def get_user(user_id):
    if user_id == MAIN_OWNER:
        return (
            user_id,
            "مالک اصلی",
            "",
            4,
            "normal",
            "ندارد",
            0,
            0,
            "-"
        )

    with db_lock:
        cur = conn.cursor()

        cur.execute("""
            SELECT
                user_id,
                name,
                username,
                role,
                status,
                reason,
                warnings,
                msg_count,
                action_date
            FROM users
            WHERE user_id = ?
        """, (user_id,))

        user = cur.fetchone()

        if user:
            return user

    return (
        user_id,
        "ناشناس",
        "",
        0,
        "normal",
        "ندارد",
        0,
        0,
        "-"
    )


def update_user(
    user_id,
    name,
    username,
    role=None,
    status=None,
    reason=None,
    warnings=None,
    add_msg=False,
    action_date=None
):
    with db_lock:
        cur = conn.cursor()

        cur.execute(
            "SELECT * FROM users WHERE user_id = ?",
            (user_id,)
        )

        old = cur.fetchone()

        if old is None:
            cur.execute("""
                INSERT INTO users
                (
                    user_id,
                    name,
                    username,
                    role,
                    status,
                    reason,
                    warnings,
                    msg_count,
                    action_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                user_id,
                name,
                username or "",
                role if role is not None else 0,
                status if status is not None else "normal",
                reason if reason is not None else "ندارد",
                warnings if warnings is not None else 0,
                1 if add_msg else 0,
                action_date if action_date is not None else "-"
            ))

        else:
            old_role = old[3] if len(old) > 3 else 0
            old_status = old[4] if len(old) > 4 else "normal"
            old_reason = old[5] if len(old) > 5 else "ندارد"
            old_warn = old[6] if len(old) > 6 else 0
            old_msg = old[7] if len(old) > 7 else 0
            old_date = old[8] if len(old) > 8 else "-"

            cur.execute("""
                UPDATE users
                SET
                    name = ?,
                    username = ?,
                    role = ?,
                    status = ?,
                    reason = ?,
                    warnings = ?,
                    msg_count = ?,
                    action_date = ?
                WHERE user_id = ?
            """, (
                name,
                username or "",
                role if role is not None else old_role,
                status if status is not None else old_status,
                reason if reason is not None else old_reason,
                warnings if warnings is not None else old_warn,
                old_msg + 1 if add_msg else old_msg,
                action_date if action_date is not None else old_date,
                user_id
            ))

        conn.commit()


def update_group_stats(content_type):
    col_map = {
        "text": "total_msg",
        "photo": "total_photo",
        "video": "total_video",
        "sticker": "total_sticker",
        "animation": "total_gif",
        "voice": "total_voice"
    }

    col = col_map.get(content_type, "total_msg")

    with db_lock:
        cur = conn.cursor()

        cur.execute(
            "SELECT chat_id FROM group_stats WHERE chat_id = ?",
            (ALLOWED_GROUP,)
        )

        if cur.fetchone() is None:
            cur.execute(
                "INSERT INTO group_stats (chat_id) VALUES (?)",
                (ALLOWED_GROUP,)
            )

        cur.execute(
            f"""
            UPDATE group_stats
            SET {col} = {col} + 1
            WHERE chat_id = ?
            """,
            (ALLOWED_GROUP,)
        )

        conn.commit()


# =========================================================
# اخطار
# =========================================================

def add_warning(chat_id, user_id, user_name, reason):
    user = get_user(user_id)

    current_warns = user[6] + 1
    safe_name = html.escape(user_name or "کاربر")

    current_time = time.strftime("%Y-%m-%d %H:%M:%S")

    if current_warns >= 6:
        try:
            bot.restrict_chat_member(
                chat_id,
                user_id,
                permissions=ChatPermissions(
                    can_send_messages=False
                )
            )
        except Exception:
            pass

        update_user(
            user_id,
            user[1],
            user[2],
            status="muted",
            reason="دریافت 6 اخطار متوالی",
            warnings=0,
            action_date=current_time
        )

        text = (
            f"🚨 کاربر "
            f"<a href='tg://user?id={user_id}'>{safe_name}</a> "
            f"به دلیل دریافت 6 اخطار متوالی "
            f"<b>سکوت دائم</b> شد!"
        )

    else:
        update_user(
            user_id,
            user[1],
            user[2],
            warnings=current_warns
        )

        text = (
            "⚠️ <b>اخطار جدید توسط "
            "Casino Meowi Cop 👮‍♂️!</b>\n\n"
            f"👤 <a href='tg://user?id={user_id}'>{safe_name}</a>\n"
            f"📝 <b>دلیل:</b> {html.escape(reason)}\n"
            f"⚠️ تعداد اخطار: [ {current_warns} / 6 ]"
        )

    try:
        bot.send_message(
            chat_id,
            text,
            parse_mode="HTML"
        )
    except Exception:
        pass


# =========================================================
# مانیتورینگ امنیتی
# =========================================================

user_spam_cache = {}


def security_listener(messages):
    settings = get_settings()

    for m in messages:
        try:
            if not m.chat:
                continue

            # فقط گروه اصلی
            if (
                m.chat.type in ["group", "supergroup"]
                and m.chat.id != ALLOWED_GROUP
            ):
                try:
                    bot.send_message(
                        m.chat.id,
                        "من Casino Meowi Cop 👮‍♂️ هستم و فقط در گپ کازینو میویی فعالیت میکنم!"
                    )
                except Exception:
                    pass

                try:
                    bot.leave_chat(m.chat.id)
                except Exception:
                    pass

                continue

            if m.chat.id != ALLOWED_GROUP:
                continue

            if not m.from_user:
                continue

            user_id = m.from_user.id

            user = get_user(user_id)
            role = user[3]

            update_user(
                user_id,
                m.from_user.first_name or "بدون نام",
                m.from_user.username or "",
                add_msg=True
            )

            update_group_stats(m.content_type)

            # مدیران از قفل‌ها مستثنی هستند
            if role >= 1:
                continue

            # قفل کل گپ
            if settings[5]:
                try:
                    bot.delete_message(
                        m.chat.id,
                        m.message_id
                    )
                except Exception:
                    pass
                continue

            msg_text = m.text or m.caption or ""

            # لینک
            if settings[0] and re.search(
                r"(https?://|t\.me/|www\.)",
                msg_text,
                re.IGNORECASE
            ):
                try:
                    bot.delete_message(
                        m.chat.id,
                        m.message_id
                    )
                except Exception:
                    pass

                add_warning(
                    m.chat.id,
                    user_id,
                    m.from_user.first_name,
                    "ارسال لینک"
                )
                continue

            # فوروارد
            if settings[1] and m.forward_date:
                try:
                    bot.delete_message(
                        m.chat.id,
                        m.message_id
                    )
                except Exception:
                    pass

                add_warning(
                    m.chat.id,
                    user_id,
                    m.from_user.first_name,
                    "ارسال فوروارد"
                )
                continue

            # الفاظ
            if settings[2] and any(
                bad_word in msg_text
                for bad_word in BAD_WORDS
            ):
                try:
                    bot.delete_message(
                        m.chat.id,
                        m.message_id
                    )
                except Exception:
                    pass

                add_warning(
                    m.chat.id,
                    user_id,
                    m.from_user.first_name,
                    "الفاظ نامناسب"
                )
                continue

            content_locks = {
                3: ("photo", "ارسال عکس"),
                4: ("voice", "ارسال ویس"),
                6: ("video", "ارسال فیلم"),
                7: ("document", "ارسال فایل"),
                8: ("sticker", "ارسال استیکر"),
                9: ("animation", "ارسال گیف")
            }

            locked = False

            for index, (content_type, reason) in content_locks.items():
                if settings[index] and m.content_type == content_type:
                    try:
                        bot.delete_message(
                            m.chat.id,
                            m.message_id
                        )
                    except Exception:
                        pass

                    add_warning(
                        m.chat.id,
                        user_id,
                        m.from_user.first_name,
                        reason
                    )

                    locked = True
                    break

            if locked:
                continue

            # ضد اسپم
            now = time.time()

            if user_id not in user_spam_cache:
                user_spam_cache[user_id] = []

            user_spam_cache[user_id].append(now)

            user_spam_cache[user_id] = [
                t for t in user_spam_cache[user_id]
                if now - t < 10
            ]

            if len(user_spam_cache[user_id]) >= 10:
                try:
                    bot.restrict_chat_member(
                        m.chat.id,
                        user_id,
                        until_date=int(now) + 600,
                        permissions=ChatPermissions(
                            can_send_messages=False
                        )
                    )

                    current_time = time.strftime(
                        "%Y-%m-%d %H:%M:%S"
                    )

                    update_user(
                        user_id,
                        m.from_user.first_name,
                        m.from_user.username or "",
                        status="muted",
                        reason="اسپم خودکار",
                        action_date=current_time
                    )

                    safe_name = html.escape(
                        m.from_user.first_name or "کاربر"
                    )

                    bot.reply_to(
                        m,
                        f"🚨 کاربر "
                        f"<a href='tg://user?id={user_id}'>{safe_name}</a> "
                        f"به دلیل اسپم 10 دقیقه سکوت شد.",
                        parse_mode="HTML"
                    )

                except Exception:
                    pass

                user_spam_cache[user_id] = []

        except Exception:
            continue


bot.set_update_listener(security_listener)


# =========================================================
# خوش‌آمدگویی و خروج
# =========================================================

@bot.chat_member_handler()
def chat_member_update(update):
    try:
        if update.chat.id != ALLOWED_GROUP:
            return

        user = update.new_chat_member.user

        if user.id == bot.get_me().id:
            return

        new_status = update.new_chat_member.status
        old_status = update.old_chat_member.status

        safe_name = html.escape(
            user.first_name or "کاربر"
        )

        # ورود
        if (
            new_status == "member"
            and old_status != "member"
        ):
            update_user(
                user.id,
                user.first_name or "کاربر",
                user.username or ""
            )

            caption = f"""
🐾 سلام <a href="tg://user?id={user.id}">{safe_name}</a> به گپ کازینو میویی خوش اومدی! 🎰

🤖 اول وارد ربات شو: {BOT_USERNAME}
💰 از افزایش موجودی سکه شارژ کن؛ هر 1K سکه = 1M میو
🎮 توی گپ «بازی» رو بفرست و بازی رو انتخاب کن.
💸 هر وقت بردی یا خواستی، میوت رو از بخش برداشت میو دریافت کن.
⛏️ از استخراج میو روزانه 500K میو بگیر؛ وقتی موجودیت به 1M رسید، می‌تونی برداشتش کنی.

📌 قوانین گپ پین شده؛ حتماً چک کن!
""".strip()

            try:
                bot.send_photo(
                    update.chat.id,
                    WELCOME_PHOTO_URL,
                    caption=caption,
                    parse_mode="HTML"
                )
            except Exception:
                bot.send_message(
                    update.chat.id,
                    caption,
                    parse_mode="HTML"
                )

        # خروج
        elif (
            new_status == "left"
            and old_status in [
                "member",
                "restricted",
                "administrator",
                "creator"
            ]
        ):
            try:
                bot.send_message(
                    update.chat.id,
                    f"سیکتیر {safe_name} 🤜🔪🎀",
                    parse_mode="HTML"
                )
            except Exception:
                pass

    except Exception:
        pass


# =========================================================
# حذف پیام‌های ورود و خروج تلگرام
# =========================================================

@bot.message_handler(
    content_types=[
        "new_chat_members",
        "left_chat_member"
    ]
)
def delete_service_messages(m):
    if m.chat.id == ALLOWED_GROUP:
        try:
            bot.delete_message(
                m.chat.id,
                m.message_id
            )
        except Exception:
            pass


# =========================================================
# پنل
# =========================================================

def generate_panel_markup():
    markup = InlineKeyboardMarkup(row_width=2)

    markup.add(
        InlineKeyboardButton(
            "⚙️ تنظیمات قفل‌ها",
            callback_data="panel_locks"
        ),
        InlineKeyboardButton(
            "👥 راهنما و دستورات",
            callback_data="panel_help"
        )
    )

    markup.add(
        InlineKeyboardButton(
            "❌ بستن پنل",
            callback_data="panel_close"
        )
    )

    return markup


def generate_locks_markup():
    settings = get_settings()

    markup = InlineKeyboardMarkup(row_width=2)

    def icon(value):
        return "🟢" if value else "🔴"

    markup.add(
        InlineKeyboardButton(
            f"🔗 لینک: {icon(settings[0])}",
            callback_data="toggle_links"
        ),
        InlineKeyboardButton(
            f"🔄 فوروارد: {icon(settings[1])}",
            callback_data="toggle_forwards"
        ),
        InlineKeyboardButton(
            f"🤬 فحش: {icon(settings[2])}",
            callback_data="toggle_words"
        ),
        InlineKeyboardButton(
            f"🖼 عکس: {icon(settings[3])}",
            callback_data="toggle_photo"
        ),
        InlineKeyboardButton(
            f"🎤 ویس: {icon(settings[4])}",
            callback_data="toggle_voice"
        ),
        InlineKeyboardButton(
            f"🎥 فیلم: {icon(settings[6])}",
            callback_data="toggle_video"
        ),
        InlineKeyboardButton(
            f"📄 فایل: {icon(settings[7])}",
            callback_data="toggle_doc"
        ),
        InlineKeyboardButton(
            f"🎭 استیکر: {icon(settings[8])}",
            callback_data="toggle_sticker"
        ),
        InlineKeyboardButton(
            f"🎞 گیف: {icon(settings[9])}",
            callback_data="toggle_gif"
        ),
        InlineKeyboardButton(
            f"🔒 کل گپ: {icon(settings[5])}",
            callback_data="toggle_chat"
        )
    )

    markup.add(
        InlineKeyboardButton(
            "🔙 بازگشت",
            callback_data="panel_main"
        )
    )

    return markup


# =========================================================
# پنل مدیریت
# =========================================================

@bot.message_handler(
    commands=["panel"],
    func=lambda m: m.chat.id == ALLOWED_GROUP
)
@bot.message_handler(
    func=lambda m: (
        m.text == "پنل"
        and m.chat.id == ALLOWED_GROUP
    )
)
def send_panel(m):
    if get_user(m.from_user.id)[3] < 2:
        return bot.reply_to(
            m,
            "❌ این بخش فقط برای مدیران است."
        )

    try:
        bot.delete_message(
            m.chat.id,
            m.message_id
        )
    except Exception:
        pass

    bot.send_message(
        m.chat.id,
        "💠 <b>پنل مدیریت پیشرفته Casino Meowi Cop 👮‍♂️</b>\n\n"
        "لطفاً یک بخش را انتخاب کنید:",
        reply_markup=generate_panel_markup(),
        parse_mode="HTML"
    )


# =========================================================
# ID
# =========================================================

@bot.message_handler(
    commands=["id"],
    func=lambda m: m.chat.id == ALLOWED_GROUP
)
def check_id(m):
    if m.reply_to_message:
        target_id = m.reply_to_message.from_user.id
    else:
        parts = m.text.split()

        if (
            len(parts) > 1
            and parts[1].lstrip("-").isdigit()
        ):
            target_id = int(parts[1])
        else:
            target_id = m.from_user.id

    user = get_user(target_id)

    roles = {
        0: "کاربر عادی",
        1: "ویژه 🌟",
        2: "ادمین 👮‍♂️",
        3: "مالک 👑",
        4: "مالک اصلی 💎"
    }

    text = f"""
👤 <b>اطلاعات کاربر در Casino Meowi Cop 👮‍♂️:</b>

- <b>نام:</b> {html.escape(user[1])}
- <b>آیدی عددی:</b> <code>{user[0]}</code>
- <b>مقام:</b> {roles.get(user[3], "نامشخص")}
- <b>وضعیت:</b> {html.escape(user[4])}
- <b>تعداد اخطار:</b> {user[6]} / 6
- <b>تعداد پیام:</b> {user[7]}
""".strip()

    if user[4] != "normal":
        text += (
            f"\n- <b>دلیل محرومیت:</b> "
            f"{html.escape(user[5])}"
            f"\n- <b>زمان:</b> "
            f"<code>{html.escape(user[8])}</code>"
        )

    bot.reply_to(
        m,
        text,
        parse_mode="HTML"
    )


# =========================================================
# کال‌بک پنل
# =========================================================

@bot.callback_query_handler(func=lambda call: True)
def panel_callback(call):
    try:
        if get_user(call.from_user.id)[3] < 2:
            return bot.answer_callback_query(
                call.id,
                "شما ادمین نیستید!",
                show_alert=True
            )

        data = call.data
        settings = get_settings()

        if data == "panel_main":
            bot.edit_message_text(
                "💠 <b>پنل مدیریت پیشرفته Casino Meowi Cop 👮‍♂️</b>\n\n"
                "لطفاً یک بخش را انتخاب کنید:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=generate_panel_markup(),
                parse_mode="HTML"
            )

        elif data == "panel_locks":
            bot.edit_message_text(
                "⚙️ <b>تنظیمات قفل‌های گروه:</b>\n\n"
                "<i>با کلیک روی هر دکمه، وضعیت آن تغییر می‌کند.</i>",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=generate_locks_markup(),
                parse_mode="HTML"
            )

        elif data.startswith("toggle_"):
            settings_map = {
                "toggle_links": ("lock_links", 0),
                "toggle_forwards": ("lock_forwards", 1),
                "toggle_words": ("lock_words", 2),
                "toggle_photo": ("lock_photo", 3),
                "toggle_voice": ("lock_voice", 4),
                "toggle_chat": ("lock_chat", 5),
                "toggle_video": ("lock_video", 6),
                "toggle_doc": ("lock_doc", 7),
                "toggle_sticker": ("lock_sticker", 8),
                "toggle_gif": ("lock_gif", 9)
            }

            if data in settings_map:
                setting, index = settings_map[data]

                new_value = (
                    0
                    if settings[index]
                    else 1
                )

                update_setting(
                    setting,
                    new_value
                )

            bot.edit_message_reply_markup(
                call.message.chat.id,
                call.message.message_id,
                reply_markup=generate_locks_markup()
            )

            bot.answer_callback_query(
                call.id,
                "✅ بروزرسانی شد."
            )

        elif data == "panel_help":
            text = """
<b>راهنمای Casino Meowi Cop 👮‍♂️</b>

▫️ ریپلای + <code>حذف</code> / <code>پین</code> / <code>حذف پین</code>
▫️ ریپلای + <code>بن دلیل [متن]</code>
▫️ ریپلای + <code>سکوت دلیل [متن]</code>
▫️ ریپلای + <code>سکوت [تایم] دلیل [متن]</code>
▫️ ریپلای + <code>اخطار دلیل [متن]</code>
▫️ ریپلای + <code>حذف اخطار [تعداد]</code>
▫️ ریپلای + <code>حذف بن / حذف سکوت</code>
▫️ دستور <code>تگ</code>
▫️ ریپلای + <code>ربات بگو [متن]</code>
▫️ <code>تنظیم پاسخ [کلمه] = [جواب]</code>
▫️ <code>آمار</code>
▫️ <code>لیست بن</code>
▫️ <code>لیست سکوت</code>
▫️ <code>لیست اخطار</code>
▫️ <code>لیست مدیران</code>
▫️ ریپلای + <code>تنظیم ادمین</code>
▫️ ریپلای + <code>تنظیم ویژه</code>
▫️ دستور <code>/id</code>
""".strip()

            markup = InlineKeyboardMarkup()
            markup.add(
                InlineKeyboardButton(
                    "🔙 بازگشت",
                    callback_data="panel_main"
                )
            )

            bot.edit_message_text(
                text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup,
                parse_mode="HTML"
            )

        elif data == "panel_close":
            bot.delete_message(
                call.message.chat.id,
                call.message.message_id
            )

        elif data == "tag_admins":
            with db_lock:
                cur = conn.cursor()
                cur.execute("""
                    SELECT user_id, name
                    FROM users
                    WHERE role >= 2
                """)
                admins = cur.fetchall()

            if not admins:
                return bot.answer_callback_query(
                    call.id,
                    "ادمین ثبت شده‌ای یافت نشد."
                )

            text = (
                "👮‍♂️ <b>ادمین‌های عزیز:</b>\n"
                + " ".join(
                    f'<a href="tg://user?id={u[0]}">▪️</a>'
                    for u in admins
                )
            )

            bot.send_message(
                call.message.chat.id,
                text,
                parse_mode="HTML"
            )

            bot.delete_message(
                call.message.chat.id,
                call.message.message_id
            )

        elif data == "tag_members":
            bot.answer_callback_query(
                call.id,
                "در حال تگ کردن ۳۰۰ نفر فعال..."
            )

            with db_lock:
                cur = conn.cursor()

                cur.execute("""
                    SELECT user_id
                    FROM users
                    WHERE role < 2
                    ORDER BY msg_count DESC
                    LIMIT 300
                """)

                members = cur.fetchall()

            if not members:
                return bot.send_message(
                    call.message.chat.id,
                    "کاربری یافت نشد."
                )

            bot.delete_message(
                call.message.chat.id,
                call.message.message_id
            )

            chunk_size = 70

            for i in range(
                0,
                len(members),
                chunk_size
            ):
                chunk = members[
                    i:i + chunk_size
                ]

                text = (
                    "📣 <b>کاربران فعال گروه:</b>\n"
                    + " ".join(
                        f'<a href="tg://user?id={u[0]}">▪️</a>'
                        for u in chunk
                    )
                )

                bot.send_message(
                    call.message.chat.id,
                    text,
                    parse_mode="HTML"
                )

                time.sleep(1)

    except Exception:
        try:
            bot.answer_callback_query(
                call.id,
                "❌ خطایی رخ داد."
            )
        except Exception:
            pass


# =========================================================
# دستورات متنی
# =========================================================

@bot.message_handler(
    func=lambda m: (
        m.chat.id == ALLOWED_GROUP
        and bool(m.text)
    )
)
def text_commands(m):
    sender_role = get_user(
        m.from_user.id
    )[3]

    text = m.text.strip()

    # سلام
    if text in [
        "سلام",
        "سلامت",
        "صلام",
        "سیلام",
        "salam",
        "slm"
    ]:
        return bot.reply_to(
            m,
            "سلام عزیزم! خوش اومدی 🐾"
        )

    # خداحافظی
    if text in [
        "خداحافظ",
        "خدافظ",
        "بای",
        "bye"
    ]:
        return bot.reply_to(
            m,
            "به سلامت، زود برگردیا! 🐾"
        )

    # =====================================================
    # دستورات مدیر
    # =====================================================

    if sender_role >= 2:

        # تگ
        if text == "تگ":
            markup = InlineKeyboardMarkup()

            markup.add(
                InlineKeyboardButton(
                    "عضوها 👥",
                    callback_data="tag_members"
                ),
                InlineKeyboardButton(
                    "ادمین‌ها 👮‍♂️",
                    callback_data="tag_admins"
                )
            )

            return bot.reply_to(
                m,
                "چه کسانی رو میخوای تگ کنی؟",
                reply_markup=markup
            )

        # آمار
        elif text == "آمار":
            with db_lock:
                cur = conn.cursor()

                cur.execute("""
                    SELECT name, msg_count
                    FROM users
                    WHERE msg_count > 0
                    ORDER BY msg_count DESC
                    LIMIT 10
                """)

                top_users = cur.fetchall()

                cur.execute("""
                    SELECT *
                    FROM group_stats
                    WHERE chat_id = ?
                """, (ALLOWED_GROUP,))

                g_stats = cur.fetchone()

            if not g_stats:
                g_stats = (
                    ALLOWED_GROUP,
                    0,
                    0,
                    0,
                    0,
                    0,
                    0
                )

            msg = (
                "📊 <b>آمار گپ کازینو میویی "
                "توسط Casino Meowi Cop 👮‍♂️</b>\n\n"
            )

            msg += (
                f"✉️ کل پیام‌ها: <b>{g_stats[1]}</b>\n"
                f"🖼 عکس‌ها: <b>{g_stats[2]}</b>\n"
                f"🎥 ویدیوها: <b>{g_stats[3]}</b>\n"
                f"🎤 ویس‌ها: <b>{g_stats[6]}</b>\n"
                f"🎭 استیکرها: <b>{g_stats[4]}</b>\n"
                f"🎞 گیف‌ها: <b>{g_stats[5]}</b>\n\n"
                "🏆 <b>۱۰ نفر پرحرف گپ:</b>\n"
            )

            if top_users:
                for idx, (name, count) in enumerate(
                    top_users,
                    start=1
                ):
                    msg += (
                        f"{idx}. "
                        f"{html.escape(name or 'بدون نام')} "
                        f"- <code>{count}</code> پیام\n"
                    )
            else:
                msg += "هنوز پیامی ثبت نشده است."

            return bot.reply_to(
                m,
                msg,
                parse_mode="HTML"
            )

        # لیست بن
        elif text == "لیست بن":
            with db_lock:
                cur = conn.cursor()

                cur.execute("""
                    SELECT name, reason
                    FROM users
                    WHERE status = 'banned'
                    LIMIT 30
                """)

                banned = cur.fetchall()

            if not banned:
                return bot.reply_to(
                    m,
                    "🚫 کسی در لیست بن نیست."
                )

            msg = (
                "🚫 <b>لیست بن شده‌ها:</b>\n\n"
                + "\n".join(
                    f"👤 {html.escape(n or 'بدون نام')} "
                    f"(دلیل: {html.escape(r or 'ندارد')})"
                    for n, r in banned
                )
            )

            return bot.reply_to(
                m,
                msg,
                parse_mode="HTML"
            )

        # لیست سکوت
        elif text == "لیست سکوت":
            with db_lock:
                cur = conn.cursor()

                cur.execute("""
                    SELECT name, reason
                    FROM users
                    WHERE status LIKE 'muted%'
                    LIMIT 30
                """)

                muted = cur.fetchall()

            if not muted:
                return bot.reply_to(
                    m,
                    "🔇 کسی در لیست سکوت نیست."
                )

            msg = (
                "🔇 <b>لیست سکوت شده‌ها:</b>\n\n"
                + "\n".join(
                    f"👤 {html.escape(n or 'بدون نام')} "
                    f"(دلیل: {html.escape(r or 'ندارد')})"
                    for n, r in muted
                )
            )

            return bot.reply_to(
                m,
                msg,
                parse_mode="HTML"
            )

        # لیست اخطار
        elif text == "لیست اخطار":
            with db_lock:
                cur = conn.cursor()

                cur.execute("""
                    SELECT name, warnings
                    FROM users
                    WHERE warnings > 0
                    LIMIT 30
                """)

                warned = cur.fetchall()

            if not warned:
                return bot.reply_to(
                    m,
                    "⚠️ کسی اخطار ندارد."
                )

            msg = (
                "⚠️ <b>لیست اخطاری‌ها:</b>\n\n"
                + "\n".join(
                    f"👤 {html.escape(n or 'بدون نام')} "
                    f"- {w} اخطار"
                    for n, w in warned
                )
            )

            return bot.reply_to(
                m,
                msg,
                parse_mode="HTML"
            )

        # لیست مدیران
        elif text == "لیست مدیران":
            with db_lock:
                cur = conn.cursor()

                cur.execute("""
                    SELECT name, role
                    FROM users
                    WHERE role >= 2
                """)

                admins = cur.fetchall()

            roles_name = {
                2: "ادمین 👮‍♂️",
                3: "مالک 👑",
                4: "مالک اصلی 💎"
            }

            msg = (
                "📋 <b>لیست مدیران گروه:</b>\n\n"
                + "\n".join(
                    f"👤 {html.escape(n or 'بدون نام')} "
                    f"- {roles_name.get(r, '')}"
                    for n, r in admins
                )
            )

            return bot.reply_to(
                m,
                msg,
                parse_mode="HTML"
            )

        # پاسخ خودکار
        match_response = re.match(
            r"^تنظیم پاسخ\s+(.+?)\s*=\s*(.+)$",
            text
        )

        if match_response:
            word = match_response.group(1).strip()
            reply = match_response.group(2).strip()

            with db_lock:
                conn.execute(
                    """
                    REPLACE INTO auto_responses
                    (word, reply)
                    VALUES (?, ?)
                    """,
                    (word, reply)
                )

                conn.commit()

            return bot.reply_to(
                m,
                f"✅ پاسخ خودکار برای کلمه «{html.escape(word)}» تنظیم شد."
            )

    # =====================================================
    # پاسخ خودکار
    # =====================================================

    if not m.reply_to_message:
        with db_lock:
            cur = conn.cursor()

            cur.execute(
                """
                SELECT reply
                FROM auto_responses
                WHERE word = ?
                """,
                (text,)
            )

            result = cur.fetchone()

        if result:
            return bot.reply_to(
                m,
                result[0]
            )

        return

    # =====================================================
    # دستورات ریپلای
    # =====================================================

    target_user = m.reply_to_message.from_user

    if not target_user:
        return

    target_id = target_user.id

    target_data = get_user(target_id)
    target_role = target_data[3]

    safe_target_name = html.escape(
        target_user.first_name or "کاربر"
    )

    update_user(
        target_id,
        target_user.first_name or "کاربر",
        target_user.username or ""
    )

    if sender_role < 2:
        return

    # ربات بگو
    if text.startswith("ربات بگو "):
        reply_text = text.replace(
            "ربات بگو ",
            "",
            1
        ).strip()

        try:
            bot.delete_message(
                m.chat.id,
                m.message_id
            )
        except Exception:
            pass

        return bot.reply_to(
            m.reply_to_message,
            reply_text
        )

    # حذف
    if text == "حذف":
        try:
            bot.delete_message(
                m.chat.id,
                m.reply_to_message.message_id
            )
        except Exception:
            pass

        try:
            bot.delete_message(
                m.chat.id,
                m.message_id
            )
        except Exception:
            pass

        return

    # پین
    if text == "پین":
        return bot.pin_chat_message(
            m.chat.id,
            m.reply_to_message.message_id
        )

    # حذف پین
    if text == "حذف پین":
        return bot.unpin_chat_message(
            m.chat.id,
            m.reply_to_message.message_id
        )

    # حذف بن
    if text == "حذف بن":
        try:
            bot.unban_chat_member(
                m.chat.id,
                target_id
            )
        except Exception:
            pass

        update_user(
            target_id,
            target_user.first_name or "کاربر",
            target_user.username or "",
            status="normal",
            reason="ندارد",
            action_date="-"
        )

        return bot.reply_to(
            m,
            f"✅ بن کاربر "
            f"<a href='tg://user?id={target_id}'>{safe_target_name}</a> "
            f"برداشته شد.",
            parse_mode="HTML"
        )

    # حذف سکوت
    if text == "حذف سکوت":
        try:
            bot.restrict_chat_member(
                m.chat.id,
                target_id,
                permissions=ChatPermissions(
                    can_send_messages=True,
                    can_send_audios=True,
                    can_send_documents=True,
                    can_send_photos=True,
                    can_send_videos=True,
                    can_send_other_messages=True,
                    can_add_web_page_previews=True
                )
            )
        except Exception:
            pass

        update_user(
            target_id,
            target_user.first_name or "کاربر",
            target_user.username or "",
            status="normal",
            reason="ندارد",
            action_date="-"
        )

        return bot.reply_to(
            m,
            f"✅ سکوت کاربر "
            f"<a href='tg://user?id={target_id}'>{safe_target_name}</a> "
            f"شکسته شد.",
            parse_mode="HTML"
        )

    # حذف اخطار
    match_rem_warn = re.match(
        r"^حذف اخطار\s*(\d+)?$",
        text
    )

    if match_rem_warn:
        amount = (
            int(match_rem_warn.group(1))
            if match_rem_warn.group(1)
            else 1
        )

        current_warnings = target_data[6]
        new_warnings = max(
            0,
            current_warnings - amount
        )

        update_user(
            target_id,
            target_user.first_name or "کاربر",
            target_user.username or "",
            warnings=new_warnings
        )

        return bot.reply_to(
            m,
            f"✅ تعداد {amount} اخطار از "
            f"<a href='tg://user?id={target_id}'>{safe_target_name}</a> "
            f"کم شد.\n"
            f"⚠️ اخطار فعلی: {new_warnings}/6",
            parse_mode="HTML"
        )

    # تنظیم مقام
    roles_map = {
        "تنظیم ادمین": (2, "ادمین"),
        "تنظیم ویژه": (1, "ویژه 🌟")
    }

    if text in roles_map:
        new_role, role_name = roles_map[text]

        if (
            sender_role >= 3
            and sender_role > target_role
        ):
            update_user(
                target_id,
                target_user.first_name or "کاربر",
                target_user.username or "",
                role=new_role
            )

            return bot.reply_to(
                m,
                f"✅ کاربر "
                f"<a href='tg://user?id={target_id}'>{safe_target_name}</a> "
                f"به <b>{role_name}</b> ارتقا یافت.",
                parse_mode="HTML"
            )

        return bot.reply_to(
            m,
            "❌ دسترسی کافی ندارید."
        )

    # اخطار
    match_warn = re.match(
        r"^اخطار\s+دلیل\s+(.+)$",
        text
    )

    if match_warn:
        if (
            target_role >= sender_role
            or target_role >= 1
        ):
            return bot.reply_to(
                m,
                "❌ غیرمجاز!"
            )

        reason = match_warn.group(1).strip()

        add_warning(
            m.chat.id,
            target_id,
            target_user.first_name or "کاربر",
            reason
        )

        return

    # بن / سکوت دائم
    match_perm = re.match(
        r"^(بن|سکوت)\s+دلیل\s+(.+)$",
        text
    )

    if match_perm:
        if (
            target_role >= sender_role
            or target_role >= 1
        ):
            return bot.reply_to(
                m,
                "❌ غیرمجاز!"
            )

        action = match_perm.group(1)
        reason = match_perm.group(2).strip()

        current_time = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        if action == "بن":
            try:
                bot.ban_chat_member(
                    m.chat.id,
                    target_id
                )
            except Exception:
                return bot.reply_to(
                    m,
                    "❌ عملیات بن انجام نشد."
                )

            update_user(
                target_id,
                target_user.first_name or "کاربر",
                target_user.username or "",
                status="banned",
                reason=reason,
                action_date=current_time
            )

            return bot.reply_to(
                m,
                f"🚫 کاربر بن شد.\n"
                f"📝 دلیل: {html.escape(reason)}",
                parse_mode="HTML"
            )

        if action == "سکوت":
            try:
                bot.restrict_chat_member(
                    m.chat.id,
                    target_id,
                    permissions=ChatPermissions(
                        can_send_messages=False
                    )
                )
            except Exception:
                return bot.reply_to(
                    m,
                    "❌ عملیات سکوت انجام نشد."
                )

            update_user(
                target_id,
                target_user.first_name or "کاربر",
                target_user.username or "",
                status="muted",
                reason=reason,
                action_date=current_time
            )

            return bot.reply_to(
                m,
                f"🔇 کاربر سکوت دائم شد.\n"
                f"📝 دلیل: {html.escape(reason)}",
                parse_mode="HTML"
            )

    # سکوت موقت
    mute_match = re.match(
        r"^سکوت\s+(\d+)(s|m|h|d|mo)\s+دلیل\s+(.+)$",
        text
    )

    if mute_match:
        if (
            target_role >= sender_role
            or target_role >= 1
        ):
            return bot.reply_to(
                m,
                "❌ غیرمجاز!"
            )

        amount = int(
            mute_match.group(1)
        )

        unit = mute_match.group(2)

        reason = mute_match.group(3).strip()

        multipliers = {
            "s": 1,
            "m": 60,
            "h": 3600,
            "d": 86400,
            "mo": 2592000
        }

        unit_names = {
            "s": "ثانیه",
            "m": "دقیقه",
            "h": "ساعت",
            "d": "روز",
            "mo": "ماه"
        }

        until = (
            int(time.time())
            + amount * multipliers[unit]
        )

        current_time = time.strftime(
            "%Y-%m-%d %H:%M:%S"
        )

        try:
            bot.restrict_chat_member(
                m.chat.id,
                target_id,
                until_date=until,
                permissions=ChatPermissions(
                    can_send_messages=False
                )
            )
        except Exception:
            return bot.reply_to(
                m,
                "❌ عملیات سکوت انجام نشد."
            )

        update_user(
            target_id,
            target_user.first_name or "کاربر",
            target_user.username or "",
            status="muted_temp",
            reason=reason,
            action_date=current_time
        )

        return bot.reply_to(
            m,
            f"⏱ کاربر به مدت "
            f"<b>{amount} {unit_names[unit]}</b> سکوت شد.\n"
            f"📝 دلیل: {html.escape(reason)}",
            parse_mode="HTML"
        )


# =========================================================
# اجرای ربات
# =========================================================

print(
    "Casino Meowi Cop Bot started successfully! 👮‍♂️"
)

while True:
    try:
        bot.infinity_polling(
            allowed_updates=[
                "message",
                "callback_query",
                "chat_member"
            ],
            skip_pending=True
        )
    except Exception as e:
        print(
            f"Polling error: {e}"
        )
        time.sleep(5)
