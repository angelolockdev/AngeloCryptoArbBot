import os
import asyncio
import ccxt
import time
import logging
import aiohttp  # Pour les notifications asynchrones
from datetime import datetime
from functools import wraps
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# -------------------------
# Configuration du Logging
# -------------------------
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# -------------------------
# Chargement des Variables d'Environnement
# -------------------------
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# -------------------------
# Configuration des Exchanges
# -------------------------
# Pour OKX (OKC) : la passphrase ("password") est obligatoire.
okc = ccxt.okx({
    'apiKey': os.getenv("OKX_API_KEY"),
    'secret': os.getenv("OKX_API_SECRET"),
    'password': os.getenv("OKX_PASSWORD"),
    # Pour tester en mode sandbox, décommentez et modifiez ces URLs :
    # 'urls': {
    #     'api': {
    #         'public': 'https://testnet.okx.com',
    #         'private': 'https://testnet.okx.com',
    #     },
    # },
})
kraken = ccxt.kraken({
    'apiKey': os.getenv("KRAKEN_API_KEY"),
    'secret': os.getenv("KRAKEN_API_SECRET"),
})

symbol = 'BTC/USDT'
risk_profit_threshold = 0.5  # Seuil de profit minimal ajusté à 0,5%
trade_amount = 0.001         # Montant du trade (ex: 0.001 BTC)
fee_rate = 0.001             # Frais de trading de 0,1% par transaction

# -------------------------
# Variables Globales pour les Boucles et Historiques
# -------------------------
loop_arbitrage_task = None         # Pour le mode simulation
loop_real_arbitrage_task = None      # Pour le mode réel

simulation_history = []            # Historique des transactions simulées
real_trade_history = []            # Historique des transactions réelles
initial_balances = {}              # Stocke les balances initiales pour le suivi des variations

# -------------------------
# Décorateur retry pour les appels API
# -------------------------
def retry(max_attempts=3, delay=1, backoff=2):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            attempts = 0
            current_delay = delay
            while attempts < max_attempts:
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    attempts += 1
                    logger.warning(f"Erreur dans {func.__name__}: {e} (tentative {attempts}/{max_attempts})")
                    time.sleep(current_delay)
                    current_delay *= backoff
            logger.error(f"Échec après {max_attempts} tentatives dans {func.__name__}.")
            return None
        return wrapper
    return decorator

# -------------------------
# Fonctions API avec retry
# -------------------------
@retry(max_attempts=3, delay=1)
def get_okc_price(symbol):
    ticker = okc.fetch_ticker(symbol)
    return ticker['ask'], ticker['bid']

@retry(max_attempts=3, delay=1)
def get_kraken_price(symbol):
    ticker = kraken.fetch_ticker(symbol)
    return ticker['ask'], ticker['bid']

@retry(max_attempts=3, delay=1)
def get_balance(exchange, currency="USDT"):
    bal = exchange.fetch_balance()
    return bal.get(currency, {}).get("free", 0)

# -------------------------
# Fonctions de Calcul
# -------------------------
def calc_spread(ask, bid):
    return bid - ask

def calc_profit_after_fees(price_in, price_out):
    effective_buy = price_in * (1 + fee_rate)
    effective_sell = price_out * (1 - fee_rate)
    profit = effective_sell - effective_buy
    profit_percent = (profit / effective_buy) * 100
    return profit, profit_percent

# -------------------------
# Notification Asynchrone via aiohttp
# -------------------------
async def async_send_telegram_message(message: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload) as resp:
                if resp.status != 200:
                    logger.error(f"Erreur lors de l'envoi asynchrone: {resp.status}")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi asynchrone du message: {e}")

