import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime
import json
import plotly.graph_objects as go  # keep this if you added Plotly

TAKER_FEE_BPS = 5            # 0.05% taker fee (demo)
MAINT_MARGIN_RATIO = 0.005   # 0.5% maintenance margin (demo)


# ---- Page config (must be exactly once and before any other st.* call) ----
st.set_page_config(page_title="Comodofi – MVP", page_icon="📊", layout="wide")

# ---- Access Gate (invite-only) ----
INVITE_CODE = "COMODOFI2025"  # change this if you want

if "auth_ok" not in st.session_state:
    st.session_state.auth_ok = False
if "nickname" not in st.session_state:
    st.session_state.nickname = ""

if not st.session_state.auth_ok:
    st.title("🔒 Comodofi Access")
    st.caption("Enter the invite code to try the demo.")
    code = st.text_input("Invite code", type="password")
    nick = st.text_input("Pick a nickname (for the leaderboard)")
    if st.button("Enter"):
        if code.strip() == INVITE_CODE and nick.strip():
            st.session_state.auth_ok = True
            st.session_state.nickname = nick.strip()[:20]
            st.experimental_rerun()
        else:
            st.error("Wrong code or missing nickname.")
    st.stop()

# ---- Config & indices (must load BEFORE building the sidebar) ----
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

# --- Minimal styling for a clean hero ---
st.markdown("""
<style>
.hero-wrap { text-align:center; margin: -0.5rem 0 1.25rem 0; }
.hero-title { font-size: 2.25rem; font-weight: 800; line-height: 1.1; }
.hero-sub   { font-size: 0.95rem; color: #6b7280; margin-top: 0.15rem; }
.hero-tag   { font-size: 0.9rem; color: #94a3b8; margin-top: 0.35rem; }
</style>
""", unsafe_allow_html=True)


# ---- Sidebar (ONE block only) ----
with st.sidebar:
    # Branding
    st.image("logo.svg")
    st.caption("**Comodofi** — The exchange of influence")
    st.markdown("---")

    # Actions
    if st.button("🔄 Refresh data"):
        st.cache_data.clear()
        st.experimental_rerun()

    if st.button("🧹 Reset demo wallet to $10,000"):
        st.session_state.balances = {"USD": 10000.0}
        st.session_state.positions = []
        st.session_state.log = []
        st.success("Wallet reset.")
        st.experimental_rerun()

    # Add Index by URL
    with st.expander("➕ Add Index by URL (CSV)"):
        st.caption("Google Sheets → Share → Publish to web → CSV. CSV must have columns: timestamp, value.")
        _sym  = st.text_input("Symbol (e.g., TWITTER_BUZZ)")
        _name = st.text_input("Display name")
        _desc = st.text_area("Description")
        _url  = st.text_input("CSV URL")
        _dec  = st.number_input("Decimals", 0, 6, 2)
        if st.button("Add index"):
            try:
                test = pd.read_csv(_url)
                cols = {c.lower() for c in test.columns}
                if not {"timestamp","value"}.issubset(cols):
                    st.error("CSV must contain columns: timestamp, value")
                else:
                    INDEX_MAP[_sym] = {
                        "symbol": _sym,
                        "name": _name or _sym,
                        "desc": _desc or "User-added index",
                        "source": {"type":"url_csv","url":_url,"value_field":"value","time_field":"timestamp"},
                        "format": {"decimals": int(_dec), "unit": ""}
                    }
                    symbols.append(_sym)
                    st.success(f"Added {_sym}. Select it in the Index dropdown.")
            except Exception as e:
                st.error(f"Could not load CSV: {e}")

    # Category + Index pickers
    categories = sorted({INDEX_MAP[s].get("category", "Other") for s in symbols})
    cat = st.selectbox("Category", ["All"] + categories)
    filtered_symbols = [s for s in symbols if cat == "All" or INDEX_MAP[s].get("category") == cat]

    symbol = st.selectbox(
        "Index",
        filtered_symbols if filtered_symbols else symbols,
        format_func=lambda s: INDEX_MAP[s]["name"]
    )

    # Trade controls
    st.header("Trade")
    lev = st.slider("Leverage", 1, 20, 5)
    notional = st.number_input("Order Notional (USD)", min_value=10.0, value=500.0, step=10.0)
    side = st.radio("Side", ["LONG","SHORT"], horizontal=True)


idx_cfg = INDEX_MAP[symbol]
df = load_series(idx_cfg)
mark = float(df["value"].iloc[-1])
fr = funding_rate(df["value"]).iloc[-1] * 24 * 100

# Centered hero with logo + brand
# --- Clean hero: logo + brand side by side ---
c1, c2, c3 = st.columns([1, 2, 1])
with c2:
    st.markdown("""
    <div class="hero-wrap" style="display:flex; align-items:center; justify-content:center; gap:0.6rem;">
      <img src="logo.svg" width="48">
      <div class="hero-title">Comodofi</div>
    </div>
    <div class="hero-sub">The exchange of influence</div>
    """, unsafe_allow_html=True)


colA, colB = st.columns([3,2], gap="large")
with colA:
    st.subheader(idx_cfg["name"])


    df = df.copy()
    
    df["ma20"] = df["value"].rolling(20, min_periods=1).mean()
    df["ma50"] = df["value"].rolling(50, min_periods=1).mean()

 
    def _ma(s, n=30): return s.rolling(n, min_periods=1).mean()
    prem = (df["value"] - _ma(df["value"], 30)) / _ma(df["value"], 30).replace(0, np.nan)
    df["funding_daily_pct"] = (0.0005 * prem.fillna(0)) * 24 * 100

    fig = go.Figure()
   
    fig.add_trace(go.Scatter(x=df["time"], y=df["value"], name="Index", mode="lines"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["ma20"],  name="MA20",  mode="lines"))
    fig.add_trace(go.Scatter(x=df["time"], y=df["ma50"],  name="MA50",  mode="lines"))

    fig.add_trace(go.Scatter(
        x=df["time"], y=df["funding_daily_pct"], name="Funding (24h %)",
        mode="lines", yaxis="y2"
    ))

    fig.update_layout(
        xaxis=dict(title="Date", rangeslider=dict(visible=True)),
        yaxis=dict(title="Index"),
        yaxis2=dict(title="Funding %", overlaying="y", side="right", showgrid=False),
        legend=dict(orientation="h", y=1.1),
        margin=dict(l=10, r=10, t=10, b=10),
        height=420
    )

    st.plotly_chart(fig, use_container_width=True)

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
# --- Fee + liquidation estimate ---
entry = mark
qty = (notional * lev) / entry * (1 if side == "LONG" else -1)
fee = notional * (TAKER_FEE_BPS / 10_000)
maint = MAINT_MARGIN_RATIO * notional

# equity ≈ notional - fee + (P - entry) * qty == maint
# → P(liq) = entry + (maint - (notional - fee)) / qty
liq_price = entry + (maint - (notional - fee)) / qty if qty != 0 else float("nan")

lc1, lc2 = st.columns(2)
lc1.metric("Est. taker fee", f"${fee:,.2f}")
lc2.metric("Est. liq price", f"{liq_price:.4f}" if np.isfinite(liq_price) else "—")


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
