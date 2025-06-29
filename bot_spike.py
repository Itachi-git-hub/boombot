import os
import json
import time
import requests
import websocket
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

DERIV_API_TOKEN = os.getenv("DERIV_API_TOKEN")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
DERIV_SYMBOL = os.getenv("DERIV_SYMBOL", "R_1000VOL")
DERIV_APP_ID = os.getenv("DERIV_APP_ID")

STAKE_INIT = 0.5
MARTINGALE_LEVELS = 3
STOP_LOSS_DAILY = 10.0
MIN_TRADE_INTERVAL = 120
SPIKE_THRESHOLD = 15

last_trade_time = datetime.min
daily_loss = 0.0
current_level = 0
current_stake = STAKE_INIT

def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = { "chat_id": TELEGRAM_CHAT_ID, "text": message }
        requests.post(url, json=payload)
    except Exception as e:
        print("❌ Erreur Telegram :", e)

def place_trade(ws, contract_type):
    global last_trade_time, daily_loss, current_level, current_stake
    if datetime.utcnow() - last_trade_time < timedelta(seconds=MIN_TRADE_INTERVAL):
        return
    if daily_loss >= STOP_LOSS_DAILY:
        send_telegram("🛑 Stop Loss journalier atteint.")
        return
    trade = {
        "buy": 1,
        "price": round(current_stake, 2),
        "parameters": {
            "amount": round(current_stake, 2),
            "basis": "stake",
            "contract_type": contract_type,
            "currency": "USD",
            "symbol": DERIV_SYMBOL,
            "duration": 1,
            "duration_unit": "t"
        },
        "passthrough": {
            "level": current_level,
            "stake": current_stake
        }
    }
    ws.send(json.dumps(trade))
    last_trade_time = datetime.utcnow()
    send_telegram(f"🚀 Trade {contract_type} lancé | Niveau {current_level + 1} | Mise : {current_stake:.2f} $")

def on_message(ws, message):
    global daily_loss, current_level, current_stake
    data = json.loads(message)
    if "error" in data:
        send_telegram(f"❌ Erreur Deriv : {data['error']['message']}")
        return
    msg_type = data.get("msg_type")
    if msg_type == "ohlc":
        ohlc = data["ohlc"]
        open_price = float(ohlc["open"])
        close_price = float(ohlc["close"])
        diff = abs(close_price - open_price)
        if diff >= SPIKE_THRESHOLD:
            direction = "CALL" if close_price < open_price else "PUT"
            send_telegram(f"📈 Spike détecté : {diff:.2f} points. Trade en sens inverse → {direction}")
            place_trade(ws, direction)
    elif msg_type == "buy":
        print("✅ Trade exécuté.")
    elif msg_type == "proposal_open_contract":
        if data["proposal_open_contract"].get("is_expired"):
            profit = float(data["proposal_open_contract"]["profit"])
            result = "✅ GAGNÉ" if profit > 0 else "❌ PERDU"
            send_telegram(f"{result} | Profit : {profit:.2f} $")
            if profit > 0:
                current_level = 0
                current_stake = STAKE_INIT
            else:
                daily_loss += abs(profit)
                current_level += 1
                if current_level < MARTINGALE_LEVELS:
                    current_stake *= 2
                else:
                    send_telegram("⚠️ Échec martingale. Reprise à zéro.")
                    current_level = 0
                    current_stake = STAKE_INIT

def on_open(ws):
    print("🔐 Connexion Deriv : envoi autorisation...")
    ws.send(json.dumps({"authorize": DERIV_API_TOKEN}))
    sub = {
        "ticks_history": DERIV_SYMBOL,
        "adjust_start_time": 1,
        "count": 1,
        "granularity": 60,
        "style": "candles",
        "subscribe": 1
    }
    ws.send(json.dumps(sub))
    send_telegram("🤖 Bot connecté à Deriv. Prêt à détecter les spikes !")

def on_error(ws, error):
    print("❌ WebSocket error :", error)
    send_telegram(f"❌ WebSocket error : {error}")

def on_close(ws, code, reason):
    print(f"🔌 WebSocket fermé : {code} | {reason}")
    send_telegram("🔌 Connexion WebSocket fermée.")

def run_bot():
    print("🟢 Lancement du bot spike Deriv...")
    ws = websocket.WebSocketApp(
        f"wss://ws.derivws.com/websockets/v3?app_id={DERIV_APP_ID}",
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )
    ws.run_forever()

if __name__ == "__main__":
    run_bot()