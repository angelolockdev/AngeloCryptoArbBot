# Arbitrage Crypto Bot

Ce bot Telegram surveille les opportunités d'arbitrage entre OKC (OKX) et une autre plateforme de crypto-monnaie (par exemple, Kraken). Il permet également de suivre le capital, d'afficher l'historique des transactions simulées et d'exécuter une boucle d'arbitrage en continu.

## Fonctionnalités

- **Affichage des prix détaillés** : La commande `/status` affiche les prix d'achat (*Ask*) et de vente (*Bid*) sur OKC et Kraken, ainsi que les spreads calculés entre les deux plateformes.
- **Analyse d'arbitrage** : La commande `/arbitrage` permet d'analyser en détail les opportunités d'arbitrage et, le cas échéant, simule des transactions (achat et vente) tout en enregistrant l'historique de ces transactions.
- **Suivi des comptes** : La commande `/account_status` affiche le capital disponible (en USDT) sur chaque compte ainsi que la variation (gains ou pertes) par rapport au point de départ.
- **Historique des transactions** : La commande `/history` présente sous forme de tableau (en Markdown ou HTML) les transactions simulées les plus récentes, avec la date/heure, l'action (BUY/SELL), la plateforme et le prix.
- **Boucle d'arbitrage en continu** : Lancez la vérification d'arbitrage toutes les 5 secondes avec `/start_loop` et arrêtez-la avec `/stop_loop`.
- **Commande d'aide** : La commande `/help` affiche la liste complète des commandes et leur description, en utilisant un formatage HTML pour une meilleure lisibilité.

## Dépendances

- `python-telegram-bot` pour gérer le bot Telegram  
- `ccxt` pour interagir avec les plateformes de crypto-monnaie (OKC et Kraken)  
- `requests` pour envoyer des messages via l'API Telegram dans certains contextes synchrone  
- `python-dotenv` pour charger les variables d'environnement  

## Installation

1. **Cloner le repository** :
   ```bash
   git clone https://github.com/votre-utilisateur/crypto-arbitrage-bot.git
   cd crypto-arbitrage-bot

2. **Installer les dépendances** :
   ```bash
   pip install -r requirements.txt
3. **Configurer les variables d'environnement** :
   ```bash
   TELEGRAM_TOKEN=your_telegram_bot_token
   TELEGRAM_CHAT_ID=your_telegram_chat_id
   OKX_API_KEY=your_okx_api_key
   OKX_API_SECRET=your_okx_api_secret
   OKX_PASSWORD=your_okx_api_passphrase
   KRAKEN_API_KEY=your_kraken_api_key
   KRAKEN_API_SECRET=your_kraken_api_secret

## Utilisation

Lancer le bot :
- Exécutez le script principal :
    ```bash
    python main.py
    ```

Interagir avec le bot sur Telegram :
- Envoyez `/start` pour afficher le message de bienvenue et la liste des commandes.
- Utilisez `/status` pour obtenir les prix détaillés et les spreads.
- Lancez une analyse d'arbitrage avec `/arbitrage` pour vérifier les opportunités et simuler des transactions.
- Consultez le statut global de vos comptes via `/account_status`.
- Affichez l'historique des transactions simulées avec `/history`.
- Pour lancer une vérification d'arbitrage toutes les 5 secondes, utilisez `/start_loop`. Pour l'arrêter, utilisez `/stop_loop`.
- Envoyez `/help` pour afficher à nouveau la liste complète des commandes.

## Structure du Projet
```code
crypto-arbitrage-bot/
├── .env               # Fichier de configuration des variables d'environnement
├── main.py            # Script principal qui démarre le bot Telegram
├── requirements.txt   # Liste des dépendances
├── README.md          # Ce fichier

├── utils.py           # Fonctions utilitaires pour le bot
└── tests/
    └── test_arbitrage.py # Tests unitaires pour la fonction d'arbitrage
 ```
## Remarques

- **Tests en Mode Sandbox** :Utilisez les clés API de test et configurez les URLs de test dans l\'instance ccxt pour OKX (et Kraken si disponible). Cela permet de vérifier le fonctionnement du bot sans risquer de fonds réels.

- **Sécurité** :Ne partagez jamais vos clés API ou votre passphrase en public. Assurez-vous d\'utiliser des variables d\'environnement pour stocker ces informations sensibles.

- **Simulations vs Transactions Réelles** :La fonction execute_arbitrage est actuellement en mode simulation (affiche simplement des messages dans la console et enregistre l\'historique des transactions). Avant de passer en production, intégrez la logique réelle de trading tout en respectant les bonnes pratiques de gestion du risque.