# -------------------------
# Simulation de Trade (Mode Simulation)
# -------------------------
def execute_simulation_trade(action, platform, price):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if action == 'buy':
        logger.info(f"[SIMULATION] Achat sur {platform} à {price:.2f} USDT")
    elif action == 'sell':
        logger.info(f"[SIMULATION] Vente sur {platform} à {price:.2f} USDT")
    else:
        logger.warning("Action inconnue")

    simulation_history.append({
        "time": now,
        "action": action.upper(),
        "platform": platform.upper(),
        "price": price
    })

# -------------------------
# Exécution Réelle de Trade (Mode Réel)
# Avec vérification des soldes avant exécution
# -------------------------
def execute_real_trade(action, platform, price):
    try:
        if platform.lower() == 'okc':
            available = get_balance(okc, "USDT")
            if action == 'buy' and available < price * trade_amount:
                logger.error("Solde insuffisant sur OKC pour acheter.")
                return None
            if action == 'buy':
                order = okc.create_market_buy_order(symbol, trade_amount)
                logger.info(f"[REAL] Achat sur OKC : {order}")
                real_trade_history.append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": "BUY",
                    "platform": "OKC",
                    "price": price
                })
                return order
            elif action == 'sell':
                order = okc.create_market_sell_order(symbol, trade_amount)
                logger.info(f"[REAL] Vente sur OKC : {order}")
                real_trade_history.append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": "SELL",
                    "platform": "OKC",
                    "price": price
                })
                return order
        elif platform.lower() == 'kraken':
            available = get_balance(kraken, "USDT")
            if action == 'buy' and available < price * trade_amount:
                logger.error("Solde insuffisant sur Kraken pour acheter.")
                return None
            if action == 'buy':
                order = kraken.create_market_buy_order(symbol, trade_amount)
                logger.info(f"[REAL] Achat sur Kraken : {order}")
                real_trade_history.append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": "BUY",
                    "platform": "KRAKEN",
                    "price": price
                })
                return order
            elif action == 'sell':
                order = kraken.create_market_sell_order(symbol, trade_amount)
                logger.info(f"[REAL] Vente sur Kraken : {order}")
                real_trade_history.append({
                    "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": "SELL",
                    "platform": "KRAKEN",
                    "price": price
                })
                return order
    except Exception as e:
        logger.error(f"Erreur lors de l'exécution du trade réel sur {platform}: {e}")
        return None

# -------------------------
# Commandes Telegram - Mode Simulation
# -------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = (
        "🤖 <b>Bienvenue dans le bot d'arbitrage crypto amélioré !</b>\n\n"
        "<u>Commandes disponibles (Simulation) :</u>\n"
        "• <b>/status</b> - Affiche les prix et spreads (Simulation)\n"
        "• <b>/arbitrage</b> - Analyse et simule des opportunités d'arbitrage\n"
        "• <b>/account_status</b> - Affiche le capital et la variation (Simulation)\n"
        "• <b>/history</b> - Affiche l'historique des transactions simulées\n"
        "• <b>/start_loop</b> - Lance la vérification continue d'arbitrage (Simulation)\n"
        "• <b>/stop_loop</b> - Arrête la vérification continue (Simulation)\n\n"
        "<u>Commandes Réelles :</u>\n"
        "• <b>/real_status</b> - Affiche les prix pour trading réel\n"
        "• <b>/real_account</b> - Affiche le statut réel des comptes\n"
        "• <b>/real_history</b> - Affiche l'historique des transactions réelles\n"
        "• <b>/real_arbitrage</b> - Exécute de réelles opportunités d'arbitrage\n"
        "• <b>/start_real_loop</b> - Lance la vérification continue d'arbitrage (Réel)\n"
        "• <b>/stop_real_loop</b> - Arrête la vérification continue (Réel)\n"
        "• <b>/backtest</b> - Lance un test historique (Stub)\n"
        "• <b>/help</b> - Affiche ce message d'aide"
    )
    await update.effective_message.reply_text(message, parse_mode="HTML")

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    okc_data = get_okc_price(symbol)
    kraken_data = get_kraken_price(symbol)
    if not okc_data or not kraken_data:
        await update.effective_message.reply_text("<b>❗ Erreur lors de la récupération des prix.</b>", parse_mode="HTML")
        return

    okc_ask, okc_bid = okc_data
    kraken_ask, kraken_bid = kraken_data
    spread_okc_kraken = calc_spread(okc_ask, kraken_bid)
    spread_kraken_okc = calc_spread(kraken_ask, okc_bid)
    message = (
        f"<b>📊 Statut des Prix pour {symbol} (Simulation)</b>\n\n"
        f"<b>OKC (OKX) :</b>\n"
        f"• Ask : <b>{okc_ask:.2f} USDT</b>\n"
        f"• Bid : <b>{okc_bid:.2f} USDT</b>\n\n"
        f"<b>Kraken :</b>\n"
        f"• Ask : <b>{kraken_ask:.2f} USDT</b>\n"
        f"• Bid : <b>{kraken_bid:.2f} USDT</b>\n\n"
        f"<b>Spreads :</b>\n"
        f"• OKC → Kraken : <b>{spread_okc_kraken:.2f} USDT</b>\n"
        f"• Kraken → OKC : <b>{spread_kraken_okc:.2f} USDT</b>"
    )
    await update.effective_message.reply_text(message, parse_mode="HTML")

