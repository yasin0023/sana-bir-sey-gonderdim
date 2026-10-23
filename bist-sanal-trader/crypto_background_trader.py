import json
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parent
STATE_PATH = ROOT / "crypto_portfolio.json"
REPORT_PATH = ROOT / "crypto_report.json"
SYMBOLS = {"BTCUSDT": "BTC-USD", "ETHUSDT": "ETH-USD", "SOLUSDT": "SOL-USD", "DOGEUSDT": "DOGE-USD"}
START_CASH = 20000.0
FEE = 0.001
MAX_POSITION_PCT = 0.10
MIN_NET_PROFIT_TRY = 1.0  # Alış ve satış komisyonlarından sonra hedef net kâr (TL)
DEFAULT_USDTRY = 40.0  # Kur servisi çalışmazsa ihtiyatlı olmayan yaklaşık yedek; raporda belirtilir
MAX_OPEN_POSITIONS = 4
# DOGE support enabled; the next scheduled run will publish its price and signal.
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Mozilla/5.0 crypto-paper-trader/1.0"})

def load_state():
    if STATE_PATH.exists():
        try:
            s = json.loads(STATE_PATH.read_text(encoding="utf-8"))
            if isinstance(s, dict) and "cash" in s and "positions" in s and "trades" in s:
                s.setdefault("last_bar", {})
                s.setdefault("last_prices", {})
                s.setdefault("equity_history", [])
                return s
        except (ValueError, OSError):
            pass
    return {"cash": START_CASH, "positions": {}, "trades": [], "last_bar": {}, "last_prices": {}, "equity_history": []}

