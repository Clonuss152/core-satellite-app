import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client
from datetime import date

st.set_page_config(page_title="Core Satellite System", layout="wide")

st.title("Core + Satellite Trading System")

# ===================================================
# SUPABASE VERBINDUNG
# ===================================================

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.success("Supabase Verbindung erfolgreich.")

# ===================================================
# STRATEGIE UNIVERSUM
# ===================================================

CORE_TICKERS = """
AAPL MSFT NVDA AMZN META GOOGL TSLA AVGO COST AMD NFLX ADBE PEP CSCO INTC QCOM TXN AMGN INTU BKNG ISRG AMAT MU LRCX PANW KLAC MELI CDNS SNPS ADP BRK-B JPM V MA UNH XOM LLY PG JNJ HD CVX ABBV MRK KO BAC WMT ORCL CRM LIN MCD ACN CAT IBM GE RTX ADS.DE ALV.DE BAS.DE BAYN.DE BMW.DE DB1.DE DBK.DE DTE.DE EOAN.DE IFX.DE MBG.DE MUV2.DE RHM.DE SAP.DE SIE.DE VOW3.DE AIR.DE BEI.DE BNR.DE EVK.DE FRE.DE HEN3.DE LEG.DE MTX.DE P911.DE RWE.DE SY1.DE ZAL.DE AIXA.DE AT1.DE BC8.DE EVT.DE NEM.DE QIA.DE SRT3.DE ASML.AS MC.PA OR.PA SAN.MC SU.PA TTE.PA AI.PA DG.PA BN.PA ENI.MI ISP.MI ABI.BR
""".split()

SAT_TICKERS = """
1COV.DE ABT ADYEN.AS AFRM AFX.DE AMD APP ARM ASML.AS AVGO BABA BE BKNG BYDDF CCJ CELH CHWY COIN CRWD CVNA DASH DDOG DTG.DE DUOL ENPH ETSY EVGO FSLY FTNT GCT GLOB HOOD HWM IOT JOBY KLAC LSPD MDB MELI META MRVL NET NEXI.MI NICE NIO NOKIA.HE NOW NTRA NVDA OKTA ONON PANW PATH PAYC PDD PLTR QCOM RBLX RIVN RKLB ROKU SHOP SMCI SNOW SOFI SQ STMPA.PA TEAM TEM TOST TSLA TTD TWLO U UBER UPST UTDI.DE VEEV VRT VST VZ WAF.DE WCH.DE XPEV ZS UCG.MI UCB.BR NDA.DE SZG.DE NDX1.DE SAP.DE DB1.DE ALV.DE IFX.DE RHM.DE MBG.DE BMW.DE P911.DE AIR.DE RWE.DE SY1.DE BEI.DE BNR.DE ZAL.DE LEG.DE FRE.DE HEN3.DE AIXA.DE QIA.DE EVT.DE SRT3.DE BC8.DE
""".split()

# ===================================================
# DATEN LADEN
# ===================================================

result = supabase.table("underlyings").select("*").execute()
df = pd.DataFrame(result.data)

# ===================================================
# CASH SYSTEM
# ===================================================

st.header("Cash Management")

with st.form("cash_form"):
    transaction_date = st.date_input("Datum", value=date.today())
    transaction_type = st.selectbox(
        "Typ",
        ["EINZAHLUNG", "AUSZAHLUNG", "STEUER", "GEBUEHR", "KORREKTUR"]
    )
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

cash_result = supabase.table("cash_transactions").select("*").execute()
cash_df = pd.DataFrame(cash_result.data)

st.subheader("Cash Historie")

if not cash_df.empty:
    st.dataframe(cash_df, use_container_width=True)
    st.metric("Gesamte Cash Bewegungen", f"{cash_df['amount'].sum():,.2f} €")
else:
    st.info("Noch keine Cash Buchungen vorhanden.")

# ===================================================
# UNIVERSUM IMPORT
# ===================================================

st.header("Universum initialisieren")

