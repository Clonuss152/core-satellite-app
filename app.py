import streamlit as st
from supabase import create_client

st.set_page_config(
    page_title="Core Satellite System",
    layout="wide"
)

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.title("Core + Satellite Trading System")

st.success("Supabase Verbindung erfolgreich.")

tables = supabase.table("underlyings").select("*").execute()

st.write("Anzahl Underlyings in Datenbank:")
st.write(len(tables.data))
