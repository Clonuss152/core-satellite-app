import streamlit as st
import pandas as pd
from supabase import create_client
from datetime import date

from config import CORE_TICKERS, SAT_TICKERS
from utils import add_business_days
from daily_update import run_daily_update
from snapshot_loader import (
    load_latest_regime_snapshot,
    load_latest_momentum_snapshot,
    load_latest_order_snapshot,
)
from capital_planner import calculate_capital_plan


# ===================================================
# PAGE SETUP
# ===================================================

st.set_page_config(
    page_title="Core Satellite System",
    layout="wide",
)

st.title("Core + Satellite Trading System")

today = date.today()

SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]

supabase = create_client(
    SUPABASE_URL,
    SUPABASE_KEY,
)


# ===================================================
# HELPERS
# ===================================================


def load_table(table_name):
    result = supabase.table(table_name).select("*").execute()
    return pd.DataFrame(result.data)



def safe_value(value):
    if pd.isna(value):
        return ""
    return value



def color_order(val):
    if val == "HOLD":
        return "background-color: #d4edda; color: black"
    if val == "BUY":
        return "background-color: #fff3cd; color: black"
    if val == "SELL":
        return "background-color: #f8d7da; color: black"
    return ""



def format_eur(value):
    try:
        return f"{float(value):,.0f} €"
    except Exception:
        return "-"

def calculate_cashflow_adjustment(action, quantity, price, net_cash_effect):
    gross_amount = float(quantity) * float(price)

    if action == "BUY":
        expected_cash_flow = -gross_amount
    else:
        expected_cash_flow = gross_amount

    return float(net_cash_effect) - expected_cash_flow

def get_latest_broker_cash_from_state(cash_state_df):
    if cash_state_df.empty:
        return 0.0

    temp_df = cash_state_df.copy()

    if "snapshot_date" not in temp_df.columns:
        return 0.0

    temp_df["snapshot_date"] = pd.to_datetime(
        temp_df["snapshot_date"]
    )

    temp_df = temp_df.sort_values("snapshot_date")

    latest_cash = temp_df.iloc[-1].get("broker_cash", 0.0)

    if pd.isna(latest_cash):
        return 0.0

    return float(latest_cash)


# ===================================================
# LOAD DATA
# ===================================================

underlyings_df = load_table("underlyings")
trade_df = load_table("trades")
cash_df = load_table("cash_transactions")
cash_state_df = load_table("cash_state")
rebalance_df = load_table("rebalance_state")
status_df = load_table("system_status")

# backward-compatible alias for older code sections
df = underlyings_df



def get_meta(ticker):
    if underlyings_df.empty:
        return {}

    row = underlyings_df[underlyings_df["ticker"] == ticker]

    if row.empty:
        return {}

    return row.iloc[0].to_dict()



def security_label(ticker):
    meta = get_meta(ticker)

    name = safe_value(meta.get("company_name", "")) or ticker
    isin = safe_value(meta.get("isin", ""))
    wkn = safe_value(meta.get("wkn", ""))

    label = f"{name} ({ticker})"

    if isin:
        label += f"\nISIN: {isin}"

    if wkn:
        label += f"\nWKN: {wkn}"

    return label



def enrich_snapshot(snapshot_df):
    if snapshot_df.empty or underlyings_df.empty:
        return snapshot_df

    meta_cols = [
        "ticker",
        "company_name",
        "isin",
        "wkn",
        "exchange",
        "currency",
    ]

    available_cols = [
        col for col in meta_cols
        if col in underlyings_df.columns
    ]

    return snapshot_df.merge(
        underlyings_df[available_cols],
        on="ticker",
        how="left",
    )


# ===================================================
# OPEN POSITIONS
# ===================================================

open_positions = pd.DataFrame()

if not trade_df.empty:
    grouped = trade_df.groupby(
        [
            "system_type",
            "underlying_ticker",
            "turbo_wkn",
        ],
        dropna=False,
    ).apply(
        lambda x: pd.Series(
            {
                "BUY_QTY": x.loc[
                    x["action"] == "BUY",
                    "quantity",
                ].sum(),
                "SELL_QTY": x.loc[
                    x["action"] == "SELL",
                    "quantity",
                ].sum(),
                "LAST_PRICE": x.iloc[-1]["price"],
                "turbo_isin": x.iloc[-1].get("turbo_isin", ""),
                "issuer": x.iloc[-1].get("issuer", ""),
            }
        )
    ).reset_index()

    grouped["OPEN_QTY"] = grouped["BUY_QTY"] - grouped["SELL_QTY"]

    open_positions = grouped[
        grouped["OPEN_QTY"] > 0
    ].copy()

    if not open_positions.empty:
        open_positions["ESTIMATED_POSITION_VALUE"] = (
            open_positions["OPEN_QTY"]
            * open_positions["LAST_PRICE"]
        )

        open_positions["security"] = open_positions[
            "underlying_ticker"
        ].apply(security_label)



