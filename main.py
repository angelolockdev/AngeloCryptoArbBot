import os
import requests
import asyncio
import ccxt
from datetime import datetime
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# Charger les variables d'environnement depuis le fichier .env
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# Configuration des clés API pour OKC (OKX) et pour l'autre plateforme (Kraken)
# Pour le mode sandbox, décommentez et modifiez la section 'urls' si nécessaire.
okc = ccxt.okx({
    'apiKey': os.getenv("OKX_API_KEY"),
    'secret': os.getenv("OKX_API_SECRET"),
    'password': os.getenv("OKX_PASSWORD"),
    # 'urls': {
    #     'api': {
    #         'public': 'https://testnet.okx.com',
    #         'private': 'https://testnet.okx.com',
    #     },
    # },
})
other_exchange = ccxt.kraken({
    'apiKey': os.getenv("KRAKEN_API_KEY"),
    'secret': os.getenv("KRAKEN_API_SECRET"),
})

# Définition du symbole de trading
symbol = 'BTC/USDT'

# Variables globales pour la boucle d'arbitrage, l'historique des transactions
# et les balances initiales (pour calculer gains/pertes)
loop_arbitrage_task = None
transaction_history = []    # Liste de dictionnaires représentant les transactions simulées
initial_balances = {}       # Stockera les balances initiales au premier appel de /account_status

# ----------------------------------------------------------------------
# Fonctions de récupération des prix depuis les plateformes
# ----------------------------------------------------------------------
def get_okc_price(symbol):
    """
    Récupère les prix sur OKC (OKX) pour le symbole spécifié.
    Retourne un tuple (ask, bid) ou (None, None) en cas d'erreur.
    """
    try:
        ticker = okc.fetch_ticker(symbol)
        return ticker['ask'], ticker['bid']
    except Exception as e:
        print(f"Erreur lors de la récupération des prix OKC: {e}")
        return None, None

def get_other_platform_price(symbol):
    """
    Récupère les prix sur Kraken pour le symbole spécifié.
    Retourne un tuple (ask, bid) ou (None, None) en cas d'erreur.
    """
    try:
        ticker = other_exchange.fetch_ticker(symbol)
        return ticker['ask'], ticker['bid']
    except Exception as e:
        print(f"Erreur lors de la récupération des prix sur Kraken: {e}")
        return None, None

# ----------------------------------------------------------------------
# Commandes Telegram
# ----------------------------------------------------------------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start : Envoie un message de bienvenue et la liste des commandes.
    """
    await update.effective_message.reply_text(
        "🤖 Bonjour! Je suis ton bot d'arbitrage crypto.\n"
        "Voici les commandes disponibles :\n"
        "• /status - Affiche les prix détaillés sur OKC et Kraken\n"
        "• /arbitrage - Analyse et détaille les opportunités d'arbitrage\n"
        "• /start_loop - Lance l'arbitrage en continu toutes les 5 secondes\n"
        "• /stop_loop - Arrête l'arbitrage en continu\n"
        "• /account_status - Affiche le statut global (balance, gains/pertes) de chaque compte\n"
        "• /history - Liste l'historique des transactions simulées\n"
        "• /help - Affiche ce message d'aide"
    )

async def status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /status : Affiche les prix actuels sur OKC et Kraken avec des détails.
    Le message inclut les prix 'ask' (achat) et 'bid' (vente) ainsi que le spread entre les plateformes.
    """
    okc_ask, okc_bid = get_okc_price(symbol)
    other_ask, other_bid = get_other_platform_price(symbol)

    if None in (okc_ask, okc_bid, other_ask, other_bid):
        message = "❗ Erreur lors de la récupération des prix sur l'une des plateformes."
    else:
        # Calcul des spreads (différences de prix)
        spread_okc_to_kraken = other_bid - okc_ask
        spread_kraken_to_okc = okc_bid - other_ask

        message = (
            f"📊 **Statut des Prix pour {symbol}**\n\n"
            f"**OKC (OKX) :**\n"
            f"• Prix d'achat (Ask) : **{okc_ask:.2f} USDT**\n"
            f"• Prix de vente (Bid) : **{okc_bid:.2f} USDT**\n\n"
            f"**Kraken :**\n"
            f"• Prix d'achat (Ask) : **{other_ask:.2f} USDT**\n"
            f"• Prix de vente (Bid) : **{other_bid:.2f} USDT**\n\n"
            f"**Spreads :**\n"
            f"• OKC -> Kraken : **{spread_okc_to_kraken:.2f} USDT**\n"
            f"• Kraken -> OKC : **{spread_kraken_to_okc:.2f} USDT**"
        )
    await update.effective_message.reply_text(message, parse_mode="Markdown")

