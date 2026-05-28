import time
import yfinance as yf


def enrich_underlyings(supabase, tickers):

    enriched = 0
    failed = []

    for ticker in tickers:
        try:
            print(f"Lade Stammdaten für {ticker}")

            info = yf.Ticker(ticker).get_info()

            company_name = (
                info.get("longName")
                or info.get("shortName")
                or ticker
            )

            isin = info.get("isin") or ""
            exchange = info.get("exchange") or ""
            currency = info.get("currency") or ""

            existing = (
                supabase.table("underlyings")
                .select("*")
                .eq("ticker", ticker)
                .limit(1)
                .execute()
            )

            existing_data = existing.data[0] if existing.data else {}

            supabase.table("underlyings").upsert(
                {
                    "ticker": ticker,
                    "company_name": existing_data.get("company_name") or company_name,
                    "isin": existing_data.get("isin") or isin,
                    "exchange": existing_data.get("exchange") or exchange,
                    "currency": existing_data.get("currency") or currency,
                },
                on_conflict="ticker"
            ).execute()

            enriched += 1
            time.sleep(1.0)

        except Exception as e:
            print(f"Fehler bei {ticker}: {e}")
            failed.append(ticker)

    print(f"Erfolgreich angereichert: {enriched}")
    print(f"Fehlgeschlagen: {failed}")
