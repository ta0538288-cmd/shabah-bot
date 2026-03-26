import logging
import os
import json
import datetime
import threading
import anthropic
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ForceReply
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

BOT_TOKEN  = "8695004416:AAFTA6FPAJZrd6jG0HNJuW7a6WJk4fO67Jg"
CLAUDE_KEY = "sk-ant-api03-PJew3M2NlFGIlgnJbD2q2u5yWathzMKnb-DD15W4l5y0LkfCjvQv2KTladgKQDKqJvO-hwr_YZqD9hpPFjgJ8_2Q-RJcPfQAA"
ADMIN_ID   = 5103468033

PRODUCTS = {
    "subscriptions": {
        "name": "📺 الاشتراكات",
        "sub": {
            "shahid": {
                "name": "👻 شاهد VIP",
                "items": [
                    {"id": "sh_1", "name": "شاهد ملف شهر",   "price": 6.99,  "desc": "ملف خاص + ضمان 30 يوم"},
                    {"id": "sh_2", "name": "شاهد ايميل شهر",  "price": 29.99, "desc": "ايميل خاص 4 ملفات + ضمان"},
                ]
            },
            "netflix": {
                "name": "🎬 نتفليكس",
                "items": [
                    {"id": "nf_1", "name": "نتفليكس ملف شهر",  "price": 8.99,  "desc": "ملف خاص + ضمان 30 يوم"},
                    {"id": "nf_2", "name": "نتفليكس ايميل شهر", "price": 32.99, "desc": "ايميل خاص 4 ملفات + ضمان"},
                ]
            },
        }
    },
    "games": {
        "name": "🎮 الالعاب",
        "sub": {
            "shared": {
                "name": "👥 العاب مشتركة",
                "items": [
                    {"id": "gs_1", "name": "قريبا", "price": 0, "desc": "سيتم الاضافة قريبا"},
                ]
            },
            "private": {
                "name": "🔐 العاب حساب خاص",
                "items": [
                    {"id": "gp_1", "name": "قريبا", "price": 0, "desc": "سيتم الاضافة قريبا"},
                ]
            },
            "keys": {
                "name": "🗝️ العاب Key",
                "items": [
                    {"id": "gk_1", "name": "قريبا", "price": 0, "desc": "سيتم الاضافة قريبا"},
                ]
            },
        }
    }
}

ORDERS_FILE = "orders.json"
# مخزن مؤقت: message_id الإشعار → user_id العميل
RELAY_MAP = {}

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

class Health(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
    def log_message(self, *args):
        pass

def run_health():
    port = int(os.environ.get("PORT", 8080))
    HTTPServer(("0.0.0.0", port), Health).serve_forever()

threading.Thread(target=run_health, daemon=True).start()

def load_orders():
    if os.path.exists(ORDERS_FILE):
        with open(ORDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_orders(orders):
    with open(ORDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, ensure_ascii=False, indent=2)

def get_product_by_id(pid):
    for cat in PRODUCTS.values():
        for subcat in cat["sub"].values():
            for item in subcat["items"]:
                if item["id"] == pid:
                    return item
    return None

def gen_order_id():
    return f"SH{len(load_orders()) + 1:04d}"

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ المنتجات والاسعار", callback_data="menu_products")],
        [InlineKeyboardButton("🛒 اطلب الان", callback_data="menu_order"),
         InlineKeyboardButton("📦 تتبع طلبي", callback_data="menu_track")],
        [InlineKeyboardButton("🎧 الدعم الفني", callback_data="menu_contact")],
    ])

def main_categories_menu():
    btns = [[InlineKeyboardButton(cat["name"], callback_data="maincat_" + k)] for k, cat in PRODUCTS.items()]
    btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(btns)

def sub_categories_menu(main_key):
    cat = PRODUCTS[main_key]
    btns = [[InlineKeyboardButton(sub["name"], callback_data="subcat_" + main_key + "_" + k)] for k, sub in cat["sub"].items()]
    btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_products")])
    return InlineKeyboardMarkup(btns)

def products_menu(main_key, sub_key):
    subcat = PRODUCTS[main_key]["sub"][sub_key]
    btns = []
    for i in subcat["items"]:
        if i["price"] == 0:
            btns.append([InlineKeyboardButton("🔜 " + i["name"], callback_data="coming_soon")])
        else:
            btns.append([InlineKeyboardButton("✨ " + i["name"] + " — " + str(i["price"]) + " ريال", callback_data="item_" + i["id"])])
    btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="maincat_" + main_key)])
    return InlineKeyboardMarkup(btns)