if st.button("CORE/SATELLITE Universum importieren"):
    all_tickers = sorted(set(CORE_TICKERS + SAT_TICKERS))
    imported = 0

    for ticker in all_tickers:
        in_core = ticker in CORE_TICKERS
        in_sat = ticker in SAT_TICKERS

        if in_core and in_sat:
            role = "BOTH"
        elif in_core:
            role = "CORE"
        else:
            role = "SATELLITE"

        try:
            supabase.table("underlyings").upsert(
                {
                    "ticker": ticker,
                    "company_name": ticker,
                    "strategy_role": role
                },
                on_conflict="ticker"
            ).execute()
            imported += 1
        except Exception as e:
            st.warning(f"Importfehler bei {ticker}: {e}")

    st.success(f"{imported} Underlyings importiert/aktualisiert.")
    st.info("Bitte Seite neu laden, damit die Tabelle aktualisiert wird.")

# ===================================================
# UNDERLYINGS MANUELL
# ===================================================

st.header("Neues Underlying hinzufügen")

with st.form("add_underlying_form"):
    ticker = st.text_input("Ticker")
    company_name = st.text_input("Unternehmensname")
    isin = st.text_input("ISIN")
    wkn = st.text_input("WKN")
    strategy_role = st.selectbox("Strategie", ["CORE", "SATELLITE", "BOTH"])
    exchange = st.text_input("Börse")
    currency = st.text_input("Währung")
    submit = st.form_submit_button("Speichern")

    if submit:
        supabase.table("underlyings").upsert(
            {
                "ticker": ticker,
                "company_name": company_name,
                "isin": isin,
                "wkn": wkn,
                "strategy_role": strategy_role,
                "exchange": exchange,
                "currency": currency
            },
            on_conflict="ticker"
        ).execute()
        st.success("Underlying gespeichert/aktualisiert.")

st.header("Gespeicherte Underlyings")
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

# ===================================================
# TRADE HISTORIE
# ===================================================

st.header("Trade Historie")

trade_result = supabase.table("trades").select("*").execute()
trade_df = pd.DataFrame(trade_result.data)

if not trade_df.empty:
    st.dataframe(trade_df, use_container_width=True)
else:
    st.info("Noch keine Trades vorhanden.")

# ===================================================
# OFFENE POSITIONEN
# ===================================================

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
        open_positions["ESTIMATED_POSITION_VALUE"] = (
            open_positions["OPEN_QTY"] * open_positions["LAST_PRICE"]
        )
        st.dataframe(open_positions, use_container_width=True)
        st.metric(
            "Geschätztes investiertes Kapital",
            f"{open_positions['ESTIMATED_POSITION_VALUE'].sum():,.2f} €"
        )
    else:
        st.info("Keine offenen Positionen.")
else:
    st.info("Noch keine Trades vorhanden.")

# ===================================================
# KURSDATEN UPDATE - BATCH VERSION
# ===================================================

st.header("Kursdaten Update")

if st.button("Kursdaten aktualisieren"):
    if not df.empty:
        tickers = df["ticker"].dropna().unique()

        total_rows = 0
        failed_tickers = []

        progress_bar = st.progress(0)

        for idx, ticker in enumerate(tickers):
            ticker = str(ticker).strip()

            try:
                st.write(f"Lade Daten für {ticker}...")

                data = yf.download(
                    ticker,
                    period="5y",
                    auto_adjust=True,
                    progress=False,
                    group_by="column"
                )

                if data.empty:
                    failed_tickers.append(ticker)
                    progress_bar.progress((idx + 1) / len(tickers))
                    continue

                if isinstance(data.columns, pd.MultiIndex):
                    data.columns = data.columns.get_level_values(0)

                data = data.reset_index()
                date_column = data.columns[0]

                required_columns = ["Open", "High", "Low", "Close", "Volume"]

                if not all(col in data.columns for col in required_columns):
                    failed_tickers.append(ticker)
                    progress_bar.progress((idx + 1) / len(tickers))
                    continue

                records = []

                for _, row in data.iterrows():
                    records.append({
                        "ticker": ticker,
                        "price_date": str(pd.to_datetime(row[date_column]).date()),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "adj_close": float(row["Close"]),
                        "volume": float(row["Volume"])
                    })

                if records:
                    supabase.table("price_history").upsert(
                        records,
                        on_conflict="ticker,price_date"
                    ).execute()

                    total_rows += len(records)

                progress_bar.progress((idx + 1) / len(tickers))

            except Exception as e:
                failed_tickers.append(ticker)
                st.warning(f"Fehler bei {ticker}: {e}")

        st.success(f"{total_rows} Kursdaten verarbeitet.")

        if failed_tickers:
            st.warning("Folgende Ticker konnten nicht geladen werden:")
            st.write(failed_tickers)

    else:
        st.warning("Keine Underlyings vorhanden.")

