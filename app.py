import streamlit as st
import pandas as pd
import yfinance as yf
from supabase import create_client
from datetime import date

from config import CORE_TICKERS, SAT_TICKERS
from utils import add_business_days
from daily_update import run_daily_update
from metadata import enrich_underlying_metadata
from snapshot_loader import (
    load_latest_regime_snapshot,
    load_latest_momentum_snapshot,
    load_latest_order_snapshot
)

st.set_page_config(page_title="Core Satellite System", layout="wide")
st.title("Core + Satellite Trading System")

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

st.success("Supabase Verbindung erfolgreich.")

today = date.today()

underlying_result = supabase.table("underlyings").select("*").execute()
df = pd.DataFrame(underlying_result.data)

trade_result = supabase.table("trades").select("*").execute()
trade_df = pd.DataFrame(trade_result.data)

cash_result = supabase.table("cash_transactions").select("*").execute()
cash_df = pd.DataFrame(cash_result.data)

rebalance_result = supabase.table("rebalance_state").select("*").execute()
rebalance_df = pd.DataFrame(rebalance_result.data)
status_result = supabase.table("system_status").select("*").execute()
status_df = pd.DataFrame(status_result.data)
open_positions = pd.DataFrame()

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
            "LAST_KO": x.iloc[-1].get("ko_level", None)
        })
    ).reset_index()

    grouped["OPEN_QTY"] = grouped["BUY_QTY"] - grouped["SELL_QTY"]
    open_positions = grouped[grouped["OPEN_QTY"] > 0].copy()

    if not open_positions.empty:
        open_positions["ESTIMATED_POSITION_VALUE"] = (
            open_positions["OPEN_QTY"] * open_positions["LAST_PRICE"]
        )

tab_dashboard, tab_portfolio, tab_trades, tab_data, tab_admin = st.tabs(
    ["Dashboard", "Portfolio", "Trades", "Daten", "Admin"]
)

with tab_dashboard:
    st.header("Daily Update")

    if st.button(
        "Daily Update ausführen",
        key="dashboard_daily_update"
    ):

        with st.spinner(
            "Daily Update läuft..."
        ):

            run_daily_update(
                incremental=True
            )

        st.success(
            "Daily Update erfolgreich abgeschlossen."
        )

        st.rerun()
    st.header("Snapshot Dashboard")

    st.subheader("System Status")

    last_update = "Noch kein Update"

    if not status_df.empty:

        row = status_df[
            status_df["status_key"]
            == "last_daily_update"
        ]

        if not row.empty and row.iloc[0]["status_value"]:

            timestamp_raw = row.iloc[0][
                "status_value"
            ]

            timestamp_dt = pd.to_datetime(
                timestamp_raw,
                utc=True
            ).tz_convert(
                "Europe/Berlin"
            )

            last_update = timestamp_dt.strftime(
                "%d.%m.%Y %H:%M Uhr"
            )

    col_a, col_b, col_c = st.columns(3)

    col_a.metric("Letztes Daily Update", last_update)

    next_core_display = "Noch nicht gesetzt"
    next_sat_display = "Noch nicht gesetzt"

    if not rebalance_df.empty:
        core_state = rebalance_df[rebalance_df["system_type"] == "CORE"]
        sat_state = rebalance_df[rebalance_df["system_type"] == "SATELLITE"]

        if not core_state.empty and core_state.iloc[0]["next_rebalance_date"]:
            next_core_raw = core_state.iloc[0]["next_rebalance_date"]
            next_core_display = pd.to_datetime(next_core_raw).strftime("%d.%m.%Y")

        if not sat_state.empty and sat_state.iloc[0]["next_rebalance_date"]:
            next_sat_raw = sat_state.iloc[0]["next_rebalance_date"]
            next_sat_display = pd.to_datetime(next_sat_raw).strftime("%d.%m.%Y")

    col_b.metric("Nächstes CORE Rebalance", next_core_display)
    col_c.metric("Nächstes SAT Rebalance", next_sat_display)
    regime_snapshot = load_latest_regime_snapshot(supabase)

    if not regime_snapshot.empty:
        latest_regime = regime_snapshot.iloc[0]

        col1, col2 = st.columns(2)

        col1.metric("CORE Regime", latest_regime["regime"])
        col2.metric("Top10 Momentum", f"{latest_regime['top10_momentum']:.2%}")
    else:
        st.info("Noch kein Regime Snapshot vorhanden.")

    core_snapshot = load_latest_momentum_snapshot(supabase, "CORE")
    sat_snapshot = load_latest_momentum_snapshot(supabase, "SATELLITE")

    st.subheader("CORE Zielportfolio")

    if not core_snapshot.empty:
        st.dataframe(core_snapshot.sort_values("rank"), use_container_width=True)
    else:
        st.info("Keine CORE Snapshots vorhanden.")

    st.subheader("SATELLITE Zielportfolio")

    if not sat_snapshot.empty:
        st.dataframe(sat_snapshot.sort_values("rank"), use_container_width=True)
    else:
        st.info("Keine SATELLITE Snapshots vorhanden.")

    core_orders_snapshot = load_latest_order_snapshot(supabase, "CORE")
    sat_orders_snapshot = load_latest_order_snapshot(supabase, "SATELLITE")

    st.header("Order Engine")

    st.subheader("CORE Orders")

    if not core_orders_snapshot.empty:
        st.dataframe(core_orders_snapshot, use_container_width=True)
    else:
        st.info("Keine CORE Orders vorhanden.")

    st.subheader("SATELLITE Orders")

    if not sat_orders_snapshot.empty:
        st.dataframe(sat_orders_snapshot, use_container_width=True)
    else:
        st.info("Keine SATELLITE Orders vorhanden.")


