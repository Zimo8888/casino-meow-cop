import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton, ChatPermissions
import sqlite3
import time
import re
import html
import threading
import os
import atexit

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

# ================= دیتابیس (بهبود یافته برای Railway) =================
# برای Railway، دیتابیس باید در دایرکتوری persist شود
DB_PATH = os.getenv('DB_PATH', '/data/casino_meowi.db')
DB_DIR = os.path.dirname(DB_PATH)

# اطمینان از وجود دایرکتوری
os.makedirs(DB_DIR, exist_ok=True)

# اتصال به دیتابیس با تنظیمات بهتر
conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=10)
conn.isolation_level = None  # فعال کردن autocommit برای بهتر بودن
cursor = conn.cursor()

# فعال کردن WAL mode برای بهتری concurrent access
try:
    conn.execute('PRAGMA journal_mode=WAL')
except:
    pass

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

# Commit تغییرات
try:
    conn.commit()
except:
    pass

# تابع بسته شدن صحیح دیتابیس هنگام خروج
def close_db():
    global conn
    try:
        if conn:
            conn.commit()
            conn.close()
            print("✅ Database connection closed safely.")
    except:
        pass

atexit.register(close_db)

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
                # ثبت پیام
                if m.content_type in ['text', 'photo', 'video', 'sticker', 'animation', 'voice']:
                    update_user(m.from_user.id, m.from_user.first_name, m.from_user.username, add_msg=True)
                    update_group_stats(m.content_type)

                # کنترل لینک
                if settings[0] == 1 and m.text and 'http' in m.text.lower():
                    try: bot.delete_message(m.chat.id, m.message_id)
                    except: pass
                    continue

                # کنترل فوروارد
                if settings[1] == 1 and m.forward_from:
                    try: bot.delete_message(m.chat.id, m.message_id)
                    except: pass
                    continue

                # کنترل کلمات بد
                if settings[2] == 1 and m.text:
                    text_lower = m.text.lower()
                    if any(word in text_lower for word in BAD_WORDS):
                        try: bot.delete_message(m.chat.id, m.message_id)
                        except: pass
                        continue

                # کنترل عکس
                if settings[3] == 1 and m.content_type == 'photo':
                    try: bot.delete_message(m.chat.id, m.message_id)
                    except: pass
                    continue

                # کنترل ویس
                if settings[4] == 1 and m.content_type == 'voice':
                    try: bot.delete_message(m.chat.id, m.message_id)
                    except: pass
                    continue

                # کنترل چت
                if settings[5] == 1 and m.content_type in ['photo', 'video', 'sticker', 'voice']:
                    try: bot.delete_message(m.chat.id, m.message_id)
                    except: pass
                    continue
        except:
            pass

bot.set_update_listener(security_listener)

# ================= دستور شروع =================
@bot.message_handler(commands=['start'])
def start_handler(m):
    sender_role = get_user(m.from_user.id)[3]
    if m.chat.type in ['group', 'supergroup']:
        if m.chat.id == ALLOWED_GROUP and sender_role >= 1:
            markup = InlineKeyboardMarkup()
            markup.add(InlineKeyboardButton("📊 پنل کنترل", callback_data="panel_main"))
            bot.send_photo(m.chat.id, WELCOME_PHOTO_URL, 
                         caption="🎰 خوش آمدید به Casino Meowi Cop 👮‍♂️\n\nمن یک ربات نگهبان هستم که برای حفاظت از گپ کازینو میویی طراحی شدم. من میتوانم با ابزارهای قدرتمند مدیریتی کمک کنم.",
                         reply_markup=markup)
    else:
        update_user(m.from_user.id, m.from_user.first_name, m.from_user.username)
        bot.send_message(m.chat.id, "👋 سلام! من فقط در گروه‌ها فعالیت میکنم.")

# ================= شناسایی کاربر =================
@bot.message_handler(commands=['id'])
def id_handler(m):
    target = m.reply_to_message.from_user if m.reply_to_message else m.from_user
    user_data = get_user(target.id)
    update_user(target.id, target.first_name, target.username)
    
    role_name = ["👤 کاربر عادی", "🛡 نگهبان", "👮 ادمین", "⭐ مدیرکل", "👑 مالک"][user_data[3]]
    msg = f"""
<b>👤 اطلاعات کاربر:</b>
🆔 ID: <code>{target.id}</code>
📛 نام: <a href='tg://user?id={target.id}'>{html.escape(target.first_name)}</a>
🔐 نقش: {role_name}
⚠️ اخطار: {user_data[6]}
💬 پیام: {user_data[7]}
🕐 آخرین عمل: {user_data[8]}
"""
    bot.reply_to(m, msg, parse_mode="HTML")