async def arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /arbitrage : Analyse les opportunités d'arbitrage et affiche un message détaillé.
    Le message présente les prix de chaque plateforme, les spreads calculés et indique l'opportunité détectée.
    """
    okc_ask, okc_bid = get_okc_price(symbol)
    other_ask, other_bid = get_other_platform_price(symbol)

    if None in (okc_ask, okc_bid, other_ask, other_bid):
        message = "❗ Erreur lors de la récupération des prix pour l'analyse d'arbitrage."
    else:
        spread_okc_to_kraken = other_bid - okc_ask
        spread_kraken_to_okc = okc_bid - other_ask

        message = (
            f"📊 **Analyse d'Arbitrage pour {symbol}**\n\n"
            f"**OKC (OKX) :**\n"
            f"• Ask : **{okc_ask:.2f} USDT**\n"
            f"• Bid : **{okc_bid:.2f} USDT**\n\n"
            f"**Kraken :**\n"
            f"• Ask : **{other_ask:.2f} USDT**\n"
            f"• Bid : **{other_bid:.2f} USDT**\n\n"
            f"**Spreads Calculés :**\n"
            f"• OKC -> Kraken : **{spread_okc_to_kraken:.2f} USDT**\n"
            f"• Kraken -> OKC : **{spread_kraken_to_okc:.2f} USDT**\n\n"
        )
        if spread_okc_to_kraken > 0:
            message += "🔴 **Opportunité :** Acheter sur **OKC** et vendre sur **Kraken**."
            # Simulation d'une transaction (achat et vente)
            execute_arbitrage('buy', 'okc', okc_ask)
            execute_arbitrage('sell', 'kraken', other_bid)
        elif spread_kraken_to_okc > 0:
            message += "🔴 **Opportunité :** Acheter sur **Kraken** et vendre sur **OKC**."
            execute_arbitrage('buy', 'kraken', other_ask)
            execute_arbitrage('sell', 'okc', okc_bid)
        else:
            message += "✅ **Aucune opportunité d'arbitrage** n'est détectée actuellement."

    await update.effective_message.reply_text(message, parse_mode="Markdown")

async def account_status(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /account_status : Récupère et affiche le statut de chaque compte.
    Affiche le capital disponible en USDT pour OKC et Kraken, ainsi que la variation (gains/pertes)
    par rapport au point de départ (initial).
    """
    global initial_balances
    try:
        # Récupération des balances via ccxt
        okc_balance = okc.fetch_balance()
        kraken_balance = other_exchange.fetch_balance()

        # Extraction de la balance USDT (supposée être présente)
        okc_usdt = okc_balance.get('USDT', {}).get('free', 0)
        kraken_usdt = kraken_balance.get('USDT', {}).get('free', 0)

        # Définition des balances initiales si non définies
        if not initial_balances:
            initial_balances = {"okc": okc_usdt, "kraken": kraken_usdt}

        # Calcul des variations par rapport aux balances initiales
        okc_change = okc_usdt - initial_balances["okc"]
        kraken_change = kraken_usdt - initial_balances["kraken"]

        message = (
            f"**Statut des Comptes**\n\n"
            f"**OKC (OKX) :**\n"
            f"• Capital Disponible : **{okc_usdt:.2f} USDT**\n"
            f"• Variation : **{okc_change:+.2f} USDT**\n\n"
            f"**Kraken :**\n"
            f"• Capital Disponible : **{kraken_usdt:.2f} USDT**\n"
            f"• Variation : **{kraken_change:+.2f} USDT**"
        )
    except Exception as e:
        message = f"❗ Erreur lors de la récupération des statuts des comptes : {e}"

    await update.effective_message.reply_text(message, parse_mode="Markdown")

