"""Canonical <-> broker-native symbol translation.

Canonical format: "BASE/QUOTE" (e.g. "EUR/USD", "BTC/USDT").
Strategies use canonical symbols only. Adapters translate.
"""
from __future__ import annotations


class SymbolMapper:
    def __init__(self, namespace: str, table: dict[str, str]) -> None:
        self.namespace = namespace
        self._canon_to_native = dict(table)
        self._native_to_canon = {v: k for k, v in table.items()}

    def to_native(self, canonical: str) -> str:
        try:
            return self._canon_to_native[canonical]
        except KeyError as e:
            raise ValueError(
                f"symbol '{canonical}' not mapped in namespace '{self.namespace}'"
            ) from e

    def to_canonical(self, native: str) -> str:
        try:
            return self._native_to_canon[native]
        except KeyError as e:
            raise ValueError(
                f"native symbol '{native}' not mapped in namespace '{self.namespace}'"
            ) from e


# Default namespaces. Extend per-broker as adapters are added.
PAPER_NAMESPACE = SymbolMapper(
    "paper",
    {
        "EUR/USD": "EUR/USD",
        "GBP/USD": "GBP/USD",
        "USD/JPY": "USD/JPY",
        "BTC/USD": "BTC/USD",
        "BTC/USDT": "BTC/USDT",
    },
)

OANDA_NAMESPACE = SymbolMapper(
    "oanda",
    {
        # Major forex pairs
        "EUR/USD": "EUR_USD",
        "GBP/USD": "GBP_USD",
        "USD/JPY": "USD_JPY",
        "USD/CHF": "USD_CHF",
        "AUD/USD": "AUD_USD",
        "USD/CAD": "USD_CAD",
        "NZD/USD": "NZD_USD",
        # Cross pairs
        "EUR/GBP": "EUR_GBP",
        "EUR/JPY": "EUR_JPY",
        "GBP/JPY": "GBP_JPY",
        "AUD/JPY": "AUD_JPY",
        "EUR/CHF": "EUR_CHF",
        # Metals
        "XAU/USD": "XAU_USD",
        "XAG/USD": "XAG_USD",
        # Equity indices
        "US30/USD": "US30_USD",
        "SPX500/USD": "SPX500_USD",
        "NAS100/USD": "NAS100_USD",
        "UK100/GBP": "UK100_GBP",
        "DE30/EUR": "DE30_EUR",
        "JP225/USD": "JP225_USD",
        # Commodities
        "WTICO/USD": "WTICO_USD",
        "BCO/USD": "BCO_USD",
    },
)

DERIV_NAMESPACE = SymbolMapper(
    "deriv",
    {
        # Forex
        "EUR/USD": "frxEURUSD",
        "GBP/USD": "frxGBPUSD",
        "USD/JPY": "frxUSDJPY",
        "AUD/USD": "frxAUDUSD",
        "USD/CAD": "frxUSDCAD",
        "USD/CHF": "frxUSDCHF",
        # Deriv synthetic indices (Volatility)
        "V10/USD": "1HZ10V",
        "V25/USD": "1HZ25V",
        "V50/USD": "1HZ50V",
        "V75/USD": "1HZ75V",
        "V100/USD": "1HZ100V",
        # Boom / Crash indices
        "BOOM1000/USD": "BOOM1000",
        "BOOM500/USD": "BOOM500",
        "CRASH1000/USD": "CRASH1000",
        "CRASH500/USD": "CRASH500",
    },
)

NAMESPACES: dict[str, SymbolMapper] = {
    "paper": PAPER_NAMESPACE,
    "oanda": OANDA_NAMESPACE,
    "deriv": DERIV_NAMESPACE,
}


def get_mapper(namespace: str) -> SymbolMapper:
    try:
        return NAMESPACES[namespace]
    except KeyError as e:
        raise ValueError(f"unknown symbol namespace: {namespace}") from e
