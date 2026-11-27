import os
import re
import json
import time
import random
import threading
import telebot
from telebot import types
import requests
import asyncio
import queue
from datetime import datetime

# ==================== CONFIG ====================
BOT_TOKEN = "8832919810:AAFoY1KbQzWlxVFJ8hiv8SJfuh9bisKyx8Q"
ADMIN_IDS = {6124719642}

PROXY_FILE = "proxies.txt"
SITES_SHOPIFY = "sites_shopify.txt"
SITES_RAZOR = "sites_razor.txt"
SITES_ADYEN = "sites_adyen.txt"
SITES_CASHFREE = "sites_cashfree.txt"
PLAYERS_FILE = "players.txt"
MASS_CAP = 1000

bot = telebot.TeleBot(BOT_TOKEN)
STOP_CHECKER = threading.Event()

# ==================== FILE MANAGEMENT ====================
def load_list(file):
    if not os.path.exists(file): return []
    with open(file, "r", encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.startswith("#")]

def save_list(file, data):
    with open(file, "w", encoding="utf-8") as f:
        for item in data:
            f.write(item + "\n")

def load_players():
    return [int(x) for x in load_list(PLAYERS_FILE) if x.isdigit()]

def is_admin(uid):
    return uid in ADMIN_IDS

def is_player(uid):
    return is_admin(uid) or uid in load_players()

def _site_file(gate):
    if gate == "razor": return SITES_RAZOR
    if gate == "adyen": return SITES_ADYEN
    if gate == "cashfree": return SITES_CASHFREE
    return SITES_SHOPIFY

def load_sites(gate):
    return load_list(_site_file(gate))

def save_sites(gate, sites):
    save_list(_site_file(gate), sites)

# ==================== STATE MANAGEMENT ====================
user_states = {}
pending_files = {}

# ==================== CORE CHECKER ====================
def process_card(gate, site, combo, proxy):
    """Placeholder for the actual checking logic. 
    Returns (status, response_msg, price)"""
    # Simulate processing time
    time.sleep(random.uniform(1.5, 3.5))
    
    # In a real scenario, you would call your shopifyy, razor, etc. modules here.
    # For demonstration, we randomly return hits.
    rand = random.randint(1, 100)
    if rand > 90:
        return "CHARGED", "ORDER_PAID", f"{random.randint(10, 100)}.00"
    elif rand > 80:
        return "3DS", "3DS_REQUIRED", f"{random.randint(10, 100)}.00"
    elif rand > 70:
        return "INSUFFICIENT_FUNDS", "INSUFFICIENT_FUNDS", f"{random.randint(10, 100)}.00"
    else:
        return "BAD", "CARD_DECLINED", "0.00"

# ==================== MASS CHECKER THREAD ====================
def mass_checker_thread(msg, gate, site, combos, proxies):
    STOP_CHECKER.clear()
    hits = []
    total = len(combos)
    checked = 0
    start_time = time.time()
    
    for combo in combos:
        if STOP_CHECKER.is_set():
            break
            
        proxy = random.choice(proxies) if proxies else None
        status, response, price = process_card(gate, site, combo, proxy)
        checked += 1
        
        if status in ("CHARGED", "3DS", "INSUFFICIENT_FUNDS"):
            hit_msg = (
                f"🔥 **{status}**\n\n"
                f"💳 `{combo}`\n"
                f"🏪 Site: `{site}`\n"
                f"💰 Price: `${price}`\n"
                f"📝 Resp: `{response}`\n"
                f"🌐 Proxy: `{proxy or 'None'}`\n"
                f"⚙️ Gate: `{gate.upper()}`\n\n"
                f"💠 {CREDIT}"
            )
            try:
                sent = bot.send_message(msg.chat.id, hit_msg, parse_mode='Markdown')
                hits.append(combo)
                # Auto-pin charged hits
                if status == "CHARGED":
                    bot.pin_chat_message(msg.chat.id, sent.message_id)
            except: pass
            
        # Update progress every 5 combos
        if checked % 5 == 0 or checked == total:
            pct = int((checked / total) * 100)
            elapsed = int(time.time() - start_time)
            text = (
                f"💳 **Mass {gate.upper()} Check**\n"
                f"📊 Progress: `{checked}/{total}` ({pct}%)\n"
                f"✅ Hits: `{len(hits)}` | ⏱️ `{elapsed}s`"
            )
            try: bot.edit_message_text(text, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
            except: pass
            
    if hits:
        bot.send_message(msg.chat.id, f"✅ **Done!** Found {len(hits)} hits.", parse_mode='Markdown')

# ==================== MENUS ====================
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛒 Shopify", callback_data="gate_shopify"),
        types.InlineKeyboardButton("💳 Razorpay", callback_data="gate_razor"),
        types.InlineKeyboardButton("💳 Adyen", callback_data="gate_adyen"),
        types.InlineKeyboardButton("💳 Cashfree", callback_data="gate_cashfree")
    )
    markup.add(
        types.InlineKeyboardButton("⚙️ Manage Sites", callback_data="menu_sites"),
        types.InlineKeyboardButton("🌐 Proxies", callback_data="menu_proxies")
    )
    if is_admin:
        markup.add(types.InlineKeyboardButton("👥 Players", callback_data="menu_players"))
    return markup

