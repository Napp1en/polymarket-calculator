import json
import re
import requests
import pandas as pd
import streamlit as st

EVENTS_URL = "https://gamma-api.polymarket.com/events"

st.set_page_config(page_title="Polymarket Top-N Rechner", layout="wide")

st.title("Polymarket Top-N ROI Rechner")

url = st.text_input("Polymarket Event-Link")
top_n = st.number_input("Anzahl Top Teams", min_value=1, max_value=20, value=5, step=1)
bankroll = st.number_input("Einsatz in $", min_value=1.0, value=100.0, step=10.0)

def extract_slug(url_or_slug):
    if "/event/" in url_or_slug:
        return url_or_slug.split("/event/")[1].split("?")[0].split("#")[0].strip("/")
    return url_or_slug.strip()

def parse_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return []

def get_event_by_slug(slug):
    params = {"slug": slug, "limit": 1}
    r = requests.get(EVENTS_URL, params=params, timeout=20)
    r.raise_for_status()
    data = r.json()

    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return None

def get_yes_price(market):
    outcomes = parse_list(market.get("outcomes"))
    prices = parse_list(market.get("outcomePrices"))

    for outcome, price in zip(outcomes, prices):
        if str(outcome).lower() == "yes":
            return float(price)

    return None

def market_name(market):
    return market.get("question") or market.get("title") or market.get("slug")

if st.button("Berechnen"):
    if not url:
        st.error("Bitte Polymarket-Link einfügen.")
    else:
        slug = extract_slug(url)

        try:
            event = get_event_by_slug(slug)

            if not event:
                st.error("Event nicht gefunden.")
                st.stop()

            markets = event.get("markets", [])
            teams = []

            for market in markets:
                price = get_yes_price(market)

                if price is None or price <= 0:
                    continue

                teams.append({
                    "Team / Markt": market_name(market),
                    "YES Preis": price,
                })

            if not teams:
                st.error("Keine YES-Preise gefunden.")
                st.stop()

            teams = sorted(teams, key=lambda x: x["YES Preis"], reverse=True)
            top = teams[:int(top_n)]

            yes_sum = sum(t["YES Preis"] for t in top)
            roi = (1 / yes_sum) - 1
            payout = bankroll / yes_sum
            profit = payout - bankroll

            rows = []

            for t in top:
                stake = (t["YES Preis"] / yes_sum) * bankroll
                rows.append({
                    "Team / Markt": t["Team / Markt"],
                    "YES Preis": round(t["YES Preis"], 4),
                    "Stake $": round(stake, 2),
                    "Payout wenn Treffer $": round(stake / t["YES Preis"], 2),
                })

            df = pd.DataFrame(rows)

            st.subheader(event.get("title") or slug)

            col1, col2, col3, col4 = st.columns(4)
            col1.metric("Summe Top N", round(yes_sum, 4))
            col2.metric("ROI", f"{roi * 100:.2f}%")
            col3.metric("Payout", f"${payout:.2f}")
            col4.metric("Profit", f"${profit:.2f}")

            st.dataframe(df, use_container_width=True)

            if yes_sum >= 1:
                st.warning("Top-N-Summe ist >= 1. Kein positiver ROI.")
            else:
                st.success("Top-N-Summe ist < 1. Positiver theoretischer ROI.")

        except Exception as e:
            st.error(f"Fehler: {e}")