def prepare_trade_from_order(row, system_type):
    action = row.get("action")
    ticker = row.get("ticker")

    prefill = {
        "action": action,
        "system_type": system_type,
        "underlying_ticker": ticker,
        "target_leverage": row.get("target_leverage", ""),
        "suggested_amount": row.get("suggested_amount", 0.0),
    }

    if action == "SELL" and not open_positions.empty:
        match = open_positions[
            (open_positions["system_type"] == system_type)
            & (open_positions["underlying_ticker"] == ticker)
        ]

        if not match.empty:
            pos = match.iloc[0]
            prefill["turbo_wkn"] = pos.get("turbo_wkn", "")
            prefill["turbo_isin"] = pos.get("turbo_isin", "")
            prefill["issuer"] = pos.get("issuer", "")
            prefill["quantity"] = float(pos.get("OPEN_QTY", 0.0))

    st.session_state["prefill_trade"] = prefill


# ===================================================
# TABS
# ===================================================

tab_dashboard, tab_portfolio, tab_trades, tab_data, tab_admin = st.tabs(
    [
        "Dashboard",
        "Portfolio",
        "Trades",
        "Daten",
        "Admin",
    ]
)


# ===================================================
# DASHBOARD
# ===================================================

with tab_dashboard:
    st.subheader("Dashboard")

    # -------------------------------------------
    # Statusdaten
    # -------------------------------------------

    last_update = "Noch kein Update"

    if not status_df.empty:
        row = status_df[
            status_df["status_key"] == "last_daily_update"
        ]

        if not row.empty and row.iloc[0]["status_value"]:
            timestamp_dt = pd.to_datetime(
                row.iloc[0]["status_value"],
                utc=True,
            ).tz_convert("Europe/Berlin")

            last_update = timestamp_dt.strftime("%d.%m.%Y %H:%M")

    next_core_display = "-"
    next_sat_display = "-"

    core_rebalance_due = False
    sat_rebalance_due = False

    if not rebalance_df.empty:
        core_state = rebalance_df[
            rebalance_df["system_type"] == "CORE"
        ]

        sat_state = rebalance_df[
            rebalance_df["system_type"] == "SATELLITE"
        ]

        if (
            not core_state.empty
            and pd.notna(core_state.iloc[0]["next_rebalance_date"])
        ):
            next_core_date = pd.to_datetime(
                core_state.iloc[0]["next_rebalance_date"]
            ).date()
    
            next_core_display = next_core_date.strftime("%d.%m.%Y")
            core_rebalance_due = today >= next_core_date

    if (
        not sat_state.empty
        and pd.notna(sat_state.iloc[0]["next_rebalance_date"])
    ):
        next_sat_date = pd.to_datetime(
            sat_state.iloc[0]["next_rebalance_date"]
        ).date()

        next_sat_display = next_sat_date.strftime("%d.%m.%Y")
        sat_rebalance_due = today >= next_sat_date
    regime_snapshot = load_latest_regime_snapshot(supabase)
    latest_regime = None

    if not regime_snapshot.empty:
        latest_regime = regime_snapshot.iloc[0]

    # -------------------------------------------
    # Kompakter Header
    # -------------------------------------------

    top1, top2, top3, top4, top5 = st.columns(5)

    with top1:
        if st.button("Daily Update", key="dashboard_daily_update"):
            with st.spinner("Update läuft..."):
                run_daily_update(incremental=True)

            st.success("Update abgeschlossen.")
            st.rerun()

    with top2:
        st.metric(
            "Regime",
            latest_regime.get("regime", "-")
            if latest_regime is not None
            else "-",
        )

    with top3:
        momentum_display = "-"

        if latest_regime is not None:
            momentum_display = f"{latest_regime['top10_momentum']:.1%}"

        st.metric("Momentum", momentum_display)

    with top4:
        st.metric("CORE Rebalance", next_core_display)

    with top5:
        st.metric("SAT Rebalance", next_sat_display)

    st.caption(f"Letztes Update: {last_update}")
    due1, due2 = st.columns(2)

    with due1:
        if core_rebalance_due:
            st.success("CORE heute fällig / handelbar")
        else:
            st.info("CORE heute nicht fällig")

    with due2:
        if sat_rebalance_due:
            st.success("SATELLITE heute fällig / handelbar")
        else:
            st.info("SATELLITE heute nicht fällig")
    with st.expander("Rebalance als ausgeführt speichern"):

        with st.form("dashboard_rebalance_execution_form"):

            execution_system = st.selectbox(
                "Ausgeführtes System",
                ["CORE", "SATELLITE"]
            )

            execution_date = st.date_input(
                "Tatsächliches Ausführungsdatum",
                value=today,
                format="DD.MM.YYYY"
            )

            submit_rebalance_execution = st.form_submit_button(
                "Speichern"
            )

            if submit_rebalance_execution:

                cycle_days = (
                    10
                    if execution_system == "CORE"
                    else 21
                )

                next_date = add_business_days(
                    execution_date,
                    cycle_days
                )

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
                    f"{execution_system} Rebalance gespeichert."
                )

                st.rerun()

    st.divider()
    # -------------------------------------------
    # Orders laden
    # -------------------------------------------

    core_orders_snapshot = enrich_snapshot(
        load_latest_order_snapshot(supabase, "CORE")
    )

    sat_orders_snapshot = enrich_snapshot(
        load_latest_order_snapshot(supabase, "SATELLITE")
    )

    active_core_orders = pd.DataFrame()
    active_sat_orders = pd.DataFrame()

    if not core_orders_snapshot.empty:

        active_core_orders = core_orders_snapshot[
            core_orders_snapshot["action"] != "HOLD"
        ].copy()

        if not open_positions.empty:

            existing_core_positions = set(
                open_positions[
                    open_positions["system_type"] == "CORE"
                ]["underlying_ticker"]
            )

            # BUY ausblenden wenn Position bereits existiert
            active_core_orders = active_core_orders[
                ~(
                    (active_core_orders["action"] == "BUY")
                    &
                    (
                        active_core_orders["ticker"].isin(
                            existing_core_positions
                        )
                    )
                )
            ]

            # SELL ausblenden wenn Position NICHT existiert
            active_core_orders = active_core_orders[
                ~(
                    (active_core_orders["action"] == "SELL")
                    &
                    (
                        ~active_core_orders["ticker"].isin(
                            existing_core_positions
                        )
                    )
                )
            ]


    if not sat_orders_snapshot.empty:

        active_sat_orders = sat_orders_snapshot[
            sat_orders_snapshot["action"] != "HOLD"
        ].copy()

        if not open_positions.empty:

            existing_sat_positions = set(
                open_positions[
                    open_positions["system_type"] == "SATELLITE"
                ]["underlying_ticker"]
            )

            # BUY ausblenden wenn Position bereits existiert
            active_sat_orders = active_sat_orders[
                ~(
                    (active_sat_orders["action"] == "BUY")
                    &
                    (
                        active_sat_orders["ticker"].isin(
                            existing_sat_positions
                        )
                    )
                )
            ]

            # SELL ausblenden wenn Position NICHT existiert
            active_sat_orders = active_sat_orders[
                ~(
                    (active_sat_orders["action"] == "SELL")
                    &
                    (
                        ~active_sat_orders["ticker"].isin(
                            existing_sat_positions
                        )
                    )
                )
            ]
    capital_metrics, planned_core_orders, planned_sat_orders = calculate_capital_plan(
        trade_df=trade_df,
        cash_state_df=cash_state_df,
        core_orders=active_core_orders,
        sat_orders=active_sat_orders,
    )

    # -------------------------------------------
    # Kapitalplanung + Cash-State Formular
    # -------------------------------------------

    st.subheader("Kapitalplanung")

    current_cash = get_latest_broker_cash_from_state(cash_state_df)

    with st.form("cash_state_form"):
        broker_cash_input = st.number_input(
            "Aktueller Broker Cash",
            value=float(current_cash),
            step=0.01,
        )

        submit_cash_state = st.form_submit_button(
            "Broker Cash speichern"
        )

        if submit_cash_state:
            supabase.table("cash_state").insert(
                {
                    "broker_cash": float(broker_cash_input),
                }
            ).execute()

            st.success("Broker Cash gespeichert.")
            st.rerun()

    cash1, cash2, cash3, cash4 = st.columns(4)

    cash1.metric(
        "Broker Cash",
        format_eur(capital_metrics.get("broker_cash", 0.0)),
    )

    cash2.metric(
        "Systemkapital",
        format_eur(capital_metrics.get("system_capital", 0.0)),
    )

    cash3.metric(
        "SAT Reserve",
        format_eur(capital_metrics.get("satellite_reserve", 0.0)),
    )

    cash4.metric(
        "CORE verfügbar",
        format_eur(capital_metrics.get("core_available_cash", 0.0)),
    )

    st.caption(
        "Logik: HOLD bleibt liegen. Systemkapital = Broker Cash + Einstandswerte offener Positionen. "
        "Satellite ist auf 5 % Systemkapital begrenzt, sofern keine SAT-Position offen ist."
    )

    st.divider()

    # -------------------------------------------
    # Aktuelles Portfolio
    # -------------------------------------------

    st.subheader("Aktuelles Portfolio")

    dashboard_positions = open_positions.copy()

    if not dashboard_positions.empty:
        core_latest_orders = load_latest_order_snapshot(supabase, "CORE")
        sat_latest_orders = load_latest_order_snapshot(supabase, "SATELLITE")

        latest_orders = pd.concat(
            [
                core_latest_orders,
                sat_latest_orders,
            ],
            ignore_index=True,
        )

        if not latest_orders.empty:
            latest_orders = latest_orders[
                [
                    "system_type",
                    "ticker",
                    "action",
                    "reason",
                ]
            ].rename(
                columns={
                    "ticker": "underlying_ticker",
                    "action": "signal",
                }
            )

            dashboard_positions = dashboard_positions.merge(
                latest_orders,
                on=[
                    "system_type",
                    "underlying_ticker",
                ],
                how="left",
            )

        if "signal" not in dashboard_positions.columns:
            dashboard_positions["signal"] = ""

        if "reason" not in dashboard_positions.columns:
            dashboard_positions["reason"] = ""

        core_positions = dashboard_positions[
            dashboard_positions["system_type"] == "CORE"
        ]

        sat_positions = dashboard_positions[
            dashboard_positions["system_type"] == "SATELLITE"
        ]

        st.markdown("### CORE Portfolio")

        if not core_positions.empty:
            core_portfolio_view = core_positions[
                [
                    "signal",
                    "security",
                    "OPEN_QTY",
                    "LAST_PRICE",
                    "ESTIMATED_POSITION_VALUE",
                    "reason",
                ]
            ]

            st.dataframe(
                core_portfolio_view.style.map(
                    color_order,
                    subset=["signal"],
                ),
                use_container_width=True,
            )
        else:
            st.info("Keine CORE Positionen.")

        st.markdown("### SATELLITE Portfolio")

        if not sat_positions.empty:
            sat_portfolio_view = sat_positions[
                [
                    "signal",
                    "security",
                    "OPEN_QTY",
                    "LAST_PRICE",
                    "ESTIMATED_POSITION_VALUE",
                    "reason",
                ]
            ]

            st.dataframe(
                sat_portfolio_view.style.map(
                    color_order,
                    subset=["signal"],
                ),
                use_container_width=True,
            )
        else:
            st.info("Keine SATELLITE Positionen.")
    else:
        st.info("Keine offenen Positionen.")

    st.divider()

    # -------------------------------------------
    # Aktive Orders
    # -------------------------------------------

    st.subheader("Aktive Orders")

    if core_rebalance_due:
        st.markdown("### CORE Orders ✅ Heute handelbar")
    else:
        st.markdown(
            f"### CORE Orders ⏳ Nicht handelbar bis {next_core_display}"
        )

    if not planned_core_orders.empty:
        for idx, row in planned_core_orders.iterrows():
            col1, col2, col3, col4 = st.columns([3, 1, 3, 1])

            suggested = row.get("suggested_amount", 0.0)
            reason_text = row.get("reason", "")

            if suggested > 0:
                reason_text += f"\nZielbetrag: {suggested:,.0f} €"

            col1.write(security_label(row["ticker"]))
            col2.write(row["action"])
            col3.write(reason_text)

            if col4.button(
                f"{row['action']}",
                key=f"core_order_{idx}",
                disabled=not core_rebalance_due,
            ):
                prepare_trade_from_order(row, "CORE")
                st.success("Trade vorbereitet. Bitte in den Trades-Tab wechseln.")
    else:
        st.info("Keine aktiven CORE Orders.")

    if sat_rebalance_due:
        st.markdown("### SATELLITE Orders ✅ Heute handelbar")
    else:
        st.markdown(
            f"### SATELLITE Orders ⏳ Nicht handelbar bis {next_sat_display}"
        )

    if not planned_sat_orders.empty:
        for idx, row in planned_sat_orders.iterrows():
            col1, col2, col3, col4 = st.columns([3, 1, 3, 1])

            suggested = row.get("suggested_amount", 0.0)
            reason_text = row.get("reason", "")

            if suggested > 0:
                reason_text += f"\nZielbetrag: {suggested:,.0f} €"

            col1.write(security_label(row["ticker"]))
            col2.write(row["action"])
            col3.write(reason_text)

            if col4.button(
                f"{row['action']}",
                key=f"sat_order_{idx}",
                disabled=not sat_rebalance_due,
            ):
                prepare_trade_from_order(row, "SATELLITE")
                st.success("Trade vorbereitet. Bitte in den Trades-Tab wechseln.")
    else:
        st.info("Keine aktiven SATELLITE Orders.")

    st.divider()

    # -------------------------------------------
    # Zielportfolio
    # -------------------------------------------

    st.subheader("Zielportfolio")

    core_snapshot = enrich_snapshot(
        load_latest_momentum_snapshot(supabase, "CORE")
    )

    sat_snapshot = enrich_snapshot(
        load_latest_momentum_snapshot(supabase, "SATELLITE")
    )

    st.markdown("### CORE Zielportfolio")

    if not core_snapshot.empty:
        display_cols = [
            "rank",
            "ticker",
            "company_name",
            "isin",
            "score",
            "latest_price",
            "target_leverage",
        ]

        display_cols = [
            col for col in display_cols
            if col in core_snapshot.columns
        ]

        st.dataframe(
            core_snapshot.sort_values("rank")[display_cols],
            use_container_width=True,
        )
    else:
        st.info("Keine CORE Snapshots vorhanden.")

    st.markdown("### SATELLITE Zielportfolio")

    if not sat_snapshot.empty:
        display_cols = [
            "rank",
            "ticker",
            "company_name",
            "isin",
            "score",
            "latest_price",
            "target_leverage",
        ]

        display_cols = [
            col for col in display_cols
            if col in sat_snapshot.columns
        ]

        st.dataframe(
            sat_snapshot.sort_values("rank")[display_cols],
            use_container_width=True,
        )
    else:
        st.info("Keine SATELLITE Snapshots vorhanden.")


