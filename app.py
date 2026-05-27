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
