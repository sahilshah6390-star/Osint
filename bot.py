from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import aiohttp
import json
import secrets
import string
import asyncio
import sqlite3
import datetime
import os

# Bot Configuration
API_ID = "12328511"
API_HASH = "87785246d0520062edab3afd987f637a"
BOT_TOKEN = "8438833923:AAGzxM2EhBtaNWr-mM-jHsKi0x3b81saphw"
AUTHORIZED_USERS = {6512242172,}

app = Client("dt_osint_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# Database Setup
DB_PATH = "bot_database.db"
conn = sqlite3.connect(DB_PATH)
cursor = conn.cursor()

# Create Tables
cursor.execute(
    """CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    daily_searches INTEGER DEFAULT 0,
    last_search_date TEXT,
    credits INTEGER DEFAULT 0,
    referrals INTEGER DEFAULT 0,
    unlimited INTEGER DEFAULT 0,
    banned INTEGER DEFAULT 0
)"""
)

cursor.execute(
    """CREATE TABLE IF NOT EXISTS referrals (
    referrer_id INTEGER,
    referred_id INTEGER,
    UNIQUE(referrer_id, referred_id)
)"""
)

cursor.execute(
    """CREATE TABLE IF NOT EXISTS redeem_codes (
    code TEXT PRIMARY KEY,
    credits INTEGER DEFAULT 0,
    unlimited INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at TEXT,
    claimed_by INTEGER,
    claimed_at TEXT
)"""
)

conn.commit()

# Ensure banned column exists for legacy databases
try:
    cursor.execute("ALTER TABLE users ADD COLUMN banned INTEGER DEFAULT 0")
    conn.commit()
except Exception:
    pass

# Constants
REQUIRED_CHANNELS = ["@Kasukabe00", "@Kasukabe01"]
DAILY_LIMIT = 5
REFERRALS_PER_CREDIT = 3
UNLIMITED_PRICE = 900
LOG_CHAT_ID = -1002763953812


def save_config():
    with open("bot_config.txt", "w") as f:
        f.write(f"DAILY_LIMIT={DAILY_LIMIT}\n")
        f.write(f"REFERRALS_PER_CREDIT={REFERRALS_PER_CREDIT}\n")
        f.write(f"UNLIMITED_PRICE={UNLIMITED_PRICE}\n")


def load_config():
    global DAILY_LIMIT, REFERRALS_PER_CREDIT, UNLIMITED_PRICE
    try:
        with open("bot_config.txt", "r") as f:
            for line in f:
                key, value = line.strip().split("=")
                if key == "DAILY_LIMIT":
                    DAILY_LIMIT = int(value)
                elif key == "REFERRALS_PER_CREDIT":
                    REFERRALS_PER_CREDIT = int(value)
                elif key == "UNLIMITED_PRICE":
                    UNLIMITED_PRICE = int(value)
    except FileNotFoundError:
        save_config()


load_config()

def referral_link(user_id: int) -> str:
    return f"https://t.me/UrNumberinfobot?start=ref_{user_id}"


def referral_share_link(user_id: int) -> str:
    return (
        "https://t.me/share/url?url=https%3A//t.me/UrNumberinfobot%3Fstart%3Dref_"
        f"{user_id}&text=Join%20this%20USERNAMETONUMBER%20bot%20for%20free%20searches%20"
        "and%20earn%20diamonds%20per%20referral%21%20Start%20here%3A"
    )


async def log_event(text: str):
    try:
        await app.send_message(LOG_CHAT_ID, text, disable_web_page_preview=True)
    except Exception as e:
        print(f"Log send failed: {e}")


def user_mention(user_id: int) -> str:
    return f"[user](tg://user?id={user_id})"


def generate_code(length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def is_banned(user_id: int) -> bool:
    user = get_user(user_id)
    return bool(user and len(user) > 6 and user[6])


def create_redeem_code(code: str, credits: int, unlimited: int, created_by: int) -> bool:
    try:
        cursor.execute(
            "INSERT INTO redeem_codes (code, credits, unlimited, created_by, created_at) VALUES (?, ?, ?, ?, ?)",
            (code, credits, unlimited, created_by, datetime.datetime.utcnow().isoformat()),
        )
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False


def claim_redeem_code(code: str, claimer_id: int):
    cursor.execute("SELECT credits, unlimited, claimed_by FROM redeem_codes WHERE code = ?", (code,))
    row = cursor.fetchone()
    if not row:
        return "missing", None
    credits, unlimited, claimed_by = row
    if claimed_by:
        return "claimed", None
    cursor.execute(
        "UPDATE redeem_codes SET claimed_by = ?, claimed_at = ? WHERE code = ?",
        (claimer_id, datetime.datetime.utcnow().isoformat(), code),
    )
    conn.commit()
    return "ok", {"credits": credits, "unlimited": unlimited}

def start_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎯 Refer Friends",
                    url=referral_share_link(user_id),
                ),
                InlineKeyboardButton("➕ Add to Group", url="https://t.me/UrNumberinfobot?startgroup=true"),
            ],
            [InlineKeyboardButton("📣 Updates", url="https://t.me/Kasukabe00"), InlineKeyboardButton("🛠 Support", url="https://t.me/Kasukabe01")],
            [InlineKeyboardButton("🆘 Help", callback_data="show_help")],
        ]
    )