with tab_portfolio:
    st.header("Portfolio")

    st.subheader("Cash Historie")

    if not cash_df.empty:
        st.dataframe(cash_df, use_container_width=True)
        st.metric("Gesamte Cash Bewegungen", f"{cash_df['amount'].sum():,.2f} €")
    else:
        st.info("Noch keine Cash Buchungen vorhanden.")

    st.subheader("Neue Cash Buchung")

    with st.form("cash_form"):
        transaction_date = st.date_input("Datum", value=today)
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

        st.subheader("Offene Positionen")

    if not open_positions.empty:

        st.dataframe(
            open_positions,
            use_container_width=True
        )

        st.subheader("Position verkaufen")

        for idx, row in open_positions.iterrows():

            col1, col2, col3, col4 = st.columns([2, 2, 2, 1])

            col1.write(row["underlying_ticker"])
            col2.write(row["turbo_wkn"])
            col3.write(f"Stück: {row['OPEN_QTY']}")

            if col4.button("SELL", key=f"sell_{idx}"):

                st.session_state["prefill_trade"] = {
                    "action": "SELL",
                    "system_type": row["system_type"],
                    "underlying_ticker": row["underlying_ticker"],
                    "turbo_wkn": row["turbo_wkn"],
                    "issuer": row.get("issuer", ""),
                    "turbo_isin": row.get("turbo_isin", ""),
                    "quantity": float(row["OPEN_QTY"])
                }

                st.success("SELL vorbereitet. Bitte in den Tab Trades wechseln.")

    else:

        st.info("Keine offenen Positionen.")


with tab_trades:
    st.header("Trade Erfassung")

    underlying_options = df["ticker"].tolist() if not df.empty else []

    prefill = st.session_state.get(
    "prefill_trade",
    {}
)

with st.form("trade_form"):

    trade_date = st.date_input(
        "Trade Datum"
    )

    action = st.selectbox(
        "Aktion",
        ["BUY", "SELL"],
        index=["BUY", "SELL"].index(
            prefill.get("action", "BUY")
        )
    )

    system_type = st.selectbox(
        "System",
        ["CORE", "SATELLITE"],
        index=["CORE", "SATELLITE"].index(
            prefill.get("system_type", "CORE")
        )
    )

    underlying_index = 0

    if prefill.get("underlying_ticker") in underlying_options:

        underlying_index = underlying_options.index(
            prefill.get("underlying_ticker")
        )

    underlying_ticker = st.selectbox(
        "Underlying",
        underlying_options,
        index=underlying_index
    )

    turbo_wkn = st.text_input(
        "Turbo WKN",
        value=prefill.get("turbo_wkn", "")
    )

    turbo_isin = st.text_input(
        "Turbo ISIN",
        value=prefill.get("turbo_isin", "")
    )

    issuer = st.text_input(
        "Emittent",
        value=prefill.get("issuer", "")
    )

    quantity = st.number_input(
        "Stückzahl",
        step=1.0,
        value=float(
            prefill.get("quantity", 0.0)
        )
    )

    price = st.number_input(
        "Kurs",
        step=0.01
    )

    cash_flow = st.number_input(
        "Tatsächlicher Cash Flow laut Broker",
        step=0.01
    )

    actual_leverage = 0.0
    ko_level = 0.0

    if action == "BUY":

        actual_leverage = st.number_input(
            "Tatsächlicher Hebel",
            step=0.1
        )

        ko_level = st.number_input(
            "KO Level",
            step=0.01
        )
    notes = st.text_input(
        "Notizen"
    )

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
            "quantity": int(quantity),
            "price": float(price),
            "gross_amount": float(quantity * price),
            "fees": 0.0,
            "taxes": 0.0,
            "net_cash_effect": float(cash_flow),
            "notes": notes

        }).execute()

        if "prefill_trade" in st.session_state:

            del st.session_state[
                "prefill_trade"
            ]

        st.success(
            "Trade gespeichert."
        )

        st.rerun()
    st.subheader("Trade Historie")

    if not trade_df.empty:
        st.dataframe(trade_df, use_container_width=True)
    else:
        st.info("Noch keine Trades vorhanden.")