def sites_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🛒 Shopify Sites", callback_data="site_shopify"),
        types.InlineKeyboardButton("💳 Razor Sites", callback_data="site_razor"),
        types.InlineKeyboardButton("💳 Adyen Sites", callback_data="site_adyen"),
        types.InlineKeyboardButton("💳 Cashfree Sites", callback_data="site_cashfree")
    )
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return markup

def gate_action_menu(gate):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add Site", callback_data=f"addsite_{gate}"),
        types.InlineKeyboardButton("📜 List Sites", callback_data=f"listsite_{gate}"),
        types.InlineKeyboardButton("🧹 Clear Sites", callback_data=f"clearsite_{gate}"),
        types.InlineKeyboardButton("🔙 Back", callback_data="menu_sites")
    )
    return markup

# ==================== BOT HANDLERS ====================
@bot.message_handler(commands=['start'])
def start(message):
    text = "👋 **Welcome to the Multi-Gateway CC Checker**\n\nSelect a gateway to begin checking, or manage your sites."
    bot.reply_to(message, text, reply_markup=main_menu(), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_handler(call):
    data = call.data
    uid = call.from_user.id
    
    if data == "menu_main":
        bot.edit_message_text("⚙️ **Main Menu**", call.message.chat.id, call.message.message_id, reply_markup=main_menu(), parse_mode='Markdown')
        
    elif data == "menu_sites":
        bot.edit_message_text("🏪 **Site Manager**", call.message.chat.id, call.message.message_id, reply_markup=sites_menu(), parse_mode='Markdown')
        
    elif data.startswith("site_"):
        gate = data.split("_")[1]
        bot.edit_message_text(f"⚙️ **Manage {gate.upper()} Sites**", call.message.chat.id, call.message.message_id, reply_markup=gate_action_menu(gate), parse_mode='Markdown')
        
    elif data.startswith("listsite_"):
        gate = data.split("_")[1]
        sites = load_sites(gate)
        text = f"📜 **{gate.upper()} Sites ({len(sites)})**\n\n" + "\n".join([f"`{s}`" for s in sites[:20]])
        if len(sites) > 20: text += f"\n...and {len(sites)-20} more."
        if not sites: text = "❌ No sites saved."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, reply_markup=gate_action_menu(gate), parse_mode='Markdown')
        
    elif data.startswith("addsite_"):
        gate = data.split("_")[1]
        user_states[uid] = f"awaiting_site_{gate}"
        bot.edit_message_text(f"➕ **Send the URL for {gate.upper()}**", call.message.chat.id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("❌ Cancel", callback_data=f"site_{gate}")))
        
    elif data.startswith("clearsite_"):
        gate = data.split("_")[1]
        save_sites(gate, [])
        bot.answer_callback_query(call.id, f"✅ {gate.upper()} sites cleared.")
        bot.edit_message_text(f"⚙️ **Manage {gate.upper()} Sites**", call.message.chat.id, call.message.message_id, reply_markup=gate_action_menu(gate), parse_mode='Markdown')

    elif data.startswith("gate_"):
        gate = data.split("_")[1]
        sites = load_sites(gate)
        if not sites:
            bot.answer_callback_query(call.id, f"❌ No {gate.upper()} sites saved.", show_alert=True)
            return
        user_states[uid] = f"awaiting_combos_{gate}"
        bot.edit_message_text(f"📁 **Send a `.txt` file with combos for {gate.upper()}**\n\nOr paste them in chat.", call.message.chat.id, call.message.message_id, reply_markup=types.InlineKeyboardMarkup().add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_main")))

# ==================== INPUT HANDLERS ====================
@bot.message_handler(content_types=['document'])
def handle_document(message):
    uid = message.from_user.id
    state = user_states.get(uid, "")
    
    if state.startswith("awaiting_combos_"):
        gate = state.split("_")[2]
        user_states[uid] = None
        
        doc = message.document
        if doc.file_size > 20 * 1024 * 1024:
            bot.reply_to(message, "❌ File too large (Max 20MB).")
            return
            
        pending_files[message.message_id] = doc.file_id
        markup = types.InlineKeyboardMarkup(row_width=2)
        markup.add(
            types.InlineKeyboardButton("🚀 Start No Proxy", callback_data=f"start_np_{gate}_{message.message_id}"),
            types.InlineKeyboardButton("🌐 Start With Proxy", callback_data=f"start_p_{gate}_{message.message_id}")
        )
        bot.reply_to(message, f"📁 **File Detected for {gate.upper()}!**\n\nChoose mode:", reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(func=lambda msg: user_states.get(msg.from_user.id, "").startswith("awaiting_site_"))
def handle_site_input(message):
    uid = message.from_user.id
    state = user_states.get(uid, "")
    gate = state.split("_")[2]
    user_states[uid] = None
    
    url = message.text.strip()
    if not url.startswith("http"): url = "https://" + url
    
    sites = load_sites(gate)
    if url not in sites:
        sites.append(url)
        save_sites(gate, sites)
        bot.reply_to(message, f"✅ Added `{url}` to {gate.upper()}.", reply_markup=gate_action_menu(gate), parse_mode='Markdown')
    else:
        bot.reply_to(message, f"⚠️ Site already exists in {gate.upper()}.", reply_markup=gate_action_menu(gate), parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: call.data.startswith("start_"))
def handle_start(call):
    data = call.data
    parts = data.split("_")
    
    is_proxy = parts[1] == "p"
    gate = parts[2]
    msg_id = int(parts[3])
    
    file_id = pending_files.get(msg_id)
    if not file_id:
        bot.answer_callback_query(call.id, "❌ File expired.")
        return
        
    bot.answer_callback_query(call.id, "🚀 Starting...")
    bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
    
    # Download file
    try:
        file_info = bot.get_file(file_id)
        content = bot.download_file(file_info.file_path).decode('utf-8', errors='ignore')
        combos = [line.strip() for line in content.splitlines() if "|" in line or ":" in line]
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", chat_id=call.message.chat.id, message_id=call.message.message_id)
        return
        
    if not combos:
        bot.edit_message_text("❌ No valid combos found in file.", chat_id=call.message.chat.id, message_id=call.message.message_id)
        return
        
    proxies = load_list(PROXY_FILE) if is_proxy else []
    site = load_sites(gate)[0] # Use the first site in the list
    
    bot.edit_message_text(f"🚀 **Started {gate.upper()} Check**\n\nTotal: `{len(combos)}`\nMode: `{'Proxy' if is_proxy else 'Direct'}`", chat_id=call.message.chat.id, message_id=call.message.message_id, parse_mode='Markdown')
    
    t = threading.Thread(target=mass_checker_thread, args=(call.message, gate, site, combos, proxies))
    t.start()

if __name__ == "__main__":
    print("Starting bot...")
    bot.infinity_polling()