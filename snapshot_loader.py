import pandas as pd


def load_latest_regime_snapshot(
    supabase
):

    result = supabase.table(
        "core_regime_snapshot"
    ).select("*").order(
        "snapshot_date",
        desc=True
    ).limit(1).execute()

    return pd.DataFrame(result.data)


def load_latest_momentum_snapshot(
    supabase,
    system_type
):

    latest_date_result = supabase.table(
        "momentum_snapshot"
    ).select(
        "snapshot_date"
    ).eq(
        "system_type",
        system_type
    ).order(
        "snapshot_date",
        desc=True
    ).limit(1).execute()

    if not latest_date_result.data:
        return pd.DataFrame()

    latest_date = latest_date_result.data[0]["snapshot_date"]

    result = supabase.table(
        "momentum_snapshot"
    ).select("*").eq(
        "system_type",
        system_type
    ).eq(
        "snapshot_date",
        latest_date
    ).order(
        "rank",
        desc=False
    ).execute()

    return pd.DataFrame(result.data)


def load_latest_order_snapshot(
    supabase,
    system_type
):

    latest_date_result = supabase.table(
        "order_snapshot"
    ).select(
        "snapshot_date"
    ).eq(
        "system_type",
        system_type
    ).order(
        "snapshot_date",
        desc=True
    ).limit(1).execute()

    if not latest_date_result.data:
        return pd.DataFrame()

    latest_date = latest_date_result.data[0]["snapshot_date"]

    result = supabase.table(
        "order_snapshot"
    ).select("*").eq(
        "system_type",
        system_type
    ).eq(
        "snapshot_date",
        latest_date
    ).execute()

    return pd.DataFrame(result.data)