def get_yahoo_candles(ticker, now_ms):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{ticker}"
    response = SESSION.get(url, params={"range": "5d", "interval": "5m", "events": "history"}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    chart = payload.get("chart", {})
    if chart.get("error"):
        raise RuntimeError(str(chart["error"]))
    result = chart.get("result") or []
    if not result:
        raise ValueError("Yahoo Finance mum verisi boş")
    item = result[0]
    timestamps = item.get("timestamp") or []
    quote = ((item.get("indicators") or {}).get("quote") or [{}])[0]
    closes, highs, lows = quote.get("close") or [], quote.get("high") or [], quote.get("low") or []
    candles = []
    for i, (ts, close) in enumerate(zip(timestamps, closes)):
        if close is not None and int(ts) * 1000 + 5 * 60 * 1000 <= now_ms:
            high = highs[i] if i < len(highs) else None
            low = lows[i] if i < len(lows) else None
            candles.append((int(ts) * 1000, float(close), float(high if high is not None else close), float(low if low is not None else close)))
    if len(candles) < 22:
        raise ValueError(f"Yahoo Finance yeterli kapanmış mum döndürmedi: {len(candles)}")
    return candles, "Yahoo Finance chart (USD)"

def get_kraken_candles(symbol):
    pair = {"BTCUSDT": "XBTUSDT", "ETHUSDT": "ETHUSDT", "SOLUSDT": "SOLUSDT", "DOGEUSDT": "DOGEUSDT"}[symbol]
    response = SESSION.get("https://api.kraken.com/0/public/OHLC", params={"pair": pair, "interval": 5}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    if payload.get("error"):
        raise RuntimeError("Kraken: " + "; ".join(payload["error"]))
    result = payload.get("result") or {}
    key = next((k for k in result if k != "last"), None)
    rows = result.get(key, []) if key else []
    # Kraken's final row is the currently forming candle, so exclude it.
    candles = [(int(r[0]) * 1000, float(r[4]), float(r[2]), float(r[3])) for r in rows[:-1] if r[4] is not None]
    if len(candles) < 22:
        raise ValueError(f"Kraken yeterli kapanmış mum döndürmedi: {len(candles)}")
    return candles, "Kraken OHLC (USDT)"

def get_candles(symbol, now_ms):
    errors = []
    ticker = SYMBOLS[symbol]
    try:
        candles, source = get_yahoo_candles(ticker, now_ms)
        return candles, source
    except Exception as exc:
        errors.append(f"Yahoo Finance: {type(exc).__name__}: {exc}")
    try:
        candles, source = get_kraken_candles(symbol)
        return candles, source
    except Exception as exc:
        errors.append(f"Kraken: {type(exc).__name__}: {exc}")
    raise RuntimeError(" | ".join(errors))

def get_usdtry():
    """Fetch an indicative USD/TRY rate to convert the 1 TL net-profit target."""
    response = SESSION.get("https://api.frankfurter.app/latest", params={"from": "USD", "to": "TRY"}, timeout=10)
    response.raise_for_status()
    rate = float(response.json()["rates"]["TRY"])
    if rate <= 0:
        raise ValueError("USD/TRY kuru geçersiz")
    return rate, "Frankfurter reference rate"

def main():
    state = load_state()
    try:
        usdtry, fx_source = get_usdtry()
    except Exception as exc:
        # Do not silently pretend the target is exact if live FX is unavailable.
        usdtry, fx_source = DEFAULT_USDTRY, f"fallback rate {DEFAULT_USDTRY}; live FX failed: {exc}"
    min_net_profit_quote = MIN_NET_PROFIT_TRY / usdtry
    now = datetime.now(timezone.utc)
    now_ms = int(now.timestamp() * 1000)
    prices, updates, errors, sources = {}, [], [], {}
    for symbol in SYMBOLS:
        try:
            candles, source = get_candles(symbol, now_ms)
            closes = [c[1] for c in candles]
            bar_time, px, bar_high, bar_low = candles[-1]
            fast_prev = sum(closes[-6:-1]) / 5
            slow_prev = sum(closes[-21:-1]) / 20
            fast_now = sum(closes[-5:]) / 5
            slow_now = sum(closes[-20:]) / 20
            signal = "BUY" if fast_prev <= slow_prev and fast_now > slow_now else ("SELL" if fast_prev >= slow_prev and fast_now < slow_now else "HOLD")
            prices[symbol] = px
            sources[symbol] = source
            updates.append({"symbol": symbol, "price": px, "high": bar_high, "low": bar_low, "bar_time": bar_time, "signal": signal, "source": source})
        except Exception as exc:
            errors.append(f"{symbol}: {type(exc).__name__}: {exc}")

    for item in updates:
        symbol, px, bar_time, signal = item["symbol"], item["price"], item["bar_time"], item["signal"]
        bar_high, bar_low = float(item.get("high", px)), float(item.get("low", px))
        if state["last_bar"].get(symbol) == bar_time:
            continue
        pos = state["positions"].get(symbol)
        closed_this_bar = False
        if pos:
            entry = float(pos["avg"])
            move_pct = (px / entry) - 1 if entry > 0 else 0.0
            exit_reason = None
            qty = float(pos["qty"])
            # Solve for the sell price that covers entry cost, both fees, and at least 1 TL net.
            target = (qty * entry + float(pos.get("entry_fee", 0)) + min_net_profit_quote) / (qty * (1 - FEE))
            # No stop-loss: don't intentionally close at a net loss. This can leave losing positions open.
            if bar_high >= target:
                px = target
                exit_reason = f"Net kâr hedefi en az {MIN_NET_PROFIT_TRY:.2f} TL; iki komisyon sonrası"
            elif signal == "SELL":
                # Bearish crossover alone is not enough; sell only if net profit reaches the TL target.
                candidate_fee = qty * px * FEE
                candidate_realized = qty * px - candidate_fee - qty * entry - float(pos.get("entry_fee", 0))
                if candidate_realized >= min_net_profit_quote:
                    exit_reason = f"Aşağı kesişim; net kâr en az {MIN_NET_PROFIT_TRY:.2f} TL"
            if exit_reason:
                fee = qty * px * FEE
                realized = qty * px - fee - qty * entry - float(pos.get("entry_fee", 0))
                if realized >= min_net_profit_quote:
                    state["cash"] = round(float(state["cash"]) + qty * px - fee, 8)
                    state["trades"].append({"time": now.isoformat(), "symbol": symbol, "side": "SELL", "qty": qty, "price": px, "realized_pnl": round(realized, 8), "reason": exit_reason})
                    del state["positions"][symbol]
                    pos = None
                    closed_this_bar = True
        if signal == "BUY" and not pos and not closed_this_bar and len(state["positions"]) < MAX_OPEN_POSITIONS:
            budget = min(float(state["cash"]), START_CASH * MAX_POSITION_PCT)
            qty = budget / (px * (1 + FEE))
            if qty > 0:
                fee = qty * px * FEE
                state["cash"] = round(float(state["cash"]) - qty * px - fee, 8)
                state["positions"][symbol] = {"qty": qty, "avg": px, "entry_fee": fee, "entry_time": now.isoformat()}
                state["trades"].append({"time": now.isoformat(), "symbol": symbol, "side": "BUY", "qty": qty, "price": px, "reason": "SMA5/SMA20 bullish crossover; paper only"})
        state["last_bar"][symbol] = bar_time
        state["last_prices"][symbol] = px

    market_value = sum(float(p["qty"]) * float(prices.get(s, state["last_prices"].get(s, p["avg"]))) for s, p in state["positions"].items())
    equity = round(float(state["cash"]) + market_value, 8)
    state["equity_history"].append({"time": now.isoformat(), "equity": equity})
    state["equity_history"] = state["equity_history"][-2000:]
    state["trades"] = state["trades"][-500:]
    state["last_run"] = now.isoformat()
    state["last_prices"].update(prices)
    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {
        "last_run": now.isoformat(), "mode": "paper_only",
        "source": "Yahoo Finance 5-minute candles with Kraken OHLC fallback; USD/USDT quote may differ slightly",
        "sources": sources, "prices": prices, "symbols": updates, "errors": errors,
        "cash": round(float(state["cash"]), 8), "market_value": round(market_value, 8),
        "equity": equity, "return_pct": round((equity / START_CASH - 1) * 100, 4),
        "open_positions": state["positions"], "recent_trades": state["trades"][-25:],
        "strategy": f"5-minute closed candles; SMA5/SMA20 entry; exit only when estimated net profit after entry and exit fees is at least {MIN_NET_PROFIT_TRY:.2f} TRY (quote threshold {min_net_profit_quote:.6f}); USD/TRY source: {fx_source}; no stop-loss; max 10% initial balance per entry; max four positions",
        "usdtry": usdtry, "fx_source": fx_source, "min_net_profit_try": MIN_NET_PROFIT_TRY,
        "note": "Paper simulation only; no real orders. Target is at least 1 TRY estimated net profit after entry and exit fees using the reported USD/TRY reference rate. FX and crypto quote sources can differ, fills are simulated, and 5-minute candles may miss intrabar order; no stop-loss means losing positions may remain open indefinitely. Zero-loss/profit and continuous trades are not guaranteed."
    }
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Crypto paper trader report updated at {now.isoformat()} | equity={equity:.4f} | trades={len(state['trades'])} | errors={len(errors)}")
    for item in updates:
        print(item)
    for error in errors:
        print("WARNING:", error)

if __name__ == "__main__":
    main()