def confirm_menu(pid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تاكيد الطلب", callback_data="confirm_" + pid)],
        [InlineKeyboardButton("❌ الغاء", callback_data="menu_products")],
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_main")]])

def ask_claude(question):
    try:
        client = anthropic.Anthropic(api_key=CLAUDE_KEY)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system="انت موظف دعم عملاء لمتجر شبح ستور الرقمي في السعودية. المتجر يبيع اشتراكات شاهد VIP ونتفليكس والعاب رقمية. ردودك قصيرة وواضحة باللهجة الخليجية.",
            messages=[{"role": "user", "content": question}]
        )
        return msg.content[0].text
    except Exception as e:
        log.error(e)
        return None

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👻 اهلا بك في شبح ستور!\n\n🎬 اشتراكات رقمية\n🎮 العاب\n\n✅ اسعار تنافسية\n✅ تسليم فوري\n✅ ضمان كامل\n\nاختر من القائمة 👇",
        reply_markup=main_menu()
    )

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()

    if data == "back_main":
        await q.edit_message_text("👻 اهلا بك في شبح ستور!\n\nاختر من القائمة 👇", reply_markup=main_menu())

    elif data == "menu_products" or data == "menu_order":
        await q.edit_message_text("🛍️ اختر القسم:", reply_markup=main_categories_menu())

    elif data == "coming_soon":
        await q.answer("🔜 قريبا يتم الاضافة!", show_alert=True)

    elif data.startswith("maincat_"):
        main_key = data[8:]
        cat = PRODUCTS[main_key]
        await q.edit_message_text(cat["name"] + "\n\nاختر الفئة 👇", reply_markup=sub_categories_menu(main_key))

    elif data.startswith("subcat_"):
        parts = data[7:].split("_", 1)
        main_key = parts[0]
        sub_key = parts[1]
        subcat = PRODUCTS[main_key]["sub"][sub_key]
        await q.edit_message_text(subcat["name"] + "\n\nاختر المنتج 👇", reply_markup=products_menu(main_key, sub_key))

    elif data.startswith("item_"):
        pid = data[5:]
        item = get_product_by_id(pid)
        if not item:
            return
        txt = "📦 " + item["name"] + "\n\n💰 السعر: " + str(item["price"]) + " ريال\nℹ️ " + item["desc"] + "\n\nتبي تطلب هذا المنتج؟"
        await q.edit_message_text(txt, reply_markup=confirm_menu(item["id"]))

    elif data.startswith("confirm_"):
        pid = data[8:]
        item = get_product_by_id(pid)
        user = q.from_user
        oid = gen_order_id()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        orders = load_orders()
        orders[oid] = {
            "product": item["name"],
            "price": item["price"],
            "user_id": user.id,
            "username": user.username or "---",
            "name": user.full_name,
            "status": "قيد المعالجة",
            "time": now
        }
        save_orders(orders)
        txt = "✅ تم استلام طلبك!\n\n🔖 رقم الطلب: " + oid + "\n📦 " + item["name"] + "\n💰 " + str(item["price"]) + " ريال\n\n📲 سيتواصل معك فريقنا قريبا لاتمام الدفع والتسليم\n\n🕐 احتفظ برقم طلبك"
        await q.edit_message_text(txt, reply_markup=back_btn())
        try:
            admin_txt = "🔔 طلب جديد!\n\n🔖 " + oid + "\n👤 " + user.full_name + " (@" + (user.username or "---") + ")\n🆔 " + str(user.id) + "\n📦 " + item["name"] + "\n💰 " + str(item["price"]) + " ريال\n🕐 " + now
            sent = await ctx.bot.send_message(ADMIN_ID, admin_txt)
            RELAY_MAP[sent.message_id] = user.id
        except Exception as e:
            log.warning(e)

    elif data == "menu_track":
        ctx.user_data["waiting_track"] = True
        await q.edit_message_text("📦 ارسل رقم الطلب\nمثال: SH0001", reply_markup=back_btn())

    elif data == "menu_contact":
        user = q.from_user
        await q.edit_message_text(
            "🎧 الدعم الفني\n\nتم تحويلك لفريق الدعم\nسيتواصل معك احد المختصين خلال دقائق ⚡\n\n🕐 اوقات العمل: 9ص - 12م\n\nاو اكتب سؤالك هنا مباشرة 👇",
            reply_markup=back_btn()
        )
        try:
            support_txt = "🆘 طلب دعم فني!\n\n👤 " + user.full_name + "\n📱 @" + (user.username or "---") + "\n🆔 " + str(user.id) + "\n🕐 " + datetime.datetime.now().strftime("%Y-%m-%d %H:%M") + "\n\n💬 رد على هذه الرسالة للتواصل مع العميل مباشرة"
            sent = await ctx.bot.send_message(ADMIN_ID, support_txt)
            RELAY_MAP[sent.message_id] = user.id
        except Exception as e:
            log.warning(e)

