from flask import Flask, request, jsonify
from smartapi import SmartConnect
import pyotp
import datetime

# ==== CONFIG ====
API_KEY = "YOUR_API_KEY"
CLIENT_CODE = "YOUR_CLIENT_ID"
PASSWORD = "YOUR_PASSWORD"
TOTP_SECRET = "YOUR_TOTP_SECRET"
EXPIRY = "08MAY24"  # Weekly expiry
EXCHANGE = "NFO"
QUANTITY = 75

app = Flask(__name__)

# ==== UTILITIES ====
def get_itm_strike(spot, option_type):
    atm = int(spot / 50) * 50
    if option_type == "CE":
        # For CALL: ITM-2 = spot - 100, ITM-1 = spot - 50
        for x in [100, 50]:
            s = atm - x
            if s % 100 == 0:
                return s
    else:
        # For PUT: ITM-2 = spot + 100, ITM-1 = spot + 50
        for x in [100, 50]:
            s = atm + x
            if s % 100 == 0:
                return s
    return atm  # fallback

@app.route("/signal", methods=["POST"])
def signal():
    data = request.json
    signal = data.get("signal")
    if not signal:
        return jsonify({"error": "Missing signal"}), 400

    # ==== ANGEL LOGIN ====
    smartApi = SmartConnect(api_key=API_KEY)
    otp = pyotp.TOTP(TOTP_SECRET).now()
    session = smartApi.generateSession(CLIENT_CODE, PASSWORD, otp)
    feed_token = smartApi.getfeedToken()

    # ==== GET SPOT ====
    spot_data = smartApi.ltpData(exchange="NSE", tradingsymbol="NIFTY", symboltoken="99926000")
    spot = float(spot_data['data']['ltp'])

    # ==== SIGNAL PARSE ====
    if signal == "Buy-H-AM_Strong":
        option_type = "CE"
    elif signal == "Strong_Sell-L-AM_Strong":
        option_type = "PE"
    else:
        return jsonify({"error": "Unknown signal"}), 400

    strike = get_itm_strike(spot, option_type)
    symbol = f"NIFTY{EXPIRY}{strike}{option_type}"
    search = smartApi.searchScrip(EXCHANGE, symbol)
    token = search['data'][0]['token']

    ltp_data = smartApi.ltpData(exchange=EXCHANGE, tradingsymbol=symbol, symboltoken=token)
    ltp = float(ltp_data['data']['ltp'])
    entry_price = round(ltp - 2, 2)
    target_price = round(entry_price * 1.10, 2)

    # ==== PLACE BUY ORDER ====
    buy_order = smartApi.placeOrder({
        "variety": "NORMAL",
        "tradingsymbol": symbol,
        "symboltoken": token,
        "transactiontype": "BUY",
        "exchange": EXCHANGE,
        "ordertype": "LIMIT",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": entry_price,
        "quantity": QUANTITY
    })
    buy_id = buy_order['data']['orderid']

    # ==== PLACE TARGET ORDER ====
    target_order = smartApi.placeOrder({
        "variety": "NORMAL",
        "tradingsymbol": symbol,
        "symboltoken": token,
        "transactiontype": "SELL",
        "exchange": EXCHANGE,
        "ordertype": "LIMIT",
        "producttype": "INTRADAY",
        "duration": "DAY",
        "price": target_price,
        "quantity": QUANTITY
    })

    return jsonify({
        "message": "Orders placed",
        "symbol": symbol,
        "entry": entry_price,
        "target": target_price,
        "buy_order_id": buy_id,
        "target_order_id": target_order['data']['orderid']
    })