async def arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    okc_data = get_okc_price(symbol)
    kraken_data = get_kraken_price(symbol)
    if not okc_data or not kraken_data:
        await update.effective_message.reply_text("<b>❗ Erreur lors de la récupération des prix pour l'analyse.</b>", parse_mode="HTML")
        return

    okc_ask, okc_bid = okc_data
    kraken_ask, kraken_bid = kraken_data
    spread_okc_to_kraken = kraken_bid - okc_ask
    spread_kraken_to_okc = okc_bid - kraken_ask
    profit_okc_kraken, profit_pct_okc_kraken = calc_profit_after_fees(okc_ask, kraken_bid)
    profit_kraken_okc, profit_pct_kraken_okc = calc_profit_after_fees(kraken_ask, okc_bid)

    message = (
        f"<b>📊 Analyse d'Arbitrage pour {symbol} (Simulation)</b>\n\n"
        f"<b>OKC (OKX) :</b> Ask = <b>{okc_ask:.2f} USDT</b>, Bid = <b>{okc_bid:.2f} USDT</b>\n"
        f"<b>Kraken :</b> Ask = <b>{kraken_ask:.2f} USDT</b>, Bid = <b>{kraken_bid:.2f} USDT</b>\n\n"
        f"<b>Spreads :</b>\n"
        f"• OKC → Kraken : <b>{spread_okc_to_kraken:.2f} USDT</b>\n"
        f"• Kraken → OKC : <b>{spread_kraken_to_okc:.2f} USDT</b>\n\n"
        f"<b>Profit estimé après frais :</b>\n"
        f"• OKC → Kraken : <b>{profit_pct_okc_kraken:.2f}%</b> (Gain net : <b>{calc_profit_after_fees(okc_ask, kraken_bid)[0]:.2f} USDT</b>)\n"
        f"• Kraken → OKC : <b>{profit_pct_kraken_okc:.2f}%</b> (Gain net : <b>{calc_profit_after_fees(kraken_ask, okc_bid)[0]:.2f} USDT</b>)\n\n"
    )

    if profit_pct_okc_kraken > risk_profit_threshold:
        message += "<b>🔴 Opportunité détectée :</b> Acheter sur <b>OKC</b> et vendre sur <b>Kraken</b> (Simulation).\n"
        execute_simulation_trade('buy', 'okc', okc_ask)
        execute_simulation_trade('sell', 'kraken', kraken_bid)
    elif profit_pct_kraken_okc > risk_profit_threshold:
        message += "<b>🔴 Opportunité détectée :</b> Acheter sur <b>Kraken</b> et vendre sur <b>OKC</b> (Simulation).\n"
        execute_simulation_trade('buy', 'kraken', kraken_ask)
        execute_simulation_trade('sell', 'okc', okc_bid)
    else:
        message += "<b>✅ Aucune opportunité d'arbitrage</b> n'est détectée actuellement (Simulation)."
    await update.effective_message.reply_text(message, parse_mode="HTML")