# ===================================================
# PORTFOLIO
# ===================================================

with tab_portfolio:
    st.header("Portfolio")

    st.subheader("Cash Historie")

    if not cash_df.empty:
        st.dataframe(cash_df, use_container_width=True)
        st.metric(
            "Gesamte Cash Bewegungen",
            f"{cash_df['amount'].sum():,.2f} €",
        )
    else:
        st.info("Noch keine Cash Buchungen vorhanden.")

    st.subheader("Neue Cash Buchung")

    with st.form("cash_form"):
        transaction_date = st.date_input(
            "Datum",
            value=today,
            format="DD.MM.YYYY",
        )

        transaction_type = st.selectbox(
            "Typ",
            [
                "EINZAHLUNG",
                "AUSZAHLUNG",
                "STEUER",
                "GEBUEHR",
                "KORREKTUR",
            ],
        )

        cash_system_type = st.selectbox(
            "System",
            [
                "GESAMT",
                "CORE",
                "SATELLITE",
            ],
        )

        amount = st.number_input("Betrag", step=0.01)
        broker_cash_after = st.number_input(
            "Broker Cash nach Buchung",
            step=0.01,
        )
        description = st.text_input("Beschreibung")
        submit_cash = st.form_submit_button("Cash Buchung speichern")

        if submit_cash:
            supabase.table("cash_transactions").insert(
                {
                    "transaction_date": str(transaction_date),
                    "transaction_type": transaction_type,
                    "system_type": cash_system_type,
                    "amount": float(amount),
                    "broker_cash_after": float(broker_cash_after),
                    "description": description,
                }
            ).execute()

            st.success("Cash Buchung gespeichert.")
            st.rerun()

    st.subheader("Offene Positionen")

    if not open_positions.empty:
        st.dataframe(open_positions, use_container_width=True)

        st.subheader("Position verkaufen")

        for idx, row in open_positions.iterrows():
            col1, col2, col3, col4 = st.columns([3, 2, 2, 1])

            col1.write(row["security"])
            col2.write(row["turbo_wkn"])
            col3.write(f"Stück: {row['OPEN_QTY']}")

            if col4.button("SELL", key=f"sell_{idx}"):
                st.session_state["prefill_trade"] = {
                    "action": "SELL",
                    "system_type": row["system_type"],
                    "underlying_ticker": row["underlying_ticker"],
                    "turbo_wkn": row["turbo_wkn"],
                    "turbo_isin": row.get("turbo_isin", ""),
                    "issuer": row.get("issuer", ""),
                    "quantity": float(row["OPEN_QTY"]),
                }

                st.success("SELL vorbereitet. Bitte in den Tab Trades wechseln.")
    else:
        st.info("Keine offenen Positionen.")