def help_keyboard(back_target: str = "start") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add to Group", url="https://t.me/UrNumberinfobot?startgroup=true"), InlineKeyboardButton("📣 Updates", url="https://t.me/Kasukabe00")],
            [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/offx_sahil")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"back:{back_target}")],
        ]
    )


def join_keyboard(context: str = "start") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📣 Updates", url="https://t.me/Kasukabe00"), InlineKeyboardButton("🛠 Support", url="https://t.me/Kasukabe01")],
            [InlineKeyboardButton("✅ I've Joined", callback_data=f"verify_join:{context}")],
            [InlineKeyboardButton("🔙 Back", callback_data=f"back:{context}")],
        ]
    )


def join_message_text() -> str:
    return (
        "🚪 **Access Restricted**\n\n"
        "Join both channels to continue:\n"
        "• @Kasukabe00\n"
        "• @Kasukabe01\n\n"
        "Tap **✅ I've Joined** after you subscribe."
    )


def welcome_message_text() -> str:
    return (
        "✨ **Welcome to SS OSINT Bot!**\n\n"
        "🔎 **Instant User → Number Lookup**\n"
        "📲 Convert Telegram IDs or usernames to phone numbers\n"
        "⚡ Fast, clean, and reliable\n\n"
        f"🎁 **{DAILY_LIMIT} free searches every day**\n"
        "🤝 **Refer friends to earn extra credits**\n"
        f"♾️ **Go unlimited for Rs {UNLIMITED_PRICE}**\n\n"
        "📜 **Commands:**\n"
        "/lookup <userid|@username> - Search user info\n"
        "/redeem - View your stats\n"
        "/leaderboard - Top referrers\n"
        "/refer - Get your referral link\n"
        "/claim <code> - Redeem a code\n"
        "/help - Support and FAQs\n\n"
        "🚀 **Use /lookup in any group to get started!**"
    )


# Utility Functions
async def delete_message_after(message, delay):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except Exception:
        pass


def get_user(user_id):
    cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
    return cursor.fetchone()


def update_user(user_id, **kwargs):
    user = get_user(user_id)
    if not user:
        cursor.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        user = (user_id, 0, None, 0, 0, 0, 0)

    updates = []
    params = []
    for key, value in kwargs.items():
        if key in ["daily_searches", "credits", "referrals", "unlimited", "banned"]:
            updates.append(f"{key} = ?")
            params.append(value)
        elif key == "last_search_date":
            updates.append("last_search_date = ?")
            params.append(value)

    if updates:
        params.append(user_id)
        cursor.execute(f'UPDATE users SET {", ".join(updates)} WHERE user_id = ?', params)
        conn.commit()


