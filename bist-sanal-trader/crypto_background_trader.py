import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "crypto_portfolio.json"
REPORT_PATH = ROOT / "crypto_report.json"
SYMBOLS = ["BTCUSDT", "ETHUSDT"]
START_CASH = 20000.0
FEE = 0.001
MAX_POSITION_PCT = 0.10

def load_state():
    if STATE_PATH.exists():
        try:
            s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(s, dict) and "cash" in s and "positions" in s and "trades" in s:
                return s
        except (ValueError, OSError):
            pass
    return {"cash": START_CASH, "positions": {}, "trades": [], "last_bar": {}, "last_prices": {}, "equity_history": []}

def main():
    state = load_state()
    now = datetime.now(timezone.utc)
    prices, updates, errors = {}, [], []
    for symbol in SYMBOLS:
        try:
            response = requests.get("https://api.binance.com/api/v3/klines", params={"symbol": symbol, "interval": "15m", "limit": 60}, timeout=20)
            response.raise_for_status()
            rows = response.json()
            if len(rows) < 22:
                raise ValueError("Yetersiz mum verisi")
            # Only closed candles: Binance kline close time must be before current time.
            closed = [r for r in rows if int(r[6]) < int(now.timestamp() * 1000)]
            closes = [float(r[4]) for r in closed]
            if len(closes) < 22:
                raise ValueError("Yeterli kapanmış 15 dakikalık mum yok")
            bar_time = int(closed[-1][6])
            fast_prev = sum(closes[-6:-1]) / 5
            slow_prev = sum(closes[-21:-1]) / 20
            fast_now = sum(closes[-5:]) / 5
            slow_now = sum(closes[-20:]) / 20
            px = closes[-1]
            signal = "BUY" if fast_prev <= slow_prev and fast_now > slow_now else ("SELL" if fast_prev >= slow_prev and fast_now < slow_now else "HOLD")
            prices[symbol] = px
            updates.append({"symbol": symbol, "price": px, "bar_time": bar_time, "signal": signal})
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")

    for item in updates:
        symbol, px, bar_time, signal = item["symbol"], item["price"], item["bar_time"], item["signal"]
        if state["last_bar"].get(symbol) == bar_time:
            continue
        pos = state["positions"].get(symbol)
        if signal == "BUY" and not pos:
            budget = min(float(state["cash"]), START_CASH * MAX_POSITION_PCT)
            qty = budget / (px * (1 + FEE))
            if qty > 0:
                fee = qty * px * FEE
                state["cash"] = round(float(state["cash"]) - qty * px - fee, 8)
                state["positions"][symbol] = {"qty": qty, "avg": px, "entry_fee": fee, "entry_time": now.isoformat()}
                state["trades"].append({"time": now.isoformat(), "symbol": symbol, "side": "BUY", "qty": qty, "price": px, "reason": "SMA5/SMA20 bullish crossover; paper only"})
        elif signal == "SELL" and pos:
            qty = float(pos["qty"])
            fee = qty * px * FEE
            realized = qty * px - fee - qty * float(pos["avg"]) - float(pos.get("entry_fee", 0))
            state["cash"] = round(float(state["cash"]) + qty * px - fee, 8)
            state["trades"].append({"time": now.isoformat(), "symbol": symbol, "side": "SELL", "qty": qty, "price": px, "realized_pnl": round(realized, 8), "reason": "SMA5/SMA20 bearish crossover; paper only"})
            del state["positions"][symbol]
        state["last_bar"][symbol] = bar_time
        state["last_prices"][symbol] = px

    market_value = sum(float(p["qty"]) * float(prices.get(s, p["avg"])) for s, p in state["positions"].items())
    equity = round(float(state["cash"]) + market_value, 8)
    state["equity_history"].append({"time": now.isoformat(), "equity": equity})
    state["equity_history"] = state["equity_history"][-2000:]
    state["trades"] = state["trades"][-500:]
    state["last_run"] = now.isoformat()
    state["last_prices"].update(prices)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"last_run": now.isoformat(), "mode": "paper_only", "source": "Binance public spot klines; 15-minute closed candles", "prices": prices, "symbols": updates, "errors": errors, "cash": round(float(state["cash"]), 8), "market_value": round(market_value, 8), "equity": equity, "return_pct": round((equity / START_CASH - 1) * 100, 4), "open_positions": state["positions"], "recent_trades": state["trades"][-25:], "strategy": "SMA5/SMA20 crossover; assumed 0.10% fee per side; max 10% of initial balance per entry; max two positions", "note": "Educational paper-trading simulation only. No real orders; prices and execution may differ; no profit guarantee."}
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Crypto paper trader at {now.isoformat()} | equity={equity:.4f} USDT | trades={len(state['trades'])} | errors={len(errors)}")
    for item in updates: print(item)
    for error in errors: print("WARNING:", error)

if __name__ == "__main__":
    main()