# ===================================================
# TRADES
# ===================================================

with tab_trades:
    st.header("Trade Erfassung")

    underlying_options = (
        underlyings_df["ticker"].tolist()
        if not underlyings_df.empty
        else []
    )

    prefill = st.session_state.get("prefill_trade", {})

    if prefill.get("target_leverage"):
        st.info(
            f"Zielhebel laut Strategie: {prefill.get('target_leverage')}"
        )

    if prefill.get("suggested_amount"):
        st.info(
            f"Vorgeschlagener Zielbetrag: {float(prefill.get('suggested_amount')):,.0f} €"
        )

    with st.form("trade_form"):
        trade_date = st.date_input(
            "Trade Datum",
            value=today,
            format="DD.MM.YYYY",
        )

        action = st.selectbox(
            "Aktion",
            ["BUY", "SELL"],
            index=["BUY", "SELL"].index(prefill.get("action", "BUY")),
        )

        trade_system_type = st.selectbox(
            "System",
            ["CORE", "SATELLITE"],
            index=["CORE", "SATELLITE"].index(
                prefill.get("system_type", "CORE")
            ),
        )

        underlying_index = 0

        if prefill.get("underlying_ticker") in underlying_options:
            underlying_index = underlying_options.index(
                prefill.get("underlying_ticker")
            )

        underlying_ticker = st.selectbox(
            "Underlying",
            underlying_options,
            index=underlying_index,
        )

        selected_meta = get_meta(underlying_ticker)

        if selected_meta:
            st.info(
                f"{selected_meta.get('company_name', underlying_ticker)} | "
                f"ISIN: {selected_meta.get('isin', '')}"
            )

        turbo_wkn = st.text_input(
            "Turbo WKN",
            value=prefill.get("turbo_wkn", ""),
        )

        turbo_isin = st.text_input(
            "Turbo ISIN",
            value=prefill.get("turbo_isin", ""),
        )

        issuer = st.text_input(
            "Emittent",
            value=prefill.get("issuer", ""),
        )

        quantity = st.number_input(
            "Stückzahl",
            step=1.0,
            value=float(prefill.get("quantity", 0.0)),
        )

        price = st.number_input("Kurs", step=0.01)

        cash_flow = st.number_input(
            "Tatsächlicher Cash Flow laut Broker",
            step=0.01,
        )

        notes = st.text_input("Notizen")
        submit_trade = st.form_submit_button("Trade speichern")

        if submit_trade:
            supabase.table("trades").insert(
                {
                    "trade_date": str(trade_date),
                    "system_type": trade_system_type,
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
                    "cashflow_adjustment": calculate_cashflow_adjustment(
                        action,
                        quantity,
                        price,
                        cash_flow,
                    ),
                    "notes": notes,
                }
            ).execute()

            if "prefill_trade" in st.session_state:
                del st.session_state["prefill_trade"]

            st.success("Trade gespeichert.")
            st.rerun()

    st.subheader("Trade Historie")

    if not trade_df.empty:

        trade_history_df = trade_df.sort_values(
            "trade_date",
            ascending=False
        ).copy()

        st.dataframe(
            trade_history_df,
            use_container_width=True
        )

        st.subheader("Trade auswählen")

        for idx, row in trade_history_df.iterrows():

            col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 1, 1])

            col1.write(row.get("trade_date", ""))
            col2.write(row.get("action", ""))
            col3.write(
                f"{row.get('underlying_ticker', '')} | "
                f"{row.get('quantity', '')} Stück | "
                f"{row.get('price', '')}"
            )

            if col4.button(
                "Edit",
                key=f"edit_trade_{row['id']}"
            ):
                st.session_state["edit_trade_id"] = row["id"]
                st.rerun()

            if col5.button(
                "Löschen",
                key=f"delete_trade_{row['id']}"
            ):

                supabase.table("trades").delete().eq(
                    "id",
                    row["id"]
                ).execute()

                if st.session_state.get("edit_trade_id") == row["id"]:
                    del st.session_state["edit_trade_id"]

                st.success("Trade gelöscht.")
                st.rerun()

        if "edit_trade_id" in st.session_state:

            selected_trade_id = st.session_state["edit_trade_id"]

            selected_trade_df = trade_history_df[
                trade_history_df["id"] == selected_trade_id
            ]

            if selected_trade_df.empty:

                st.warning("Der ausgewählte Trade existiert nicht mehr.")

                if "edit_trade_id" in st.session_state:
                    del st.session_state["edit_trade_id"]

            else:

                selected_trade = selected_trade_df.iloc[0]

                st.subheader("Trade bearbeiten")

                with st.form("edit_trade_form"):

                    edit_trade_date = st.date_input(
                        "Trade Datum",
                        value=pd.to_datetime(
                            selected_trade.get("trade_date")
                        ).date(),
                        format="DD.MM.YYYY",
                        key="edit_trade_date",
                    )

                    edit_action = st.selectbox(
                        "Aktion",
                        ["BUY", "SELL"],
                        index=["BUY", "SELL"].index(
                            selected_trade.get("action", "BUY")
                        ),
                        key="edit_action",
                    )

                    edit_system_type = st.selectbox(
                        "System",
                        ["CORE", "SATELLITE"],
                        index=["CORE", "SATELLITE"].index(
                            selected_trade.get("system_type", "CORE")
                        ),
                        key="edit_system_type",
                    )

                    edit_underlying_index = 0

                    if selected_trade.get("underlying_ticker") in underlying_options:
                        edit_underlying_index = underlying_options.index(
                            selected_trade.get("underlying_ticker")
                        )

                    edit_underlying_ticker = st.selectbox(
                        "Underlying",
                        underlying_options,
                        index=edit_underlying_index,
                        key="edit_underlying_ticker",
                    )

                    edit_turbo_wkn = st.text_input(
                        "Turbo WKN",
                        value=safe_value(selected_trade.get("turbo_wkn", "")),
                        key="edit_turbo_wkn",
                    )

                    edit_turbo_isin = st.text_input(
                        "Turbo ISIN",
                        value=safe_value(selected_trade.get("turbo_isin", "")),
                        key="edit_turbo_isin",
                    )

                    edit_issuer = st.text_input(
                        "Emittent",
                        value=safe_value(selected_trade.get("issuer", "")),
                        key="edit_issuer",
                    )

                    edit_quantity = st.number_input(
                        "Stückzahl",
                        step=1.0,
                        value=float(selected_trade.get("quantity", 0.0)),
                        key="edit_quantity",
                    )

                    edit_price = st.number_input(
                        "Kurs",
                        step=0.01,
                        value=float(selected_trade.get("price", 0.0)),
                        key="edit_price",
                    )

                    edit_cash_flow = st.number_input(
                        "Tatsächlicher Cash Flow laut Broker",
                        step=0.01,
                        value=float(selected_trade.get("net_cash_effect", 0.0)),
                        key="edit_cash_flow",
                    )

                    edit_notes = st.text_input(
                        "Notizen",
                        value=safe_value(selected_trade.get("notes", "")),
                        key="edit_notes",
                    )

                    edit_col1, edit_col2 = st.columns(2)

                    submit_edit_trade = edit_col1.form_submit_button(
                        "Trade aktualisieren"
                    )

                    cancel_edit_trade = edit_col2.form_submit_button(
                        "Bearbeitung abbrechen"
                    )

                    if submit_edit_trade:

                        supabase.table("trades").update(
                            {
                                "trade_date": str(edit_trade_date),
                                "system_type": edit_system_type,
                                "action": edit_action,
                                "underlying_ticker": edit_underlying_ticker,
                                "turbo_wkn": edit_turbo_wkn,
                                "turbo_isin": edit_turbo_isin,
                                "issuer": edit_issuer,
                                "quantity": int(edit_quantity),
                                "price": float(edit_price),
                                "gross_amount": float(edit_quantity * edit_price),
                                "net_cash_effect": float(edit_cash_flow),
                                "cashflow_adjustment": calculate_cashflow_adjustment(
                                    edit_action,
                                    edit_quantity,
                                    edit_price,
                                    edit_cash_flow,
                                ),
                                "notes": edit_notes,
                            }
                        ).eq(
                            "id",
                            selected_trade_id
                        ).execute()

                        del st.session_state["edit_trade_id"]

                        st.success("Trade aktualisiert.")
                        st.rerun()

                    if cancel_edit_trade:

                        del st.session_state["edit_trade_id"]

                        st.info("Bearbeitung abgebrochen.")
                        st.rerun()

    else:

        st.info("Noch keine Trades vorhanden.")