async def account_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global initial_balances
    try:
        okc_usdt = get_balance(okc, "USDT")
        kraken_usdt = get_balance(kraken, "USDT")
        if not initial_balances:
            initial_balances = {"okc": okc_usdt, "kraken": kraken_usdt}
        okc_change = okc_usdt - initial_balances["okc"]
        kraken_change = kraken_usdt - initial_balances["kraken"]

        message = (
            f"<b>Statut des Comptes (Simulation)</b>\n\n"
            f"<b>OKC (OKX) :</b>\n"
            f"• Capital : <b>{okc_usdt:.2f} USDT</b>\n"
            f"• Variation : <b>{okc_change:+.2f} USDT</b>\n\n"
            f"<b>Kraken :</b>\n"
            f"• Capital : <b>{kraken_usdt:.2f} USDT</b>\n"
            f"• Variation : <b>{kraken_change:+.2f} USDT</b>"
        )
    except Exception as e:
        message = f"<b>❗ Erreur lors de la récupération des statuts des comptes :</b> {e}"
    await update.effective_message.reply_text(message, parse_mode="HTML")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not simulation_history:
        message = "<b>Aucune transaction simulée enregistrée pour le moment.</b>"
    else:
        message = "<b>Historique des Transactions Récentes (Simulation)</b>\n\n"
        message += (
            "<table border='1' cellspacing='0' cellpadding='4'>"
            "<tr>"
            "<th>Date/Heure</th>"
            "<th>Action</th>"
            "<th>Plateforme</th>"
            "<th>Prix (USDT)</th>"
            "</tr>"
        )
        for record in simulation_history[-10:]:
            message += (
                f"<tr>"
                f"<td>{record['time']}</td>"
                f"<td>{record['action']}</td>"
                f"<td>{record['platform']}</td>"
                f"<td>{record['price']:.2f}</td>"
                f"</tr>"
            )
        message += "</table>"
    await update.effective_message.reply_text(message, parse_mode="HTML")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_message = (
        "📖 <b>Liste des Commandes Disponibles :</b>\n\n"
        "• <b>/start</b> - Démarre le bot et affiche le message de bienvenue.\n"
        "• <b>/status</b> - Affiche les prix et spreads (Simulation).\n"
        "• <b>/arbitrage</b> - Analyse et simule des opportunités d'arbitrage (Simulation).\n"
        "• <b>/account_status</b> - Affiche le capital et la variation (Simulation).\n"
        "• <b>/history</b> - Affiche l'historique des transactions simulées (Simulation).\n"
        "• <b>/start_loop</b> - Lance la vérification continue d'arbitrage (Simulation).\n"
        "• <b>/stop_loop</b> - Arrête la vérification continue (Simulation).\n\n"
        "• <b>/real_status</b> - Affiche les prix pour trading réel.\n"
        "• <b>/real_account</b> - Affiche le statut réel des comptes.\n"
        "• <b>/real_history</b> - Affiche l'historique des transactions réelles.\n"
        "• <b>/real_arbitrage</b> - Exécute de réelles opportunités d'arbitrage.\n"
        "• <b>/start_real_loop</b> - Lance la vérification continue d'arbitrage (Réel).\n"
        "• <b>/stop_real_loop</b> - Arrête la vérification continue (Réel).\n"
        "• <b>/backtest</b> - Lance un test historique (Stub).\n"
        "• <b>/help</b> - Affiche ce message d'aide."
    )
    await update.effective_message.reply_text(help_message, parse_mode="HTML")

