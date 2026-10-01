"""Quick check that EirGrid's data endpoint is reachable from this machine.

    python check_eirgrid.py

Requests each data series for today, one at a time, and prints whether it worked,
how long it took, and how many readings came back. Paste the output when reporting
a problem.
"""

import datetime as dt
import time

from app.eirgrid import REQUESTS, EirGridClient, EirGridError

client = EirGridClient()
day = dt.date.today()
print(f"EirGrid check for {day:%d-%b-%Y}, region {client.region}\n")
for chart_type, area in REQUESTS:
    started = time.time()
    try:
        rows = client._chart(chart_type, area, day, day, attempts=1)
        values = sum(1 for r in rows if r.get("Value") is not None)
        status = "OK   " if values else "EMPTY"
        print(f"{status} {area:15} {time.time() - started:5.1f}s  {values:3} readings")
    except EirGridError as exc:
        print(f"FAIL  {area:15} {time.time() - started:5.1f}s  {str(exc).split(': ', 1)[-1]}")
