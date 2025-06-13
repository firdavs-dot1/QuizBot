import json
import random
import logging
import time
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from telegram.error import Conflict, TelegramError

# Bot token va owner ID
API_TOKEN = "8147306205:AAHouy6JXwWGsDIGH9emJ0fXrRA-AsszO3A"
OWNER_ID = 5728779626  # O'zingizning Telegram user ID'ingiz bilan almashtiring

# Logging sozlamalari
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Savollar faylini yuklash
try:
    with open("questions.json", encoding="utf-8") as f:
        all_questions = json.load(f)
except FileNotFoundError:
    logger.error("questions.json file not found!")
    all_questions = {}

# Foydalanuvchi sessiyalari va natijalari
user_sessions = {}
user_results = {}

# Xato boshqaruvi
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error(f"Update {update} caused error: {context.error}")
    if isinstance(context.error, Conflict):
        if update and hasattr(update, "message"):
            await update.message.reply_text(
                "⚠️ Bot xatosi: boshqa nusxa ishlayapti. Iltimos, boshqa bot instansiyalarini to‘xtating va qayta urinib ko‘ring."
            )
    elif isinstance(context.error, TelegramError):
        if update and hasattr(update, "message"):
            await update.message.reply_text("⚠️ Telegram bilan aloqa xatosi. Keyinroq urinib ko‘ring.")