async def backtest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.effective_message.reply_text("<b>Le backtesting n'est pas encore implémenté. (Stub)</b>", parse_mode="HTML")

# -------------------------
# Commandes Telegram - Mode Réel
# -------------------------
async def real_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    okc_data = get_okc_price(symbol)
    kraken_data = get_kraken_price(symbol)
    if not okc_data or not kraken_data:
        await update.effective_message.reply_text("<b>❗ Erreur lors de la récupération des prix.</b>", parse_mode="HTML")
        return

    okc_ask, okc_bid = okc_data
    kraken_ask, kraken_bid = kraken_data
    spread_okc_kraken = calc_spread(okc_ask, kraken_bid)
    spread_kraken_okc = calc_spread(kraken_ask, okc_bid)
    message = (
        f"<b>📊 Statut des Prix pour {symbol} (Réel)</b>\n\n"
        f"<b>OKC (OKX) :</b>\n"
        f"• Ask : <b>{okc_ask:.2f} USDT</b>\n"
        f"• Bid : <b>{okc_bid:.2f} USDT</b>\n\n"
        f"<b>Kraken :</b>\n"
        f"• Ask : <b>{kraken_ask:.2f} USDT</b>\n"
        f"• Bid : <b>{kraken_bid:.2f} USDT</b>\n\n"
        f"<b>Spreads :</b>\n"
        f"• OKC → Kraken : <b>{spread_okc_kraken:.2f} USDT</b>\n"
        f"• Kraken → OKC : <b>{spread_kraken_okc:.2f} USDT</b>"
    )
    await update.effective_message.reply_text(message, parse_mode="HTML")

