const API_BASE = "http://localhost:8000/api";

const emailEl = document.getElementById("email");
const passwordEl = document.getElementById("password");
const authStatusEl = document.getElementById("authStatus");
const bankStatusEl = document.getElementById("bankStatus");
const connectBtn = document.getElementById("connectBankBtn");

let token = localStorage.getItem("moo_money_token") || null;

function setAuthStatus(message) {
  authStatusEl.textContent = message;
}

function setBankStatus(message) {
  bankStatusEl.textContent = message;
}

function updateUiForAuth() {
  connectBtn.disabled = !token;
  setAuthStatus(token ? "Authenticated" : "Not authenticated");
}

async function request(path, method, body) {
  const response = await fetch(`${API_BASE}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  const json = await response.json();
  if (!response.ok) {
    throw new Error(json.detail || "Request failed");
  }
  return json;
}

async function authenticate(path) {
  try {
    const email = emailEl.value.trim();
    const password = passwordEl.value;
    const result = await request(path, "POST", { email, password });
    token = result.access_token;
    localStorage.setItem("moo_money_token", token);
    updateUiForAuth();
    setBankStatus("Ready to connect bank account.");
  } catch (err) {
    setAuthStatus(`Auth error: ${err.message}`);
  }
}

async function connectBank() {
  try {
    const { link_token } = await request("/plaid/create_link_token", "POST");
    const handler = Plaid.create({
      token: link_token,
      onSuccess: async (public_token) => {
        try {
          const result = await request("/plaid/exchange_public_token", "POST", { public_token });
          setBankStatus(`Bank connected. Item ID: ${result.item_id}`);
        } catch (err) {
          setBankStatus(`Exchange error: ${err.message}`);
        }
      },
      onExit: (err) => {
        if (err) {
          setBankStatus(`Plaid exited: ${err.display_message || err.error_message}`);
        }
      },
    });
    handler.open();
  } catch (err) {
    setBankStatus(`Plaid error: ${err.message}`);
  }
}

document.getElementById("registerBtn").addEventListener("click", () => authenticate("/register"));
document.getElementById("loginBtn").addEventListener("click", () => authenticate("/login"));
document.getElementById("logoutBtn").addEventListener("click", () => {
  token = null;
  localStorage.removeItem("moo_money_token");
  updateUiForAuth();
  setBankStatus("Logged out.");
});
connectBtn.addEventListener("click", connectBank);

updateUiForAuth();
