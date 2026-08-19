"""
Talent Market Signal
════════════════════

A scaled-insights product over public U.S. labor-market data.

The package is deliberately small — four modules with one job each:

    schema   the column contract every other module agrees on
    data     load the committed Parquet (or the synthetic fixture)
    metrics  the derived measures: competition index, adjacency, arbitrage
    report   render the client-ready Talent Pool Report one-pager

`app.py` at the repo root is Streamlit UI and nothing else. Everything
worth testing lives in here.
"""

__version__ = "0.1.0"
