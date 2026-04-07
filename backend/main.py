import os
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel, EmailStr
from plaid.api import plaid_api
from plaid.configuration import Configuration
from plaid.api_client import ApiClient
from plaid.model.country_code import CountryCode
from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.products import Products

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "moo_money.db"

SECRET_KEY = os.getenv("JWT_SECRET_KEY", "dev-secret-change-me")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))

PLAID_CLIENT_ID = os.getenv("PLAID_CLIENT_ID")
PLAID_SECRET = os.getenv("PLAID_SECRET")
PLAID_ENV = os.getenv("PLAID_ENV", "sandbox")

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/login")

app = FastAPI(title="Moo Money API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS plaid_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            access_token TEXT NOT NULL,
            created_at TEXT NOT NULL,
            FOREIGN KEY(user_id) REFERENCES users(id)
        )
        """
    )
    conn.commit()
    conn.close()


@app.on_event("startup")
def on_startup() -> None:
    init_db()


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class PublicTokenRequest(BaseModel):
    public_token: str


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def create_access_token(subject: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    payload = {"sub": subject, "exp": expire}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_user(token: str = Depends(oauth2_scheme)) -> sqlite3.Row:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: Optional[str] = payload.get("sub")
        if email is None:
            raise credentials_exception
    except JWTError as exc:
        raise credentials_exception from exc

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    conn.close()
    if user is None:
        raise credentials_exception
    return user


def get_plaid_client() -> plaid_api.PlaidApi:
    host = {
        "sandbox": "https://sandbox.plaid.com",
        "development": "https://development.plaid.com",
        "production": "https://production.plaid.com",
    }.get(PLAID_ENV, "https://sandbox.plaid.com")

    config = Configuration(
        host=host,
        api_key={
            "clientId": PLAID_CLIENT_ID,
            "secret": PLAID_SECRET,
            "plaidVersion": "2020-09-14",
        },
    )
    api_client = ApiClient(config)
    return plaid_api.PlaidApi(api_client)


@app.get("/api/health")
def health_check() -> dict:
    return {"status": "ok"}


@app.post("/api/register", response_model=TokenResponse)
def register(payload: RegisterRequest) -> TokenResponse:
    if len(payload.password) < 8:
        raise HTTPException(status_code=400, detail="Password must be at least 8 characters")

    conn = get_db()
    try:
        conn.execute(
            "INSERT INTO users (email, password_hash, created_at) VALUES (?, ?, ?)",
            (payload.email.lower(), hash_password(payload.password), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()
    except sqlite3.IntegrityError as exc:
        raise HTTPException(status_code=409, detail="Email already exists") from exc
    finally:
        conn.close()

    token = create_access_token(payload.email.lower())
    return TokenResponse(access_token=token)


@app.post("/api/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (payload.email.lower(),)).fetchone()
    conn.close()

    if not user or not verify_password(payload.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token(payload.email.lower())
    return TokenResponse(access_token=token)


@app.get("/api/me")
def me(current_user: sqlite3.Row = Depends(get_current_user)) -> dict:
    return {"id": current_user["id"], "email": current_user["email"]}


@app.post("/api/plaid/create_link_token")
def create_link_token(current_user: sqlite3.Row = Depends(get_current_user)) -> dict:
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        raise HTTPException(status_code=500, detail="Plaid credentials are not configured")

    request = LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id=str(current_user["id"])),
        client_name="Moo Money",
        products=[Products("transactions")],
        country_codes=[CountryCode("US")],
        language="en",
    )

    client = get_plaid_client()
    response = client.link_token_create(request)
    return {"link_token": response["link_token"]}


@app.post("/api/plaid/exchange_public_token")
def exchange_public_token(
    payload: PublicTokenRequest,
    current_user: sqlite3.Row = Depends(get_current_user),
) -> dict:
    if not PLAID_CLIENT_ID or not PLAID_SECRET:
        raise HTTPException(status_code=500, detail="Plaid credentials are not configured")

    client = get_plaid_client()
    exchange_request = ItemPublicTokenExchangeRequest(public_token=payload.public_token)
    exchange_response = client.item_public_token_exchange(exchange_request)

    conn = get_db()
    conn.execute(
        "INSERT INTO plaid_items (user_id, item_id, access_token, created_at) VALUES (?, ?, ?, ?)",
        (
            current_user["id"],
            exchange_response["item_id"],
            exchange_response["access_token"],
            datetime.now(timezone.utc).isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    return {"status": "connected", "item_id": exchange_response["item_id"]}