async def real_account(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        okc_usdt = get_balance(okc, "USDT")
        kraken_usdt = get_balance(kraken, "USDT")
        message = (
            f"<b>Statut des Comptes (Réel)</b>\n\n"
            f"<b>OKC (OKX) :</b>\n"
            f"• Capital : <b>{okc_usdt:.2f} USDT</b>\n\n"
            f"<b>Kraken :</b>\n"
            f"• Capital : <b>{kraken_usdt:.2f} USDT</b>"
        )
    except Exception as e:
        message = f"<b>❗ Erreur lors de la récupération des statuts des comptes :</b> {e}"
    await update.effective_message.reply_text(message, parse_mode="HTML")

async def real_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not real_trade_history:
        message = "<b>Aucune transaction réelle enregistrée pour le moment.</b>"
    else:
        message = "<b>Historique des Transactions Réelles</b>\n\n"
        message += (
            "<table border='1' cellspacing='0' cellpadding='4'>"
            "<tr>"
            "<th>Date/Heure</th>"
            "<th>Action</th>"
            "<th>Plateforme</th>"
            "<th>Prix (USDT)</th>"
            "</tr>"
        )
        for record in real_trade_history[-10:]:
            message += (
                f"<tr>"
                f"<td>{record['time']}</td>"
                f"<td>{record['action']}</td>"
                f"<td>{record['platform']}</td>"
                f"<td>{record['price']:.2f}</td>"
                f"</tr>"
            )
        message += "</table>"
    await update.effective_message.reply_text(message, parse_mode="HTML")

async def real_arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    okc_data = get_okc_price(symbol)
    kraken_data = get_kraken_price(symbol)
    if not okc_data or not kraken_data:
        await update.effective_message.reply_text("<b>❗ Erreur lors de la récupération des prix pour l'analyse.</b>", parse_mode="HTML")
        return

    okc_ask, okc_bid = okc_data
    kraken_ask, kraken_bid = kraken_data
    spread_okc_to_kraken = kraken_bid - okc_ask
    spread_kraken_to_okc = okc_bid - kraken_ask
    profit_okc_kraken, profit_pct_okc_kraken = calc_profit_after_fees(okc_ask, kraken_bid)
    profit_kraken_okc, profit_pct_kraken_okc = calc_profit_after_fees(kraken_ask, okc_bid)

    message = (
        f"<b>📊 Analyse d'Arbitrage pour {symbol} (Réel)</b>\n\n"
        f"<b>OKC (OKX) :</b> Ask = <b>{okc_ask:.2f} USDT</b>, Bid = <b>{okc_bid:.2f} USDT</b>\n"
        f"<b>Kraken :</b> Ask = <b>{kraken_ask:.2f} USDT</b>, Bid = <b>{kraken_bid:.2f} USDT</b>\n\n"
        f"<b>Spreads :</b>\n"
        f"• OKC → Kraken : <b>{spread_okc_to_kraken:.2f} USDT</b>\n"
        f"• Kraken → OKC : <b>{spread_kraken_to_okc:.2f} USDT</b>\n\n"
        f"<b>Profit estimé après frais :</b>\n"
        f"• OKC → Kraken : <b>{profit_pct_okc_kraken:.2f}%</b>\n"
        f"• Kraken → OKC : <b>{profit_pct_kraken_okc:.2f}%</b>\n\n"
    )

    if profit_pct_okc_kraken > risk_profit_threshold:
        message += "<b>🔴 Opportunité détectée :</b> Acheter sur <b>OKC</b> et vendre sur <b>Kraken</b> (Réel).\n"
        real_trade_buy = execute_real_trade('buy', 'okc', okc_ask)
        real_trade_sell = execute_real_trade('sell', 'kraken', kraken_bid)
        message += f"Trade Achat OKC: {real_trade_buy}\nTrade Vente Kraken: {real_trade_sell}"
    elif profit_pct_kraken_okc > risk_profit_threshold:
        message += "<b>🔴 Opportunité détectée :</b> Acheter sur <b>Kraken</b> et vendre sur <b>OKC</b> (Réel).\n"
        real_trade_buy = execute_real_trade('buy', 'kraken', kraken_ask)
        real_trade_sell = execute_real_trade('sell', 'okc', okc_bid)
        message += f"Trade Achat Kraken: {real_trade_buy}\nTrade Vente OKC: {real_trade_sell}"
    else:
        message += "<b>✅ Aucune opportunité d'arbitrage</b> n'est détectée actuellement (Réel)."
    await update.effective_message.reply_text(message, parse_mode="HTML")

# -------------------------
# Boucles Automatisées - Mode Simulation
# -------------------------
async def continuous_arbitrage_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    while True:
        okc_data = get_okc_price(symbol)
        kraken_data = get_kraken_price(symbol)
        if not okc_data or not kraken_data:
            logger.error("Erreur lors de la récupération des prix (Simulation).")
        else:
            okc_ask, okc_bid = okc_data
            kraken_ask, kraken_bid = kraken_data
            spread_okc_kraken = calc_spread(okc_ask, kraken_bid)
            spread_kraken_okc = calc_spread(kraken_ask, okc_bid)
            profit_okc_kraken, profit_pct_okc_kraken = calc_profit_after_fees(okc_ask, kraken_bid)
            profit_kraken_okc, profit_pct_kraken_okc = calc_profit_after_fees(kraken_ask, okc_bid)

            message = None
            if profit_pct_okc_kraken > risk_profit_threshold:
                message = (
                    f"<b>📊 Opportunité (Simulation) détectée pour {symbol}</b>\n\n"
                    f"<b>OKC → Kraken :</b>\n"
                    f"Profit estimé : <b>{profit_pct_okc_kraken:.2f}%</b> (Gain net : <b>{calc_profit_after_fees(okc_ask, kraken_bid)[0]:.2f} USDT</b>)\n"
                    f"Achetez sur <b>OKC</b> à <b>{okc_ask:.2f} USDT</b> et vendez sur <b>Kraken</b> à <b>{kraken_bid:.2f} USDT</b>."
                )
                execute_simulation_trade('buy', 'okc', okc_ask)
                execute_simulation_trade('sell', 'kraken', kraken_bid)
            elif profit_pct_kraken_okc > risk_profit_threshold:
                message = (
                    f"<b>📊 Opportunité (Simulation) détectée pour {symbol}</b>\n\n"
                    f"<b>Kraken → OKC :</b>\n"
                    f"Profit estimé : <b>{profit_pct_kraken_okc:.2f}%</b> (Gain net : <b>{calc_profit_after_fees(kraken_ask, okc_bid)[0]:.2f} USDT</b>)\n"
                    f"Achetez sur <b>Kraken</b> à <b>{kraken_ask:.2f} USDT</b> et vendez sur <b>OKC</b> à <b>{okc_bid:.2f} USDT</b>."
                )
                execute_simulation_trade('buy', 'kraken', kraken_ask)
                execute_simulation_trade('sell', 'okc', okc_bid)
            else:
                logger.info("Aucune opportunité (Simulation) détectée cette itération.")
            if message:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Erreur lors de l'envoi du message (Simulation) : {e}")
        await asyncio.sleep(2)  # Intervalle pour respecter les rate limits

async def start_loop_arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global loop_arbitrage_task
    if loop_arbitrage_task is None or loop_arbitrage_task.done():
        loop_arbitrage_task = asyncio.create_task(
            continuous_arbitrage_loop(update.effective_chat.id, context)
        )
        await update.effective_message.reply_text("<b>🔄 Boucle d'arbitrage (Simulation) lancée (actualisation toutes les 2 secondes).</b>", parse_mode="HTML")
    else:
        await update.effective_message.reply_text("<b>La boucle d'arbitrage (Simulation) est déjà active.</b>", parse_mode="HTML")

async def stop_loop_arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global loop_arbitrage_task
    if loop_arbitrage_task and not loop_arbitrage_task.done():
        loop_arbitrage_task.cancel()
        try:
            await loop_arbitrage_task
        except asyncio.CancelledError:
            pass
        await update.effective_message.reply_text("<b>⏹ Boucle d'arbitrage (Simulation) arrêtée.</b>", parse_mode="HTML")
    else:
        await update.effective_message.reply_text("<b>Aucune boucle d'arbitrage (Simulation) n'est en cours.</b>", parse_mode="HTML")

# -------------------------
# Boucles Automatisées - Mode Réel
# -------------------------
async def continuous_real_arbitrage_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    while True:
        okc_data = get_okc_price(symbol)
        kraken_data = get_kraken_price(symbol)
        if not okc_data or not kraken_data:
            logger.error("Erreur lors de la récupération des prix pour l'analyse d'arbitrage (Réel).")
        else:
            okc_ask, okc_bid = okc_data
            kraken_ask, kraken_bid = kraken_data
            spread_okc_to_kraken = kraken_bid - okc_ask
            spread_kraken_to_okc = okc_bid - kraken_ask
            profit_okc_kraken, profit_pct_okc_kraken = calc_profit_after_fees(okc_ask, kraken_bid)
            profit_kraken_okc, profit_pct_kraken_okc = calc_profit_after_fees(kraken_ask, okc_bid)

            message = None
            if profit_pct_okc_kraken > risk_profit_threshold:
                message = (
                    f"<b>📊 Opportunité Réelle détectée pour {symbol}</b>\n\n"
                    f"<b>OKC → Kraken :</b>\n"
                    f"Profit estimé : <b>{profit_pct_okc_kraken:.2f}%</b> (Gain net : <b>{calc_profit_after_fees(okc_ask, kraken_bid)[0]:.2f} USDT</b>)\n"
                    f"Achetez sur <b>OKC</b> à <b>{okc_ask:.2f} USDT</b> et vendez sur <b>Kraken</b> à <b>{kraken_bid:.2f} USDT</b>."
                )
                real_trade_buy = execute_real_trade('buy', 'okc', okc_ask)
                real_trade_sell = execute_real_trade('sell', 'kraken', kraken_bid)
                message += f"\nTrade Achat OKC: {real_trade_buy}\nTrade Vente Kraken: {real_trade_sell}"
            elif profit_pct_kraken_okc > risk_profit_threshold:
                message = (
                    f"<b>📊 Opportunité Réelle détectée pour {symbol}</b>\n\n"
                    f"<b>Kraken → OKC :</b>\n"
                    f"Profit estimé : <b>{profit_pct_kraken_okc:.2f}%</b> (Gain net : <b>{calc_profit_after_fees(kraken_ask, okc_bid)[0]:.2f} USDT</b>)\n"
                    f"Achetez sur <b>Kraken</b> à <b>{kraken_ask:.2f} USDT</b> et vendez sur <b>OKC</b> à <b>{okc_bid:.2f} USDT</b>."
                )
                real_trade_buy = execute_real_trade('buy', 'kraken', kraken_ask)
                real_trade_sell = execute_real_trade('sell', 'okc', okc_bid)
                message += f"\nTrade Achat Kraken: {real_trade_buy}\nTrade Vente OKC: {real_trade_sell}"
            else:
                logger.info("Aucune opportunité réelle détectée cette itération.")
            if message:
                try:
                    await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="HTML")
                except Exception as e:
                    logger.error(f"Erreur lors de l'envoi du message (Réel) : {e}")
        await asyncio.sleep(2)

