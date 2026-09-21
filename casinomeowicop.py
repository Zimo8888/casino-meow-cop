import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
import sqlite3
import time
import re
import html
import threading
import os

# ================= تنظیمات اصلی =================
TOKEN = os.getenv('BOT_TOKEN')
if not TOKEN:
    raise RuntimeError('BOT_TOKEN environment variable is not set.')
ALLOWED_GROUP = -1004410278746
MAIN_OWNER = 7105951313
WELCOME_PHOTO_URL = 'https://i.postimg.cc/bsFhLBzs/image.jpg' 

BAD_WORDS = [
    'بیناموس', 'بیناموص', 'مادرجنده', 'حرومزاده', 'خارکصدع', 'خارکصده',
    'خارکسده', 'خارکسدع', 'گوه نخور', 'گوه بخور', 'گوه', 'کونی', 'کص', 'کس',
    'کصننت', 'کسننت', 'کص بیبیت', 'کس بیبیت', 'کصبیبیت', 'کسبیبیت',
    'کس بی بیت', 'کص بی بیت', 'کص بی بی', 'کس بی بی', 'کص بیبی', 'کس بیبی',
    'کسبیبی', 'کصبیبی', 'کس ننت', 'کص ننت', 'کص ننه', 'کس ننه', 'کصننه',
    'کسننه', 'کسکش', 'کصکش', 'پدرسگ', 'پدرصگ', 'پدر سگ', 'پدر صگ',
    'مادرسگ', 'مادرصگ', 'مادر سگ', 'مادر صگ', 'مادرکونی', 'مادر کونی',
    'ولد زنا', 'زنا زاده', 'عمه ننه'
]

bot = telebot.TeleBot(TOKEN)
db_lock = threading.RLock() 

# ================= دیتابیس (ارتقا یافته) =================
DB_PATH = os.getenv('DB_PATH', '/data/casino_meowi.db')
os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
conn = sqlite3.connect(DB_PATH, check_same_thread=False)
cursor = conn.cursor()

cursor.execute('''CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY, name TEXT, username TEXT,
                    role INTEGER, status TEXT, reason TEXT
                )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS settings (
                    chat_id INTEGER PRIMARY KEY, lock_links INTEGER DEFAULT 0,
                    lock_forwards INTEGER DEFAULT 0, lock_words INTEGER DEFAULT 0
                )''')
cursor.execute('''CREATE TABLE IF NOT EXISTS group_stats (
                    chat_id INTEGER PRIMARY KEY, total_msg INTEGER DEFAULT 0,
                    total_photo INTEGER DEFAULT 0, total_video INTEGER DEFAULT 0,
                    total_sticker INTEGER DEFAULT 0, total_gif INTEGER DEFAULT 0,
                    total_voice INTEGER DEFAULT 0
                )''')

def add_column(table, column, col_type):
    try: cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}")
    except sqlite3.OperationalError: pass

add_column('users', 'warnings', 'INTEGER DEFAULT 0')
add_column('users', 'msg_count', 'INTEGER DEFAULT 0')
add_column('users', 'action_date', "TEXT DEFAULT '-'") # زمان دقیق محدودیت
add_column('settings', 'lock_photo', 'INTEGER DEFAULT 0')
add_column('settings', 'lock_voice', 'INTEGER DEFAULT 0')
add_column('settings', 'lock_chat', 'INTEGER DEFAULT 0')
conn.commit()

def get_settings():
    with db_lock:
        cur = conn.cursor()
        cur.execute("SELECT lock_links, lock_forwards, lock_words, lock_photo, lock_voice, lock_chat FROM settings WHERE chat_id = ?", (ALLOWED_GROUP,))
        res = cur.fetchone()
        if not res:
            cur.execute("INSERT INTO settings (chat_id) VALUES (?)", (ALLOWED_GROUP,))
            conn.commit()
            return (0, 0, 0, 0, 0, 0)
        return res

