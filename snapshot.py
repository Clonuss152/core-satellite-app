from datetime import date
def clear_today_snapshots(supabase):

    snapshot_date = str(date.today())

    supabase.table("core_regime_snapshot").delete().eq(
        "snapshot_date",
        snapshot_date
    ).execute()

    supabase.table("momentum_snapshot").delete().eq(
        "snapshot_date",
        snapshot_date
    ).execute()

    supabase.table("order_snapshot").delete().eq(
        "snapshot_date",
        snapshot_date
    ).execute()

def save_regime_snapshot(
    supabase,
    regime,
    top10_momentum
):

    snapshot_date = str(date.today())

    supabase.table(
        "core_regime_snapshot"
    ).insert({

        "snapshot_date": snapshot_date,
        "regime": regime,
        "top10_momentum": float(top10_momentum)

    }).execute()


def save_momentum_snapshot(
    supabase,
    system_type,
    ranking_df,
    leverage_list,
    sell_buffer
):

    snapshot_date = str(date.today())

    rows = []

    for idx, (_, row) in enumerate(
        ranking_df.iterrows()
    ):

        leverage = None

        if idx < len(leverage_list):
            leverage = leverage_list[idx]

        rows.append({

            "snapshot_date": snapshot_date,
            "system_type": system_type,

            "ticker": row["ticker"],
            "rank": int(row["rank"]),
            "score": float(row["score"]),
            "latest_price": float(row["latest_price"]),

            "target_leverage": leverage,
            "sell_buffer": sell_buffer

        })

    if rows:

        supabase.table(
            "momentum_snapshot"
        ).insert(rows).execute()


def save_order_snapshot(
    supabase,
    orders_df
):

    if orders_df.empty:
        return

    snapshot_date = str(date.today())

    rows = []

    for _, row in orders_df.iterrows():

        rows.append({

            "snapshot_date": snapshot_date,

            "system_type": row.get("system"),
            "action": row.get("action"),
            "ticker": row.get("ticker"),
            "reason": row.get("reason"),

            "target_leverage": row.get(
                "target_leverage",
                None
            ),

            "rank": row.get(
                "rank",
                None
            )

        })

    supabase.table(
        "order_snapshot"
    ).insert(rows).execute()
