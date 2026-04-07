# Moo Money

Moo Money is a collaborative personal finance website for households. This repo now includes a working frontend and a secured FastAPI backend with Plaid bank connection support.

## Project Structure

- `frontend/` — Static website (HTML/CSS/JS) for sign-up/login and bank linking.
- `backend/` — FastAPI API with JWT auth, hashed passwords, SQLite persistence, and Plaid integration.

## Security Features

- JWT-based authentication for protected API routes.
- Password hashing via bcrypt (`passlib`).
- User-scoped Plaid item storage.
- Environment-variable based secret handling.

## Backend Setup

1. Create and activate a virtual environment.
2. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```
3. Configure environment variables:
   ```bash
   cp backend/.env.example backend/.env
   ```
4. Fill in `PLAID_CLIENT_ID` and `PLAID_SECRET` with your Plaid credentials.
5. Start API server:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

## Frontend Setup

Serve the frontend with any static web server:

```bash
python -m http.server 5173 --directory frontend
```

Open `http://localhost:5173` and use the UI to register/login, then click **Connect Bank Account** to launch Plaid Link.

## Important Note

This implementation is production-oriented in architecture but still requires production hardening before live deployment (HTTPS, secure cookies, CSRF protection strategy for browser sessions, stronger DB setup, secrets management, and stricter CORS policies).
