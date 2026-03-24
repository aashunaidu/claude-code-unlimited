# 🔀 OpenRouter Key Balancer — Free Claude Code on Autopilot

> **Run Claude Code (or any AI tool) for free, forever — using rotating OpenRouter API keys with zero 429 errors.**

---

## ✨ What Is This?

This is a **local proxy server** that sits between Claude Code (or any OpenAI-compatible tool) and OpenRouter. It:

- 🔑 **Rotates across dozens of free OpenRouter API keys** automatically
- 🔄 **Retries failed requests** without you ever noticing
- 😴 **Puts rate-limited keys to sleep** and wakes them up later
- 📊 **Shows a live dashboard** in your terminal so you know what's happening
- 🆓 **Works with free OpenRouter models** — no credit card required

You get a single local endpoint (`http://127.0.0.1:11434`) that looks like an Ollama server. Point Claude Code at it and forget about it.

---

## 🎯 Who Is This For?

| You are... | This means... |
|---|---|
| 🎨 **Vibe coder** | You just want free Claude Code. Follow the Quick Start. Done. |
| 🔧 **Real coder** | You want to swap models, tune retry logic, or run this in prod. Skip to [Advanced Config](#advanced-configuration). |

---

## ⚡ Quick Start (Vibe Coders — Start Here)

### Step 1 — Get Free OpenRouter Keys

1. Go to [openrouter.ai](https://openrouter.ai) and make a free account
2. Go to **Keys** → **Create Key**
3. Make as many accounts as you can, more accounts, more keys. You can use temp mail if you take responsibility. 
4. Copy them all — you'll paste them into the script
5. If you are a all day user, you only need max 45-50 keys and you can almost never able to hit the limit. 



---

### Step 2 — Install Python Dependencies

Open your terminal and run:

```bash
pip install fastapi uvicorn httpx
```

That's it. No Docker, no nonsense.

---

### Step 3 — Paste Your Keys Into the Script

Open `balancer.py` and find this line near the top:

```python
OPENROUTER_KEYS_STRING = "sk-or-v1-abc123...,sk-or-v1-def456..."
```

Replace it with your own keys, **separated by commas**. No spaces needed.

#### Adding Multiple Keys (The Right Way)

The more keys you add, the more parallel requests you can handle and the less you'll hit rate limits. Here's how to format them:

**2 keys:**
```python
OPENROUTER_KEYS_STRING = "sk-or-v1-aaa111,sk-or-v1-bbb222"
```

**Many keys — use a multi-line string to keep it readable:**
```python
OPENROUTER_KEYS_STRING = (
    "sk-or-v1-aaa111,"
    "sk-or-v1-bbb222,"
    "sk-or-v1-ccc333,"
    "sk-or-v1-ddd444,"
    "sk-or-v1-eee555"
)
```

> ⚠️ **No trailing comma on the last key.** Every other key must have a comma directly after it with no space.

> 💡 **How many keys should I add?** A good rule of thumb: **1 key per person** using the proxy simultaneously. If it's just you, 5–10 keys is plenty. Free tier limits reset every minute so even a handful of keys cycles smoothly.

---

### Step 4 — Run It

```bash
python openrouter.py
```

You'll see a dashboard pop up in your terminal. Leave it running.

---

### Step 5 — Connect Claude Code and also works with openclaw

Run this command **once** to point Claude Code at your local proxy:

```bash
claude config set --global apiBaseUrl http://127.0.0.1:11434
```

Then set a fake API key (Claude Code requires one, but the proxy handles auth):

```bash
claude config set --global apiKey fake-key-proxy-handles-this
```

Now just use Claude Code normally:

```bash
claude
```

🎉 **That's it.** Claude Code is now routing through your free keys.

---

### Step 6 — To Undo / Switch Back

```bash
claude config set --global apiBaseUrl https://api.anthropic.com
claude config set --global apiKey sk-ant-your-real-key-here
```

---

## 🧠 How It Works (The Simple Version)

```
You → Claude Code → Your Local Proxy (port 11434) → OpenRouter → AI Model
                         ↑
              Secretly rotates through all your keys
              Retries if one fails
              Sleeps rate-limited keys & wakes them up
```

The proxy pretends to be an Ollama server. Claude Code thinks it's talking to a normal local model. In reality, your request is being forwarded to OpenRouter with whichever key is available right now.

---

## 🖥️ The Live Dashboard

When you run the script, your terminal looks something like this:

```
=================================================================
            🚀 CLAUDE CODE DIAGNOSTIC BALANCER 🚀
=================================================================
 Routing Model  : nvidia/nemotron-3-super-120b-a12b:free
 Total Requests : 47
 Successful     : 45
 Intercepted    : 12
 Hard Fails     : 0
 Active Keys    : 41 / 48  |  Cooled Down: 7
 Next RR Key    : ...fd63a7ec
 Queued/Waiting : 0  (holding for a free key)
-----------------------------------------------------------------
 LAST ERROR     : [429] Rate limit exceeded
-----------------------------------------------------------------
  Key                | OK       | Fail   | Status
  ------------------+---------+--------+---------------------
👉 ...fd63a7ec       | 12       | 0      | Active
   ...0f41eef        | 8        | 2      | Cooldown (52s)
   ...40335          | 11       | 0      | Active
   ...1e60ebe5       | 9        | 1      | Active
=================================================================
```

- **Active Keys** = keys ready to go right now
- **Cooled Down** = temporarily rate-limited, will auto-recover
- **Intercepted** = requests that got retried (you never saw these fail)
- **Hard Fails** = actual failures (400 bad request, etc.)

---

## 🔧 Advanced Configuration

For people who want to tune the behaviour — all config is at the top of `balancer.py`.

### Change the Model

```python
TARGET_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"
```

Replace this with any model from [openrouter.ai/models](https://openrouter.ai/models). Filter by **Free** to find zero-cost options. Good ones:

| Model | Good For |
|---|---|
| `nvidia/nemotron-3-super-120b-a12b:free` | General coding (default) |
| `google/gemma-3-27b-it:free` | Fast responses |
| `meta-llama/llama-4-maverick:free` | Longer context |
| `deepseek/deepseek-chat-v3-0324:free` | Strong reasoning |
| `microsoft/phi-4-reasoning-plus:free` | Math & logic |

---

### Tune Rate Limit Behaviour

```python
RATE_LIMIT_COOLDOWN = 65      # seconds to wait after a 429 (default: 65)
DEAD_KEY_COOLDOWN   = 86400   # seconds to lock out a dead key (default: 24h)
MAX_RETRIES_PER_REQUEST = 15  # how many times to retry before giving up
```

---

### Tune the Request Queue

When all keys are busy, requests wait instead of failing:

```python
KEY_WAIT_TIMEOUT  = 120   # give up waiting after 2 minutes
KEY_POLL_INTERVAL = 2     # check for a free key every 2 seconds
```

Increase `KEY_WAIT_TIMEOUT` if you're running large batches and are okay with waiting longer.

---

### Tune Exponential Backoff

Between retries, the proxy waits a bit longer each time to avoid hammering:

```python
BACKOFF_BASE = 1.5    # each retry waits 1.5x longer than the last
BACKOFF_MAX  = 30     # never wait more than 30 seconds between retries
```

Retry wait times: `1.5s → 2.3s → 3.4s → 5.1s → ... → 30s (capped)`

---

### Change the Port

By default the proxy runs on `11434` (Ollama's default port). Change it at the bottom:

```python
uvicorn.run(app, host="127.0.0.1", port=11434, log_level="warning")
```

If you change the port, update your Claude Code config too:

```bash
claude config set --global apiBaseUrl http://127.0.0.1:YOUR_PORT
```

---

## 🛠️ Running as a Background Service

### macOS / Linux — Keep It Running After Terminal Closes

```bash
nohup python balancer.py > balancer.log 2>&1 &
echo "Proxy PID: $!"
```

To stop it:
```bash
kill $(lsof -ti:11434)
```

### Windows — Background with PowerShell

```powershell
Start-Process python -ArgumentList "balancer.py" -WindowStyle Hidden
```

### Docker (Optional)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY balancer.py .
RUN pip install fastapi uvicorn httpx
EXPOSE 11434
CMD ["python", "balancer.py"]
```

```bash
docker build -t or-balancer .
docker run -d -p 11434:11434 or-balancer
```

---

## 🤝 Using With Other Tools

Because the proxy mimics an Ollama/OpenAI-compatible API, it works with **anything** that lets you set a custom base URL:

### Cursor / Windsurf / Continue.dev
Set base URL to `http://127.0.0.1:11434` and model to whatever you set in `TARGET_MODEL`.

### Python / OpenAI SDK
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://127.0.0.1:11434/api",
    api_key="fake-key"
)

response = client.chat.completions.create(
    model="anything",  # proxy ignores this and uses TARGET_MODEL
    messages=[{"role": "user", "content": "Hello!"}]
)
```

### Direct HTTP
```bash
curl http://127.0.0.1:11434/api/v1/messages \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer fake-key" \
  -d '{"model": "anything", "max_tokens": 100, "messages": [{"role": "user", "content": "Hi"}]}'
```

---

## ❓ Troubleshooting

**"All proxy keys on cooldown" error**
→ All your keys hit rate limits at once. Add more keys, or increase `KEY_WAIT_TIMEOUT` and wait it out.

**Claude Code says connection refused**
→ The proxy isn't running. Check your terminal or start it again with `python balancer.py`.

**Responses are slow**
→ Free tier models can be slow. Try a different `TARGET_MODEL`, or add more API keys to reduce wait time between retries.

**I want my real Claude back**
```bash
claude config set --global apiBaseUrl https://api.anthropic.com
claude config set --global apiKey sk-ant-your-real-key
```

---

## ⚠️ Disclaimer

This tool uses free-tier OpenRouter API access. Please respect each provider's terms of service. Free tiers exist because AI companies want developers to try their models — don't abuse them. This project is for **personal use and experimentation**, not production workloads.

---

## 📄 License

MIT — do whatever you want with it.

---

*Built with FastAPI + httpx. Inspired by the Claude Code × Ollama integration guide.*
