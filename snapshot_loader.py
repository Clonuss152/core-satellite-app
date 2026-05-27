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

    result = supabase.table(
        "momentum_snapshot"
    ).select("*").eq(
        "system_type",
        system_type
    ).order(
        "snapshot_date",
        desc=True
    ).execute()

    return pd.DataFrame(result.data)


def load_latest_order_snapshot(
    supabase,
    system_type
):

    result = supabase.table(
        "order_snapshot"
    ).select("*").eq(
        "system_type",
        system_type
    ).order(
        "snapshot_date",
        desc=True
    ).execute()

    return pd.DataFrame(result.data)