# ===================================================
# DATEN
# ===================================================

with tab_data:
    st.header("Daten")

    st.subheader("Gespeicherte Underlyings")

    if not underlyings_df.empty:
        st.dataframe(underlyings_df, use_container_width=True)
    else:
        st.info("Noch keine Underlyings vorhanden.")

    st.subheader("Stammdaten CSV Import")

    uploaded_file = st.file_uploader(
        "CSV mit Stammdaten hochladen",
        type=["csv"],
    )

    if uploaded_file is not None:
        import_df = pd.read_csv(uploaded_file)
        import_df = import_df.fillna("")

        st.write(import_df.head())

        if st.button("Stammdaten importieren"):
            imported = 0

            for _, row in import_df.iterrows():
                ticker = str(row.get("ticker", "")).strip()

                if not ticker:
                    continue

                supabase.table("underlyings").upsert(
                    {
                        "ticker": ticker,
                        "company_name": row.get("company_name", ""),
                        "isin": row.get("isin", ""),
                        "wkn": row.get("wkn", ""),
                        "exchange": row.get("exchange", ""),
                        "currency": row.get("currency", ""),
                        "strategy_role": row.get("strategy_role", "CORE"),
                    },
                    on_conflict="ticker",
                ).execute()

                imported += 1

            st.success(f"{imported} Stammdaten importiert.")
            st.rerun()

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
                    "strategy_role": role,
                },
                on_conflict="ticker",
            ).execute()

            imported += 1

        st.success(f"{imported} Underlyings importiert.")
        st.rerun()

    st.subheader("Neues Underlying hinzufügen")

    with st.form("add_underlying_form"):
        ticker = st.text_input("Ticker")
        company_name = st.text_input("Unternehmensname")
        isin = st.text_input("ISIN")
        wkn = st.text_input("WKN")
        strategy_role = st.selectbox(
            "Strategie",
            ["CORE", "SATELLITE", "BOTH"],
        )
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
                    "currency": currency,
                },
                on_conflict="ticker",
            ).execute()

            st.success("Underlying gespeichert.")
            st.rerun()