def update_setting(setting_name, value):
    with db_lock:
        cur = conn.cursor()
        cur.execute(f"UPDATE settings SET {setting_name} = ? WHERE chat_id = ?", (value, ALLOWED_GROUP))
        conn.commit()

def get_user(user_id):
    if user_id == MAIN_OWNER:
        return (user_id, "مالک اصلی", "", 4, "normal", "ندارد", 0, 0, "-")
    with db_lock:
        cur = conn.cursor()
        cur.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        user = cur.fetchone()
        if user:
            u_role = user[3]
            u_status = user[4]
            u_reason = user[5]
            u_warns = user[6] if len(user) > 6 else 0
            u_msg = user[7] if len(user) > 7 else 0
            u_date = user[8] if len(user) > 8 else '-'
            return (user[0], user[1], user[2], u_role, u_status, u_reason, u_warns, u_msg, u_date)
        return (user_id, "ناشناس", "", 0, "normal", "ندارد", 0, 0, "-")

def update_user(user_id, name, username, role=None, status=None, reason=None, warnings=None, add_msg=False, action_date=None):
    with db_lock:
        cur = conn.cursor()
        user = get_user(user_id)
        if user[1] == "ناشناس":
            cur.execute("INSERT INTO users (user_id, name, username, role, status, reason, warnings, msg_count, action_date) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (user_id, name, username, role or 0, status or 'normal', reason or 'ندارد', warnings or 0, 1 if add_msg else 0, action_date or '-'))
        else:
            new_role = role if role is not None else user[3]
            new_status = status if status is not None else user[4]
            new_reason = reason if reason is not None else user[5]
            new_warns = warnings if warnings is not None else user[6]
            new_msg = (user[7] + 1) if add_msg else user[7]
            new_date = action_date if action_date is not None else user[8]
            cur.execute("UPDATE users SET name=?, username=?, role=?, status=?, reason=?, warnings=?, msg_count=?, action_date=? WHERE user_id=?",
                        (name, username, new_role, new_status, new_reason, new_warns, new_msg, new_date, user_id))
        conn.commit()

def update_group_stats(content_type):
    with db_lock:
        cur = conn.cursor()
        cur.execute("SELECT * FROM group_stats WHERE chat_id = ?", (ALLOWED_GROUP,))
        if not cur.fetchone():
            cur.execute("INSERT INTO group_stats (chat_id) VALUES (?)", (ALLOWED_GROUP,))
        col_map = {'text': 'total_msg', 'photo': 'total_photo', 'video': 'total_video', 
                   'sticker': 'total_sticker', 'animation': 'total_gif', 'voice': 'total_voice'}
        col = col_map.get(content_type, 'total_msg')
        cur.execute(f"UPDATE group_stats SET {col} = {col} + 1 WHERE chat_id = ?", (ALLOWED_GROUP,))
        conn.commit()

def add_warning(chat_id, user_id, user_name, reason):
    user = get_user(user_id)
    current_warns = user[6] + 1
    safe_name = html.escape(user_name)
    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
    
    if current_warns >= 6:
        bot.restrict_chat_member(chat_id, user_id, permissions=ChatPermissions(can_send_messages=False))
        update_user(user_id, user[1], user[2], status='muted', reason='دریافت 6 اخطار متوالی', warnings=0, action_date=current_time)
        text = f"🚨 کاربر <a href='tg://user?id={user_id}'>{safe_name}</a> به دلیل دریافت 6 اخطار متوالی <b>سکوت دائم</b> شد!"
    else:
        update_user(user_id, user[1], user[2], warnings=current_warns)
        text = f"⚠️ <b>اخطار جدید توسط Casino Meowi Cop 👮‍♂️!</b>\nکاربر <a href='tg://user?id={user_id}'>{safe_name}</a>\n📝 <b>دلیل:</b> {reason}\nتعداد اخطار: [ {current_warns} / 6 ]"
    bot.send_message(chat_id, text, parse_mode="HTML")

# ================= مانیتورینگ =================
user_spam_cache = {}
def security_listener(messages):
    settings = get_settings() 
    for m in messages:
        try:
            if m.chat.type in ['group', 'supergroup'] and m.chat.id != ALLOWED_GROUP:
                try: bot.send_message(m.chat.id, "من Casino Meowi Cop 👮‍♂️ هستم و فقط در گپ کازینو میویی فعالیت میکنم!")
                except: pass
                try: bot.leave_chat(m.chat.id)
                except: pass
                continue

            if m.chat.id == ALLOWED_GROUP:
                user_id = m.from_user.id
                user = get_user(user_id)
                role = user[3]
                
                update_user(user_id, m.from_user.first_name, m.from_user.username, add_msg=True)
                update_group_stats(m.content_type)
                
                if role >= 1: continue 

                if settings[5]:
                    bot.delete_message(m.chat.id, m.message_id)
                    continue

                msg_text = m.text or m.caption or ""
                
                if settings[1] and m.forward_date:
                    bot.delete_message(m.chat.id, m.message_id)
                    add_warning(m.chat.id, user_id, m.from_user.first_name, "ارسال فوروارد")
                    continue
                if settings[0] and re.search(r"(https?://|t\.me/|www\.)", msg_text, re.I):
                    bot.delete_message(m.chat.id, m.message_id)
                    add_warning(m.chat.id, user_id, m.from_user.first_name, "ارسال لینک")
                    continue
                if settings[2] and any(bad in msg_text for bad in BAD_WORDS):
                    bot.delete_message(m.chat.id, m.message_id)
                    add_warning(m.chat.id, user_id, m.from_user.first_name, "الفاظ نامناسب")
                    continue
                if settings[3] and m.content_type == 'photo':
                    bot.delete_message(m.chat.id, m.message_id)
                    add_warning(m.chat.id, user_id, m.from_user.first_name, "ارسال عکس")
                    continue
                if settings[4] and m.content_type == 'voice':
                    bot.delete_message(m.chat.id, m.message_id)
                    add_warning(m.chat.id, user_id, m.from_user.first_name, "ارسال ویس")
                    continue

                now = time.time()
                if user_id not in user_spam_cache: user_spam_cache[user_id] = []
                user_spam_cache[user_id].append(now)
                user_spam_cache[user_id] = [t for t in user_spam_cache[user_id] if now - t < 10]
                
                if len(user_spam_cache[user_id]) >= 10:
                    bot.restrict_chat_member(m.chat.id, user_id, until_date=int(now) + 600)
                    current_time = time.strftime('%Y-%m-%d %H:%M:%S')
                    update_user(user_id, m.from_user.first_name, m.from_user.username, status='muted', reason='اسپم خودکار', action_date=current_time)
                    safe_name = html.escape(m.from_user.first_name)
                    bot.reply_to(m, f"🚨 کاربر <a href='tg://user?id={user_id}'>{safe_name}</a> به دلیل اسپم 10 دقیقه سکوت شد.", parse_mode="HTML")
                    user_spam_cache[user_id] = []
        except Exception: pass

bot.set_update_listener(security_listener)

@bot.message_handler(content_types=['new_chat_members'])
def welcome_message(m):
    if m.chat.id != ALLOWED_GROUP: return
    for new_member in m.new_chat_members:
        if new_member.id == bot.get_me().id: continue
        update_user(new_member.id, new_member.first_name, new_member.username)
        safe_name = html.escape(new_member.first_name)
        caption = f"""🐾 سلام <a href="tg://user?id={new_member.id}">{safe_name}</a> به گپ کازینو میویی خوش اومدی! 🎰

🤖 اول وارد ربات شو: @casinomeowibot
💰 از افزایش موجودی سکه شارژ کن؛ هر 1K سکه = 1M میو
🎮 توی گپ «بازی» رو بفرست و بازی رو انتخاب کن.
💸 هر وقت بردی یا خواستی، میوت رو از بخش برداشت میو دریافت کن.
⛏️ از استخراج میو روزانه 500K میو بگیر؛ وقتی موجودیت به 1M رسید، می‌تونی برداشتش کنی.

📌 قوانین گپ پین شده؛ حتماً چک کن!"""
        bot.send_photo(m.chat.id, WELCOME_PHOTO_URL, caption=caption, parse_mode="HTML")

@bot.message_handler(content_types=['left_chat_member'])
def goodbye_message(m):
    if m.chat.id != ALLOWED_GROUP: return
    if m.left_chat_member.id == bot.get_me().id: return
    safe_name = html.escape(m.left_chat_member.first_name)
    bot.send_message(m.chat.id, f"سیکتیر {safe_name} 🤜🔪🎀", parse_mode="HTML")

# ================= پنل، آیدی و منوها =================
def generate_panel_markup():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("⚙️ تنظیمات قفل‌ها", callback_data="panel_locks"),
        InlineKeyboardButton("👥 راهنما و دستورات", callback_data="panel_help")
    )
    markup.add(InlineKeyboardButton("❌ بستن پنل", callback_data="panel_close"))
    return markup