async def start_real_loop_arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global loop_real_arbitrage_task
    if loop_real_arbitrage_task is None or loop_real_arbitrage_task.done():
        loop_real_arbitrage_task = asyncio.create_task(
            continuous_real_arbitrage_loop(update.effective_chat.id, context)
        )
        await update.effective_message.reply_text("<b>🔄 Boucle d'arbitrage réelle lancée (actualisation toutes les 2 secondes).</b>", parse_mode="HTML")
    else:
        await update.effective_message.reply_text("<b>La boucle d'arbitrage réelle est déjà active.</b>", parse_mode="HTML")

async def stop_real_loop_arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global loop_real_arbitrage_task
    if loop_real_arbitrage_task and not loop_real_arbitrage_task.done():
        loop_real_arbitrage_task.cancel()
        try:
            await loop_real_arbitrage_task
        except asyncio.CancelledError:
            pass
        await update.effective_message.reply_text("<b>⏹ Boucle d'arbitrage réelle arrêtée.</b>", parse_mode="HTML")
    else:
        await update.effective_message.reply_text("<b>Aucune boucle d'arbitrage réelle n'est en cours.</b>", parse_mode="HTML")

# -------------------------
# Envoi de message Telegram en mode synchrone (pour certains cas hors async)
# -------------------------
def send_telegram_message(message):
    # Cette fonction reste en synchrone pour certains cas spécifiques
    import requests
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload)
        logger.info("Message envoyé sur Telegram.")
    except Exception as e:
        logger.error(f"Erreur lors de l'envoi du message Telegram : {e}")

# -------------------------
# Fonction principale
# -------------------------
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Commandes Simulation
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("arbitrage", arbitrage))
    application.add_handler(CommandHandler("account_status", account_status))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("start_loop", start_loop_arbitrage))
    application.add_handler(CommandHandler("stop_loop", stop_loop_arbitrage))
    application.add_handler(CommandHandler("backtest", backtest))
    application.add_handler(CommandHandler("help", help_command))

    # Commandes Réelles
    application.add_handler(CommandHandler("real_status", real_status))
    application.add_handler(CommandHandler("real_account", real_account))
    application.add_handler(CommandHandler("real_history", real_history))
    application.add_handler(CommandHandler("real_arbitrage", real_arbitrage))
    application.add_handler(CommandHandler("start_real_loop", start_real_loop_arbitrage))
    application.add_handler(CommandHandler("stop_real_loop", stop_real_loop_arbitrage))

    application.run_polling()

if __name__ == "__main__":
    main()
