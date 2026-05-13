import requests
import pandas as pd
import streamlit as st

EVENTS_URL = "https://gamma-api.polymarket.com/events"
ORDERBOOK_URL = "https://clob.polymarket.com/book"

st.set_page_config(page_title="Polymarket Real ROI Rechner", layout="wide")

st.title("Polymarket REAL ROI Rechner")

url = st.text_input("Polymarket Event-Link")
top_n = st.slider("Top Teams", 2, 10, 5)
bankroll = st.number_input("Einsatz ($)", value=100.0)

# -------------------------
# HELPERS
# -------------------------

def extract_slug(url):
    return url.split("/event/")[1].split("?")[0]

def get_event(slug):
    r = requests.get(EVENTS_URL, params={"slug": slug})
    r.raise_for_status()
    return r.json()[0]

def get_best_ask(token_id):
    try:
        r = requests.get(f"{ORDERBOOK_URL}?token_id={token_id}")
        data = r.json()

        asks = data.get("asks", [])
        if not asks:
            return None, 0

        best_ask = float(asks[0]["price"])
        size = float(asks[0]["size"])

        return best_ask, size
    except:
        return None, 0

# -------------------------
# MAIN
# -------------------------

if st.button("Berechnen"):

    slug = extract_slug(url)
    event = get_event(slug)

    markets = event.get("markets", [])

    rows = []

    for m in markets:
        token_ids = m.get("clobTokenIds", [])

        if not token_ids:
            continue

        # YES ist immer erstes Token (meistens)
        token_id = token_ids[0]

        price, size = get_best_ask(token_id)

        if price is None:
            continue

        rows.append({
            "Team": m.get("question"),
            "Ask Price": price,
            "Liquidity": size
        })

    if not rows:
        st.error("Keine Orderbook Daten gefunden")
        st.stop()

    df = pd.DataFrame(rows)

    # sortiere nach niedrigstem Preis (beste Value)
    df = df.sort_values("Ask Price")

    top = df.head(top_n)

    sum_prices = top["Ask Price"].sum()
    roi = (1 / sum_prices) - 1

    payout = bankroll / sum_prices
    profit = payout - bankroll

    # Stake Berechnung
    top["Stake"] = (top["Ask Price"] / sum_prices) * bankroll
    top["Payout if Win"] = top["Stake"] / top["Ask Price"]

    st.subheader(event.get("title"))

    col1, col2, col3 = st.columns(3)

    col1.metric("Summe Preise", round(sum_prices, 4))
    col2.metric("ROI", f"{roi*100:.2f}%")
    col3.metric("Profit", f"${profit:.2f}")

    st.dataframe(top, use_container_width=True)

    # Liquidity Check
    st.subheader("Liquidity Check")

    for _, row in top.iterrows():
        if row["Liquidity"] < row["Stake"]:
            st.warning(f"{row['Team']} hat zu wenig Liquidity!")
        else:
            st.success(f"{row['Team']} ist ausführbar")
            st.error(f"Fehler: {e}")