def generate_locks_markup():
    settings = get_settings()
    markup = InlineKeyboardMarkup(row_width=2)
    s = lambda x: "🟢" if x else "🔴"
    markup.add(
        InlineKeyboardButton(f"🔗 لینک: {s(settings[0])}", callback_data="toggle_links"),
        InlineKeyboardButton(f"🔄 فوروارد: {s(settings[1])}", callback_data="toggle_forwards"),
        InlineKeyboardButton(f"🤬 فحش: {s(settings[2])}", callback_data="toggle_words"),
        InlineKeyboardButton(f"🖼 عکس: {s(settings[3])}", callback_data="toggle_photo"),
        InlineKeyboardButton(f"🎤 ویس: {s(settings[4])}", callback_data="toggle_voice"),
        InlineKeyboardButton(f"🔒 کل گپ: {s(settings[5])}", callback_data="toggle_chat")
    )
    markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="panel_main"))
    return markup

@bot.message_handler(commands=['panel'], func=lambda m: m.chat.id == ALLOWED_GROUP)
@bot.message_handler(func=lambda m: m.text == "پنل" and m.chat.id == ALLOWED_GROUP)
def send_panel(m):
    if get_user(m.from_user.id)[3] < 2: return bot.reply_to(m, "❌ این بخش فقط برای مدیران است.")
    bot.reply_to(m, "💠 <b>پنل مدیریت پیشرفته Casino Meowi Cop 👮‍♂️</b>\n\nلطفاً یک بخش را انتخاب کنید:", reply_markup=generate_panel_markup(), parse_mode="HTML")

