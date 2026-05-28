# QuantumChat

A Flask + Socket.IO chat application with authentication, direct messaging, and real-time signaling.

## Local setup

1. Create and activate a virtual environment:

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. Install dependencies:

   ```powershell
   pip install -r requirements.txt
   ```

3. Run the app:

   ```powershell
   python app.py
   ```

4. Open the app in your browser:

   `http://127.0.0.1:5000`

## GitHub repository setup

1. Initialize git and commit locally:

   ```powershell
   git init
   git branch -M main
   git add .
   git commit -m "Initial commit"
   ```

2. Create a new repository on GitHub, then add the remote and push:

   ```powershell
   git remote add origin https://github.com/<your-username>/<repo-name>.git
   git push -u origin main
   ```

## Notes

- `app.py` uses SQLite by default, stored in `quantumchat.db`.
- Set `FLASK_SECRET` and `DATABASE_URL` in environment variables for production.
- `instance/` and `static/uploads/` are ignored so local secrets and uploads stay private.
