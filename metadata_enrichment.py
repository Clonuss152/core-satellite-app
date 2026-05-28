import time
import yfinance as yf


def enrich_underlyings(
    supabase,
    tickers
):

    enriched = 0
    failed = []

    for ticker in tickers:

        try:

            print(f"Lade Stammdaten für {ticker}")

            yf_ticker = yf.Ticker(ticker)

            info = yf_ticker.info

            company_name = info.get(
                "longName",
                ticker
            )

            currency = info.get(
                "currency",
                ""
            )

            exchange = info.get(
                "exchange",
                ""
            )

            isin = info.get(
                "isin",
                ""
            )

            existing = (
                supabase.table("underlyings")
                .select("*")
                .eq("ticker", ticker)
                .limit(1)
                .execute()
            )

            existing_data = {}

            if existing.data:
                existing_data = existing.data[0]

            supabase.table(
                "underlyings"
            ).upsert(
                {
                    "ticker": ticker,

                    "company_name":
                        existing_data.get("company_name")
                        or company_name,

                    "isin":
                        existing_data.get("isin")
                        or isin,

                    "exchange":
                        existing_data.get("exchange")
                        or exchange,

                    "currency":
                        existing_data.get("currency")
                        or currency
                },
                on_conflict="ticker"
            ).execute()

            enriched += 1

            time.sleep(0.5)

        except Exception as e:

            print(f"Fehler bei {ticker}: {e}")

            failed.append(ticker)

    print(f"Erfolgreich angereichert: {enriched}")
    print(f"Fehlgeschlagen: {failed}")