@bot.message_handler(commands=['id'], func=lambda m: m.chat.id == ALLOWED_GROUP)
def check_id(m):
    target_id = None
    if m.reply_to_message: target_id = m.reply_to_message.from_user.id
    else:
        parts = m.text.split()
        if len(parts) > 1 and parts[1].lstrip('-').isdigit(): target_id = int(parts[1])
        else: target_id = m.from_user.id
            
    user = get_user(target_id)
    roles = {0: "کاربر عادی", 1: "ویژه 🌟", 2: "ادمین 👮‍♂️", 3: "مالک 👑", 4: "مالک اصلی 💎"}
    
    text = f"""👤 <b>اطلاعات کاربر در Casino Meowi Cop 👮‍♂️:</b>
- <b>نام:</b> {html.escape(user[1])}
- <b>آیدی عددی:</b> <code>{user[0]}</code>
- <b>مقام:</b> {roles.get(user[3], "نامشخص")}
- <b>وضعیت:</b> {user[4]}
- <b>تعداد اخطار:</b> {user[6]} / 6
- <b>تعداد پیام:</b> {user[7]}"""

    if user[4] != 'normal':
        text += f"\n- <b>دلیل محرومیت:</b> {html.escape(user[5])}\n- <b>زمان ثبت محرومیت:</b> <code>{user[8]}</code>"
        
    bot.reply_to(m, text, parse_mode="HTML")