# /start buyrug‘i
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_sessions:
        keyboard = [
            [InlineKeyboardButton("Davom etish", callback_data="continue_quiz")],
            [InlineKeyboardButton("Qayta boshlash", callback_data="restart_quiz")],
            [InlineKeyboardButton("Testni yakunlash", callback_data="end_quiz")]
        ]
        await update.message.reply_text(
            "⚠️ Sizda faol test mavjud! Quyidagilardan birini tanlang:\n/stop buyrug‘i bilan viktorinani to‘xtatishingiz mumkin.",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
    else:
        await show_part_selection(update.message.reply_text)

# /stop buyrug‘i
async def stop(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id in user_sessions:
        await show_result(update.message.chat.id, context, user_id)
        await update.message.reply_text("✅ Viktorina to‘xtatildi. /start orqali yangi viktorina boshlashingiz mumkin.")
    else:
        await update.message.reply_text("⚠️ Hozirda faol viktorina yo‘q. /start orqali boshlang.")

# /results buyrug‘i (faqat owner uchun)
async def results(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    if user_id != OWNER_ID:
        await update.message.reply_text("🚫 Bu buyruq faqat bot egasi uchun mavjud.")
        logger.warning(f"Unauthorized /results access attempt by user {user_id}")
        return

    if not user_results:
        await update.message.reply_text("📊 Hozircha hech kim viktorinani o‘tmagan.")
        return

    result_text = "📊 **Viktorina natijalari**:\n\n"
    for user_id, parts in user_results.items():
        result_text += f"👤 Foydalanuvchi ID: {user_id}\n"
        for part, data in parts.items():
            m, s = divmod(data["time"], 60)
            percentage = (data["correct"] / data["total"]) * 100
            result_text += (
                f"  📚 Qism: {part}\n"
                f"  ✅ To‘g‘ri: {data['correct']}/{data['total']} ({percentage:.1f}%)\n"
                f"  🕒 Vaqt: {m} daqiqa {s} soniya\n\n"
            )
    await update.message.reply_text(result_text)

# Bo‘lim tanlash menyusi
async def show_part_selection(send_func):
    keyboard = [
        [InlineKeyboardButton(name, callback_data=part)]
        for name, part in {
            "1-qism (1–25)": "part1",
            "2-qism (26–50)": "part2",
            "3-qism (51–75)": "part3",
            "4-qism (76–100)": "part4",
            "5-qism (101–125)": "part5",
            "6-qism (126–150)": "part6",
            "7-qism (151–175)": "part7",
            "8-qism (176–200)": "part8"
        }.items()
    ]
    await send_func("📚 Viktorina qismini tanlang:", reply_markup=InlineKeyboardMarkup(keyboard))

# Sessiya tanlovini boshqarish
async def handle_session_choice(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    choice = query.data

    if choice == "continue_quiz":
        await query.edit_message_text("✅ Viktorina davom etmoqda...")
        await send_question(query.message.chat.id, context, user_id)
    elif choice == "restart_quiz":
        user_sessions.pop(user_id, None)
        await show_part_selection(query.edit_message_text)
    elif choice == "end_quiz":
        await show_result(query.message.chat.id, context, user_id)
        await query.edit_message_text("✅ Viktorina yakunlandi. /start orqali yangi viktorina boshlashingiz mumkin.")

# Viktorinani boshlash
async def start_quiz(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    part = query.data
    questions = all_questions.get(part, [])

    if not questions:
        await query.edit_message_text("😕 Bu bo‘limda savollar yo‘q.")
        return

    # Avvalgi natijani ko‘rsatish
    previous = user_results.get(query.from_user.id, {}).get(part)
    if previous:
        m, s = divmod(previous["time"], 60)
        await query.edit_message_text(
            f"📊 Avvalgi natijangiz:\n✅ To‘g‘ri: {previous['correct']} / {previous['total']}\n🕒 Vaqt: {m} daqiqa {s} soniya\n\nEndi viktorinani qayta boshlaymiz:"
        )
    else:
        await query.edit_message_text("🎉 Viktorina boshlandi!")

    # Savollarni aralashtirish
    random.shuffle(questions)
    for q in questions:
        correct = q["options"][q["correct_option"]]
        random.shuffle(q["options"])
        q["correct_option"] = q["options"].index(correct)

    user_sessions[query.from_user.id] = {
        "questions": questions,
        "current": 0,
        "correct": 0,
        "start_time": time.time(),
        "part": part
    }

    await send_question(query.message.chat.id, context, query.from_user.id)

# Savol yuborish
async def send_question(chat_id, context: ContextTypes.DEFAULT_TYPE, user_id):
    session = user_sessions.get(user_id)
    if not session:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Viktorina faol emas. /start orqali yangi viktorina boshlang.")
        return

    i = session["current"]
    if i >= len(session["questions"]):
        await show_result(chat_id, context, user_id)
        return

    q = session["questions"][i]
    keyboard = [[InlineKeyboardButton(opt, callback_data=str(j))] for j, opt in enumerate(q["options"])]
    text = f"❓ {i + 1}/{len(session['questions'])}. {q['question']}"
    await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=InlineKeyboardMarkup(keyboard))

# Javobni boshqarish
async def handle_answer(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    session = user_sessions.get(user_id)

    if not session:
        await query.answer("⚠️ Viktorina faol emas. /start orqali boshlang!", show_alert=True)
        return

    await query.answer()
    question = session["questions"][session["current"]]
    user_choice = int(query.data)
    correct_option = question["correct_option"]

    # Javoblar natijasini ko‘rsatish
    options_text = []
    for idx, opt in enumerate(question["options"]):
        prefix = (
            "✅" if idx == correct_option and idx == user_choice else
            "✔️" if idx == correct_option else
            "❌" if idx == user_choice else
            "➖"
        )
        options_text.append(f"{prefix} {opt}")

    if user_choice == correct_option:
        session["correct"] += 1

    text = (
        f"❓ {session['current'] + 1}/{len(session['questions'])}. {question['question']}\n\n" +
        ("✅ To‘g‘ri!" if user_choice == correct_option else "❌ Xato!") + "\n\n" +
        "\n".join(options_text)
    )

    try:
        await query.message.edit_text(text)
    except Exception as e:
        logger.warning(f"Xabarni o‘zgartirib bo‘lmadi: {e}")

    session["current"] += 1
    await asyncio.sleep(1.5)
    await send_question(query.message.chat.id, context, user_id)

# Natijani ko‘rsatish
async def show_result(chat_id, context: ContextTypes.DEFAULT_TYPE, user_id):
    session = user_sessions.get(user_id)
    if not session:
        await context.bot.send_message(chat_id=chat_id, text="⚠️ Yakunlash uchun faol viktorina yo‘q.")
        return

    total = len(session["questions"])
    correct = session["correct"]
    wrong = total - correct
    elapsed = int(time.time() - session["start_time"])
    m, s = divmod(elapsed, 60)

    percentage = (correct / total) * 100
    msg = f"""
🎉 **Viktorina natijasi**:
✅ **To‘g‘ri javoblar**: {correct}/{total} ({percentage:.1f}%)
❌ **Xato javoblar**: {wrong}
🕒 **Sarflangan vaqt**: {m} daqiqa {s} soniya
"""

    await context.bot.send_message(chat_id=chat_id, text=msg)

    # Natijani saqlash
    user_results.setdefault(user_id, {})[session["part"]] = {
        "correct": correct,
        "total": total,
        "time": elapsed
    }
    user_sessions.pop(user_id, None)

    # Yaxshiroq natija uchun taklif
    if percentage < 80:
        await context.bot.send_message(chat_id=chat_id, text="📚 Yana mashq qiling, natijangiz yaxshilanadi!")

# Botni ishga tushirish
async def main():
    app = None
    try:
        app = Application.builder().token(API_TOKEN).build()

        # Handlerlar
        app.add_handler(CallbackQueryHandler(handle_answer, pattern=r"^[0-3]+$"))
        app.add_handler(CallbackQueryHandler(start_quiz, pattern=r"^part[1-8]$"))
        app.add_handler(CallbackQueryHandler(handle_session_choice, pattern=r"^(continue_quiz|restart_quiz|end_quiz)$"))
        app.add_handler(CommandHandler("start", start))
        app.add_handler(CommandHandler("stop", stop))
        app.add_handler(CommandHandler("results", results))  # Yangi results handler
        app.add_error_handler(error_handler)

        logger.info("Bot muvaffaqiyat bilan ishga tushdi!")
        await app.initialize()
        await app.start()
        await app.updater.start_polling(allowed_updates=Update.ALL_TYPES, drop_pending_updates=True)
        # Keep the bot running
        while True:
            await asyncio.sleep(3600)  # Sleep for an hour to keep the loop alive
    except Conflict as e:
        logger.error(f"Conflict error: {e}")
        print(f"❌ Bot xatosi: Boshqa bot instansiyasi ishlayapti. Iltimos, boshqa instansiyalarni to‘xtating.")
    except Exception as e:
        logger.error(f"Botni ishga tushirishda xato: {e}")
        print(f"❌ Botni ishga tushirishda xato yuz berdi: {e}")
    finally:
        if app is not None:
            try:
                await app.updater.stop()
                await app.stop()
                await app.shutdown()
                logger.info("Bot muvaffaqiyat bilan to‘xtatildi.")
            except Exception as shutdown_error:
                logger.error(f"Botni to‘xtatishda xato: {shutdown_error}")

if __name__ == "__main__":
    try:
        # DeprecationWarning oldini olish uchun yangi event loop yaratamiz
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(main())
    except RuntimeError as e:
        logger.error(f"Event loop error: {e}")
        print(f"❌ Event loop xatosi: {e}")
    except KeyboardInterrupt:
        logger.info("Bot foydalanuvchi tomonidan to‘xtatildi.")
        print("✅ Bot to‘xtatildi.")
    finally:
        if not loop.is_closed():
            loop.close()