with tab_data:
    st.header("Daten")
    st.subheader("Metadaten Enricher")

    if st.button("Underlyings automatisch anreichern"):

        success_count = 0
        failed = []

        tickers = df["ticker"].dropna().unique()

        progress_bar = st.progress(0)

        for idx, ticker in enumerate(tickers):

            ok, err = enrich_underlying_metadata(
                supabase,
                ticker
            )

            if ok:
                success_count += 1
            else:
                failed.append({
                    "ticker": ticker,
                    "error": err
                })

            progress_bar.progress(
                (idx + 1) / len(tickers)
            )

        st.success(
            f"{success_count} Underlyings angereichert."
        )

        if failed:

            st.warning(
                "Fehler bei einigen Tickern."
            )

            st.dataframe(
                pd.DataFrame(failed),
                use_container_width=True
            )
    st.subheader("Gespeicherte Underlyings")

    if not df.empty:
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Noch keine Underlyings vorhanden.")

    st.subheader("Universum initialisieren")

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

            supabase.table("underlyings").upsert(
                {
                    "ticker": ticker,
                    "company_name": ticker,
                    "strategy_role": role
                },
                on_conflict="ticker"
            ).execute()

            imported += 1

        st.success(f"{imported} Underlyings importiert.")

    st.subheader("Neues Underlying hinzufügen")

    with st.form("add_underlying_form"):
        ticker = st.text_input("Ticker")
        company_name = st.text_input("Unternehmensname")
        isin = st.text_input("ISIN")
        wkn = st.text_input("WKN")
        strategy_role = st.selectbox("Strategie", ["CORE", "SATELLITE", "BOTH"])
        exchange = st.text_input("Börse")
        currency = st.text_input("Währung")
        submit_underlying = st.form_submit_button("Speichern")

        if submit_underlying:
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

            st.success("Underlying gespeichert.")

    st.subheader("Kursdaten Update")

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


with tab_admin:
    st.header("Admin")

    st.subheader("Full Data Refresh")

    if st.button(
       "Full Data Refresh ausführen",
        key="admin_full_refresh"
    ):
        with st.spinner("Full Data Refresh läuft..."):
            run_daily_update(
                incremental=False
            )

        st.success("Full Data Refresh erfolgreich abgeschlossen.")
        st.rerun()

    st.subheader("Rebalance Status")

    if not rebalance_df.empty:
        st.dataframe(rebalance_df, use_container_width=True)
    else:
        st.info("Kein Rebalance Status vorhanden.")

    core_rebalance_due = True
    sat_rebalance_due = True

    if not rebalance_df.empty:
        core_state = rebalance_df[rebalance_df["system_type"] == "CORE"]
        sat_state = rebalance_df[rebalance_df["system_type"] == "SATELLITE"]

        col1, col2 = st.columns(2)

        if not core_state.empty:
            next_core = core_state.iloc[0]["next_rebalance_date"]

            if pd.notna(next_core) and next_core:
                next_core_date = pd.to_datetime(next_core).date()
                core_rebalance_due = today >= next_core_date
                col1.metric(
                    "Nächstes CORE Rebalance",
                    next_core_date.strftime("%d.%m.%Y")
                )
            else:
                col1.metric("Nächstes CORE Rebalance", "Noch nicht gesetzt")

        if not sat_state.empty:
            next_sat = sat_state.iloc[0]["next_rebalance_date"]

            if pd.notna(next_sat) and next_sat:
                next_sat_date = pd.to_datetime(next_sat).date()
                sat_rebalance_due = today >= next_sat_date
                col2.metric(
                    "Nächstes SATELLITE Rebalance",
                    next_sat_date.strftime("%d.%m.%Y")
                )
            else:
                col2.metric("Nächstes SATELLITE Rebalance", "Noch nicht gesetzt")

    st.write("CORE Rebalance heute aktiv:", core_rebalance_due)
    st.write("SATELLITE Rebalance heute aktiv:", sat_rebalance_due)

    st.subheader("Rebalance als ausgeführt speichern")

    with st.form("rebalance_execution_form"):
        execution_system = st.selectbox("Ausgeführtes System", ["CORE", "SATELLITE"])
        execution_date = st.date_input("Tatsächliches Ausführungsdatum", value=today, format="DD.MM.YYYY")
        submit_rebalance_execution = st.form_submit_button("Speichern")

        if submit_rebalance_execution:
            cycle_days = 10 if execution_system == "CORE" else 21
            next_date = add_business_days(execution_date, cycle_days)

            supabase.table("rebalance_state").upsert(
                {
                    "system_type": execution_system,
                    "last_rebalance_date": str(execution_date),
                    "next_rebalance_date": str(next_date),
                    "rebalance_cycle_days": cycle_days
                },
                on_conflict="system_type"
            ).execute()

            st.success(
                f"{execution_system} Rebalance gespeichert. "
                f"Nächstes Rebalance: {next_date}"
            )
