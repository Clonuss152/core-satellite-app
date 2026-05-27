import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date

st.set_page_config(
    page_title="Core Satellite System",
    layout="wide"
)

st.title("Core + Satellite Trading System")

# ---------------------------------------------------
# Supabase Verbindung
# ---------------------------------------------------

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.success("Supabase Verbindung erfolgreich.")

# ===================================================
# CASH SYSTEM
# ===================================================

st.header("Cash Management")

with st.form("cash_form"):

    transaction_date = st.date_input(
        "Datum",
        value=date.today()
    )

    transaction_type = st.selectbox(
        "Typ",
        [
            "EINZAHLUNG",
            "AUSZAHLUNG",
            "STEUER",
            "GEBUEHR",
            "KORREKTUR"
        ]
    )

    system_type = st.selectbox(
        "System",
        [
            "GESAMT",
            "CORE",
            "SATELLITE"
        ]
    )

    amount = st.number_input(
        "Betrag",
        step=0.01
    )

    broker_cash_after = st.number_input(
        "Broker Cash nach Buchung",
        step=0.01
    )

    description = st.text_input(
        "Beschreibung"
    )

    submit_cash = st.form_submit_button(
        "Cash Buchung speichern"
    )

    if submit_cash:

        supabase.table("cash_transactions").insert({
            "transaction_date": str(transaction_date),
            "transaction_type": transaction_type,
            "system_type": system_type,
            "amount": amount,
            "broker_cash_after": broker_cash_after,
            "description": description
        }).execute()

        st.success("Cash Buchung gespeichert.")

# ===================================================
# CASH ÜBERSICHT
# ===================================================

st.subheader("Cash Historie")

cash_result = supabase.table(
    "cash_transactions"
).select("*").execute()

cash_df = pd.DataFrame(cash_result.data)

if not cash_df.empty:

    st.dataframe(
        cash_df,
        use_container_width=True
    )

    total_cash = cash_df["amount"].sum()

    st.metric(
        "Gesamte Cash Bewegungen",
        f"{total_cash:,.2f} €"
    )

else:
    st.info("Noch keine Cash Buchungen vorhanden.")

# ===================================================
# UNDERLYINGS
# ===================================================

st.header("Neues Underlying hinzufügen")

with st.form("add_underlying_form"):

    ticker = st.text_input("Ticker")
    company_name = st.text_input("Unternehmensname")

    isin = st.text_input("ISIN")
    wkn = st.text_input("WKN")

    strategy_role = st.selectbox(
        "Strategie",
        ["CORE", "SATELLITE"]
    )

    exchange = st.text_input("Börse")
    currency = st.text_input("Währung")

    submit = st.form_submit_button("Speichern")

    if submit:

        supabase.table("underlyings").insert({
            "ticker": ticker,
            "company_name": company_name,
            "isin": isin,
            "wkn": wkn,
            "strategy_role": strategy_role,
            "exchange": exchange,
            "currency": currency
        }).execute()

        st.success("Underlying gespeichert.")

st.header("Gespeicherte Underlyings")

result = supabase.table("underlyings").select("*").execute()

df = pd.DataFrame(result.data)

st.dataframe(df, use_container_width=True)
# ===================================================
# TRADE ERFASSUNG
# ===================================================

st.header("Trade Erfassung")

underlying_options = []

if not df.empty:
    underlying_options = df["ticker"].tolist()

with st.form("trade_form"):

    trade_date = st.date_input("Trade Datum")

    action = st.selectbox(
        "Aktion",
        ["BUY", "SELL"]
    )

    system_type = st.selectbox(
        "System",
        ["CORE", "SATELLITE"]
    )

    underlying_ticker = st.selectbox(
        "Underlying",
        underlying_options
    )

    turbo_wkn = st.text_input("Turbo WKN")
    turbo_isin = st.text_input("Turbo ISIN")

    issuer = st.text_input("Emittent")

    quantity = st.number_input(
        "Stückzahl",
        step=1.0
    )

    price = st.number_input(
        "Kurs",
        step=0.01
    )

    cash_flow = st.number_input(
        "Tatsächlicher Cash Flow laut Broker",
        step=0.01
    )

    actual_leverage = st.number_input(
        "Tatsächlicher Hebel",
        step=0.1
    )

    ko_level = st.number_input(
        "KO Level",
        step=0.01
    )

    notes = st.text_input("Notizen")

    submit_trade = st.form_submit_button(
        "Trade speichern"
    )

    if submit_trade:

        theoretical_value = quantity * price

        implicit_costs = abs(
            cash_flow - theoretical_value
        )

        supabase.table("trades").insert({
            "trade_date": str(trade_date),
            "system_type": system_type,
            "action": action,
            "underlying_ticker": underlying_ticker,
            "turbo_wkn": turbo_wkn,
            "turbo_isin": turbo_isin,
            "issuer": issuer,
            "quantity": quantity,
            "price": price,
            "gross_amount": theoretical_value,
            "net_cash_effect": cash_flow,
            "fees": implicit_costs,
            "notes": notes
        }).execute()

        st.success("Trade gespeichert.")

# ===================================================
# TRADE HISTORIE
# ===================================================

st.header("Trade Historie")

trade_result = supabase.table(
    "trades"
).select("*").execute()

trade_df = pd.DataFrame(trade_result.data)

if not trade_df.empty:

    st.dataframe(
        trade_df,
        use_container_width=True
    )

else:
    st.info("Noch keine Trades vorhanden.")
