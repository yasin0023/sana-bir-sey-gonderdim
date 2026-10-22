import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yfinance as yf

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "paper_portfolio.json"
REPORT_PATH = ROOT / "paper_report.json"
SYMBOLS = ["THYAO", "ASELS", "TUPRS", "BIMAS", "AKBNK", "GARAN", "FROTO", "SISE"]
START_CASH = 100_000.0
FEE = 0.001
MAX_POSITION_PCT = 0.10
MAX_POSITIONS = 5


def load_state():
    if STATE_PATH.exists():
        try:
            state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(state, dict) and "cash" in state and "positions" in state and "trades" in state:
                return state
        except (ValueError, OSError):
            pass
    return {"cash": START_CASH, "positions": {}, "trades": [], "last_prices": {}, "equity_history": []}


def main():
    state = load_state()
    state.setdefault("last_prices", {})
    state.setdefault("equity_history", [])
    now = datetime.now(timezone.utc)
    updates = []
    errors = []
    prices = {}

    for symbol in SYMBOLS:
        try:
            frame = yf.Ticker(f"{symbol}.IS").history(period="5d", interval="15m", auto_adjust=True)
            if frame is None or frame.empty or "Close" not in frame:
                errors.append(f"{symbol}: fiyat verisi yok")
                continue
            close = frame["Close"].dropna()
            if len(close) < 21:
                errors.append(f"{symbol}: yeterli 15 dakikalık bar yok")
                continue
            # Use only closed bars. Yahoo's data can be delayed and may not be real-time.
            close = close.iloc[:-1] if len(close) > 1 else close
            fast = close.rolling(5).mean()
            slow = close.rolling(20).mean()
            px = float(close.iloc[-1])
            previous_fast, previous_slow = float(fast.iloc[-2]), float(slow.iloc[-2])
            current_fast, current_slow = float(fast.iloc[-1]), float(slow.iloc[-1])
            prices[symbol] = px
            signal = "BUY" if previous_fast <= previous_slow and current_fast > current_slow else (
                "SELL" if previous_fast >= previous_slow and current_fast < current_slow else "HOLD"
            )
            updates.append({"symbol": symbol, "price": round(px, 4), "bar_time": close.index[-1].isoformat(), "signal": signal})
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")

    # Trade only on an actual new bar; avoid duplicate trades when a scheduled run sees stale data.
    traded_symbols = set()
    for item in updates:
        symbol, px, bar_time, signal = item["symbol"], item["price"], item["bar_time"], item["signal"]
        if state["last_prices"].get(symbol + "_bar") == bar_time:
            continue
        pos = state["positions"].get(symbol)
        if signal == "BUY" and not pos and len(state["positions"]) < MAX_POSITIONS:
            budget = min(float(state["cash"]), START_CASH * MAX_POSITION_PCT)
            qty = int(budget / (px * (1 + FEE)))
            if qty > 0:
                gross, fee = qty * px, qty * px * FEE
                state["cash"] = round(float(state["cash"]) - gross - fee, 2)
                state["positions"][symbol] = {"qty": qty, "avg": px, "entry_fee": fee, "entry_time": bar_time}
                state["trades"].append({"time": now.isoformat(), "bar_time": bar_time, "symbol": symbol, "side": "BUY", "qty": qty, "price": px, "fee": round(fee, 2), "reason": "SMA5/SMA20 bullish crossover"})
                traded_symbols.add(symbol)
        elif signal == "SELL" and pos:
            qty = int(pos["qty"])
            gross, fee = qty * px, qty * px * FEE
            realized = gross - fee - qty * float(pos["avg"]) - float(pos.get("entry_fee", 0))
            state["cash"] = round(float(state["cash"]) + gross - fee, 2)
            state["trades"].append({"time": now.isoformat(), "bar_time": bar_time, "symbol": symbol, "side": "SELL", "qty": qty, "price": px, "fee": round(fee, 2), "realized_pnl": round(realized, 2), "reason": "SMA5/SMA20 bearish crossover"})
            del state["positions"][symbol]
            traded_symbols.add(symbol)
        state["last_prices"][symbol] = px
        state["last_prices"][symbol + "_bar"] = bar_time

    market_value = sum(int(p["qty"]) * prices.get(s, float(p["avg"])) for s, p in state["positions"].items())
    equity = round(float(state["cash"]) + market_value, 2)
    state["equity_history"].append({"time": now.isoformat(), "equity": equity, "cash": round(float(state["cash"]), 2), "market_value": round(market_value, 2)})
    state["equity_history"] = state["equity_history"][-2000:]
    state["last_run"] = now.isoformat()
    state["last_prices"].update({s: p for s, p in prices.items()})
    state["trades"] = state["trades"][-2000:]
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    REPORT_PATH.write_text(json.dumps({
        "updated_at": now.isoformat(),
        "mode": "paper_only",
        "source": "Yahoo Finance via yfinance; BIST .IS; 15-minute bars, delayed/availability not guaranteed",
        "symbols": updates,
        "errors": errors,
        "cash": round(float(state["cash"]), 2),
        "market_value": round(market_value, 2),
        "equity": equity,
        "return_pct": round((equity / START_CASH - 1) * 100, 4),
        "open_positions": state["positions"],
        "recent_trades": state["trades"][-20:],
        "strategy": "SMA5/SMA20 crossover; illustrative fee 0.10% per side; 10% of initial cash per entry; max 5 positions",
        "note": "Educational simulation only. Not real-time guaranteed; not investment advice; no real orders."
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Paper trader run at {now.isoformat()} | equity={equity:.2f} | trades={len(state['trades'])} | errors={len(errors)}")
    for item in updates:
        print(item)
    for error in errors:
        print("WARNING:", error)


if __name__ == "__main__":
    main()