# ================= پنل کنترل =================
@bot.callback_query_handler(func=lambda call: call.data.startswith("panel_"))
def panel_handler(call):
    sender_role = get_user(call.from_user.id)[3]
    if sender_role < 1:
        return bot.answer_callback_query(call.id, "❌ شما دسترسی ندارید.", show_alert=True)
    
    data = call.data
    if data == "panel_main":
        if sender_role >= 1:
            markup = InlineKeyboardMarkup()
            if sender_role >= 2: markup.add(InlineKeyboardButton("⚙️ تنظیمات", callback_data="panel_settings"))
            markup.add(InlineKeyboardButton("📋 راهنما", callback_data="panel_help"))
            markup.add(InlineKeyboardButton("❌ بستن", callback_data="panel_close"))
            bot.edit_message_text("🎰 <b>پنل مدیریت Casino Meowi Cop</b>\n\nبرای مدیریت بهتر گروه، گزینه‌های زیر را انتخاب کنید.",
                                call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    
    elif data == "panel_settings":
        if sender_role >= 2:
            settings = get_settings()
            markup = InlineKeyboardMarkup()
            lock_links_btn = "🔒 لینک فعال" if settings[0] else "🔓 لینک غیرفعال"
            lock_forwards_btn = "🔒 فوروارد فعال" if settings[1] else "🔓 فوروارد غیرفعال"
            lock_words_btn = "🔒 کلمات بد فعال" if settings[2] else "🔓 کلمات بد غیرفعال"
            lock_photo_btn = "🔒 عکس فعال" if settings[3] else "🔓 عکس غیرفعال"
            lock_voice_btn = "🔒 ویس فعال" if settings[4] else "🔓 ویس غیرفعال"
            
            markup.add(InlineKeyboardButton(lock_links_btn, callback_data="toggle_links"))
            markup.add(InlineKeyboardButton(lock_forwards_btn, callback_data="toggle_forwards"))
            markup.add(InlineKeyboardButton(lock_words_btn, callback_data="toggle_words"))
            markup.add(InlineKeyboardButton(lock_photo_btn, callback_data="toggle_photo"))
            markup.add(InlineKeyboardButton(lock_voice_btn, callback_data="toggle_voice"))
            markup.add(InlineKeyboardButton("🔙 بازگشت", callback_data="panel_main"))
            bot.edit_message_text("⚙️ <b>تنظیمات:</b>", call.message.chat.id, call.message.message_id, reply_markup=markup, parse_mode="HTML")
    
    elif data.startswith("toggle_"):
        if sender_role >= 2:
            setting = data.replace("toggle_", "")
            setting_map = {"links": "lock_links", "forwards": "lock_forwards", "words": "lock_words", "photo": "lock_photo", "voice": "lock_voice"}
            settings = get_settings()
            setting_index = {"lock_links": 0, "lock_forwards": 1, "lock_words": 2, "lock_photo": 3, "lock_voice": 4}[setting_map[setting]]
            new_value = 1 - settings[setting_index]
            update_setting(setting_map[setting], new_value)
            bot.answer_callback_query(call.id, "✅ تغییر اعمال شد.", show_alert=False)
            panel_handler(telebot.types.CallbackQuery(
                id=call.id, from_user=call.from_user, chat_instance=call.chat_instance,
                message=call.message, data="panel_settings"
            ))
    
    elif data == "panel_help":
        text = """<b>📖 راهنمای استفاده:</b>

<b>دستورات عمومی:</b>
▫️ <code>/id</code>: مشاهده اطلاعات کاربر
▫️ ریپلای + <code>/id</code>: مشاهده اطلاعات کاربر هدف

<b>دستورات ادمین:</b>
▫️ ریپلای + <code>بن دلیل [متن]</code>: بن
▫️ ریپلای + <code>سکوت دلیل [متن]</code>: سکوت دائم
▫️ ریپلای + <code>اخطار دلیل [متن]</code>: اخطار دادن
▫️ ریپلای + <code>سکوت [تایم] دلیل [متن]</code>: سکوت موقت (s,m,h,d,mo)
▫️ ریپلای + <code>حذف بن / حذف سکوت / حذف اخطار</code>: لغو
▫️ <code>آمار</code>: مشاهده آمار گپ و 10 نفر پرحرف
▫️ <code>لیست بن / لیست سکوت / لیست اخطار</code>: لیست‌ها
▫️ ریپلای + <code>تنظیم ادمین</code>: مقام‌دهی
▫️ ریپلای + <code>/id</code>: وضعیت کاربر"""
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
