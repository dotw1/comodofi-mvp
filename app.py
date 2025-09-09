
import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import json

st.set_page_config(page_title="Comodofi – MVP", page_icon="📊", layout="wide")

# Sidebar Branding
with st.sidebar:
    st.image("logo.svg")
    st.caption("**Comodofi** — The exchange of influence")
    st.markdown("---")

@st.cache_data
def load_config():
    with open("indices.json", "r") as f:
        return json.load(f)

cfg = load_config()
INDEX_MAP = {i["symbol"]: i for i in cfg["indices"]}
symbols = list(INDEX_MAP.keys())

@st.cache_data(ttl=60)
def load_series(index_cfg):
    src = index_cfg["source"]
    if src["type"] == "csv":
        df = pd.read_csv(src["path"])
        df[src["time_field"]] = pd.to_datetime(df[src["time_field"]])
        df = df.sort_values(src["time_field"])
        df = df.rename(columns={src["time_field"]:"time", src["value_field"]:"value"})
        return df[["time","value"]].reset_index(drop=True)
    elif src["type"] == "url_csv":
        df = pd.read_csv(src["url"])
        df[src["time_field"]] = pd.to_datetime(df[src["time_field"]])
        df = df.sort_values(src["time_field"])
        df = df.rename(columns={src["time_field"]:"time", src["value_field"]:"value"})
        return df[["time","value"]].reset_index(drop=True)
    else:
        raise ValueError("Unsupported source type")

def moving_avg(s, n=30): return s.rolling(n, min_periods=1).mean()
def funding_rate(price_series, lookback=30, k=0.0005):
    ma = moving_avg(price_series, n=lookback)
    premium = (price_series - ma) / ma.replace(0, np.nan)
    return k * premium.fillna(0.0)

def ensure_state():
    if "balances" not in st.session_state: st.session_state.balances = {"USD": 10000.0}
    if "positions" not in st.session_state: st.session_state.positions = []
    if "log" not in st.session_state: st.session_state.log = []
ensure_state()

# Controls
st.sidebar.header("Trade")
symbol = st.sidebar.selectbox("Index", symbols, format_func=lambda s: INDEX_MAP[s]["name"])
lev = st.sidebar.slider("Leverage", 1, 20, 5)
notional = st.sidebar.number_input("Order Notional (USD)", min_value=10.0, value=500.0, step=10.0)
side = st.sidebar.radio("Side", ["LONG","SHORT"], horizontal=True)

idx_cfg = INDEX_MAP[symbol]
df = load_series(idx_cfg)
mark = float(df["value"].iloc[-1])
fr = funding_rate(df["value"]).iloc[-1] * 24 * 100

st.title("📊 Comodofi – Influence Perps (MVP)")
st.caption("Trade attention & influence as indices. Demo only.")

colA, colB = st.columns([3,2], gap="large")
with colA:
    st.subheader(idx_cfg["name"])
    st.line_chart(df.set_index("time")["value"])
with colB:
    st.markdown("**About this index**")
    st.write(idx_cfg["desc"])
    st.metric("Mark", f"{mark:.4f}")
    st.metric("Est. 24h Funding", f"{fr:+.3f}%")
    st.metric("USD Balance", f"${st.session_state.balances['USD']:.2f}")

st.divider()
st.subheader("Place Order")
c1,c2,c3,c4 = st.columns(4)
c1.write(f"**Symbol**: {symbol}")
c2.write(f"**Side**: {side}")
c3.write(f"**Leverage**: {lev}x")
c4.write(f"**Notional**: ${notional:,.2f}")

def open_position(symbol, side, notional, lev, entry):
    qty = (notional * lev) / entry
    if side == "SHORT": qty *= -1
    st.session_state.balances["USD"] -= notional
    pos = {"symbol":symbol, "qty":qty, "entry":entry, "notional":notional, "lev":lev, "opened": datetime.utcnow().isoformat()}
    st.session_state.positions.append(pos)
    st.session_state.log.append({"time": datetime.utcnow(), "action":"OPEN", "symbol":symbol, "side":side, "price":entry, "notional":notional, "lev":lev})

if st.button("Open Position"):
    if notional > st.session_state.balances["USD"]:
        st.error("Insufficient balance.")
    else:
        open_position(symbol, side, notional, lev, mark)
        st.success(f"Opened {side} {symbol} at {mark:.4f}")
        st.experimental_rerun()

st.divider()
st.subheader("Open Positions")
if len(st.session_state.positions)==0:
    st.info("No open positions.")
else:
    rows = []
    for pos in st.session_state.positions:
        pnl = (mark - pos["entry"]) * pos["qty"]
        rows.append({"Symbol": pos["symbol"], "Qty": pos["qty"], "Entry": pos["entry"], "Mark": mark, "Unreal. PnL": pnl})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
    for i,pos in enumerate(list(st.session_state.positions)):
        if st.button(f"Close {pos['symbol']} @ {mark:.4f}", key=f"close_{i}"):
            pnl = (mark - pos["entry"]) * pos["qty"]
            st.session_state.balances["USD"] += pos["notional"] + pnl
            st.session_state.log.append({"time": datetime.utcnow(), "action":"CLOSE", "symbol":pos["symbol"], "pnl":pnl, "price":mark})
            st.session_state.positions.pop(i)
            st.success(f"Closed {pos['symbol']} PnL {pnl:+.2f} USD")
            st.experimental_rerun()

st.divider()
st.subheader("Activity")
if len(st.session_state.log)==0:
    st.info("No activity yet.")
else:
    log_df = pd.DataFrame(st.session_state.log).sort_values("time", ascending=False)
    st.dataframe(log_df, use_container_width=True)

with st.expander("Methodology (MVP)"):
    st.markdown("""
- Indices are loaded from CSV or URLs (e.g., Google Sheets export or GitHub raw). Edit **indices.json** to change sources.
- Perp math (demo): PnL = (Mark − Entry) × Qty. Funding ≈ deviation from 30d moving average.
- No custody, no real money — product concept only.
    """)
