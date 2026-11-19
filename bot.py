import os
import asyncio
import logging
import aiosqlite
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder

# --- НАСТРОЙКИ ---
BOT_TOKEN = os.getenv("BOT_TOKEN", "ВАШ_НОВЫЙ_ТОКЕН")
ADMIN_ID = 8553406744  # Ваш ID

logging.basicConfig(level=logging.INFO)
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
DB_NAME = "shop.db"

# --- СОСТОЯНИЯ ---
class OrderForm(StatesGroup):
    name = State()
    phone = State()
    address = State()

# --- БАЗА ДАННЫХ ---
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS products (
                id INTEGER PRIMARY KEY,
                name TEXT,
                price INTEGER,
                description TEXT
            )
        """)
        # Добавляем тестовые товары (если их еще нет)
        async with db.execute("SELECT COUNT(*) FROM products") as cursor:
            count = await cursor.fetchone()
            if count[0] == 0:
                await db.execute("INSERT INTO products (name, price, description) VALUES (?, ?, ?)", ("Крем для рук", 500, "Увлажняющий крем 50мл"))
                await db.execute("INSERT INTO products (name, price, description) VALUES (?, ?, ?)", ("Маска для лица", 1200, "Очищающая маска с глиной"))
                await db.execute("INSERT INTO products (name, price, description) VALUES (?, ?, ?)", ("Шампунь", 800, "Профессиональный шампунь 250мл"))
        await db.commit()

# --- КЛАВИАТУРЫ ---
def get_main_menu():
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="🛍 Каталог товаров", callback_data="catalog"))
    builder.row(InlineKeyboardButton(text="🛒 Моя корзина", callback_data="cart"))
    return builder.as_markup()

def get_catalog_menu(products):
    builder = InlineKeyboardBuilder()
    for prod in products:
        builder.row(InlineKeyboardButton(text=f"{prod[1]} - {prod[2]}₽", callback_data=f"add_{prod[0]}"))
    builder.row(InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_menu"))
    return builder.as_markup()

# --- ОБРАБОТЧИКИ ---
@dp.callback_query(F.data == "cart")
async def show_cart(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])
    
    if not cart:
        await callback.message.edit_text("Ваша корзина пуста. 😔", reply_markup=get_main_menu())
        await callback.answer()
        return

    total = 0
    text = "🛒 *Ваша корзина:*\n\n"
    async with aiosqlite.connect(DB_NAME) as db:
        for prod_id in cart:
            async with db.execute("SELECT name, price FROM products WHERE id = ?", (prod_id,)) as cursor:
                prod = await cursor.fetchone()
                if prod:
                    text += f"- {prod[0]}: {prod[1]}₽\n"
                    total += prod[1]
    
    text += f"\n*Итого: {total}₽*"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout"))
    builder.row(InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_menu"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

@dp.callback_query(F.data == "back_to_menu")
async def back_to_menu(callback: types.CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("Главное меню:", reply_markup=get_main_menu())
    await callback.answer()

# КАТАЛОГ
@dp.callback_query(F.data == "catalog")
async def show_catalog(callback: types.CallbackQuery):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT id, name, price FROM products") as cursor:
            products = await cursor.fetchall()
    await callback.message.edit_text(
        "🛍 Наш каталог:\nНажмите на товар, чтобы добавить его в корзину:",
        reply_markup=get_catalog_menu(products)
    )
    await callback.answer()

@dp.callback_query(F.data.startswith("add_"))
async def add_to_cart(callback: types.CallbackQuery, state: FSMContext):
    prod_id = int(callback.data.split("_")[1])
    data = await state.get_data()
    cart = data.get("cart", [])
    cart.append(prod_id)
    await state.update_data(cart=cart)
    await callback.answer("Товар добавлен в корзину! ✅")

# КОРЗИНА
@dp.callback_query(F.data == "cart")
async def show_cart(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    cart = data.get("cart", [])
    
    if not cart:
        await callback.message.edit_text("Ваша корзина пуста. 😔", reply_markup=get_main_menu())
        await callback.answer()
        return

    total = 0
    text = "🛒 *Ваша корзина:*\n\n"
    async with aiosqlite.connect(DB_NAME) as db:
        for prod_id in cart:
            async with db.execute("SELECT name, price FROM products WHERE id = ?", (prod_id,)) as cursor:
                prod = await cursor.fetchone()
                if prod:
                    text += f"- {prod[0]}: {prod[1]}₽\n"
                    total += prod[1]
    
    text += f"\n*Итого: {total}₽*"
    
    builder = InlineKeyboardBuilder()
    builder.row(InlineKeyboardButton(text="✅ Оформить заказ", callback_data="checkout"))
    builder.row(InlineKeyboardButton(text="⬅️ В главное меню", callback_data="back_to_menu"))
    
    await callback.message.edit_text(text, reply_markup=builder.as_markup(), parse_mode="Markdown")
    await callback.answer()

# ОФОРМЛЕНИЕ ЗАКАЗА
@dp.callback_query(F.data == "checkout")
async def checkout_start(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    if not data.get("cart"):
        await callback.answer("Корзина пуста!", show_alert=True)
        return
    await callback.message.edit_text("Отлично! Как вас зовут?")
    await state.set_state(OrderForm.name)
    await callback.answer()

@dp.message(OrderForm.name)
async def process_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Напишите ваш номер телефона:")
    await state.set_state(OrderForm.phone)

@dp.message(OrderForm.phone)
async def process_phone(message: types.Message, state: FSMContext):
    await state.update_data(phone=message.text)
    await message.answer("Укажите адрес доставки:")
    await state.set_state(OrderForm.address)

@dp.message(OrderForm.address)
async def process_address(message: types.Message, state: FSMContext):
    await state.update_data(address=message.text)
    data = await state.get_data()
    
    cart_ids = data.get("cart", [])
    total = 0
    items_text = ""
    async with aiosqlite.connect(DB_NAME) as db:
        for prod_id in cart_ids:
            async with db.execute("SELECT name, price FROM products WHERE id = ?", (prod_id,)) as cursor:
                prod = await cursor.fetchone()
                if prod:
                    items_text += f"- {prod[0]}: {prod[1]}₽\n"
                    total += prod[1]

    text_to_admin = (
        f"🔥 *Новый заказ!*\n\n"
        f"👤 Имя: {data['name']}\n"
        f"📞 Телефон: {data['phone']}\n"
        f"📍 Адрес: {data['address']}\n"
        f"💬 От: @{message.from_user.username or message.from_user.id}\n\n"
        f"*Состав заказа:*\n{items_text}\n"
        f"*Итого: {total}₽*"
    )
    
    try:
        await bot.send_message(ADMIN_ID, text_to_admin, parse_mode="Markdown")
        await message.answer("Спасибо! Ваш заказ принят. Мы свяжемся с вами для подтверждения. ✅", reply_markup=get_main_menu())
    except Exception as e:
        await message.answer(f"Ошибка отправки админу: {e}")
        print(f"ОШИБКА: {e}")
    
    await state.clear()

# --- ВЕБ-СЕРВЕР ДЛЯ RENDER ---
async def handle(request):
    return web.Response(text="Shop Bot is running!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Web server started on port {port}")

async def main():
    await init_db()
    await start_web_server()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
