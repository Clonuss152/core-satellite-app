import streamlit as st

st.set_page_config(
    page_title="Core Satellite System",
    layout="wide"
)

st.title("Core + Satellite Trading System")

try:
    from supabase import create_client

    SUPABASE_URL = st.secrets["SUPABASE_URL"]
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

    supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

    result = supabase.table("underlyings").select("*").execute()

    st.success("Supabase Verbindung erfolgreich.")

    st.write("Anzahl Underlyings in Datenbank:")
    st.write(len(result.data))

except Exception as e:
    st.error("Fehler beim Starten oder bei der Supabase-Verbindung.")
    st.code(str(e))
