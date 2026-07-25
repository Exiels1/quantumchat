# Keeping QuantumChat Awake

Render free web services can spin down after inactivity. To reduce cold-start pain, ping the lightweight `/health` route every 4 minutes.

Options:

- cron-job.org: create a cron job for `https://your-app.onrender.com/health` every 4 minutes.
- UptimeRobot: create an HTTP monitor for `https://your-app.onrender.com/health`.
- Simple Python script:

```python
import time
import requests

URL = "https://your-app.onrender.com/health"

while True:
    try:
        response = requests.get(URL, timeout=20)
        print(response.status_code, response.text[:120])
    except requests.RequestException as exc:
        print(f"Ping failed: {exc}")
    time.sleep(240)
```
