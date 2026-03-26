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
            {"id": "sh_1", "name": "شاهد ملف شهر",    "price": 6.99,  "desc": "ملف خاص + ضمان"},
            {"id": "sh_2", "name": "شاهد إيميل شهر",   "price": 29.99, "desc": "إيميل خاص 4 ملفات"},
        ]
    },
    "netflix": {
        "name": "🎬 نتفليكس",
        "items": [
            {"id": "nf_1", "name": "نتفليكس ملف شهر",   "price": 8.99,  "desc": "ملف خاص + ضمان"},
            {"id": "nf_2", "name": "نتفليكس إيميل شهر",  "price": 32.99, "desc": "إيميل خاص 4 ملفات"},
        ]
    }
}

ORDERS_FILE = "orders.json"
logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

# ── Health Server عشان Railway ما يوقف البوت ──
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

# ── مساعدات ──
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

# ── لوحات المفاتيح ──
def main_menu():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("🛍️ المنتجات والأسعار", callback_data="menu_products")],
        [InlineKeyboardButton("🛒 اطلب الآن", callback_data="menu_order"),
         InlineKeyboardButton("📦 تتبع طلبي", callback_data="menu_track")],
        [InlineKeyboardButton("💬 تواصل معنا", callback_data="menu_contact")],
    ])

def categories_menu():
    btns = [[InlineKeyboardButton(cat["name"], callback_data=f"cat_{k}")] for k, cat in PRODUCTS.items()]
    btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_main")])
    return InlineKeyboardMarkup(btns)

def products_menu(cat_key):
    cat = PRODUCTS[cat_key]
    btns = [[InlineKeyboardButton(f"{i['name']} — {i['price']} ريال", callback_data=f"item_{i['id']}")] for i in cat["items"]]
    btns.append([InlineKeyboardButton("🔙 رجوع", callback_data="menu_products")])
    return InlineKeyboardMarkup(btns)

def confirm_menu(pid):
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ تأكيد الطلب", callback_data=f"confirm_{pid}")],
        [InlineKeyboardButton("❌ إلغاء", callback_data="menu_products")],
    ])

def back_btn():
    return InlineKeyboardMarkup([[InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_main")]])

# ── Claude AI ──
def ask_claude(question):
    try:
        client = anthropic.Anthropic(api_key=CLAUDE_KEY)
        msg = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=400,
            system="""أنت موظف دعم عملاء لمتجر شبح ستور الرقمي في السعودية.
المتجر يبيع: شاهد VIP ونتفليكس بخيارين ملف وإيميل خاص.
ردودك قصيرة وواضحة باللهجة الخليجية.""",
            messages=[{"role": "user", "content": question}]
        )
        return msg.content[0].text
    except:
        return "عذراً حصل خطأ، تواصل معنا مباشرة 🙏"

# ── Handlers ──
async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👻 *أهلاً بك في شبح ستور!*\n\nمتجرك الموثوق للاشتراكات الرقمية 🎬\n\nاختر من القائمة 👇",
        parse_mode="Markdown", reply_markup=main_menu()
    )

async def button_handler(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q, data = update.callback_query, update.callback_query.data
    await q.answer()

    if data == "back_main":
        await q.edit_message_text("👻 *أهلاً بك في شبح ستور!*\n\nاختر من القائمة 👇", parse_mode="Markdown", reply_markup=main_menu())
    elif data in ("menu_products", "menu_order"):
        await q.edit_message_text("🛍️ *اختر الفئة:*", parse_mode="Markdown", reply_markup=categories_menu())
    elif data.startswith("cat_"):
        cat = PRODUCTS[data[4:]]
        await q.edit_message_text(f"{cat['name']}\n\nاختر المنتج 👇", parse_mode="Markdown", reply_markup=products_menu(data[4:]))
    elif data.startswith("item_"):
        item = get_product_by_id(data[5:])
        if not item: return
        await q.edit_message_text(
            f"📦 *{item['name']}*\n\n💰 السعر: *{item['price']} ريال*\nℹ️ {item['desc']}\n\nتبي تطلب؟",
            parse_mode="Markdown", reply_markup=confirm_menu(item["id"])
        )
    elif data.startswith("confirm_"):
        item = get_product_by_id(data[8:])
        user = q.from_user
        oid = gen_order_id()
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        orders = load_orders()
        orders[oid] = {
            "product": item["name"], "price": item["price"],
            "user_id": user.id, "username": user.username or "—",
            "name": user.full_name, "status": "قيد المعالجة", "time": now
        }
        save_orders(orders)
        await q.edit_message_text(
            f"✅ *تم استلام طلبك!*\n\n🔖 رقم الطلب: `{oid}`\n📦 {item['name']}\n💰 {item[
