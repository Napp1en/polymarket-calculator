import json
import requests
import pandas as pd
import streamlit as st

EVENTS_URL = "https://gamma-api.polymarket.com/events"
BOOK_URL = "https://clob.polymarket.com/book"

st.set_page_config(page_title="Polymarket Real ROI Rechner", layout="wide")
st.title("Polymarket REAL ROI Rechner")

url = st.text_input("Polymarket Event-Link")
top_n = st.slider("Top Teams", 2, 20, 5)
bankroll = st.number_input("Gesamteinsatz ($)", min_value=1.0, value=100.0, step=10.0)


def parse_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return []
    return []


def extract_slug(value):
    if "/event/" in value:
        return value.split("/event/")[1].split("?")[0].split("#")[0].strip("/")
    return value.strip()


def get_event(slug):
    r = requests.get(EVENTS_URL, params={"slug": slug, "limit": 1}, timeout=20)
    r.raise_for_status()
    data = r.json()

    if isinstance(data, list) and data:
        return data[0]

    return None


def get_yes_token_id(market):
    outcomes = parse_list(market.get("outcomes"))
    token_ids = parse_list(market.get("clobTokenIds"))

    for outcome, token_id in zip(outcomes, token_ids):
        if str(outcome).lower() == "yes":
            return str(token_id)

    return None


def get_orderbook(token_id):
    try:
        r = requests.get(BOOK_URL, params={"token_id": token_id}, timeout=10)

        if r.status_code != 200:
            return []

        data = r.json()
        asks = data.get("asks", [])

        clean_asks = []

        for ask in asks:
            try:
                price = float(ask["price"])
                size = float(ask["size"])
                if price > 0 and size > 0:
                    clean_asks.append({"price": price, "size": size})
            except:
                continue

        clean_asks.sort(key=lambda x: x["price"])

        return clean_asks

    except:
        return []

    # Wichtig: billigste Ask-Level zuerst kaufen
    clean_asks.sort(key=lambda x: x["price"])

    return clean_asks


def cost_to_buy_shares(asks, shares_needed):
    remaining = shares_needed
    cost = 0.0

    for level in asks:
        take = min(remaining, level["size"])
        cost += take * level["price"]
        remaining -= take

        if remaining <= 1e-9:
            return cost

    return None  # nicht genug Liquidität


def total_depth(asks):
    return sum(level["size"] for level in asks)


def best_ask(asks):
    if not asks:
        return None
    return asks[0]["price"]


def find_equal_payout(selected, bankroll):
    """
    Sucht die maximale gleiche Auszahlung q.
    Für jedes Team kaufen wir q YES-Shares.
    Wenn eins der Teams gewinnt, bekommst du q Dollar.
    """
    max_possible_q = min(total_depth(team["asks"]) for team in selected)

    low = 0.0
    high = max_possible_q

    for _ in range(60):
        mid = (low + high) / 2

        total_cost = 0.0
        possible = True

        for team in selected:
            cost = cost_to_buy_shares(team["asks"], mid)

            if cost is None:
                possible = False
                break

            total_cost += cost

        if possible and total_cost <= bankroll:
            low = mid
        else:
            high = mid

    payout = low

    stakes = []
    total_cost = 0.0

    for team in selected:
        cost = cost_to_buy_shares(team["asks"], payout)
        avg_price = cost / payout if payout > 0 else None
        total_cost += cost

        stakes.append({
            "Team / Markt": team["name"],
            "Best Ask": best_ask(team["asks"]),
            "Avg Buy Price": avg_price,
            "Shares": payout,
            "Stake $": cost,
            "Depth Shares": total_depth(team["asks"]),
            "Ausführbar": cost is not None,
        })

    return payout, total_cost, stakes


if st.button("Berechnen"):
    if not url:
        st.error("Bitte Polymarket-Link einfügen.")
        st.stop()

    try:
        slug = extract_slug(url)
        event = get_event(slug)

        if not event:
            st.error("Event nicht gefunden.")
            st.stop()

        markets = event.get("markets", [])
        teams = []

        for market in markets:
            token_id = get_yes_token_id(market)

            if not token_id:
                continue

            asks = get_orderbook(token_id)

            if not asks:
                continue

            name = market.get("question") or market.get("title") or market.get("slug")

            teams.append({
                "name": name,
                "token_id": token_id,
                "asks": asks,
                "best_ask": best_ask(asks),
            })

        if len(teams) < top_n:
            st.error("Nicht genug Märkte mit Orderbook-Daten gefunden.")
            st.stop()

        # Top Teams = höchste YES-Wahrscheinlichkeit = höchster Best Ask
        teams.sort(key=lambda x: x["best_ask"], reverse=True)
        selected = teams[:top_n]

        payout, real_cost, stake_rows = find_equal_payout(selected, bankroll)

        if payout <= 0:
            st.error("Nicht genug Liquidität für Berechnung.")
            st.stop()

        profit = payout - real_cost
        roi = profit / real_cost if real_cost > 0 else 0
        implied_sum = real_cost / payout

        st.subheader(event.get("title") or slug)

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Real Cost", f"${real_cost:.2f}")
        col2.metric("Payout wenn Top-N gewinnt", f"${payout:.2f}")
        col3.metric("Real Profit", f"${profit:.2f}")
        col4.metric("Real ROI", f"{roi * 100:.2f}%")

        st.metric("Effektive Summe", f"{implied_sum:.4f}")

        df = pd.DataFrame(stake_rows)

        df["Best Ask"] = df["Best Ask"].round(4)
        df["Avg Buy Price"] = df["Avg Buy Price"].round(4)
        df["Shares"] = df["Shares"].round(2)
        df["Stake $"] = df["Stake $"].round(2)
        df["Depth Shares"] = df["Depth Shares"].round(2)

        st.dataframe(df, use_container_width=True)

        if roi > 0:
            st.success("Positiver realer ROI auf Basis der aktuellen Orderbook-Tiefe.")
        else:
            st.warning("Kein positiver realer ROI nach Orderbook-Tiefe.")

    except Exception as e:
        st.error(f"Fehler: {e}")
