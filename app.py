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

# --- Front page logo & tagline ---
st.image("logo.svg", width=220)
st.markdown("<h1 style='text-align: center;'>Comodofi</h1>", unsafe_allow_html=True)
st.markdown("<p style='text-align: center; color: gray;'>The exchange of influence</p>", unsafe_allow_html=True)
st.divider()

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
# --- Hero (centered) ---
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    st.image("logo.svg", width=96)  # ← same existing file
    st.markdown(
        "<div style='text-align:center; font-size:2.6rem; font-weight:800; margin-top:.5rem;'>Comodofi</div>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<div style='text-align:center; font-size:1.15rem; color:gray; margin-top:.2rem;'>The exchange of influence</div>",
        unsafe_allow_html=True
    )
    
# ---- Sidebar (ONE block only) ----
with st.sidebar:
    st.image("logo.svg", width=48)   # ← use the existing file
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

# --- Front page logo & brand ---
st.image("The exchange of influence.png", width=280)
st.markdown(
    "<div style='text-align:center; font-size:1.2rem; color:gray;'>The exchange of influence</div>",
    unsafe_allow_html=True

colA, colB = st.columns([3,2], gap="large")
with colA:
    # --- Robinhood-style header (big price + change) ---
    dfv = df.copy()
    # timeframe toggle
    tf = st.radio("Timeframe", ["1D","1W","1M","3M","1Y","ALL"], horizontal=True, index=2, label_visibility="collapsed")
    periods = {"1D": pd.Timedelta(days=1), "1W": pd.Timedelta(weeks=1),
               "1M": pd.Timedelta(days=30), "3M": pd.Timedelta(days=90),
               "1Y": pd.Timedelta(days=365)}
    if tf != "ALL":
        start = dfv["time"].max() - periods[tf]
        dfv = dfv[dfv["time"] >= start]

    current = float(dfv["value"].iloc[-1])
    first   = float(dfv["value"].iloc[0])
    chg     = current - first
    chg_pct = (chg / first) * 100 if first != 0 else 0.0
    up = chg >= 0
    color = "#00C805" if up else "#FF3B30"   # robinhood green / red

    # price header
    st.markdown(
        f"""
        <div style="display:flex;align-items:baseline;gap:.75rem;">
          <div style="font-size:2rem;font-weight:800;">{current:.4f}</div>
          <div style="font-size:1rem;color:{color};font-weight:600;">
            {chg:+.4f} ({chg_pct:+.2f}%)
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # --- Minimal, friendly area chart ---
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dfv["time"], y=dfv["value"],
        mode="lines",
        line=dict(width=2, color=color),
        fill="tozeroy",
        fillcolor="rgba(0,200,5,0.10)" if up else "rgba(255,59,48,0.10)",
        hovertemplate="%{x|%Y-%m-%d}<br><b>%{y:.4f}</b><extra></extra>",
        name=""
    ))

    fig.update_layout(
        showlegend=False,
        margin=dict(l=6, r=6, t=6, b=6),
        height=340,
        hovermode="x unified",
        xaxis=dict(showgrid=False, zeroline=False, showspikes=True, spikemode="across", spikesnap="cursor"),
        yaxis=dict(showgrid=False, zeroline=False),
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