async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /history : Affiche un tableau (en Markdown) listant les transactions simulées les plus récentes.
    Chaque enregistrement inclut la date/heure, l'action (BUY/SELL), la plateforme et le prix.
    """
    global transaction_history
    if not transaction_history:
        message = "Aucune transaction enregistrée pour le moment."
    else:
        message = "**Historique des Transactions Récentes**\n\n"
        message += "| Date/Heure          | Action | Plateforme | Prix (USDT) |\n"
        message += "|---------------------|--------|------------|-------------|\n"
        # Affiche les 10 dernières transactions
        for record in transaction_history[-10:]:
            message += f"| {record['time']} | {record['action']} | {record['platform']} | {record['price']:.2f} |\n"
    await update.effective_message.reply_text(message, parse_mode="Markdown")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /help : Affiche la liste complète des commandes avec leurs descriptions.
    """
    help_message = (
        "📖 **Liste des Commandes Disponibles :**\n\n"
        "• **/start** - Démarre le bot et affiche le message de bienvenue.\n"
        "• **/status** - Affiche les prix détaillés sur OKC et Kraken, avec calcul des spreads.\n"
        "• **/arbitrage** - Analyse les opportunités d'arbitrage et simule des transactions.\n"
        "• **/account_status** - Affiche le capital et la variation (gains/pertes) de chaque compte.\n"
        "• **/history** - Affiche l'historique des transactions simulées récentes.\n"
        "• **/start_loop** - Lance une boucle d'arbitrage en continu toutes les 5 secondes.\n"
        "• **/stop_loop** - Arrête la boucle d'arbitrage en continu.\n"
        "• **/help** - Affiche ce message d'aide."
    )
    await update.effective_message.reply_text(help_message, parse_mode="Markdown")

# ----------------------------------------------------------------------
# Boucle d'arbitrage continu (asynchrone)
# ----------------------------------------------------------------------
async def continuous_arbitrage_loop(chat_id: int, context: ContextTypes.DEFAULT_TYPE):
    """
    Boucle qui vérifie l'arbitrage toutes les 5 secondes et envoie un message sur Telegram.
    Cette fonction est lancée en tâche asynchrone via la commande /start_loop.
    """
    while True:
        okc_ask, okc_bid = get_okc_price(symbol)
        other_ask, other_bid = get_other_platform_price(symbol)

        if None in (okc_ask, okc_bid, other_ask, other_bid):
            message = "❗ Erreur lors de la récupération des prix pour l'analyse d'arbitrage."
        else:
            spread_okc_to_kraken = other_bid - okc_ask
            spread_kraken_to_okc = okc_bid - other_ask

            message = (
                f"📊 **Arbitrage Continu pour {symbol}**\n\n"
                f"OKC - Ask: **{okc_ask:.2f} USDT**, Bid: **{okc_bid:.2f} USDT**\n"
                f"Kraken - Ask: **{other_ask:.2f} USDT**, Bid: **{other_bid:.2f} USDT**\n\n"
                f"Spread OKC -> Kraken: **{spread_okc_to_kraken:.2f} USDT**\n"
                f"Spread Kraken -> OKC: **{spread_kraken_to_okc:.2f} USDT**\n"
            )
            if spread_okc_to_kraken > 0:
                message += "🔴 Acheter sur **OKC** et vendre sur **Kraken**."
                execute_arbitrage('buy', 'okc', okc_ask)
                execute_arbitrage('sell', 'kraken', other_bid)
            elif spread_kraken_to_okc > 0:
                message += "🔴 Acheter sur **Kraken** et vendre sur **OKC**."
                execute_arbitrage('buy', 'kraken', other_ask)
                execute_arbitrage('sell', 'okc', okc_bid)
            else:
                message += "✅ Aucune opportunité d'arbitrage détectée."

        try:
            await context.bot.send_message(chat_id=chat_id, text=message, parse_mode="Markdown")
        except Exception as e:
            print(f"Erreur lors de l'envoi du message dans la boucle : {e}")

        await asyncio.sleep(5)