@bot.callback_query_handler(func=lambda call: True)
def panel_callback(call):
    if get_user(call.from_user.id)[3] < 2:
        return bot.answer_callback_query(call.id, "شما ادمین نیستید!", show_alert=True)
    data = call.data
    settings = get_settings()
    
    if data == "panel_main":
        bot.edit_message_text("💠 <b>پنل مدیریت پیشرفته Casino Meowi Cop 👮‍♂️</b>\n\nلطفاً یک بخش را انتخاب کنید:", 
                              call.message.chat.id, call.message.message_id, reply_markup=generate_panel_markup(), parse_mode="HTML")
    elif data == "panel_locks":
        bot.edit_message_text("⚙️ <b>تنظیمات قفل‌های گروه:</b>\n<i>با کلیک روی هر دکمه، وضعیت آن تغییر میکند.</i>", 
                              call.message.chat.id, call.message.message_id, reply_markup=generate_locks_markup(), parse_mode="HTML")
    elif data.startswith("toggle_"):
        if data == "toggle_links": update_setting('lock_links', 0 if settings[0] else 1)
        elif data == "toggle_forwards": update_setting('lock_forwards', 0 if settings[1] else 1)
        elif data == "toggle_words": update_setting('lock_words', 0 if settings[2] else 1)
        elif data == "toggle_photo": update_setting('lock_photo', 0 if settings[3] else 1)
        elif data == "toggle_voice": update_setting('lock_voice', 0 if settings[4] else 1)
        elif data == "toggle_chat": update_setting('lock_chat', 0 if settings[5] else 1)
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=generate_locks_markup())
        bot.answer_callback_query(call.id, "✅ تنظیمات با موفقیت بروزرسانی شد.")
    elif data == "panel_help":
        text = """<b>راهنمای Casino Meowi Cop 👮‍♂️</b>
▫️ ریپلای + <code>حذف</code> / <code>پین</code>: پیام
▫️ ریپلای + <code>بن دلیل [متن]</code>: اخراج کاربر
▫️ ریپلای + <code>سکوت دلیل [متن]</code>: سکوت دائم
▫️ ریپلای + <code>اخطار دلیل [متن]</code>: اخطار دادن
▫️ ریپلای + <code>سکوت [تایم] دلیل [متن]</code>: سکوت موقت (s,m,h,d,mo)
▫️ ریپلای + <code>حذف بن / حذف سکوت / حذف اخطار</code>: لغو
▫️ <code>آمار</code>: مشاهده آمار گپ و 10 نفر پرحرف
▫️ <code>لیست بن / لیست سکوت / لیست اخطار</code>: لیست‌ها
▫️ ریپلای + <code>تنظیم ادمین</code>: مقام‌دهی
▫️ دستور <code>/id</code> (یا ریپلای + <code>/id</code>): وضعیت کاربر"""
        markup = InlineKeyboardMarkup().add(InlineKeyboardButton("🔙 بازگشت", callback_data="panel_main"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    elif data == "panel_close":
        bot.delete_message(call.message.chat.id, call.message.message_id)

# ================= سایر دستورات متنی (حذف، پین، بن، سکوت...) =================
@bot.message_handler(func=lambda m: m.chat.id == ALLOWED_GROUP and m.text)
def text_commands(m):
    sender_role = get_user(m.from_user.id)[3]
    text = m.text.strip()

    if sender_role >= 2:
        if text == "آمار":
            with db_lock:
                cur = conn.cursor()
                cur.execute("SELECT name, msg_count FROM users WHERE msg_count > 0 ORDER BY msg_count DESC LIMIT 10")
                top_users = cur.fetchall()
                cur.execute("SELECT * FROM group_stats WHERE chat_id = ?", (ALLOWED_GROUP,))
                g_stats = cur.fetchone() or (0,0,0,0,0,0,0)
                
            msg = "📊 <b>آمار گپ کازینو میویی توسط Casino Meowi Cop 👮‍♂️</b>\n\n"
            msg += f"✉️ کل پیام‌ها: <b>{g_stats[1]}</b>\n"
            msg += f"🖼 عکس‌ها: <b>{g_stats[2]}</b>\n"
            msg += f"🎥 ویدیوها: <b>{g_stats[3]}</b>\n"
            msg += f"🎤 ویس‌ها: <b>{g_stats[6]}</b>\n"
            msg += f"🎭 استیکرها: <b>{g_stats[4]}</b>\n"
            msg += f"🎞 گیف‌ها: <b>{g_stats[5]}</b>\n\n"
            msg += "🏆 <b>۱۰ نفر پرحرف گپ:</b>\n"
            for idx, (n, c) in enumerate(top_users): msg += f"{idx+1}. {html.escape(n)} - <code>{c}</code> پیام\n"
            return bot.reply_to(m, msg, parse_mode="HTML")
            
        elif text == "لیست بن":
            with db_lock:
                cur = conn.cursor()
                cur.execute("SELECT name, reason FROM users WHERE status = 'banned' LIMIT 30")
                banned = cur.fetchall()
            if not banned: return bot.reply_to(m, "🚫 کسی در لیست بن نیست.")
            msg = "🚫 <b>لیست بن شده‌ها:</b>\n\n" + "\n".join([f"👤 {html.escape(n)} (دلیل: {r})" for n, r in banned])
            return bot.reply_to(m, msg, parse_mode="HTML")
            
        elif text == "لیست سکوت":
            with db_lock:
                cur = conn.cursor()
                cur.execute("SELECT name, reason FROM users WHERE status LIKE 'muted%' LIMIT 30")
                muted = cur.fetchall()
            if not muted: return bot.reply_to(m, "🔇 کسی در لیست سکوت نیست.")
            msg = "🔇 <b>لیست سکوت شده‌ها:</b>\n\n" + "\n".join([f"👤 {html.escape(n)} (دلیل: {r})" for n, r in muted])
            return bot.reply_to(m, msg, parse_mode="HTML")

        elif text == "لیست اخطار":
            with db_lock:
                cur = conn.cursor()
                cur.execute("SELECT name, warnings FROM users WHERE warnings > 0 LIMIT 30")
                warned = cur.fetchall()
            if not warned: return bot.reply_to(m, "⚠️ کسی اخطار ندارد.")
            msg = "⚠️ <b>لیست اخطاری‌ها:</b>\n\n" + "\n".join([f"👤 {html.escape(n)} - {w} اخطار" for n, w in warned])
            return bot.reply_to(m, msg, parse_mode="HTML")

    if not m.reply_to_message: return
    
    target_user = m.reply_to_message.from_user
    target_id = target_user.id
    target_role = get_user(target_id)[3]
    safe_target_name = html.escape(target_user.first_name)
    update_user(target_id, target_user.first_name, target_user.username)

    if sender_role < 2: return # از اینجا به بعد فقط ادمین

    # دستورات پیام (حذف و پین)
    if text == "حذف":
        bot.delete_message(m.chat.id, m.reply_to_message.message_id)
        try: bot.delete_message(m.chat.id, m.message_id)
        except: pass
        return
    elif text == "پین":
        bot.pin_chat_message(m.chat.id, m.reply_to_message.message_id)
        return

    # دستورات لغو محرومیت
    if text == "حذف بن":
        bot.unban_chat_member(m.chat.id, target_id)
        update_user(target_id, target_user.first_name, target_user.username, status='normal', reason='ندارد', action_date='-')
        return bot.reply_to(m, f"✅ بن کاربر <a href='tg://user?id={target_id}'>{safe_target_name}</a> توسط Casino Meowi Cop 👮‍♂️ برداشته شد.", parse_mode="HTML")
        
    elif text == "حذف سکوت":
        bot.restrict_chat_member(m.chat.id, target_id, permissions=ChatPermissions(can_send_messages=True, can_send_audios=True, can_send_documents=True, can_send_photos=True, can_send_videos=True, can_send_other_messages=True, can_add_web_page_previews=True))
        update_user(target_id, target_user.first_name, target_user.username, status='normal', reason='ندارد', action_date='-')
        return bot.reply_to(m, f"✅ سکوت کاربر <a href='tg://user?id={target_id}'>{safe_target_name}</a> شکسته شد.", parse_mode="HTML")

    elif text == "حذف اخطار":
        update_user(target_id, target_user.first_name, target_user.username, warnings=0)
        return bot.reply_to(m, f"✅ تمام اخطارهای <a href='tg://user?id={target_id}'>{safe_target_name}</a> پاک شد.", parse_mode="HTML")

    if text == "تنظیم ادمین":
        if sender_role >= 3:
            update_user(target_id, target_user.first_name, target_user.username, role=2)
            bot.reply_to(m, f"✅ کاربر <a href='tg://user?id={target_id}'>{safe_target_name}</a> به <b>ادمین</b> ارتقا یافت.", parse_mode="HTML")
        else:
            bot.reply_to(m, "❌ دسترسی کافی ندارید (فقط مالک).")
        return

    # دستور اخطار با دلیل
    match_warn = re.match(r"^اخطار\s+دلیل\s+(.+)$", text)
    if match_warn:
        if target_role >= sender_role or target_role >= 1: return bot.reply_to(m, "❌ محدود کردن این کاربر مجاز نیست.")
        reason = match_warn.group(1).strip()
        add_warning(m.chat.id, target_id, target_user.first_name, reason)
        return

    # بن و سکوت دائم با دلیل
    match_perm = re.match(r"^(بن|سکوت)\s+دلیل\s+(.+)$", text)
    if match_perm:
        if target_role >= sender_role or target_role >= 1: return bot.reply_to(m, "❌ محدود کردن این کاربر مجاز نیست.")
        action, reason = match_perm.group(1), match_perm.group(2).strip()
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')

        if action == "بن":
            bot.ban_chat_member(m.chat.id, target_id)
            update_user(target_id, target_user.first_name, target_user.username, status='banned', reason=reason, action_date=current_time)
            bot.reply_to(m, f"🚫 کاربر بن شد.\n📝 دلیل: {html.escape(reason)}")
        elif action == "سکوت":
            bot.restrict_chat_member(m.chat.id, target_id, permissions=ChatPermissions(can_send_messages=False))
            update_user(target_id, target_user.first_name, target_user.username, status='muted', reason=reason, action_date=current_time)
            bot.reply_to(m, f"🔇 کاربر سکوت دائم شد.\n📝 دلیل: {html.escape(reason)}")
        return

    # سکوت تایمی با فرمت کامل (s, m, h, d, mo)
    mute_time_match = re.match(r"^سکوت\s+(\d+)(s|m|h|d|mo)\s+دلیل\s+(.+)$", text)
    if mute_time_match:
        if target_role >= sender_role or target_role >= 1: return bot.reply_to(m, "❌ محدود کردن کاربر مجاز نیست.")
        
        amount = int(mute_time_match.group(1))
        unit = mute_time_match.group(2)
        reason = mute_time_match.group(3).strip()
        
        multipliers = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400, 'mo': 2592000}
        seconds = amount * multipliers[unit]
        until = int(time.time()) + seconds
        current_time = time.strftime('%Y-%m-%d %H:%M:%S')
        
        bot.restrict_chat_member(m.chat.id, target_id, until_date=until)
        update_user(target_id, target_user.first_name, target_user.username, status='muted_temp', reason=reason, action_date=current_time)
        
        unit_names = {'s': 'ثانیه', 'm': 'دقیقه', 'h': 'ساعت', 'd': 'روز', 'mo': 'ماه'}
        bot.reply_to(m, f"⏱ کاربر به مدت <b>{amount} {unit_names[unit]}</b> توسط Casino Meowi Cop 👮‍♂️ سکوت شد.\n📝 دلیل: {html.escape(reason)}", parse_mode="HTML")
        return

print("Casino Meowi Cop Bot is fully armed and operational! 👮‍♂️")
bot.infinity_polling()
