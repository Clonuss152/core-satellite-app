import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client
from datetime import date

st.set_page_config(page_title="Core Satellite System", layout="wide")

st.title("Core + Satellite Trading System")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.success("Supabase Verbindung erfolgreich.")

st.header("Cash Management")

with st.form("cash_form"):
    transaction_date = st.date_input("Datum", value=date.today())
    transaction_type = st.selectbox("Typ", ["EINZAHLUNG", "AUSZAHLUNG", "STEUER", "GEBUEHR", "KORREKTUR"])
    system_type = st.selectbox("System", ["GESAMT", "CORE", "SATELLITE"])
    amount = st.number_input("Betrag", step=0.01)
    broker_cash_after = st.number_input("Broker Cash nach Buchung", step=0.01)
    description = st.text_input("Beschreibung")
    submit_cash = st.form_submit_button("Cash Buchung speichern")

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

st.subheader("Cash Historie")

cash_result = supabase.table("cash_transactions").select("*").execute()
cash_df = pd.DataFrame(cash_result.data)

if not cash_df.empty:
    st.dataframe(cash_df, use_container_width=True)
    st.metric("Gesamte Cash Bewegungen", f"{cash_df['amount'].sum():,.2f} €")
else:
    st.info("Noch keine Cash Buchungen vorhanden.")

st.header("Neues Underlying hinzufügen")

with st.form("add_underlying_form"):
    ticker = st.text_input("Ticker")
    company_name = st.text_input("Unternehmensname")
    isin = st.text_input("ISIN")
    wkn = st.text_input("WKN")
    strategy_role = st.selectbox("Strategie", ["CORE", "SATELLITE"])
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

st.header("Trade Erfassung")

underlying_options = []
if not df.empty:
    underlying_options = df["ticker"].tolist()

with st.form("trade_form"):
    trade_date = st.date_input("Trade Datum")
    action = st.selectbox("Aktion", ["BUY", "SELL"])
    system_type = st.selectbox("System", ["CORE", "SATELLITE"])
    underlying_ticker = st.selectbox("Underlying", underlying_options)
    turbo_wkn = st.text_input("Turbo WKN")
    turbo_isin = st.text_input("Turbo ISIN")
    issuer = st.text_input("Emittent")
    quantity = st.number_input("Stückzahl", step=1.0)
    price = st.number_input("Kurs", step=0.01)
    cash_flow = st.number_input("Tatsächlicher Cash Flow laut Broker", step=0.01)
    actual_leverage = st.number_input("Tatsächlicher Hebel", step=0.1)
    ko_level = st.number_input("KO Level", step=0.01)
    notes = st.text_input("Notizen")
    submit_trade = st.form_submit_button("Trade speichern")

    if submit_trade:
        theoretical_value = quantity * price
        implicit_costs = abs(cash_flow - theoretical_value)

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
            "actual_leverage": actual_leverage,
            "ko_level": ko_level,
            "notes": notes
        }).execute()

        st.success("Trade gespeichert.")

st.header("Trade Historie")

trade_result = supabase.table("trades").select("*").execute()
trade_df = pd.DataFrame(trade_result.data)

if not trade_df.empty:
    st.dataframe(trade_df, use_container_width=True)
else:
    st.info("Noch keine Trades vorhanden.")

st.header("Offene Positionen")

if not trade_df.empty:
    grouped = trade_df.groupby(
        ["system_type", "underlying_ticker", "turbo_wkn"],
        dropna=False
    ).apply(
        lambda x: pd.Series({
            "BUY_QTY": x.loc[x["action"] == "BUY", "quantity"].sum(),
            "SELL_QTY": x.loc[x["action"] == "SELL", "quantity"].sum(),
            "LAST_PRICE": x.iloc[-1]["price"],
            "LAST_LEVERAGE": x.iloc[-1].get("actual_leverage", None),
            "LAST_KO": x.iloc[-1].get("ko_level", None),
        })
    ).reset_index()

    grouped["OPEN_QTY"] = grouped["BUY_QTY"] - grouped["SELL_QTY"]
    open_positions = grouped[grouped["OPEN_QTY"] > 0]

    if not open_positions.empty:
        open_positions["ESTIMATED_POSITION_VALUE"] = open_positions["OPEN_QTY"] * open_positions["LAST_PRICE"]
        st.dataframe(open_positions, use_container_width=True)
        st.metric("Geschätztes investiertes Kapital", f"{open_positions['ESTIMATED_POSITION_VALUE'].sum():,.2f} €")
    else:
        st.info("Keine offenen Positionen.")
else:
    st.info("Noch keine Trades vorhanden.")

st.header("Kursdaten Update")

if st.button("Kursdaten aktualisieren"):
    if not df.empty:
        tickers = df["ticker"].dropna().unique()
        inserted_rows = 0
        progress_bar = st.progress(0)

        for idx, ticker in enumerate(tickers):
            ticker = str(ticker).strip()

            try:
                st.write(f"Lade Daten für {ticker}...")

                data = yf.download(
                    ticker,
                    period="2y",
                    auto_adjust=False,
                    progress=False,
                    group_by="column"
                )

                if data.empty:
                    st.warning(f"Keine Daten für {ticker} gefunden.")
                    progress_bar.progress((idx + 1) / len(tickers))
                    continue

                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)

                data = data.reset_index()

                date_column = data.columns[0]

                required_columns = ["Open", "High", "Low", "Close", "Adj Close", "Volume"]
                missing_columns = [col for col in required_columns if col not in data.columns]

                if missing_columns:
                    st.warning(f"Fehlende Spalten bei {ticker}: {missing_columns}")
                    progress_bar.progress((idx + 1) / len(tickers))
                    continue

                for _, row in data.iterrows():
                    record = {
                        "ticker": ticker,
                        "price_date": str(pd.to_datetime(row[date_column]).date()),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "adj_close": float(row["Adj Close"]),
                        "volume": float(row["Volume"])
                    }

                    try:
                        supabase.table("price_history").upsert(record).execute()
                        inserted_rows += 1
                    except Exception as e:
                        st.warning(f"Speicherfehler bei {ticker}: {e}")

                progress_bar.progress((idx + 1) / len(tickers))

            except Exception as e:
                st.warning(f"Fehler bei {ticker}: {e}")

        st.success(f"{inserted_rows} Kursdaten gespeichert.")
    else:
        st.warning("Keine Underlyings vorhanden.")