async def start_loop_arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /start_loop : Lance la boucle d'arbitrage continu si elle n'est pas déjà active.
    """
    global loop_arbitrage_task
    if loop_arbitrage_task is None or loop_arbitrage_task.done():
        loop_arbitrage_task = asyncio.create_task(
            continuous_arbitrage_loop(update.effective_chat.id, context)
        )
        await update.effective_message.reply_text("🔄 Boucle d'arbitrage lancée (mise à jour toutes les 5 secondes).")
    else:
        await update.effective_message.reply_text("La boucle d'arbitrage est déjà en cours.")

async def stop_loop_arbitrage(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    /stop_loop : Arrête la boucle d'arbitrage continu si elle est active.
    """
    global loop_arbitrage_task
    if loop_arbitrage_task and not loop_arbitrage_task.done():
        loop_arbitrage_task.cancel()
        try:
            await loop_arbitrage_task
        except asyncio.CancelledError:
            pass
        await update.effective_message.reply_text("⏹ Boucle d'arbitrage arrêtée.")
    else:
        await update.effective_message.reply_text("Aucune boucle d'arbitrage n'est en cours.")

# ----------------------------------------------------------------------
# Fonction d'envoi de message Telegram (mode synchrone)
# ----------------------------------------------------------------------
def send_telegram_message(message):
    """
    Envoi de message via l'API Telegram en mode synchrone.
    Utile pour envoyer des notifications depuis du code non asynchrone.
    """
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message}
    try:
        requests.post(url, json=payload)
        print("📩 Message envoyé sur Telegram")
    except Exception as e:
        print(f"Erreur lors de l'envoi du message Telegram : {e}")

# ----------------------------------------------------------------------
# Simulation d'exécution d'une transaction d'arbitrage
# ----------------------------------------------------------------------
def execute_arbitrage(action, platform, price):
    """
    Simulation de l'exécution d'une transaction d'arbitrage.
    Enregistre également la transaction dans l'historique.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if action == 'buy':
        print(f"[SIMULATION] Achat sur {platform} à {price} USDT")
    elif action == 'sell':
        print(f"[SIMULATION] Vente sur {platform} à {price} USDT")
    else:
        print("Action inconnue")

    # Enregistrement de la transaction dans l'historique
    global transaction_history
    transaction = {
        "time": now,
        "action": action.upper(),
        "platform": platform.upper(),
        "price": price
    }
    transaction_history.append(transaction)

# ----------------------------------------------------------------------
# Fonction principale pour démarrer le bot Telegram
# ----------------------------------------------------------------------
def main():
    application = Application.builder().token(TELEGRAM_TOKEN).build()

    # Enregistrement des gestionnaires de commandes
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("status", status))
    application.add_handler(CommandHandler("arbitrage", arbitrage))
    application.add_handler(CommandHandler("account_status", account_status))
    application.add_handler(CommandHandler("history", history_command))
    application.add_handler(CommandHandler("start_loop", start_loop_arbitrage))
    application.add_handler(CommandHandler("stop_loop", stop_loop_arbitrage))
    application.add_handler(CommandHandler("help", help_command))

    # Démarrage du bot en mode polling
    application.run_polling()

if __name__ == "__main__":
    main()
