import requests
import logging
from telegram import Update, ReplyKeyboardMarkup, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import pytz
from datetime import datetime, timedelta
import re

# إعداد التسجيل لتتبع الأخطاء ومحاولات الاختراق
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# توكن البوت ومعرف الأدمن الرئيسي
TOKEN = "7429350308:AAFsi4OgTRsr32HshWU4EpuSopR45yEo2TU"  # استبدل بالتوكن الحقيقي
MAIN_ADMIN_ID = 7516340024  # استبدل بمعرف الأدمن الرئيسي (user_id)

# تخزين بيانات المستخدمين والإعدادات
users_data = {}  # {user_id: {"points": int, "last_gift": datetime, "referrals": int, "banned": bool}}
admins = {MAIN_ADMIN_ID}  # مجموعة معرفات الأدمن
settings = {"welcome_message": "مرحبًا {username}! اختر أحد الأوامر أدناه:", "daily_gift_points": 500}
banned_users = set()  # مجموعة المستخدمين المحظورين

# دالة للتحقق من أمان المدخلات
def is_safe_input(text):
    suspicious_patterns = [r"(\b(SELECT|INSERT|DELETE|UPDATE|DROP)\b)", r"(\b(SCRIPT|eval|exec)\b)", r"[<>{}]"]
    for pattern in suspicious_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            logger.warning(f"محاولة إدخال مشبوهة: {text}")
            return False
    return True