async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    text = update.message.text.strip()

    # اذا الادمن رد على رسالة إشعار
    if user.id == ADMIN_ID and update.message.reply_to_message:
        replied_msg_id = update.message.reply_to_message.message_id
        if replied_msg_id in RELAY_MAP:
            target_user_id = RELAY_MAP[replied_msg_id]
            try:
                await ctx.bot.send_message(target_user_id, "👻 شبح ستور:\n\n" + text)
                await update.message.reply_text("✅ تم ارسال ردك للعميل")
            except Exception as e:
                await update.message.reply_text("❌ ما قدرت ارسل: " + str(e))
            return

    # اذا ادمن كتب بدون رد على رسالة
    if user.id == ADMIN_ID:
        await update.message.reply_text("💡 للرد على عميل، اضغط رد على رسالة الاشعار")
        return

    # تتبع الطلبات
    if ctx.user_data.get("waiting_track"):
        ctx.user_data.pop("waiting_track")
        orders = load_orders()
        oid = text.upper()
        if oid in orders:
            o = orders[oid]
            txt = "📦 طلب " + oid + "\n\n🛍️ " + o["product"] + "\n💰 " + str(o["price"]) + " ريال\n📋 الحالة: " + o["status"] + "\n🕐 " + o["time"]
            await update.message.reply_text(txt, reply_markup=back_btn())
        else:
            await update.message.reply_text("❌ رقم الطلب غير موجود\nتاكد من الرقم وحاول مجددا", reply_markup=back_btn())
        return

    # رسائل العملاء — توصل للادمن وClaude يرد
    try:
        relay_txt = "💬 رسالة من " + user.full_name + " (@" + (user.username or "---") + ")\n🆔 " + str(user.id) + "\n\n" + text + "\n\n💬 رد على هذه الرسالة للتواصل مع العميل مباشرة"
        sent = await ctx.bot.send_message(ADMIN_ID, relay_txt)
        RELAY_MAP[sent.message_id] = user.id
    except Exception as e:
        log.warning(e)

    # Claude يرد تلقائي
    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
    reply = ask_claude(text)
    if reply:
        await update.message.reply_text(reply, reply_markup=back_btn())
    else:
        await update.message.reply_text("عذرا حصل خطا، تواصل معنا مباشرة 🙏", reply_markup=back_btn())

async def admin_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or len(ctx.args) < 2:
        return
    oid = ctx.args[0].upper()
    status = " ".join(ctx.args[1:])
    orders = load_orders()
    if oid not in orders:
        await update.message.reply_text("❌ الطلب " + oid + " غير موجود")
        return
    orders[oid]["status"] = status
    save_orders(orders)
    try:
        await ctx.bot.send_message(orders[oid]["user_id"], "🔔 تحديث طلبك " + oid + "\n\n📋 الحالة: " + status)
    except Exception:
        pass
    await update.message.reply_text("✅ تم تحديث " + oid + " الى: " + status)

async def admin_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    orders = load_orders()
    if not orders:
        await update.message.reply_text("📭 لا يوجد طلبات")
        return
    msg = "📋 اخر الطلبات:\n\n"
    for oid, o in list(orders.items())[-20:]:
        msg += oid + " | " + o["product"] + " | " + o["status"] + "\n"
    await update.message.reply_text(msg)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("update", admin_update))
    app.add_handler(CommandHandler("orders", admin_orders))
    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    log.info("شبح ستور شغال!")
    app.run_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)

if __name__ == "__main__":
    main()