async def check_channel_membership(user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await app.get_chat_member(channel, user_id)
            if member.status in ("left", "kicked", "banned"):
                return False
        except Exception as e:
            print(f"Channel check failed for {channel}: {e}")
            return False
    return True


def reset_daily_searches_if_needed(user_id):
    user = get_user(user_id)
    if user:
        today = str(datetime.date.today())
        if user[2] != today:
            update_user(user_id, daily_searches=0, last_search_date=today)


def can_perform_search(user_id):
    if user_id in AUTHORIZED_USERS:
        return True

    user = get_user(user_id)
    if not user:
        return True

    if user[5]:  # unlimited
        return True

    if user[3] > 0:  # credits
        return True

    reset_daily_searches_if_needed(user_id)
    user = get_user(user_id)
    return user[1] < DAILY_LIMIT


def deduct_search_cost(user_id):
    if user_id in AUTHORIZED_USERS:
        return

    user = get_user(user_id)
    if user and user[5]:  # unlimited
        return

    if user and user[3] > 0:
        update_user(user_id, credits=user[3] - 1)
        return

    reset_daily_searches_if_needed(user_id)
    user = get_user(user_id)
    if user:
        update_user(
            user_id,
            daily_searches=user[1] + 1,
            last_search_date=str(datetime.date.today()),
        )


async def process_referral(referrer_id, referred_id):
    cursor.execute("INSERT OR IGNORE INTO referrals VALUES (?, ?)", (referrer_id, referred_id))
    conn.commit()

    cursor.execute("SELECT COUNT(*) FROM referrals WHERE referrer_id = ?", (referrer_id,))
    count = cursor.fetchone()[0]
    update_user(referrer_id, referrals=count)

    credits_earned = count // REFERRALS_PER_CREDIT
    user = get_user(referrer_id)
    if user and credits_earned > user[3]:
        update_user(referrer_id, credits=credits_earned)

    await log_event(f"👥 Referral recorded: {user_mention(referrer_id)} referred {user_mention(referred_id)} (total {count})")


# API Functions
async def fetch_user_phone(user_id):
    try:
        url = f"https://encore.toxictanji0503.workers.dev/tguidtonumv2?uid={user_id}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    return json.loads(data)
    except Exception as e:
        print(f"User ID API Error: {e}")
    return None


async def fetch_phone_details(phone):
    try:
        url = f"https://no-info-api.onrender.com/num/{phone}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    return json.loads(data)
    except Exception as e:
        print(f"Phone Details API Error: {e}")
    return None


async def fetch_username_phone(username):
    try:
        url = f"https://encore.toxictanji0503.workers.dev/@ceobitco?username={username}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.text()
                    return json.loads(data)
    except Exception as e:
        print(f"Username API Error: {e}")
    return None


async def execute_lookup(message, user_id, target: str, source: str = "lookup", is_test: bool = False):
    try:
        await log_event(f"🔍 {source.capitalize()} requested by {user_mention(user_id)} in chat {message.chat.id}")
        status_msg = await message.reply("🌐 **Connecting to data sources...**")
        await asyncio.sleep(2)
        await status_msg.edit("🛰️ **Scanning databases...**")
        await asyncio.sleep(2)
        await status_msg.edit("🧠 **Processing OSINT data...**")
        await asyncio.sleep(2)

        telegram_data = None
        if is_test:
            telegram_data = await fetch_user_phone(6512242172)
        else:
            if target.isdigit():
                telegram_data = await fetch_user_phone(int(target))
            elif target.startswith("@"):
                telegram_data = await fetch_username_phone(target[1:])

        details_data = None
        if telegram_data and telegram_data.get("success"):
            phone = telegram_data.get("number", "")
            if phone:
                details_data = await fetch_phone_details(phone)

        result, keyboard = format_search_result(telegram_data, details_data, user_id)
        title = "🧪 **Test Result:**" if is_test else "🔍 **Lookup Result:**"
        await status_msg.edit(f"{title}\n\n{result}", reply_markup=keyboard)

        await log_event(
            f"✅ {source.capitalize()} done for {user_mention(user_id)} target `{target}` "
            f"{'found data' if telegram_data else 'no data'}"
        )
        asyncio.create_task(delete_message_after(status_msg, 300))

    except Exception as e:
        print(f"{source.capitalize()} Error: {e}")
        await log_event(f"❌ {source.capitalize()} error for {user_mention(user_id)}: {e}")
        await message.reply("❌ **An error occurred. Please try again.**")


def format_search_result(telegram_data, details_data, user_id):
    result = ""
    if telegram_data and telegram_data.get("success"):
        phone = telegram_data.get("number", "")
        result += f"📞 **Phone Number:** `{phone}`\n\n"

    if details_data:
        result += f"📑 **Phone Details:**\n```json\n{json.dumps(details_data, indent=2)}\n```\n\n"

    if result:
        result += "✅ **OSINT Complete!**\n\n🤖 **Bot by @offx_sahil**"
    else:
        result = "⚠️ **No data found**"

    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "🎯 Refer Friends",
                    url=referral_share_link(user_id),
                ),
                InlineKeyboardButton("➕ Add to Group", url="https://t.me/UrNumberinfobot?startgroup=true"),
            ],
            [InlineKeyboardButton("📣 Updates", url="https://t.me/Kasukabe00"), InlineKeyboardButton("🛠 Support", url="https://t.me/Kasukabe01")],
            [InlineKeyboardButton("📞 Contact Admin", url="https://t.me/offx_sahil")],
        ]
    )

    return result, keyboard


