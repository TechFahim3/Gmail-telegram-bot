from flask import Flask
from threading import Thread
app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running!"

def run():
    app.run(host='0.0.0.0', port=10000)

t = Thread(target=run)
t.start()

import os
import logging
import sqlite3
import random
import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler, 
    MessageHandler, filters, ContextTypes, ConversationHandler
)

# লগিং কনফিগারেশন
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- ⚙️ কনফিগারেশন প্যানেল ---
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))  
CHANNEL_USERNAME = "@MHF_Earn_Money"  
CHANNEL_LINK = "https://t.me/MHF_Earn_Money"

# --- 💰 বিজনেস পলিসি ---
GMAIL_PRICE = 25
REFER_COMMISSION = 2
MIN_WITHDRAW = 100  # 🎯 উইথড্র লিমিট 100 টাকা করা হয়েছে

# ==================== 🗄️ SQLITE SYSTEM ====================
def init_db():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    # last_seen কলামটি ইউজার অনলাইন/অফলাইন ট্র্যাকিংয়ের জন্য যুক্ত করা হয়েছে
    cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                      (user_id INTEGER PRIMARY KEY, balance INTEGER, referred_by INTEGER, 
                       ref_count INTEGER, username TEXT, name TEXT, banned INTEGER, last_seen TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS files 
                      (id INTEGER PRIMARY KEY AUTOINCREMENT, user_id INTEGER, file_id TEXT, file_name TEXT)''')
    conn.commit()
    conn.close()

init_db()

def get_user(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT balance, referred_by, ref_count, username, name, banned, last_seen FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        return {
            'balance': row[0], 'referred_by': row[1], 'ref_count': row[2], 
            'username': row[3], 'name': row[4], 'banned': bool(row[5]), 'last_seen': row[6]
        }
    return None

def add_user(user_id, referred_by, username, name):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, 0, ?, 0, ?, ?, 0, ?)", (user_id, referred_by, username, name, now))
    conn.commit()
    conn.close()

def update_balance(user_id, amount):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (amount, user_id))
    conn.commit()
    conn.close()

def update_ref_count(user_id):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET ref_count = ref_count + 1 WHERE user_id = ?", (user_id,))
    conn.commit()
    conn.close()

def set_ban_status(user_id, status):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET banned = ? WHERE user_id = ?", (1 if status else 0, user_id))
    conn.commit()
    conn.close()

def update_last_seen(user_id):
    """ইউজারের অনলাইন/অফলাইন ট্র্যাক করার জন্য সময় আপডেট করার ফাংশন"""
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("UPDATE users SET last_seen = ? WHERE user_id = ?", (now, user_id))
    conn.commit()
    conn.close()

def save_file(user_id, file_id, file_name):
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO files (user_id, file_id, file_name) VALUES (?, ?, ?)", (user_id, file_id, file_name))
    conn.commit()
    conn.close()

def get_all_files():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id, file_id, file_name FROM files")
    rows = cursor.fetchall()
    conn.close()
    return rows

def get_stats():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM files")
    total_files = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users WHERE banned = 1")
    total_banned = cursor.fetchone()[0]
    conn.close()
    return total_users, total_files, total_banned

def get_all_user_ids():
    conn = sqlite3.connect("bot_database.db")
    cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    rows = cursor.fetchall()
    conn.close()
    return [r[0] for r in rows]

# ===================================================================

# কনভারসেশন স্টেটস
(SUBMIT_FILE, ADMIN_ADD_BAL, ADMIN_REM_BAL, ADMIN_BAN, 
 ADMIN_UNBAN, ADMIN_BROADCAST, ADMIN_CHECK_USER, 
 WITHDRAW_METHOD, WITHDRAW_AMOUNT, WITHDRAW_NUMBER) = range(10)

# সাবস্ক্রিপশন চেক
async def check_user_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> str:
    user_id = update.effective_user.id
    u = get_user(user_id)
    if u and u['banned']:
        return "banned"
    try:
        member = await context.bot.get_chat_member(chat_id=CHANNEL_USERNAME, user_id=user_id)
        if member.status in ['member', 'administrator', 'creator']:
            return "ok"
    except Exception:
        pass
    return "no_sub"

# /start কমান্ড
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    u = get_user(user.id)
    
    if u and u['banned']:
        await update.message.reply_text("🚫 <b>অ্যাক্সেস ডিনাইড!</b> আপনাকে এই বট থেকে আজীবনের জন্য ব্যান করা হয়েছে।", parse_mode="HTML")
        return ConversationHandler.END

    if not u:
        ref_id = context.args[0] if context.args else None
        ref_id_int = int(ref_id) if (ref_id and ref_id.isdigit() and int(ref_id) != user.id) else None
        
        add_user(user.id, ref_id_int, user.username or "No_Username", user.first_name)
        if ref_id_int and get_user(ref_id_int):
            update_ref_count(ref_id_int)
    else:
        update_last_seen(user.id)

    status = await check_user_status(update, context)
    if status == "no_sub":
        keyboard = [
            [InlineKeyboardButton("📢 অফিশিয়াল চ্যানেলে জয়েন করুন", url=CHANNEL_LINK)],
            [InlineKeyboardButton("✅ জয়েন ভেরিফাই করুন (Check)", callback_data="check_sub")]
        ]
        await update.message.reply_text(
            "👋 <b>MHF Earn Money বটে আপনাকে স্বাগতম!</b>\n\nবটের সার্ভিসগুলো সচল করতে দয়া করে নিচের চ্যানেলটিতে জয়েন করে ভেরিফাই করুন।",
            reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML"
        )
        return ConversationHandler.END

    await show_main_menu(update)
    return ConversationHandler.END

# প্রফেশনাল মেইন মেনু
async def show_main_menu(update: Update):
    keyboard = [
        [InlineKeyboardButton("💰 Gmail Sell", callback_data="sell_gmail"), InlineKeyboardButton("👤 Account", callback_data="account")],
        [InlineKeyboardButton("🏧 Withdraw", callback_data="withdraw"), InlineKeyboardButton("👥 Refer Program", callback_data="refer")],
        [InlineKeyboardButton("📞 Live Support", callback_data="support"), InlineKeyboardButton("ℹ️ Information", callback_data="info")]
    ]
    text = "🎯 <b>MHF Earn Money — Official Automated Engine</b>\n\n" \
           "নিচের ড্যাশবোর্ড থেকে আপনার কাঙ্ক্ষিত বাটনটি সিলেক্ট করে কাজ শুরু করুন। আমরা ১০০% বিশ্বস্ততার সাথে সার্ভিস প্রদান করছি।"
    
    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        except:
            await update.callback_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    elif update.message:
        await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")

# ইউজার ইন্টারফেস বাটন একশন
async def button_click(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    
    update_last_seen(user_id) # ইউজারের লাস্ট সিন আপডেট
    
    status = await check_user_status(update, context)
    if status == "banned":
        await query.edit_message_text("❌ আপনাকে এই বট থেকে ব্যান করা হয়েছে!")
        return ConversationHandler.END

    if query.data == "check_sub":
        if status == "ok":
            await query.message.delete()
            await show_main_menu(update)
        else:
            await query.edit_message_text("⚠️ <b>আপনি এখনো চ্যানেলে জয়েন করেননি!</b> নিচে দেওয়া লিংকে জয়েন করে আবার ট্রাই করুন।", reply_markup=query.message.reply_markup, parse_mode="HTML")
            
    elif query.data == "account":
        u = get_user(user_id)
        text = f"🛡️ <b>Secure Account Dashboard:</b>\n\n" \
               f"👤 নাম: <b>{u['name']}</b>\n" \
               f"🆔 ইউজার আইডি: <code>{user_id}</code>\n" \
               f"💵 বর্তমান মেইন ব্যালেন্স: <code>{u['balance']} TK</code>\n" \
               f"👥 একটিভ রেফারেল নেটওয়ার্ক: <b>{u['ref_count']} জন</b>\n\n" \
               f"🔒 <i>আপনার অ্যাকাউন্টটি সম্পূর্ণ নিরাপদ।</i>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ব্যাক টু মেনু", callback_data="back_main")]]), parse_mode="HTML")

    elif query.data == "refer":
        bot_info = await context.bot.get_me()
        ref_link = f"https://t.me/{bot_info.username}?start={user_id}"
        text = f"👥 <b>স্মার্ট মাল্টি-লেভেল রেফারেল প্রোগ্রাম:</b>\n\n" \
               f"আপনার বন্ধুদের আমন্ত্রণ জানিয়ে আজীবন ইনকাম করার সুবর্ণ সুযোগ!\n\n" \
               f"🔥 <b>রেফারেল অফার:</b> আপনার লিংকে জয়েন করা মেম্বার এডমিনের কাছে যত পিস জিমেইল সফলভাবে সেল করবে, প্রতি জিমেইলের জন্য আপনি সাথে সাথে <b>{REFER_COMMISSION} টাকা</b> করে আজীবন রেফার কমিশন পেতে থাকবেন।\n\n" \
               f"🔗 <b>আপনার ইউনিক রেফারেল লিংক:</b>\n<code>{ref_link}</code>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ব্যাক টু মেনু", callback_data="back_main")]]), parse_mode="HTML")

    elif query.data == "support":
        text = "📞 <b>24/7 Corporate Support Desktop:</b>\n\n" \
               "পেমেন্ট হোল্ড, বাল্ক জিমেইল ডিল বা যেকোনো যান্ত্রিক ত্রুটি সমাধানের জন্য সরাসরি আমাদের অফিসিয়াল প্রধান এডমিনের সাথে যোগাযোগ করুন।\n\n" \
               "👉 <b>এডমিন আইডি:</b> @Gmail_Buyer_MHF\n📢 <b>টেলিগ্রাম চ্যানেল:</b> @MHF_Earn_Money"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ব্যাক টু মেনু", callback_data="back_main")]]), parse_mode="HTML")

    elif query.data == "info":
        text = f"ℹ️ <b>MHF System Information:</b>\n\n" \
               f"🔹 প্রতি সঠিক জিমেইলের দাম: <b>{GMAIL_PRICE} TK</b>\n" \
               f"🔹 লাইফটাইম রেফার কমিশন: <b>{REFER_COMMISSION} TK/Gmail</b>\n" \
               f"🔹 সর্বনিম্ন উইথড্র অ্যামাউন্ট: <b>{MIN_WITHDRAW} TK</b>\n" \
               f"🔹 গ্রহণযোগ্য ফরম্যাট: <b>.xlsx / Excel File (Email:Password)</b>\n" \
               f"⚡ <i>পেমেন্ট প্রসেসিং টাইম ১ থেকে সর্বোচ্চ ২৪ ঘণ্টা।</i>"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ব্যাক টু মেনু", callback_data="back_main")]]), parse_mode="HTML")

    elif query.data == "back_main":
        await show_main_menu(update)

    elif query.data == "sell_gmail":
        if status == "no_sub":
            await query.edit_message_text("❌ সিকিউরিটি পারপাসে দয়া করে আগে আমাদের চ্যানেলে জয়েন করুন।")
            return ConversationHandler.END
        
        notice_text = "⚠️ <b>জিমেইল সেল করার অফিশিয়াল নিয়মাবলী:</b>\n\n" \
                      "১. আপনার জিমেইলগুলো অবশ্যই একটি <code>.xlsx</code> (Excel) ফাইল হিসেবে আপলোড করবেন।  এৱং Gmail এর Password এটা  (aass1122) দিতে হবে,  তাছাড়া Gmail Receive হবে না, Mind It\n" \
                      "২. ফাইলের ভেতর ডেটাগুলো (Email:Password) এভাবে সাজানো থাকতে হবে।\n" \
                      "৩. এডমিন প্যানেল আপনার ফাইলটি লাইভ ডাউনলোড করে প্রতিটি মেইল ম্যানুয়ালি নিখুঁতভাবে চেক করবে।\n" \
                      "৪. মেইল চেকিং সম্পন্ন হওয়া মাত্রই আপনার মেইন অ্যাকাউন্টে টাকা এবং আপলাইনের অ্যাকাউন্টে রেফার বোনাস একসাথে ক্রেডিট করে দেওয়া হবে。\n\n" \
                      "📥 <b>এখন আপনার .xlsx ফাইলটি এখানে ডকুমেন্ট আকারে আপলোড করুন:</b>\n" \
                      "<i>(বাতিল করতে /cancel লিখুন)</i>"
        await query.edit_message_text(notice_text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ব্যাক", callback_data="back_main")]]), parse_mode="HTML")
        return SUBMIT_FILE

    elif query.data == "withdraw":
        u = get_user(user_id)
        if u['balance'] < MIN_WITHDRAW:
            await query.edit_message_text(f"❌ <b>দুঃখিত! আপনার ব্যালেন্স অপর্যাপ্ত।</b>\n\nআমাদের সিস্টেম থেকে সর্বনিম্ন উইথড্র লিমিট হলো <b>{MIN_WITHDRAW} টাকা</b>। আপনার অ্যাকাউন্টে বর্তমানে আছে <b>{u['balance']} টাকা</b>।", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ব্যাক টু মেনু", callback_data="back_main")]]), parse_mode="HTML")
            return ConversationHandler.END
        
        keyboard = [
            [InlineKeyboardButton("📱 bKash (Personal)", callback_data="w_Bkash"), InlineKeyboardButton("📱 Nagad (Personal)", callback_data="w_Nagad")],
            [InlineKeyboardButton("📱 Rocket (Personal)", callback_data="w_Rocket"), InlineKeyboardButton("🔶 Binance (USDT)", callback_data="w_Binance")],
            [InlineKeyboardButton("⬅️ ব্যাক", callback_data="back_main")]
        ]
        await query.edit_message_text("🏧 <b>Secure Gateway - পেমেন্ট মেথড সিলেক্ট করুন:</b>\n\nকোন পেমেন্ট মেথডের মাধ্যমে আপনি আপনার টাকা তুলতে চান তা সিলেক্ট করুন:", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return WITHDRAW_METHOD

# ফাইল রিসিভিং সিস্টেম
async def receive_file(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    update_last_seen(user.id)
    
    if not update.message.document:
        await update.message.reply_text("❌ <b>ভুল ফরম্যাট!</b> দয়া করে একটি সঠিক এক্সেল (.xlsx) বা ডকুমেন্ট ফাইল সেন্ড করুন।")
        return SUBMIT_FILE
        
    file_id = update.message.document.file_id
    file_name = update.message.document.file_name
    save_file(user.id, file_id, file_name)
    
    req_id = random.randint(100000, 999999)
    
    admin_text = f"📩 <b>[NEW GMAIL FILE RECEIVED]</b>\n\n" \
                 f"👤 মেম্বারের নাম: <a href='tg://user?id={user.id}'>{user.first_name}</a>\n" \
                 f"🆔 ইউজার আইডি: <code>{user.id}</code>\n" \
                 f"📄 ফাইলের নাম: <code>{file_name}</code>\n" \
                 f"🔢 ট্র্যাকিং আইডি: #{req_id}\n\n" \
                 f"ℹ️ ফাইলটি ডাউনলোড করে চেক করুন এবং পেমেন্ট রিলিজ করতে /admin প্যানেল ব্যবহার করুন।"
                 
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_text, parse_mode="HTML")
    await context.bot.send_document(chat_id=ADMIN_ID, document=file_id)
    
    await update.message.reply_text(f"✅ <b>আপনার জিমেইল ফাইলটি সফলভাবে সিস্টেমে আপলোড হয়েছে!</b>\n\n🔢 ট্র্যাকিং আইডি: <code>#{req_id}</code>\n⏳ এডমিন কিছুক্ষণের মধ্যেই ফাইলটি ভেরিফাই করে আপনার ব্যালেন্স অ্যাড করে দেবে। ধন্যবাদ!", parse_mode="HTML")
    await show_main_menu(update)
    return ConversationHandler.END


# ==================== 🏧 WITHDRAW CONVERSATION GATEWAY ====================

async def withdraw_method_select(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if query.data == "back_main":
        await show_main_menu(update)
        return ConversationHandler.END
        
    method = query.data.split("_")[1]
    context.user_data['w_method'] = method
    
    await query.edit_message_text(f"💳 <b>পেমেন্ট গেটওয়ে: {method}</b>\n\nআপনি কত টাকা তুলতে চান তা টাইপ করে সংখ্যায় লিখুন। (যেমন: <code>350</code>):", parse_mode="HTML")
    return WITHDRAW_AMOUNT

async def withdraw_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        amount = int(update.message.text.strip())
        user_id = update.effective_user.id
        u = get_user(user_id)
        
        if amount < MIN_WITHDRAW:
            await update.message.reply_text(f"❌ <b>দুঃখিত!</b> আমাদের সর্বনিম্ন উইথড্রয়াল অ্যামাউন্ট হলো <b>{MIN_WITHDRAW} টাকা</b>। সঠিক পরিমাণ আবার লিখুন:")
            return WITHDRAW_AMOUNT
            
        if amount > u['balance']:
            await update.message.reply_text(f"❌ <b>সীমা অতিক্রম করেছেন!</b> আপনার মেইন ব্যালেন্সে পর্যাপ্ত টাকা নেই। আপনার বর্তমান ব্যালেন্স: <b>{u['balance']} TK</b>। সঠিক এমাউন্ট আবার দিন:")
            return WITHDRAW_AMOUNT
            
        context.user_data['w_amount'] = amount
        method = context.user_data['w_method']
        
        prompt = f"📱 আপনার <b>{method} পার্সোনাল নাম্বারটি</b> টাইপ করুন (Binance হলে Pay ID/Address দিন):"
        await update.message.reply_text(prompt, parse_mode="HTML")
        return WITHDRAW_NUMBER
    except ValueError:
        await update.message.reply_text("❌ <b>ভুল ইনপুট!</b> দয়া করে শুধুমাত্র সংখ্যায় টাকার পরিমাণটি টাইপ করুন:")
        return WITHDRAW_AMOUNT

async def withdraw_number_input(update: Update, context: ContextTypes.DEFAULT_TYPE):
    account_num = update.message.text.strip()
    user = update.effective_user
    
    method = context.user_data['w_method']
    amount = context.user_data['w_amount']
    
    # পেমেন্ট পেন্ডিং স্ট্যাটাস (ডাটাবেসে একটি pending_withdraw টেবিল থাকা ভালো, তবে আপাতত ইউজার ব্যালেন্স কেটে রাখছি)
    update_balance(user.id, -amount)
    
    # বাটন সেটআপ
    keyboard = [
        [InlineKeyboardButton("✅ Approve", callback_data=f"app_{user.id}_{amount}"),
         InlineKeyboardButton("❌ Reject", callback_data=f"rej_{user.id}_{amount}")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    admin_alert = f"🔔 <b>[WITHDRAWAL REQUEST PENDING]</b>\n\n" \
                  f"👤 ইউজার: <a href='tg://user?id={user.id}'>{user.first_name}</a>\n" \
                  f"🆔 আইডি: <code>{user.id}</code>\n" \
                  f"💰 পরিমাণ: <b>{amount} TK</b>\n" \
                  f"⚡ গেটওয়ে: <b>{method}</b>\n" \
                  f"💳 অ্যাকাউন্ট: <code>{account_num}</code>"
                  
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, reply_markup=reply_markup, parse_mode="HTML")
    
    await update.message.reply_text(f"⚡ <b>আপনার উইথড্র রিকোয়েস্টটি এডমিনের কাছে পাঠানো হয়েছে!</b>", parse_mode="HTML")
    await show_main_menu(update)
    return ConversationHandler.END
                  
    await context.bot.send_message(chat_id=ADMIN_ID, text=admin_alert, parse_mode="HTML")
    
    await update.message.reply_text(f"⚡ <b>আপনার উইথড্র রিকোয়েস্টটি প্রসেসিংয়ে পাঠানো হয়েছে!</b>\n\n"
                                    f"📊 ট্রানজেকশন ডিটেইলস:\n"
                                    f"💵 পরিমাণ: <code>{amount} TK</code>\n"
                                    f"📱 পেমেন্ট গেটওয়ে: <b>{method}</b>\n"
                                    f"⏳ <b>স্ট্যাটাস:</b> Pending (১-২৪ ঘণ্টার মধ্যে এডমিন পেমেন্টটি ক্লিয়ার করে দেবে)।", parse_mode="HTML")
    await show_main_menu(update)
    return ConversationHandler.END


# ==================== 👑 MEGA ADMIN CONTROLLER ====================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return ConversationHandler.END
        
    keyboard = [
        [InlineKeyboardButton("📊 System Stats", callback_data="admin_stats"), InlineKeyboardButton("📁 All Files Folder", callback_data="admin_folder")],
        [InlineKeyboardButton("💰 Add Balance & Refer", callback_data="admin_addbal"), InlineKeyboardButton("➖ Remove Balance", callback_data="admin_rembal")],
        [InlineKeyboardButton("🔍 Check User Profile", callback_data="admin_checkuser"), InlineKeyboardButton("📢 Global Broadcast", callback_data="admin_broadcast")],
        [InlineKeyboardButton("🚫 Ban Member", callback_data="admin_ban"), InlineKeyboardButton("🔓 Unban Member", callback_data="admin_unban")],
        [InlineKeyboardButton("❌ ক্লোজ প্যানেল", callback_data="admin_close")]
    ]
    await update.message.reply_text("👑 <b>MHF Megapower Admin Operating Console</b>\n\n<i>নিরাপদ ডাইনামিক স্যালারি ও রেফারেল ডিস্ট্রিবিউশন ইঞ্জিন একটিভ আছে।</i>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
    return ConversationHandler.END

async def admin_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.from_user.id != ADMIN_ID: 
        return ConversationHandler.END

    if query.data == "admin_stats":
        t_users, t_files, t_banned = get_stats()
        text = f"📊 <b>লাইভ সার্ভার পরিসংখ্যান:</b>\n\n👥 মোট রেজিস্টার্ড ইউজার: {t_users} জন\n📁 মোট আপলোডকৃত ডাটা ফাইল: {t_files} টি\n🚫 মোট ব্লকলিস্টেড ইউজার: {t_banned} জন"
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ব্যাক", callback_data="admin_back")]]), parse_mode="HTML")
        return ConversationHandler.END
        
    elif query.data == "admin_folder":
        files = get_all_files()
        if not files:
            await query.edit_message_text("📁 <b>ফাইল ডাটাবেস সম্পূর্ণ খালি!</b>", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ ব্যাক", callback_data="admin_back")]]), parse_mode="HTML")
        else:
            await query.message.delete()
            for idx, f_info in enumerate(files, 1):
                await context.bot.send_message(chat_id=ADMIN_ID, text=f"📄 <b>ফাইল নং: {idx}</b>\n👤 মেম্বার আইডি: <code>{f_info[0]}</code>", parse_mode="HTML")
                await context.bot.send_document(chat_id=ADMIN_ID, document=f_info[1])
            
            # পুনরায় ব্যাক প্যানেল ওপেন
            keyboard = [
                [InlineKeyboardButton("📊 System Stats", callback_data="admin_stats"), InlineKeyboardButton("📁 All Files Folder", callback_data="admin_folder")],
                [InlineKeyboardButton("💰 Add Balance & Refer", callback_data="admin_addbal"), InlineKeyboardButton("➖ Remove Balance", callback_data="admin_rembal")],
                [InlineKeyboardButton("🔍 Check User Profile", callback_data="admin_checkuser"), InlineKeyboardButton("📢 Global Broadcast", callback_data="admin_broadcast")],
                [InlineKeyboardButton("🚫 Ban Member", callback_data="admin_ban"), InlineKeyboardButton("🔓 Unban Member", callback_data="admin_unban")],
                [InlineKeyboardButton("❌ ক্লোজ প্যানেল", callback_data="admin_close")]
            ]
            await context.bot.send_message(chat_id=ADMIN_ID, text="👑 <b>MHF Megapower Admin Operating Console</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return ConversationHandler.END

    elif query.data == "admin_addbal":
        await query.edit_message_text("💰 <b>মেম্বার আইডি এবং এক্সেপ্টেড জিমেইলের সংখ্যা</b> স্পেস দিয়ে লিখুন।\n\n"
                                      "📝 ফরম্যাট: <code>[User_ID] [Count]</code>", parse_mode="HTML")
        return ADMIN_ADD_BAL
    elif query.data == "admin_rembal":
        await query.edit_message_text("➖ <b>ব্যালেন্স কাটার প্যানেল:</b> ইউজার আইডি এবং টাকার পরিমাণ স্পেস দিয়ে লিখুন:", parse_mode="HTML")
        return ADMIN_REM_BAL
    elif query.data == "admin_checkuser":
        await query.edit_message_text("🔍 মেম্বারের <b>ইউজার আইডি</b> টাইপ করুন:")
        return ADMIN_CHECK_USER
    elif query.data == "admin_ban":
        await query.edit_message_text("🚫 বট থেকে পার্মানেন্ট ব্যান করার জন্য <b>ইউজার আইডি</b> দিন:")
        return ADMIN_BAN
    elif query.data == "admin_unban":
        await query.edit_message_text("🔓 আনব্যান করার জন্য মেম্বারের <b>ইউজার আইডি</b> দিন:")
        return ADMIN_UNBAN
    elif query.data == "admin_broadcast":
        await query.edit_message_text("📢 <b>গ্লোবাল ব্রডকাস্ট:</b> সকল মেম্বারদের ইনবক্সে পাঠানোর নোটিশটি লিখুন:")
        return ADMIN_BROADCAST
    elif query.data == "admin_back":
        keyboard = [
            [InlineKeyboardButton("📊 System Stats", callback_data="admin_stats"), InlineKeyboardButton("📁 All Files Folder", callback_data="admin_folder")],
            [InlineKeyboardButton("💰 Add Balance & Refer", callback_data="admin_addbal"), InlineKeyboardButton("➖ Remove Balance", callback_data="admin_rembal")],
            [InlineKeyboardButton("🔍 Check User Profile", callback_data="admin_checkuser"), InlineKeyboardButton("📢 Global Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton("🚫 Ban Member", callback_data="admin_ban"), InlineKeyboardButton("🔓 Unban Member", callback_data="admin_unban")],
            [InlineKeyboardButton("❌ ক্লোজ প্যানেল", callback_data="admin_close")]
        ]
        await query.edit_message_text("👑 <b>MHF Megapower Admin Operating Console</b>", reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="HTML")
        return ConversationHandler.END
    elif query.data == "admin_close":
        await query.message.delete()
        return ConversationHandler.END

async def admin_process_addbal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid, gmail_count = map(int, update.message.text.split())
        u = get_user(uid)
        if u:
            member_total = gmail_count * GMAIL_PRICE
            ref_total = gmail_count * REFER_COMMISSION
            update_balance(uid, member_total)
            await update.message.reply_text(f"✅ ইউজার <code>{uid}</code> কে {member_total} টাকা দেওয়া হয়েছে।", parse_mode="HTML")
            try: await context.bot.send_message(chat_id=uid, text=f"🎉 আপনার {gmail_count} টি ভ্যালিড জিমেইলের জন্য মোট <b>{member_total} টাকা</b> ব্যালেন্সে জমা হয়েছে।", parse_mode="HTML")
            except: pass
            
            ref_id = u['referred_by']
            if ref_id and get_user(ref_id):
                update_balance(ref_id, ref_total)
                try: await context.bot.send_message(chat_id=ref_id, text=f"🎉 রেফার বোনাস <b>{ref_total} টাকা</b> আপনার ব্যালেন্সে যোগ হয়েছে।", parse_mode="HTML")
                except: pass
        else:
            await update.message.reply_text("❌ এই ইউজার আইডিটি নিবন্ধিত নেই।")
    except:
        await update.message.reply_text("❌ ভুল ফরম্যাট!")
    return ConversationHandler.END

async def admin_process_rembal(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid, amt = map(int, update.message.text.split())
        if get_user(uid):
            update_balance(uid, -amt)
            await update.message.reply_text(f"✅ ব্যালেন্স থেকে {amt} টাকা মাইনাস করা হয়েছে।")
        else: await update.message.reply_text("❌ মেম্বার খুঁজে পাওয়া যায়নি।")
    except: await update.message.reply_text("❌ ভুল ফরম্যাট!")
    return ConversationHandler.END

# 🎯 Upline ID এবং Online/Offline ট্র্যাকিং সহ সংশোধিত প্রোফাইল চেকার
async def admin_process_checkuser(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        u = get_user(uid)
        if u:
            status = "🚫 Banned" if u['banned'] else "🟢 Active"
            
            # ১. আপলাইন (Upline) টেক্সট নির্ধারণ
            upline_id = u['referred_by']
            upline_text = f"<code>{upline_id}</code>" if upline_id else "<i>সরাসরি জয়েন (None)</i>"
            
            # ২. অ্যাক্টিভিটি স্ট্যাটাস (Online/Offline) নির্ধারণ (৫ মিনিট চেক)
            online_status = "⚫ Offline"
            if u['last_seen']:
                last_time = datetime.datetime.strptime(u['last_seen'], "%Y-%m-%d %H:%M:%S")
                if (datetime.datetime.now() - last_time).total_seconds() < 300:  # ৩০০ সেকেন্ড = ৫ মিনিট
                    online_status = "🟢 Online"
                else:
                    online_status = f"⚫ Offline (Last Seen: {u['last_seen']})"
            else:
                online_status = "⚫ Offline (No data)"

            text = f"🔍 <b>মেম্বার প্রোফাইল:</b>\n\n" \
                   f"🆔 আইডি: <code>{uid}</code>\n" \
                   f"👤 নাম: <b>{u['name']}</b>\n" \
                   f"🔗 আপলাইন (Upline) আইডি: {upline_text}\n" \
                   f"💵 ব্যালেন্স: <code>{u['balance']} TK</code>\n" \
                   f"👥 রেফার: <b>{u['ref_count']} জন</b>\n" \
                   f"⚡ অ্যাকাউন্ট স্ট্যাটাস: {status}\n" \
                   f"🌐 অ্যাক্টিভিটি স্ট্যাটাস: <b>{online_status}</b>"
            await update.message.reply_text(text, parse_mode="HTML")
        else: 
            await update.message.reply_text("❌ আইডি পাওয়া যায়নি।")
    except Exception as e: 
        await update.message.reply_text("❌ ভুল আইডি বা ডেটা প্রসেসিংয়ে সমস্যা হয়েছে।")
    return ConversationHandler.END

async def admin_process_ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        if get_user(uid):
            set_ban_status(uid, True)
            await update.message.reply_text(f"✅ ইউজার <code>{uid}</code> কে ব্যান করা হয়েছে।", parse_mode="HTML")
        else: await update.message.reply_text("❌ ইউজার ডাটাবেসে নেই।")
    except: pass
    return ConversationHandler.END

async def admin_process_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        uid = int(update.message.text.strip())
        if get_user(uid):
            set_ban_status(uid, False)
            await update.message.reply_text(f"✅ ইউজার <code>{uid}</code> কে আনব্যান করা হয়েছে।", parse_mode="HTML")
        else: await update.message.reply_text("❌ ইউজার ডাটাবেসে নেই。")
    except: pass
    return ConversationHandler.END

async def admin_process_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message.text
    all_ids = get_all_user_ids()
    count = 0
    for uid in all_ids:
        try:
            await context.bot.send_message(chat_id=uid, text=f"📢 <b>MHF Global Announcement:</b>\n\n{msg}", parse_mode="HTML")
            count += 1
        except: pass
    await update.message.reply_text(f"📢 ব্রডকাস্ট সফল! মোট {count} জনকে পাঠানো হয়েছে।")
    return ConversationHandler.END
async def handle_withdraw_action(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    data = query.data.split("_")
    action = data[0]
    user_id = int(data[1])
    amount = int(data[2])
    
    if action == "app":
        await query.edit_message_text(f"✅ <b>উইথড্র সফলভাবে এপ্রুভ করা হয়েছে!</b>\nইউজার: {user_id}\nপরিমাণ: {amount} TK")
        try:
            await context.bot.send_message(chat_id=user_id, text=f"🎉 অভিনন্দন! আপনার <b>{amount} TK</b> উইথড্র রিকোয়েস্টটি এপ্রুভ করা হয়েছে। পেমেন্ট চেক করুন।", parse_mode="HTML")
        except: pass
        
    elif action == "rej":
        update_balance(user_id, amount) # টাকা ফেরত দেওয়া
        await query.edit_message_text(f"❌ <b>উইথড্র রিজেক্ট করা হয়েছে।</b>\nইউজার: {user_id}\nটাকা ব্যালেন্সে ফেরত দেওয়া হয়েছে।")
        try:
            await context.bot.send_message(chat_id=user_id, text=f"⚠️ দুঃখিত! আপনার <b>{amount} TK</b> উইথড্র রিকোয়েস্টটি রিজেক্ট করা হয়েছে। টাকা আপনার ব্যালেন্সে ফেরত দেওয়া হয়েছে।", parse_mode="HTML")
        except: pass

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.callback_query:
        await update.callback_query.answer()
    await show_main_menu(update)
    return ConversationHandler.END

def main():
    application = Application.builder().token(BOT_TOKEN).build()

    # মেইন কনভারসেশনাল ফ্লো হ্যান্ডলার (ফাইল আপলোড এবং উইথড্রয়াল)
    user_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(button_click, pattern="^sell_gmail$"),
            CallbackQueryHandler(button_click, pattern="^withdraw$"),
        ],
        states={
            SUBMIT_FILE: [MessageHandler(filters.Document.ALL, receive_file)],
            WITHDRAW_METHOD: [CallbackQueryHandler(withdraw_method_select, pattern="^(w_Bkash|w_Nagad|w_Rocket|w_Binance)$")],
            WITHDRAW_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_amount_input)],
            WITHDRAW_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, withdraw_number_input)],
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(cancel, pattern="^back_main$")
        ],
        per_message=False
    )

    # অ্যাডমিন প্যানেল কনভারসেশনাল হ্যান্ডলার
    admin_conv = ConversationHandler(
        entry_points=[
            CallbackQueryHandler(admin_buttons, pattern="^admin_addbal$"),
            CallbackQueryHandler(admin_buttons, pattern="^admin_rembal$"),
            CallbackQueryHandler(admin_buttons, pattern="^admin_checkuser$"),
            CallbackQueryHandler(admin_buttons, pattern="^admin_ban$"),
            CallbackQueryHandler(admin_buttons, pattern="^admin_unban$"),
            CallbackQueryHandler(admin_buttons, pattern="^admin_broadcast$")
        ],
        states={
            ADMIN_ADD_BAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_addbal)],
            ADMIN_REM_BAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_rembal)],
            ADMIN_CHECK_USER: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_checkuser)],
            ADMIN_BAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_ban)],
            ADMIN_UNBAN: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_unban)],
            ADMIN_BROADCAST: [MessageHandler(filters.TEXT & ~filters.COMMAND, admin_process_broadcast)]
        },
        fallbacks=[
            CommandHandler("cancel", cancel),
            CallbackQueryHandler(admin_buttons, pattern="^admin_back$")
        ],
        per_message=False
    )

    # রুট কমান্ডস
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin_panel))
    
    # কনভারসেশনাল ট্র্যাকারস
    application.add_handler(user_conv)
    application.add_handler(admin_conv)
    
    # স্ট্যান্ডার্ড বাটন হ্যান্ডলারস
    application.add_handler(CallbackQueryHandler(button_click, pattern="^(check_sub|account|refer|support|info|back_main)$"))
    application.add_handler(CallbackQueryHandler(admin_buttons, pattern="^admin_"))

    print("MHF Premium Automated Bot successfully initialized...")
    application.run_polling()

if __name__ == '__main__':
    main()