# ===================================================
# MOMENTUM ENGINE
# ===================================================

st.header("Momentum Ranking")

all_price_rows = []
chunk_size = 1000
start = 0

while True:

    chunk = supabase.table("price_history") \
        .select("*") \
        .range(start, start + chunk_size - 1) \
        .execute()

    if not chunk.data:
        break

    all_price_rows.extend(chunk.data)

    if len(chunk.data) < chunk_size:
        break

    start += chunk_size

price_df = pd.DataFrame(all_price_rows)

st.write("Geladene Kursdaten-Zeilen:", len(price_df))

if not price_df.empty:
    st.write("Anzahl Ticker in price_history:", price_df["ticker"].nunique())
    st.write("Ticker mit Kursdaten:", sorted(price_df["ticker"].unique())[:50])

if price_df.empty:
    st.info("Noch keine Kursdaten vorhanden.")
else:
    price_df["price_date"] = pd.to_datetime(price_df["price_date"])
    price_df["adj_close"] = pd.to_numeric(price_df["adj_close"])
    price_df = price_df.sort_values(["ticker", "price_date"])

    def calculate_momentum(prices, lookbacks, weights):
        rows = []

        for ticker, group in prices.groupby("ticker"):
            group = group.sort_values("price_date").reset_index(drop=True)

            if len(group) < max(lookbacks) + 1:
                continue

            latest_price = group.iloc[-1]["adj_close"]
            score = 0
            momentum_values = {}

            for lookback, weight in zip(lookbacks, weights):
                old_price = group.iloc[-lookback - 1]["adj_close"]
                momentum = (latest_price / old_price) - 1
                momentum_values[f"mom_{lookback}d"] = momentum
                score += momentum * weight

            rows.append({
                "ticker": ticker,
                "latest_date": group.iloc[-1]["price_date"].date(),
                "latest_price": latest_price,
                "score": score,
                **momentum_values
            })

        result_df = pd.DataFrame(rows)

        if not result_df.empty:
            result_df = result_df.sort_values("score", ascending=False)
            result_df["rank"] = range(1, len(result_df) + 1)

        return result_df

    core_tickers = []
    sat_tickers = []

    if not df.empty:
        core_tickers = df.loc[
            df["strategy_role"].isin(["CORE", "BOTH"]),
            "ticker"
        ].tolist()

        sat_tickers = df.loc[
            df["strategy_role"].isin(["SATELLITE", "BOTH"]),
            "ticker"
        ].tolist()

    core_prices = price_df[price_df["ticker"].isin(core_tickers)]
    sat_prices = price_df[price_df["ticker"].isin(sat_tickers)]

    core_lookbacks = [63, 126, 189, 252, 504]
    core_weights = [0.10, 0.20, 0.25, 0.25, 0.20]

    sat_lookbacks = [21, 63, 126, 252]
    sat_weights = [0.40, 0.35, 0.20, 0.05]

    core_rank = calculate_momentum(core_prices, core_lookbacks, core_weights)
    sat_rank = calculate_momentum(sat_prices, sat_lookbacks, sat_weights)

    st.subheader("CORE Momentum Ranking")

    if not core_rank.empty:
        st.dataframe(core_rank, use_container_width=True)
    else:
        st.info("Noch nicht genug CORE-Kursdaten für Ranking vorhanden.")

    st.subheader("SATELLITE Momentum Ranking")

    if not sat_rank.empty:
        st.dataframe(sat_rank, use_container_width=True)
    else:
        st.info("Noch nicht genug SATELLITE-Kursdaten für Ranking vorhanden.")