# Handlers
@app.on_message(filters.command("start"))
async def start_handler(client, message):
    user_id = message.from_user.id
    args = message.text.split()

    if is_banned(user_id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return

    if len(args) > 1 and args[1].startswith("ref_"):
        try:
            referrer_id = int(args[1][4:])
            await process_referral(referrer_id, user_id)
        except Exception:
            pass

    if user_id not in AUTHORIZED_USERS and not await check_channel_membership(user_id):
        await message.reply(join_message_text(), reply_markup=join_keyboard("start"))
        await log_event(f"🚪 Start blocked (join required) for {user_mention(user_id)}")
        return

    await log_event(f"🚀 /start by {user_mention(user_id)}")
    await message.reply(welcome_message_text(), reply_markup=start_keyboard(user_id))


@app.on_message(filters.command("lookup") & filters.private)
async def lookup_private_handler(client, message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return

    if user_id in AUTHORIZED_USERS:
        args = message.text.split()
        if len(args) < 2:
            await message.reply("ℹ️ **Usage:** /lookup <userid> or /lookup @username")
            return
        target = args[1]
        await execute_lookup(message, user_id, target, source="lookup-dm")
        return

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add me to your group", url="https://t.me/UrNumberinfobot?startgroup=true")],
            [InlineKeyboardButton("🛠 Support", url="https://t.me/Kasukabe00")],
        ]
    )
    await message.reply(
        "🚧 **Group only.** Add me to a group and use `/lookup` there.\n\n"
        "Need help? Tap Support.",
        reply_markup=keyboard,
    )


@app.on_message(filters.command("test") & filters.private)
async def test_private_handler(client, message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return

    if user_id in AUTHORIZED_USERS:
        await execute_lookup(message, user_id, "6512242172", source="test-dm", is_test=True)
        return

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("➕ Add me to your group", url="https://t.me/UrNumberinfobot?startgroup=true")],
            [InlineKeyboardButton("🛠 Support", url="https://t.me/Kasukabe01")],
        ]
    )
    await message.reply(
        "🚧 **Group only.** Add me to a group and use `/test` there.\n\n"
        "Need help? Tap Support.",
        reply_markup=keyboard,
    )


@app.on_message(filters.command("lookup") & filters.group)
async def lookup_handler(client, message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return

    if user_id not in AUTHORIZED_USERS and not await check_channel_membership(user_id):
        join_message = (
            "🚪 **Join required channels to use /lookup**\n\n"
            "Subscribe to @Kasukabe00 and @Kasukabe01, then tap ✅."
        )
        await message.reply(join_message, reply_markup=join_keyboard("lookup"))
        await log_event(f"🚪 Lookup blocked (join required) for {user_mention(user_id)}")
        return

    if not can_perform_search(user_id):
        limit_message = (
            "🚫 **Daily Limit Reached**\n\n"
            f"You've used all {DAILY_LIMIT} free searches today.\n\n"
            "🎯 Earn more by referring friends:\n"
            f"• {REFERRALS_PER_CREDIT} referrals = 1 search credit\n\n"
            f"♾️ Or get unlimited for Rs {UNLIMITED_PRICE}."
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎯 Share Referral Link", url=referral_share_link(user_id)),
                    InlineKeyboardButton("♾️ Buy Unlimited", url="https://t.me/offx_sahil"),
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="back:start")],
        ]
        )
        await message.reply(limit_message, reply_markup=keyboard)
        return

    deduct_search_cost(user_id)

    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ **Usage:** /lookup <userid> or /lookup @username")
        return

    target = args[1]
    await execute_lookup(message, user_id, target, source="lookup")


@app.on_message(filters.command("test") & filters.group)
async def test_handler(client, message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return

    if user_id not in AUTHORIZED_USERS and not await check_channel_membership(user_id):
        join_message = (
            "🚪 **Join required channels to use /test**\n\n"
            "Subscribe to @Kasukabe00 and @Kasukabe01, then tap ✅."
        )
        await message.reply(join_message, reply_markup=join_keyboard("test"))
        await log_event(f"🚪 Test blocked (join required) for {user_mention(user_id)}")
        return

    if not can_perform_search(user_id):
        limit_message = (
            "🚫 **Daily Limit Reached**\n\n"
            f"You've used all {DAILY_LIMIT} free searches today.\n\n"
            "🎯 Earn more by referring friends:\n"
            f"• {REFERRALS_PER_CREDIT} referrals = 1 search credit\n\n"
            f"♾️ Or get unlimited for Rs {UNLIMITED_PRICE}."
        )
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("🎯 Share Referral Link", url=referral_share_link(user_id)),
                    InlineKeyboardButton("♾️ Buy Unlimited", url="https://t.me/offx_sahil"),
                ],
                [InlineKeyboardButton("🔙 Back", callback_data="back:start")],
        ]
        )
        await message.reply(limit_message, reply_markup=keyboard)
        return

    deduct_search_cost(user_id)

    await execute_lookup(message, user_id, "6512242172", source="test", is_test=True)