# ===================================================
# ADMIN
# ===================================================

with tab_admin:
    st.header("Admin")

    st.subheader("Full Data Refresh")

    if st.button("Full Data Refresh ausführen", key="admin_full_refresh"):
        with st.spinner("Full Data Refresh läuft..."):
            run_daily_update(incremental=False)

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
        core_state = rebalance_df[
            rebalance_df["system_type"] == "CORE"
        ]

        sat_state = rebalance_df[
            rebalance_df["system_type"] == "SATELLITE"
        ]

        col1, col2 = st.columns(2)

        if not core_state.empty:
            next_core = core_state.iloc[0]["next_rebalance_date"]

            if pd.notna(next_core) and next_core:
                next_core_date = pd.to_datetime(next_core).date()
                core_rebalance_due = today >= next_core_date

                col1.metric(
                    "Nächstes CORE Rebalance",
                    next_core_date.strftime("%d.%m.%Y"),
                )
            else:
                col1.metric(
                    "Nächstes CORE Rebalance",
                    "Noch nicht gesetzt",
                )

        if not sat_state.empty:
            next_sat = sat_state.iloc[0]["next_rebalance_date"]

            if pd.notna(next_sat) and next_sat:
                next_sat_date = pd.to_datetime(next_sat).date()
                sat_rebalance_due = today >= next_sat_date

                col2.metric(
                    "Nächstes SATELLITE Rebalance",
                    next_sat_date.strftime("%d.%m.%Y"),
                )
            else:
                col2.metric(
                    "Nächstes SATELLITE Rebalance",
                    "Noch nicht gesetzt",
                )

    st.write("CORE Rebalance heute aktiv:", core_rebalance_due)
    st.write("SATELLITE Rebalance heute aktiv:", sat_rebalance_due)

    st.subheader("Rebalance als ausgeführt speichern")

    with st.form("rebalance_execution_form"):
        execution_system = st.selectbox(
            "Ausgeführtes System",
            ["CORE", "SATELLITE"],
        )

        execution_date = st.date_input(
            "Tatsächliches Ausführungsdatum",
            value=today,
            format="DD.MM.YYYY",
        )

        submit_rebalance_execution = st.form_submit_button("Speichern")

        if submit_rebalance_execution:
            cycle_days = 10 if execution_system == "CORE" else 21
            next_date = add_business_days(execution_date, cycle_days)

            supabase.table("rebalance_state").upsert(
                {
                    "system_type": execution_system,
                    "last_rebalance_date": str(execution_date),
                    "next_rebalance_date": str(next_date),
                    "rebalance_cycle_days": cycle_days,
                },
                on_conflict="system_type",
            ).execute()

            st.success(
                f"{execution_system} Rebalance gespeichert. "
                f"Nächstes Rebalance: {next_date.strftime('%d.%m.%Y')}"
            )

            st.rerun()
