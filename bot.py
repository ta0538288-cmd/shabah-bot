import logging
import os
import json
import datetime
import threading
import anthropic
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, filters, ContextTypes,
)

BOT_TOKEN  = "8695004416:AAFTA6FPAJZrd6jG0HNJuW7a6WJk4fO67Jg"
CLAUDE_KEY = "sk-ant-api03-PJew3M2NlFGIlgnJbD2q2u5yWathzMKnb-DD15W4l5y0LkfCjvQv2KTladgKQDKqJvO-hwr_YZqD9hpPFjgJ8_2Q-RJcPfQAA"
ADMIN_ID   = 5103468033

PRODUCTS = {
    "shahid": {
        "name": "👻 شاهد VIP",
        "items": [
            {"id": "sh_1", "name": "شاهد ملف شهر",   "price": 6.99,  "desc": "ملف خاص + ضمان"},
            {"id": "sh_2", "name": "شاهد ايميل شهر",  "price": 29.99, "desc": "ايميل خاص 4 ملفات"},
        ]
    },
    "netflix": {
        "name": "🎬 نتفليكس",
        "items": [
            {"id": "nf_1", "name": "نتفليكس ملف شهر",  "price": 8.99,  "desc": "ملف خاص + ضمان"},
            {"id": "nf_2", "name": "نتفليكس ايميل شهر", "price": 32.99, "desc": "ايميل خاص 4 ملفات"},
        ]
    }
}

ORDERS_FILE = "orders.json"
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
        for item in cat["items"]:
            if item["id"] == pid:
                return item
    return None

def gen_order_id():
    return f"SH{len(load_orders()) + 1:04d}"

def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("المنتجات والاسعار", callback_data="menu_products")],
        [InlineKeyboardButton("اطلب الان", callback_data="menu_order"),
         InlineKeyboardButton("تتبع طلبي", callback_data="menu_track")],
        [InlineKeyboardButton("تواصل معنا", callback_data="menu_contact")],
    ])

def categories_menu():
    btns = [[InlineKeyboardButton(cat["name"], callback_data="cat_" + k)] for k, cat in PRODUCTS.items()]
    btns.append([InlineKeyboardButton("رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(btns)

def products_menu(cat_key):
    cat = PRODUCTS[cat_key]
    btns = []
    for i in cat["items"]:
        btns.append([InlineKeyboardButton(i["name"] + " - " + str(i["price"]) + " ريال", callback_data="item_" + i["id"])])
    btns.append([InlineKeyboardButton("رجوع", callback_data="menu_products")])
    return InlineKeyboardMarkup(btns)

def confirm_menu(pid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("تاكيد الطلب", callback_data="confirm_" + pid)],
        [InlineKeyboardButton("الغاء", callback_data="menu_products")],
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("القائمة الرئيسية", callback_data="back_main")]])

def ask_claude(question):
    try:
        client = anthropic.Anthropic(api_key=CLAUDE_KEY)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system="انت موظف دعم عملاء لمتجر شبح ستور الرقمي في السعودية. المتجر يبيع شاهد VIP ونتفليكس بخيارين ملف وايميل خاص. ردودك قصيرة وواضحة باللهجة الخليجية.",
            messages=[{"role": "user", "content": question}]
        )
        return msg.content[0].text
    except Exception as e:
        log.error(e)
        return "عذرا حصل خطا، تواصل معنا مباشرة"

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "اهلا بك في شبح ستور!\n\nمتجرك الموثوق للاشتراكات الرقمية\n\nاختر من القائمة",
        reply_markup=main_menu()
    )

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data
    await q.answer()

    if data == "back_main":
        await q.edit_message_text("اهلا بك في شبح ستور!\n\nاختر من القائمة", reply_markup=main_menu())

    elif data == "menu_products" or data == "menu_order":
        await q.edit_message_text("اختر الفئة:", reply_markup=categories_menu())

    elif data.startswith("cat_"):
        cat_key = data[4:]
        cat = PRODUCTS[cat_key]
        await q.edit_message_text(cat["name"] + "\n\nاختر المنتج", reply_markup=products_menu(cat_key))

    elif data.startswith("item_"):
        pid = data[5:]
        item = get_product_by_id(pid)
        if not item:
            return
        txt = "المنتج: " + item["name"] + "\nالسعر: " + str(item["price"]) + " ريال\n" + item["desc"] + "\n\nتبي تطلب؟"
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
        txt = "تم استلام طلبك!\n\nرقم الطلب: " + oid + "\nالمنتج: " + item["name"] + "\nالمبلغ: " + str(item["price"]) + " ريال\n\nسيتواصل معك فريقنا قريبا"
        await q.edit_message_text(txt, reply_markup=back_btn())
        try:
            admin_txt = "طلب جديد!\n\nرقم: " + oid + "\nالعميل: " + user.full_name + "\nالمنتج: " + item["name"] + "\nالمبلغ: " + str(item["price"]) + " ريال\nالوقت: " + now
            await ctx.bot.send_message(ADMIN_ID, admin_txt)
        except Exception as e:
            log.warning(e)

    elif data == "menu_track":
        ctx.user_data["waiting_track"] = True
        await q.edit_message_text("ارسل رقم الطلب مثال SH0001", reply_markup=back_btn())

    elif data == "menu_contact":
        await q.edit_message_text("تواصل معنا\n\nاوقات العمل: 9 صباحا - 12 منتصف الليل\n\naكتب سؤالك هنا", reply_markup=back_btn())

async def message_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if ctx.user_data.get("waiting_track"):
        ctx.user_data.pop("waiting_track")
        orders = load_orders()
        oid = text.upper()
        if oid in orders:
            o = orders[oid]
            txt = "طلب " + oid + "\n\nالمنتج: " + o["product"] + "\nالمبلغ: " + str(o["price"]) + " ريال\nالحالة: " + o["status"]
            await update.message.reply_text(txt, reply_markup=back_btn())
        else:
            await update.message.reply_text("رقم الطلب غير موجود", reply_markup=back_btn())
        return
    await ctx.bot.send_chat_action(update.effective_chat.id, "typing")
    await update.message.reply_text(ask_claude(text), reply_markup=back_btn())

async def admin_update(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID or len(ctx.args) < 2:
        return
    oid = ctx.args[0].upper()
    status = " ".join(ctx.args[1:])
    orders = load_orders()
    if oid not in orders:
        await update.message.reply_text("الطلب " + oid + " غير موجود")
        return
    orders[oid]["status"] = status
    save_orders(orders)
    try:
        await ctx.bot.send_message(orders[oid]["user_id"], "تحديث طلبك " + oid + "\nالحالة: " + status)
    except Exception:
        pass
    await update.message.reply_text("تم تحديث " + oid)

async def admin_orders(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    orders = load_orders()
    if not orders:
        await update.message.reply_text("لا يوجد طلبات")
        return
    msg = "الطلبات:\n\n"
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