@app.on_message(filters.command("redeem"))
async def redeem_handler(client, message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return
    user = get_user(user_id)

    if not user:
        await message.reply("⚠️ **No data found. Use /start first.**")
        return

    referrals = user[4]
    credits_earned = referrals // REFERRALS_PER_CREDIT
    next_credit = REFERRALS_PER_CREDIT - (referrals % REFERRALS_PER_CREDIT)

    stats_message = (
        "📊 **Your Statistics:**\n\n"
        f"🎯 **Total Referrals:** {referrals}\n"
        f"💎 **Credits Earned:** {credits_earned}\n"
        f"⏭️ **Referrals for Next Credit:** {next_credit}\n\n"
        "🔗 **Your Referral Link:**\n"
        f"{referral_link(user_id)}\n"
        f"Share link: {referral_share_link(user_id)}\n\n"
        f"♾️ **Buy Unlimited Credits:** Rs {UNLIMITED_PRICE} - Contact @offx_sahil"
    )

    await message.reply(stats_message, disable_web_page_preview=True)
    await log_event(f"📊 Stats viewed by {user_mention(user_id)} (refs {referrals}, credits {credits_earned})")


@app.on_message(filters.command("refer"))
async def refer_handler(client, message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return
    text = (
        "🎯 **Your Referral Link**\n\n"
        f"Link: {referral_link(user_id)}\n"
        "Share this link to earn credits. Each successful referral counts toward the leaderboard."
    )
    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🎯 Share Now", url=referral_share_link(user_id))],
            [InlineKeyboardButton("🔙 Back", callback_data="back:start")],
        ]
    )
    await message.reply(text, reply_markup=keyboard, disable_web_page_preview=True)
    await log_event(f"📣 Referral link sent to {user_mention(user_id)}")


