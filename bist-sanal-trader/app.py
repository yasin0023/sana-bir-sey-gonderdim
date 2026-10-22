import streamlit as st
import pandas as pd
import yfinance as yf
from datetime import datetime

st.set_page_config(page_title="BIST Sanal Trader", page_icon="📈", layout="wide")

START_CASH = 100_000.0
FEE_RATE = 0.001  # illustrative 0.10% per side, not an actual broker tariff
DEFAULT_SYMBOLS = ["THYAO", "ASELS", "TUPRS", "BIMAS", "AKBNK", "GARAN", "FROTO", "SISE"]

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; max-width: 1400px;}
div[data-testid="stMetric"] {background: rgba(120,120,120,.08); padding: 14px; border-radius: 12px;}
.small-note {font-size: .86rem; opacity: .82;}
</style>
""", unsafe_allow_html=True)

st.title("📈 BIST Sanal Trader")
st.caption("Ücretsiz prototip • Sanal portföy • Gerçek emir göndermez")

with st.sidebar:
    st.header("Kontrol paneli")
    raw_symbols = st.text_area("Takip edilecek BIST kodları", ", ".join(DEFAULT_SYMBOLS), height=110)
    symbols = list(dict.fromkeys(
        s.strip().upper().replace(".IS", "")
        for s in raw_symbols.replace("\n", ",").split(",")
        if s.strip()
    ))[:30]
    period = st.selectbox("Geçmiş veri", ["6mo", "1y", "2y", "5y"], index=1)
    st.markdown("---")
    st.markdown("**Strateji (eğitim amaçlı)**")
    st.write("• SMA 20 / SMA 50 kesişimi")
    st.write("• RSI(14) filtresi")
    st.write("• Sanal işlem maliyeti: %0,10 / taraf")
    st.markdown("---")
    if st.button("Sanal portföyü sıfırla", use_container_width=True):
        for k in ["cash", "positions", "trades"]:
            st.session_state.pop(k, None)
        st.rerun()

if "cash" not in st.session_state:
    st.session_state.cash = START_CASH
if "positions" not in st.session_state:
    st.session_state.positions = {}  # symbol -> quantity, average entry
if "trades" not in st.session_state:
    st.session_state.trades = []

@st.cache_data(ttl=300, show_spinner=False)
def get_history(symbol, period):
    ticker = yf.Ticker(f"{symbol}.IS")
    hist = ticker.history(period=period, interval="1d", auto_adjust=True)
    if hist is None or hist.empty:
        return pd.DataFrame()
    hist = hist[["Close", "Volume"]].dropna()
    hist.index = pd.to_datetime(hist.index).tz_localize(None)
    hist["SMA20"] = hist["Close"].rolling(20).mean()
    hist["SMA50"] = hist["Close"].rolling(50).mean()
    delta = hist["Close"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    rs = gain / loss.mask(loss == 0)
    hist["RSI14"] = 100 - (100 / (1 + rs))
    hist.loc[(loss == 0) & (gain > 0), "RSI14"] = 100.0
    hist["RSI14"] = hist["RSI14"].fillna(50)
    hist["CrossUp"] = (hist["SMA20"] > hist["SMA50"]) & (hist["SMA20"].shift(1) <= hist["SMA50"].shift(1))
    hist["CrossDown"] = (hist["SMA20"] < hist["SMA50"]) & (hist["SMA20"].shift(1) >= hist["SMA50"].shift(1))
    return hist

def fmt_try(value):
    return f"{value:,.2f} TL".replace(",", "X").replace(".", ",").replace("X", ".")

st.info("Güvenlik ilkesi: uygulama yalnızca sanal para kullanır. Otomatik emir veya aracı kurum bağlantısı yoktur. Hiçbir strateji kârı garanti edemez.")

if not symbols:
    st.warning("Sol taraftan en az bir hisse kodu gir.")
    st.stop()

rows = []
histories = {}
with st.spinner("Fiyat geçmişi alınıyor (kaynak erişimi ve veri gecikmesi değişebilir)..."):
    for symbol in symbols:
        try:
            h = get_history(symbol, period)
            if h.empty or h["Close"].dropna().empty:
                rows.append({"Hisse": symbol, "Durum": "Veri yok", "Fiyat (TL)": None, "Günlük %": None, "RSI": None, "Sinyal": "VERİ YOK", "Veri tarihi": "—"})
                continue
            histories[symbol] = h
            last = h.iloc[-1]
            prev = h.iloc[-2] if len(h) > 1 else last
            price = float(last["Close"])
            day_pct = (price / float(prev["Close"]) - 1) * 100 if float(prev["Close"]) else 0
            if bool(last["CrossUp"]) and float(last["RSI14"]) < 70:
                signal = "ALIM ADAYI"
            elif bool(last["CrossDown"]) or float(last["RSI14"]) >= 75:
                signal = "SATIŞ / RİSKİ İNCELE"
            elif float(last["SMA20"]) > float(last["SMA50"]) and 40 <= float(last["RSI14"]) <= 68:
                signal = "YÜKSELİŞ EĞİLİMİ"
            else:
                signal = "BEKLE"
            rows.append({"Hisse": symbol, "Durum": "OK", "Fiyat (TL)": price, "Günlük %": day_pct, "RSI": float(last["RSI14"]), "Sinyal": signal, "Veri tarihi": last.name.strftime("%Y-%m-%d")})
        except Exception as e:
            rows.append({"Hisse": symbol, "Durum": "Hata", "Fiyat (TL)": None, "Günlük %": None, "RSI": None, "Sinyal": "VERİ ALINAMADI", "Veri tarihi": "—"})

quotes = pd.DataFrame(rows)
st.subheader("Piyasa izleme listesi")
if not quotes.empty:
    st.dataframe(
        quotes,
        use_container_width=True,
        hide_index=True,
        column_config={
            "Fiyat (TL)": st.column_config.NumberColumn(format="%.2f TL"),
            "Günlük %": st.column_config.NumberColumn(format="%.2f%%"),
            "RSI": st.column_config.NumberColumn(format="%.1f"),
        },
    )
st.caption(f"Son sorgu zamanı: {datetime.now().astimezone().strftime('%d.%m.%Y %H:%M:%S %Z')} • Veri önbelleği 5 dakika. Bu zaman fiyatın güncellik zamanı değildir; her satırdaki 'Veri tarihi' son bar tarihidir.")

st.subheader("Hisse ayrıntısı")
selected = st.selectbox("İncelenecek hisse", [s for s in symbols if s in histories] or symbols)
if selected in histories:
    h = histories[selected]
    latest = h.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Son kapanış", fmt_try(float(latest["Close"])))
    c2.metric("SMA 20", fmt_try(float(latest["SMA20"])) if pd.notna(latest["SMA20"]) else "—")
    c3.metric("SMA 50", fmt_try(float(latest["SMA50"])) if pd.notna(latest["SMA50"]) else "—")
    c4.metric("RSI 14", f"{float(latest['RSI14']):.1f}")
    st.line_chart(h[["Close", "SMA20", "SMA50"]].tail(180), use_container_width=True)
    st.line_chart(h[["RSI14"]].tail(180), use_container_width=True)
    st.markdown(f"[KAP'ta şirket bildirimlerini ara](https://www.kap.org.tr/tr/)")
    st.caption("Grafik günlük fiyat barlarını gösterir; gün içi işlem için gerçek zamanlı veri değildir.")

st.divider()
st.subheader("Sanal portföy")
prices = {s: float(h.iloc[-1]["Close"]) for s, h in histories.items() if not h.empty}
market_value = sum(pos["qty"] * prices.get(s, pos["avg"]) for s, pos in st.session_state.positions.items())
equity = float(st.session_state.cash) + market_value
realized = sum(float(t.get("realized_pnl", 0)) for t in st.session_state.trades)
open_pnl = sum(pos["qty"] * (prices.get(s, pos["avg"]) - pos["avg"]) for s, pos in st.session_state.positions.items())
m1, m2, m3, m4 = st.columns(4)
m1.metric("Nakit", fmt_try(float(st.session_state.cash)))
m2.metric("Pozisyon değeri", fmt_try(market_value))
m3.metric("Toplam sanal varlık", fmt_try(equity), f"{(equity / START_CASH - 1)*100:+.2f}%")
m4.metric("Açık pozisyon K/Z", fmt_try(open_pnl))

left, right = st.columns(2)
with left:
    st.markdown("**Sanal alım**")
    buy_symbol = st.selectbox("Alınacak hisse", list(prices.keys()) or symbols, key="buy_symbol")
    buy_qty = st.number_input("Adet", min_value=1, max_value=100000, value=1, step=1, key="buy_qty")
    buy_price = prices.get(buy_symbol)
    if buy_price is not None:
        st.caption(f"Referans fiyat: {fmt_try(buy_price)} (son alınan kapanış)")
        estimated = buy_qty * buy_price * (1 + 0.001)
        st.caption(f"Tahmini toplam (örnek maliyet dahil): {fmt_try(estimated)}")
    if st.button("Sanal AL", use_container_width=True):
        if buy_price is None:
            st.error("Bu hisse için fiyat yok.")
        else:
            gross = int(buy_qty) * buy_price
            fee = gross * FEE_RATE
            total = gross + fee
            if total > st.session_state.cash:
                st.error("Sanal nakit yetersiz.")
            else:
                pos = st.session_state.positions.get(buy_symbol, {"qty": 0, "avg": 0.0})
                new_qty = pos["qty"] + int(buy_qty)
                pos["avg"] = ((pos["qty"] * pos["avg"]) + gross) / new_qty
                pos["qty"] = new_qty
                st.session_state.positions[buy_symbol] = pos
                st.session_state.cash -= total
                st.session_state.trades.append({"Zaman": datetime.now().astimezone().isoformat(timespec="seconds"), "Hisse": buy_symbol, "İşlem": "SANAL AL", "Adet": int(buy_qty), "Fiyat": round(buy_price, 4), "Maliyet": round(fee, 2), "realized_pnl": 0.0})
                st.success("Sanal alış kaydedildi.")
                st.rerun()
with right:
    st.markdown("**Sanal satış**")
    owned = [s for s, p in st.session_state.positions.items() if p["qty"] > 0]
    sell_symbol = st.selectbox("Satılacak hisse", owned or ["Portföy boş"], key="sell_symbol")
    sell_qty = st.number_input("Satış adedi", min_value=1, max_value=int(st.session_state.positions[sell_symbol]["qty"]) if sell_symbol in st.session_state.positions else 1, value=1, step=1, key="sell_qty")
    if st.button("Sanal SAT", use_container_width=True):
        if sell_symbol not in st.session_state.positions or sell_symbol not in prices:
            st.error("Satılabilir pozisyon veya fiyat yok.")
        else:
            pos = st.session_state.positions[sell_symbol]
            qty = int(sell_qty)
            if qty > pos["qty"]:
                st.error("Eldeki adetten fazla satış yapılamaz.")
            else:
                price = prices[sell_symbol]
                gross = qty * price
                fee = gross * FEE_RATE
                realized_trade = gross - fee - qty * pos["avg"]
                st.session_state.cash += gross - fee
                pos["qty"] -= qty
                st.session_state.positions[sell_symbol] = pos
                st.session_state.trades.append({"Zaman": datetime.now().astimezone().isoformat(timespec="seconds"), "Hisse": sell_symbol, "İşlem": "SANAL SAT", "Adet": qty, "Fiyat": round(price, 4), "Maliyet": round(fee, 2), "realized_pnl": round(realized_trade, 2)})
                if pos["qty"] == 0:
                    del st.session_state.positions[sell_symbol]
                st.success(f"Sanal satış kaydedildi. Bu satışın yaklaşık gerçekleşen K/Z'si: {fmt_try(realized_trade)}")
                st.rerun()

if st.session_state.positions:
    pos_rows = []
    for s, p in st.session_state.positions.items():
        price = prices.get(s, p["avg"])
        pos_rows.append({"Hisse": s, "Adet": p["qty"], "Ortalama alış": p["avg"], "Son kapanış": price, "Piyasa değeri": p["qty"]*price, "Açık K/Z": p["qty"]*(price-p["avg"])})
    st.dataframe(pd.DataFrame(pos_rows), use_container_width=True, hide_index=True)
else:
    st.caption("Henüz sanal pozisyon yok. Denemek için bir hisse seçip sanal alış yapabilirsin.")

st.subheader("Sanal işlem kayıtları")
if st.session_state.trades:
    trade_df = pd.DataFrame(st.session_state.trades)
    visible_cols = [c for c in ["Zaman", "Hisse", "İşlem", "Adet", "Fiyat", "Maliyet", "realized_pnl"] if c in trade_df.columns]
    st.dataframe(trade_df[visible_cols].rename(columns={"realized_pnl": "Gerçekleşen sanal K/Z"}), use_container_width=True, hide_index=True)
    st.download_button("İşlem geçmişini CSV indir", trade_df.to_csv(index=False).encode("utf-8-sig"), file_name="bist_sanal_islemler.csv", mime="text/csv")
else:
    st.write("Bu oturumda henüz işlem yapılmadı.")

st.divider()
st.subheader("Veri kaynakları ve sınırlar")
st.markdown("""
- Fiyat geçmişi: Yahoo Finance üzerinden `.IS` sembolleriyle alınır. Ücretsiz erişim kesilebilir, gecikebilir veya hatalı/eksik veri döndürebilir.
- Resmî Borsa İstanbul verileri ve veri dağıtımı: [Borsa İstanbul — Veri Yayını](https://www.borsaistanbul.com/veriler/veri-yayini). Resmî sayfada yayımlanan bazı ekran verileri 15 dakika gecikmelidir; ücretsiz, lisanslı gerçek zamanlı API varsayılmamıştır.
- Şirket açıklamaları için [KAP](https://www.kap.org.tr/tr/) kontrol edilmelidir. Bu prototip henüz KAP bildirimlerini otomatik analiz etmez.
- Sinyaller geçmiş günlük fiyatlardan hesaplanan teknik kurallardır; yatırım tavsiyesi değildir. Komisyon varsayımı örnektir; vergi, kayma, likidite ve kurumsal işlemler tam modellenmez.
- Sanal portföy oturum bazında tutulur; sayfa oturumu kapanınca sıfırlanabilir. Kalıcı kayıt sonraki sürümde eklenecek.
""")
st.caption("BIST Sanal Trader • v0.2 • Sanal test modu")