# دالة لإنشاء بريد مؤقت
def get_temp_email():
    try:
        response = requests.get("https://api.tempmail.lol/generate", timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info(f"API Response: {data}")
        return data.get("address"), data.get("token")
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في طلب API: {e}")
        return None, None

# دالة للتحقق من الرسائل في البريد المؤقت
def check_inbox(token):
    try:
        response = requests.get(f"https://api.tempmail.lol/inbox?token={token}", timeout=10)
        response.raise_for_status()
        data = response.json()
        logger.info(f"Inbox Response: {data}")
        return data.get("emails", [])
    except requests.exceptions.RequestException as e:
        logger.error(f"خطأ في التحقق من البريد الوارد: {e}")
        return None

# أمر /start مع لوحة مفاتيح
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "غير معروف"
    logger.info(f"User ID: {user_id}, Username: {username} requested /start")

    # التحقق من الحظر
    if user_id in banned_users:
        await update.message.reply_text("تم حظرك من استخدام البوت.")
        return

    # تهيئة بيانات المستخدم
    if user_id not in users_data:
        users_data[user_id] = {"points": 0, "last_gift": None, "referrals": 0, "banned": False}
        # التحقق من عدد المستخدمين
        if len(users_data) == 1000:
            for admin_id in admins:
                await context.bot.send_message(admin_id, "🎉 تهانينا! وصلنا إلى 1000 مستخدم!")

    # التحقق من رابط الدعوة
    if context.args:
        referrer_id = int(context.args[0]) if context.args[0].isdigit() else None
        if referrer_id and referrer_id != user_id and referrer_id in users_data and referrer_id not in banned_users:
            users_data[user_id]["points"] += 500
            users_data[referrer_id]["points"] += 500
            users_data[referrer_id]["referrals"] += 1
            await context.bot.send_message(referrer_id, f"لقد دعوت مستخدمًا جديدًا! تمت إضافة 500 نقطة إلى رصيدك.")

    # لوحة المفاتيح
    if user_id in admins:
        keyboard = [
            ["/getemail", "/checkinbox"],
            ["/daily_gift", "/invite"],
            ["/admin_stats", "/admin_settings", "/help"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(f"مرحبًا أدمن {username}! اختر أحد الأوامر:", reply_markup=reply_markup)
    else:
        keyboard = [
            ["/getemail", "/checkinbox"],
            ["/daily_gift", "/invite"],
            ["/help"]
        ]
        reply_markup = ReplyKeyboardMarkup(keyboard, resize_keyboard=True, one_time_keyboard=False)
        await update.message.reply_text(settings["welcome_message"].format(username=username), reply_markup=reply_markup)

# أمر /getemail لإنشاء بريد مؤقت
async def get_email(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "غير معروف"
    text = update.message.text
    logger.info(f"User ID: {user_id}, Username: {username} requested /getemail")

    if user_id in banned_users:
        await update.message.reply_text("تم حظرك من استخدام البوت.")
        return

    if not is_safe_input(text):
        await update.message.reply_text("تم اكتشاف إدخال غير آمن. تم تسجيل المحاولة.")
        logger.warning(f"محاولة اختراق محتملة من User ID: {user_id}")
        for admin_id in admins:
            await context.bot.send_message(admin_id, f"تحذير: محاولة إدخال مشبوهة من User ID: {user_id}, Username: {username}")
        return

    if user_id not in users_data or users_data[user_id]["points"] < 1:
        await update.message.reply_text("ليس لديك نقاط كافية. اجمع نقاط عبر /daily_gift أو /invite.")
        return

    users_data[user_id]["points"] -= 1
    email, token = get_temp_email()
    if email and token:
        context.user_data["email_token"] = token
        await update.message.reply_text(f"بريدك المؤقت: {email}\nاستخدم /checkinbox للتحقق من الرسائل.")
    else:
        await update.message.reply_text("حدث خطأ أثناء إنشاء البريد المؤقت. حاول مرة أخرى.")

# أمر /checkinbox للتحقق من الرسائل
async def check_inbox_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id in banned_users:
        await update.message.reply_text("تم حظرك من استخدام البوت.")
        return

    if not is_safe_input(text):
        await update.message.reply_text("تم اكتشاف إدخال غير آمن. تم تسجيل المحاولة.")
        logger.warning(f"محاولة اختراق محتملة من User ID: {user_id}")
        for admin_id in admins:
            await context.bot.send_message(admin_id, f"تحذير: محاولة إدخال مشبوهة من User ID: {user_id}")
        return

    token = context.user_data.get("email_token")
    if not token:
        await update.message.reply_text("قم بإنشاء بريد مؤقت أولاً باستخدام /getemail")
        return
    emails = check_inbox(token)
    if emails:
        for email in emails:
            await update.message.reply_text(f"من: {email['from']}\nالموضوع: {email['subject']}\nالرسالة: {email['body']}")
    else:
        await update.message.reply_text("لا توجد رسائل في البريد الوارد أو حدث خطأ.")

# أمر /daily_gift للهدية اليومية
async def daily_gift(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "غير معروف"

    if user_id in banned_users:
        await update.message.reply_text("تم حظرك من استخدام البوت.")
        return

    if user_id not in users_data:
        users_data[user_id] = {"points": 0, "last_gift": None, "referrals": 0, "banned": False}

    now = datetime.now(pytz.UTC)
    last_gift = users_data[user_id]["last_gift"]
    if last_gift and now < last_gift + timedelta(days=1):
        await update.message.reply_text("لقد حصلت بالفعل على هديتك اليومية! حاول مرة أخرى غدًا.")
        return

    users_data[user_id]["points"] += settings["daily_gift_points"]
    users_data[user_id]["last_gift"] = now
    await update.message.reply_text(f"تمت إضافة {settings['daily_gift_points']} نقطة إلى رصيدك! رصيدك الآن: {users_data[user_id]['points']}")

# أمر /invite لإنشاء رابط دعوة
async def invite(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    username = update.message.from_user.username or "غير معروف"

    if user_id in banned_users:
        await update.message.reply_text("تم حظرك من استخدام البوت.")
        return

    invite_link = f"https://t.me/{context.bot.username}?start={user_id}"
    await update.message.reply_text(
        f"رابط الدعوة الخاص بك: {invite_link}\n"
        "شارك هذا الرابط مع أصدقائك. كل صديق ينضم يمنحك ويمنحه 500 نقطة!"
    )

# أمر /admin_stats للإحصائيات
async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admins:
        await update.message.reply_text("هذا الأمر مخصص للأدمن فقط!")
        return

    total_users = len(users_data)
    total_points = sum(data["points"] for data in users_data.values())
    total_referrals = sum(data["referrals"] for data in users_data.values())
    banned_count = len(banned_users)
    stats = (
        f"إحصائيات البوت:\n"
        f"إجمالي المستخدمين: {total_users}\n"
        f"إجمالي النقاط الموزعة: {total_points}\n"
        f"إجمالي الدعوات: {total_referrals}\n"
        f"عدد المستخدمين المحظورين: {banned_count}"
    )
    await update.message.reply_text(stats)

# أمر /admin_settings لتعديل الإعدادات
async def admin_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id not in admins:
        await update.message.reply_text("هذا الأمر مخصص للأدمن فقط!")
        return

    keyboard = [
        [InlineKeyboardButton("تغيير رسالة الترحيب", callback_data="change_welcome")],
        [InlineKeyboardButton("تغيير نقاط الهدية اليومية", callback_data="change_gift_points")],
        [InlineKeyboardButton("إضافة أدمن", callback_data="add_admin")],
        [InlineKeyboardButton("حظر مستخدم", callback_data="ban_user")],
        [InlineKeyboardButton("رفع الحظر عن مستخدم", callback_data="unban_user")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("اختر إعدادًا لتعديله:", reply_markup=reply_markup)

# معالجة أزرار الإعدادات
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id

    if user_id not in admins:
        await query.message.reply_text("هذا الأمر مخصص للأدمن فقط!")
        return

    if query.data == "change_welcome":
        await query.message.reply_text("أرسل رسالة الترحيب الجديدة (استخدم {username} لاسم المستخدم):")
        context.user_data["awaiting_welcome"] = True
    elif query.data == "change_gift_points":
        await query.message.reply_text("أرسل عدد النقاط الجديدة للهدية اليومية:")
        context.user_data["awaiting_gift_points"] = True
    elif query.data == "add_admin":
        await query.message.reply_text("أرسل معرف المستخدم (user_id) للأدمن الجديد:")
        context.user_data["awaiting_admin_id"] = True
    elif query.data == "ban_user":
        await query.message.reply_text("أرسل معرف المستخدم (user_id) للحظر:")
        context.user_data["awaiting_ban_id"] = True
    elif query.data == "unban_user":
        await query.message.reply_text("أرسل معرف المستخدم (user_id) لرفع الحظر:")
        context.user_data["awaiting_unban_id"] = True

# معالجة الرسائل (للإعدادات)
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    text = update.message.text

    if user_id not in admins:
        return

    if context.user_data.get("awaiting_welcome"):
        if is_safe_input(text):
            settings["welcome_message"] = text
            await update.message.reply_text(f"تم تحديث رسالة الترحيب إلى: {text}")
        else:
            await update.message.reply_text("الرسالة تحتوي على محتوى غير آمن. حاول مرة أخرى.")
        context.user_data["awaiting_welcome"] = False
    elif context.user_data.get("awaiting_gift_points"):
        if text.isdigit() and int(text) > 0:
            settings["daily_gift_points"] = int(text)
            await update.message.reply_text(f"تم تحديث نقاط الهدية اليومية إلى: {text}")
        else:
            await update.message.reply_text("أرسل رقمًا صحيحًا أكبر من 0.")
        context.user_data["awaiting_gift_points"] = False
    elif context.user_data.get("awaiting_admin_id"):
        if text.isdigit() and int(text) in users_data:
            admins.add(int(text))
            await update.message.reply_text(f"تمت إضافة User ID {text} كأدمن.")
        else:
            await update.message.reply_text("معرف المستخدم غير صالح أو غير موجود.")
        context.user_data["awaiting_admin_id"] = False
    elif context.user_data.get("awaiting_ban_id"):
        if text.isdigit() and int(text) in users_data:
            banned_users.add(int(text))
            users_data[int(text)]["banned"] = True
            await update.message.reply_text(f"تم حظر User ID {text}.")
        else:
            await update.message.reply_text("معرف المستخدم غير صالح أو غير موجود.")
        context.user_data["awaiting_ban_id"] = False
    elif context.user_data.get("awaiting_unban_id"):
        if text.isdigit() and int(text) in banned_users:
            banned_users.remove(int(text))
            users_data[int(text)]["banned"] = False
            await update.message.reply_text(f"تم رفع الحظر عن User ID {text}.")
        else:
            await update.message.reply_text("معرف المستخدم غير محظور أو غير موجود.")
        context.user_data["awaiting_unban_id"] = False

# أمر /help
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in banned_users:
        await update.message.reply_text("تم حظرك من استخدام البوت.")
        return

    await update.message.reply_text(
        "الأوامر المتاحة:\n"
        "/start - بدء البوت وعرض لوحة التحكم\n"
        "/getemail - إنشاء بريد مؤقت (يكلف نقطة واحدة)\n"
        "/checkinbox - التحقق من الرسائل في البريد المؤقت\n"
        "/daily_gift - الحصول على هدية يومية\n"
        "/invite - إنشاء رابط دعوة لكسب نقاط\n"
        "/help - عرض الأوامر المتاحة\n"
        "للأدمن: /admin_stats, /admin_settings"
    )

# الدالة الرئيسية
def main():
    app = Application.builder().token(TOKEN).build()

    # إضافة الأوامر
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("getemail", get_email))
    app.add_handler(CommandHandler("checkinbox", check_inbox_command))
    app.add_handler(CommandHandler("daily_gift", daily_gift))
    app.add_handler(CommandHandler("invite", invite))
    app.add_handler(CommandHandler("admin_stats", admin_stats))
    app.add_handler(CommandHandler("admin_settings", admin_settings))
    app.add_handler(CallbackQueryHandler(button_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # تحديد منطقة زمنية
    app.job_queue.scheduler.configure(timezone=pytz.timezone("UTC"))

    # بدء البوت
    logger.info("Starting bot...")
    app.run_polling()

if __name__ == '__main__':
    main()