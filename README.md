# OmniRoute Web Chat & Gateway Suite

A modern, full-stack web chat application and terminal client for testing and chatting with AI models through the **OmniRoute** gateway proxy, pre-configured for instant local testing and **one-click deployment to Render**.

```
├── app.py                 ← FastAPI web backend & SSE streaming proxy
├── index.html             ← Modern glassmorphic chat interface
├── requirements.txt       ← Python dependencies for local & Render
├── render.yaml            ← Render Blueprint specification
├── Procfile               ← Process manager configuration for Render
├── omniroute_client.py    ← Zero-dependency Python client (stdlib)
├── chat.py                ← Terminal REPL chatbot
└── .env.example           ← Environment variable template
```

---

## 🚀 Running the Web App Locally

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Start OmniRoute Gateway (if running locally)

```bash
omniroute                  # Starts gateway on http://localhost:20128
```

### 3. Launch Web Server

```bash
python3 app.py
```
*(Or use live reload: `uvicorn app:app --reload --port 8000`)*

Open **http://localhost:8000** in your browser!

---

## 🌐 Deploying to Render

This repository is pre-configured for **Render Web Services**:

### Option 1: Automatic Blueprint (Recommended)
1. Push this repository to **GitHub / GitLab**.
2. Log into your [Render Dashboard](https://dashboard.render.com).
3. Click **New +** → **Blueprint**.
4. Select this repository. Render will automatically read `render.yaml` and configure the Python build and start commands.
5. In the **Environment Variables** section, set your `OMNIROUTE_API_KEY` and remote `OMNIROUTE_BASE_URL` (if your gateway is hosted remotely).
6. Click **Apply**.

### Option 2: Manual Web Service Setup
1. On Render, click **New +** → **Web Service**.
2. Connect your repository.
3. Configure settings:
   - **Environment**: `Python 3`
   - **Build Command**: `pip install -r requirements.txt`
   - **Start Command**: `uvicorn app:app --host 0.0.0.0 --port $PORT`
4. Add Environment Variables:
   - `OMNIROUTE_BASE_URL` (e.g. your remote gateway URL or endpoint)
   - `OMNIROUTE_API_KEY` (your OmniRoute API key)
   - `OMNIROUTE_MODEL` (default: `auto/best-chat`)
5. Click **Deploy Web Service**.

---

## 💻 Terminal Chatbot

If you prefer testing from the command line:

```bash
python3 chat.py
```

### Terminal Commands

| Command | Action |
|---|---|
| `/models [filter]` | list routable models — `/models claude` |
| `/model <id>` | switch model, e.g. `/model aug/opus4.8` |
| `/system <text>` | set a system prompt |
| `/stream` | toggle streaming |
| `/think` | show the model's reasoning |
| `/temp 0.7` | set temperature |
| `/clear` `/retry` `/history` | manage conversation |
| `/save [file]` | dump transcript to markdown |
| `/exit` | quit |

---

## ⚙️ Configuration (.env)

```ini
OMNIROUTE_API_KEY=your-api-key-here
OMNIROUTE_BASE_URL=http://localhost:20128/v1
OMNIROUTE_MODEL=auto/best-chat
OMNIROUTE_SYSTEM=
PORT=8000
```
