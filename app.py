import streamlit as st
import pandas as pd
from supabase import create_client

st.set_page_config(
    page_title="Core Satellite System",
    layout="wide"
)

st.title("Core + Satellite Trading System")

# Supabase Verbindung
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.success("Supabase Verbindung erfolgreich.")

# ---------------------------------------------------
# Neues Underlying hinzufügen
# ---------------------------------------------------

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

# ---------------------------------------------------
# Underlyings anzeigen
# ---------------------------------------------------

st.header("Gespeicherte Underlyings")

result = supabase.table("underlyings").select("*").execute()

df = pd.DataFrame(result.data)

st.dataframe(df, use_container_width=True)