@app.on_message(filters.command("leaderboard"))
async def leaderboard_handler(client, message):
    if is_banned(message.from_user.id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return
    cursor.execute("SELECT referrer_id, COUNT(*) as c FROM referrals GROUP BY referrer_id ORDER BY c DESC LIMIT 10")
    rows = cursor.fetchall()
    if not rows:
        await message.reply("🏆 **Leaderboard**\n\nNo referrals yet. Be the first!")
        return

    lines = []
    for idx, (uid, count) in enumerate(rows, start=1):
        lines.append(f"{idx}. {user_mention(uid)} — {count} referrals")

    text = "🏆 **Top Referrers**\n\n" + "\n".join(lines)
    await message.reply(text, disable_web_page_preview=True)
    await log_event(f"🏆 Leaderboard viewed by {user_mention(message.from_user.id)}")


@app.on_message(filters.command("claim"))
async def claim_handler(client, message):
    user_id = message.from_user.id
    if is_banned(user_id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return

    if not await check_channel_membership(user_id):
        await message.reply(join_message_text(), reply_markup=join_keyboard("start"))
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ **Usage:** /claim <code>")
        return

    code = args[1].strip()
    status, data = claim_redeem_code(code, user_id)
    if status == "missing":
        await message.reply("⚠️ **Invalid code.**")
        return
    if status == "claimed":
        await message.reply("⚠️ **This code has already been used.**")
        return

    credits_added = data["credits"]
    unlimited = data["unlimited"]
    if unlimited:
        update_user(user_id, unlimited=1)
    if credits_added:
        user = get_user(user_id)
        current = user[3] if user else 0
        update_user(user_id, credits=current + credits_added)

    reward_text = []
    if credits_added:
        reward_text.append(f"+{credits_added} credits")
    if unlimited:
        reward_text.append("unlimited access")
    rewards = " and ".join(reward_text) if reward_text else "no rewards"

    await message.reply(f"🎉 **Redeemed!** You received {rewards}.")
    await log_event(f"🎟️ Code `{code}` claimed by {user_mention(user_id)} ({rewards})")


@app.on_callback_query()
async def callback_handler(client, callback):
    user_id = callback.from_user.id
    data = callback.data

    if data.startswith("verify_join"):
        context = data.split(":", 1)[1] if ":" in data else "start"
        if await check_channel_membership(user_id):
            await log_event(f"✅ Join verified for {user_mention(user_id)} (context {context})")
            if context == "lookup":
                await callback.message.edit_text(
                    "✅ **Access Granted!**\n\nRun /lookup again in the group.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back:start")]]),
                )
            elif context == "test":
                await callback.message.edit_text(
                    "✅ **Access Granted!**\n\nRun /test again in the group.",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back:start")]]),
                )
            else:
                await callback.message.edit_text(welcome_message_text(), reply_markup=start_keyboard(user_id))
        else:
            await log_event(f"⚠️ Join verification failed for {user_mention(user_id)} (context {context})")
            await callback.answer("⚠️ You haven't joined all required channels yet.", show_alert=True)

    elif data.startswith("back:") or data == "back_to_start":
        context = "start" if data == "back_to_start" else data.split(":", 1)[1]
        if context == "start":
            if await check_channel_membership(user_id):
                await callback.message.edit_text(welcome_message_text(), reply_markup=start_keyboard(user_id))
            else:
                await callback.message.edit_text(join_message_text(), reply_markup=join_keyboard("start"))
        elif context in ("lookup", "test"):
            if await check_channel_membership(user_id):
                await callback.message.edit_text(
                    "🔁 **Ready! Run the command again in chat.**",
                    reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back:start")]]),
                )
            else:
                await callback.message.edit_text(join_message_text(), reply_markup=join_keyboard(context))
        elif context == "help":
            await callback.message.edit_text(welcome_message_text(), reply_markup=start_keyboard(user_id))
        elif context == "admin":
            admin_text = "🛡️ **Admin Panel**\n\nChoose an action:"
            admin_keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("💎 Add Credits", callback_data="admin_add_credits"), InlineKeyboardButton("🧹 Remove Credits", callback_data="admin_remove_credits")],
                    [InlineKeyboardButton("♾️ Set Unlimited", callback_data="admin_set_unlimited"), InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
                    [InlineKeyboardButton("⚙️ Bot Settings", callback_data="admin_settings"), InlineKeyboardButton("📈 User Stats", callback_data="admin_stats")],
                    [InlineKeyboardButton("🔙 Back", callback_data="back:start")],
                ]
            )
            await callback.message.edit_text(admin_text, reply_markup=admin_keyboard)
        else:
            await callback.message.edit_text(welcome_message_text(), reply_markup=start_keyboard(user_id))

    elif data == "retry_lookup":
        await callback.message.edit_text("🔁 **Please try your /lookup command again.**")

    elif data == "show_help":
        help_text = (
            "💞 **DT OSINT Bot Help**\n\n"
            "📜 **Commands:**\n"
            "/start - Welcome message\n"
            "/lookup <userid|@username> - Search user info\n"
            "/redeem - View your stats\n"
            "/refer - Get your referral link\n"
            "/leaderboard - Top referrers\n"
            "/claim <code> - Redeem a code\n"
            "/help - Show this help\n\n"
            "💡 **How it works:**\n"
            f"• {DAILY_LIMIT} free searches daily\n"
            f"• {REFERRALS_PER_CREDIT} referrals = 1 credit\n"
            f"• Unlimited plan: Rs {UNLIMITED_PRICE}\n\n"
            "📞 **Support:** @datatraceadmin"
        )

        await callback.message.edit_text(help_text, reply_markup=help_keyboard("start"))

    elif callback.data.startswith("admin_"):
        if user_id not in AUTHORIZED_USERS:
            await callback.answer("❌ Access denied.", show_alert=True)
            return

        action = callback.data[6:]  # Remove "admin_"

        if action == "add_credits":
            await callback.message.edit_text("💎 **Add Credits**\n\nSend: /addcredits <user_id> <amount>")
        elif action == "remove_credits":
            await callback.message.edit_text("🧹 **Remove Credits**\n\nSend: /removecredits <user_id> <amount>")
        elif action == "set_unlimited":
            await callback.message.edit_text("♾️ **Set Unlimited**\n\nSend: /setunlimited <user_id>")
        elif action == "broadcast":
            await callback.message.edit_text("📢 **Broadcast Message**\n\nSend: /broadcast <message>")
        elif action == "settings":
            settings_text = (
                "⚙️ **Bot Settings**\n\n"
                f"🎁 **Daily Limit:** {DAILY_LIMIT} searches\n"
                f"🎯 **Referral Ratio:** {REFERRALS_PER_CREDIT} refs = 1 credit\n"
                f"♾️ **Unlimited Price:** Rs {UNLIMITED_PRICE}\n\n"
                "🛠️ **Setup Commands:**\n"
                "/set_daily_limit <number>\n"
                "/set_referral_ratio <number>\n"
                "/set_unlimited_price <amount>"
            )

            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_back")]])
            await callback.message.edit_text(settings_text, reply_markup=keyboard)

        elif action == "stats":
            cursor.execute("SELECT COUNT(*) FROM users")
            total_users = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM users WHERE unlimited = 1")
            unlimited_users = cursor.fetchone()[0]
            cursor.execute("SELECT SUM(credits) FROM users")
            total_credits = cursor.fetchone()[0] or 0

            stats_text = (
                "📈 **Bot Statistics**\n\n"
                f"👥 **Total Users:** {total_users}\n"
                f"♾️ **Unlimited Users:** {unlimited_users}\n"
                f"💳 **Total Credits:** {total_credits}"
            )

            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Back to Admin", callback_data="admin_back")]])
            await callback.message.edit_text(stats_text, reply_markup=keyboard)

        elif action == "back":
            admin_text = "🛡️ **Admin Panel**\n\nChoose an action:"

            keyboard = InlineKeyboardMarkup(
                [
                    [InlineKeyboardButton("💎 Add Credits", callback_data="admin_add_credits")],
                    [InlineKeyboardButton("🧹 Remove Credits", callback_data="admin_remove_credits")],
                    [InlineKeyboardButton("♾️ Set Unlimited", callback_data="admin_set_unlimited")],
                    [InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
                    [InlineKeyboardButton("⚙️ Bot Settings", callback_data="admin_settings")],
                    [InlineKeyboardButton("📈 User Stats", callback_data="admin_stats")],
                ]
            )
            await callback.message.edit_text(admin_text, reply_markup=keyboard)


# Admin Commands
@app.on_message(filters.command("addcredits"))
async def add_credits_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.reply("ℹ️ **Usage:** /addcredits <user_id> <amount>")
        return

    try:
        target_user = int(args[1])
        amount = int(args[2])
        user = get_user(target_user)
        current = user[3] if user else 0
        update_user(target_user, credits=current + amount)
        await message.reply(f"✅ **Added {amount} credits to user {target_user}. Total: {current + amount}**")
    except ValueError:
        await message.reply("⚠️ **Invalid user ID or amount.**")


@app.on_message(filters.command("removecredits"))
async def remove_credits_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.reply("ℹ️ **Usage:** /removecredits <user_id> <amount>")
        return

    try:
        target_user = int(args[1])
        amount = int(args[2])
        user = get_user(target_user)
        current = user[3] if user else 0
        new_amount = max(0, current - amount)
        update_user(target_user, credits=new_amount)
        await message.reply(f"✅ **Removed {amount} credits from user {target_user}. Total: {new_amount}**")
    except ValueError:
        await message.reply("⚠️ **Invalid user ID or amount.**")


@app.on_message(filters.command("setunlimited"))
async def set_unlimited_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ **Usage:** /setunlimited <user_id>")
        return

    try:
        target_user = int(args[1])
        update_user(target_user, unlimited=1)
        await message.reply(f"✅ **Set unlimited access for user {target_user}.**")
    except ValueError:
        await message.reply("⚠️ **Invalid user ID.**")


@app.on_message(filters.command("broadcast"))
async def broadcast_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split(maxsplit=1)
    if len(args) < 2:
        await message.reply("ℹ️ **Usage:** /broadcast <message>")
        return

    broadcast_message = args[1]
    cursor.execute("SELECT user_id FROM users")
    user_ids = [row[0] for row in cursor.fetchall()]

    sent_count = 0
    failed_count = 0

    for target_id in user_ids:
        try:
            await app.send_message(
                target_id, f"📢 **Broadcast:**\n\n{broadcast_message}", disable_web_page_preview=True
            )
            sent_count += 1
            await asyncio.sleep(0.1)  # Rate limiting
        except Exception as e:
            print(f"Broadcast failed for {target_id}: {e}")
            failed_count += 1

    await message.reply(f"✅ **Broadcast Complete**\n\n📨 Sent: {sent_count}\n⚠️ Failed: {failed_count}")


@app.on_message(filters.command("createredeem"))
async def create_redeem_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 3:
        await message.reply("ℹ️ **Usage:** /createredeem <code> <credits|unlimited>")
        return

    code = args[1].strip()
    value = args[2].strip().lower()
    unlimited = 0
    credits = 0

    if value in {"unlimited", "∞", "inf", "ul"}:
        unlimited = 1
    else:
        try:
            credits = int(value)
        except ValueError:
            await message.reply("⚠️ **Invalid amount.** Use a number or 'unlimited'.")
            return

    created = create_redeem_code(code, credits, unlimited, message.from_user.id)
    if not created:
        await message.reply("⚠️ **Code already exists. Use a different code.**")
        return

    reward_text = "unlimited access" if unlimited else f"{credits} credits"
    await message.reply(f"✅ **Redeem code created:** `{code}` for {reward_text}")
    await log_event(f"🎟️ Redeem code `{code}` created by {user_mention(message.from_user.id)} for {reward_text}")


@app.on_message(filters.command("createcode"))
async def create_code_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ **Usage:** /createcode <credits>\n\nExample: `/createcode 5`")
        return

    try:
        credits = int(args[1])
        if credits <= 0:
            raise ValueError
    except ValueError:
        await message.reply("⚠️ **Credits must be a positive number.**")
        return

    code = generate_code()
    # Ensure uniqueness
    while not create_redeem_code(code, credits, 0, message.from_user.id):
        code = generate_code()

    await message.reply(f"✅ **Code generated:** `{code}`\nValue: {credits} credits\nRedeem with `/claim {code}`")
    await log_event(f"🎟️ Auto-code `{code}` ({credits} credits) created by {user_mention(message.from_user.id)}")


@app.on_message(filters.command("ban"))
async def ban_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ **Usage:** /ban <user_id>")
        return

    try:
        target_user = int(args[1])
        update_user(target_user, banned=1)
        await message.reply(f"⛔ **User {target_user} banned.**")
        await log_event(f"⛔ User {user_mention(target_user)} banned by {user_mention(message.from_user.id)}")
    except ValueError:
        await message.reply("⚠️ **Invalid user ID.**")


@app.on_message(filters.command("unban"))
async def unban_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply("ℹ️ **Usage:** /unban <user_id>")
        return

    try:
        target_user = int(args[1])
        update_user(target_user, banned=0)
        await message.reply(f"✅ **User {target_user} unbanned.**")
        await log_event(f"✅ User {user_mention(target_user)} unbanned by {user_mention(message.from_user.id)}")
    except ValueError:
        await message.reply("⚠️ **Invalid user ID.**")


@app.on_message(filters.command("help"))
async def help_handler(client, message):
    if is_banned(message.from_user.id):
        await message.reply("⛔ **You are banned from using this bot.**")
        return
    help_text = (
        "💞 **SS OSINT Bot Help**\n\n"
        "📜 **Commands:**\n"
        "/start - Welcome message\n"
        "/lookup <userid|@username> - Search user info\n"
        "/redeem - View your stats\n"
        "/refer - Get your referral link\n"
        "/leaderboard - Top referrers\n"
        "/claim <code> - Redeem a code\n"
        "/help - Show this help\n\n"
        "💡 **How it works:**\n"
        f"• {DAILY_LIMIT} free searches daily\n"
        f"• {REFERRALS_PER_CREDIT} referrals = 1 credit\n"
        f"• Unlimited plan: Rs {UNLIMITED_PRICE}\n\n"
        "📞 **Support:** @offx_sahil"
    )

    await message.reply(help_text, reply_markup=help_keyboard("start"))


@app.on_message(filters.command("admin"))
async def admin_handler(client, message):
    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Access denied. Admin only.**")
        return

    admin_text = "🛡️ **Admin Panel**\n\nChoose an action:"

    keyboard = InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("💎 Add Credits", callback_data="admin_add_credits"), InlineKeyboardButton("🧹 Remove Credits", callback_data="admin_remove_credits")],
            [InlineKeyboardButton("♾️ Set Unlimited", callback_data="admin_set_unlimited"), InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")],
            [InlineKeyboardButton("⚙️ Bot Settings", callback_data="admin_settings"), InlineKeyboardButton("📈 User Stats", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 Back", callback_data="back:start")],
        ]
    )

    await message.reply(admin_text, reply_markup=keyboard)


# Setup Commands
@app.on_message(filters.command("set_daily_limit"))
async def set_daily_limit_handler(client, message):
    global DAILY_LIMIT

    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply(f"ℹ️ **Usage:** /set_daily_limit <number>\n\nCurrent: {DAILY_LIMIT}")
        return

    try:
        DAILY_LIMIT = int(args[1])
        save_config()
        await message.reply(f"✅ **Daily limit set to {DAILY_LIMIT}**")
    except ValueError:
        await message.reply("⚠️ **Invalid number.**")


@app.on_message(filters.command("set_referral_ratio"))
async def set_referral_ratio_handler(client, message):
    global REFERRALS_PER_CREDIT

    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply(f"ℹ️ **Usage:** `/set_referral_ratio <number>`\n\nCurrent: {REFERRALS_PER_CREDIT}")
        return

    try:
        REFERRALS_PER_CREDIT = int(args[1])
        save_config()
        await message.reply(f"✅ **Referral ratio set to {REFERRALS_PER_CREDIT}**")
    except ValueError:
        await message.reply("⚠️ **Invalid number.**")


@app.on_message(filters.command("set_unlimited_price"))
async def set_unlimited_price_handler(client, message):
    global UNLIMITED_PRICE

    if message.from_user.id not in AUTHORIZED_USERS:
        await message.reply("❌ **Only authorized users.**")
        return

    args = message.text.split()
    if len(args) < 2:
        await message.reply(f"ℹ️ **Usage:** `/set_unlimited_price <amount>`\n\nCurrent: Rs {UNLIMITED_PRICE}")
        return

    try:
        UNLIMITED_PRICE = int(args[1])
        save_config()
        await message.reply(f"✅ **Unlimited price set to Rs {UNLIMITED_PRICE}**")
    except ValueError:
        await message.reply("⚠️ **Invalid amount.**")


if __name__ == "__main__":
    print("DT OSINT Bot Starting...")
    print(f"Daily {DAILY_LIMIT} free searches")
    print("Referral system active")
    print("Auto-delete results after 5 minutes")

    try:
        app.run()
    finally:
        conn.close()
