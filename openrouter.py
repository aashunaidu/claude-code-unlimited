import asyncio
import json
import re
import time
import os
import logging
import httpx
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse, JSONResponse
import uvicorn

logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

# --- CONFIGURATION ---
TARGET_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"

OPENROUTER_KEYS_STRING = "key1,key2,key3,key4"

RATE_LIMIT_COOLDOWN = 65
DEAD_KEY_COOLDOWN = 86400
MAX_RETRIES_PER_REQUEST = 15

# --- Strategy 1: Request Queue ---
KEY_WAIT_TIMEOUT  = 120   # seconds to wait for a free key before giving up
KEY_POLL_INTERVAL = 2     # how often (seconds) to re-check for a free key

# --- Strategy 4: Exponential Backoff ---
BACKOFF_BASE      = 1.5   # multiplier:  1.5^attempt  → ~1.5s, 2.3s, 3.4s, 5s …
BACKOFF_MAX       = 30    # cap (seconds) so we never wait more than 30s per retry

api_keys = [k.strip() for k in OPENROUTER_KEYS_STRING.split(",")]

# --- STATE ---
# ✅ FIX: Use asyncio.Lock instead of threading.Lock — safe for async code
state_lock = asyncio.Lock()
keys_data = {key: {"successes": 0, "failures": 0, "cooldown_until": 0} for key in api_keys}
stats = {
    "total_requests": 0, "success_requests": 0, "failed_requests": 0,
    "retried_requests": 0, "input_tokens": 0, "output_tokens": 0,
    "last_error": "None", "active_model": "Waiting...",
    "queued_requests": 0,   # requests currently waiting for a free key
}
# ✅ FIX: Round-robin pointer — advances on EVERY call, not just on failure
rr_index = 0

# ✅ FIX: Shared httpx client — created once, reused for all requests
http_client: httpx.AsyncClient = None


async def get_next_available_key() -> str | None:
    """
    Round-robin across all keys, skipping ones on cooldown.
    Returns immediately — None if every key is busy right now.
    """
    global rr_index
    async with state_lock:
        for _ in range(len(api_keys)):
            key = api_keys[rr_index]
            rr_index = (rr_index + 1) % len(api_keys)
            if time.time() > keys_data[key]["cooldown_until"]:
                return key
        return None


async def get_next_available_key_with_wait() -> str | None:
    """
    Strategy 1 — Request Queue:
    Instead of instantly returning None (→ 429) when all keys are busy,
    park the coroutine here and keep polling every KEY_POLL_INTERVAL seconds
    until either a key frees up or KEY_WAIT_TIMEOUT is reached.
    Claude Code just sees a slow response, never a failure.
    """
    async with state_lock:
        stats["queued_requests"] += 1
    try:
        deadline = time.monotonic() + KEY_WAIT_TIMEOUT
        while time.monotonic() < deadline:
            key = await get_next_available_key()
            if key:
                return key
            await asyncio.sleep(KEY_POLL_INTERVAL)
        return None   # genuinely timed out after KEY_WAIT_TIMEOUT seconds
    finally:
        async with state_lock:
            stats["queued_requests"] -= 1


async def trigger_cooldown(key, status_code):
    async with state_lock:
        keys_data[key]["failures"] += 1
        cooldown = DEAD_KEY_COOLDOWN if status_code in [401, 403] else RATE_LIMIT_COOLDOWN
        keys_data[key]["cooldown_until"] = time.time() + cooldown


# --- DASHBOARD ---
async def print_terminal_dashboard():
    while True:
        await asyncio.sleep(1.5)
        os.system('cls' if os.name == 'nt' else 'clear')

        async with state_lock:
            active_keys = sum(1 for k in keys_data.values() if time.time() > k["cooldown_until"])
            cooldown_keys = len(api_keys) - active_keys
            current_rr = rr_index  # snapshot for display

            print("=" * 65)
            print("🚀 CLAUDE CODE DIAGNOSTIC BALANCER 🚀".center(65))
            print("=" * 65)
            print(f" Routing Model  : {stats['active_model']}")
            print(f" Total Requests : {stats['total_requests']}")
            print(f" Successful     : {stats['success_requests']}")
            print(f" Intercepted    : {stats['retried_requests']}")
            print(f" Hard Fails     : {stats['failed_requests']}")
            print(f" Active Keys    : {active_keys} / {len(api_keys)}  |  Cooled Down: {cooldown_keys}")
            print(f" Next RR Key    : ...{api_keys[current_rr][-8:]}")
            print(f" Queued/Waiting : {stats['queued_requests']}  (holding for a free key)")
            print("-" * 65)
            print(f" LAST ERROR     : {stats['last_error']}")
            print("-" * 65)
            print(f"  {'Key':18} | {'OK':8} | {'Fail':6} | Status")
            print(f"  {'-'*18}-+-{'-'*8}-+-{'-'*6}-+-{'-'*20}")

            shown = 0
            for i, (key, data) in enumerate(keys_data.items()):
                if shown >= 8:
                    break
                short_key = "..." + key[-8:]
                remaining = data["cooldown_until"] - time.time()
                if remaining > 0:
                    status = f"Cooldown ({int(remaining)}s)"
                else:
                    status = "Active"
                    marker = "👉 " if i == current_rr else "   "
                    short_key = marker + short_key
                print(f"  {short_key:<18} | {data['successes']:<8} | {data['failures']:<6} | {status}")
                shown += 1
            print("=" * 65)


# --- LIFESPAN (replaces deprecated @app.on_event) ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    global http_client
    # ✅ FIX: Single shared client, created once at startup
    http_client = httpx.AsyncClient(timeout=120.0)
    asyncio.create_task(print_terminal_dashboard())
    yield
    await http_client.aclose()


app = FastAPI(lifespan=lifespan)


# --- MAIN PROXY ---
@app.api_route("/{path:path}", methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"])
async def proxy(path: str, request: Request):
    if path == "favicon.ico":
        return Response(status_code=204)

    # Intercept model list — Claude Code crashes without this
    if "models" in path and request.method == "GET":
        return JSONResponse({
            "type": "list",
            "data": [{
                "type": "model",
                "id": TARGET_MODEL,
                "display_name": "My OpenRouter Model",
                "created_at": "2024-01-01T00:00:00Z"
            }]
        })

    body = await request.body()

    # Force target model in every POST payload
    if request.method == "POST" and body:
        try:
            json_data = json.loads(body)
            json_data["model"] = TARGET_MODEL
            async with state_lock:
                stats["active_model"] = TARGET_MODEL
            body = json.dumps(json_data).encode("utf-8")
        except Exception:
            pass

    async with state_lock:
        stats["total_requests"] += 1

    bad_headers = {"host", "authorization", "x-api-key", "content-length",
                   "connection", "anthropic-beta", "anthropic-version"}

    for attempt in range(MAX_RETRIES_PER_REQUEST):

        # Strategy 1: wait for a free key instead of instantly 429-ing
        key = await get_next_available_key_with_wait()

        if not key:
            # Timed out after KEY_WAIT_TIMEOUT — genuinely no key available
            return JSONResponse(
                content={"type": "error", "error": {"type": "rate_limit_error",
                         "message": f"All proxy keys on cooldown for >{KEY_WAIT_TIMEOUT}s. Try again later."}},
                status_code=429
            )

        headers = {k: v for k, v in request.headers.items() if k.lower() not in bad_headers}
        headers["Authorization"] = f"Bearer {key}"
        headers["HTTP-Referer"] = "http://127.0.0.1:11434"
        headers["X-Title"] = "Claude Code Router"

        clean_path = path.lstrip("/")
        if clean_path.startswith("api/"):
            target_url = f"https://openrouter.ai/{clean_path}"
        else:
            target_url = f"https://openrouter.ai/api/{clean_path}"

        req = http_client.build_request(request.method, target_url, headers=headers, content=body)

        try:
            resp = await http_client.send(req, stream=True)
        except Exception as e:
            await trigger_cooldown(key, 500)
            async with state_lock:
                stats["retried_requests"] += 1
                stats["last_error"] = f"Connection error: {str(e)[:100]}"
            # Strategy 4: backoff so we don't spin-hammer on flaky network
            backoff = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            await asyncio.sleep(backoff)
            continue

        excluded_resp_headers = {"content-encoding", "content-length",
                                  "transfer-encoding", "connection"}
        resp_headers = {k: v for k, v in resp.headers.items()
                        if k.lower() not in excluded_resp_headers}

        if resp.status_code == 200:
            # ✅ FIX: Track tokens only from the final usage block to avoid double-counting
            usage_buffer = ""

            async def stream_generator():
                nonlocal usage_buffer
                try:
                    async for chunk in resp.aiter_bytes():
                        if chunk:
                            usage_buffer += chunk.decode("utf-8", errors="ignore")
                            yield chunk
                    # Parse token counts once from complete response
                    in_tokens = re.findall(r'"input_tokens"\s*:\s*(\d+)', usage_buffer)
                    out_tokens = re.findall(r'"output_tokens"\s*:\s*(\d+)', usage_buffer)
                    async with state_lock:
                        # Take the LAST occurrence — that's the final usage summary
                        if in_tokens:
                            stats["input_tokens"] += int(in_tokens[-1])
                        if out_tokens:
                            stats["output_tokens"] += int(out_tokens[-1])
                        stats["success_requests"] += 1
                        keys_data[key]["successes"] += 1
                finally:
                    await resp.aclose()

            return StreamingResponse(stream_generator(), status_code=200, headers=resp_headers)

        else:
            await resp.aread()
            status = resp.status_code
            content = resp.content
            await resp.aclose()

            error_msg = f"HTTP {status}"
            try:
                error_json = json.loads(content)
                error_msg = error_json.get("error", {}).get("message", error_msg)
            except Exception:
                error_msg = content.decode("utf-8", errors="ignore")[:150]

            async with state_lock:
                stats["last_error"] = f"[{status}] {error_msg}"

            # Hard errors — don't retry, return immediately
            if status in [400, 422]:
                async with state_lock:
                    stats["failed_requests"] += 1
                return JSONResponse(
                    content={"type": "error", "error": {"type": "invalid_request_error",
                             "message": f"[Proxy] {error_msg}"}},
                    status_code=status
                )

            # Auth/not-found errors — kill the key and retry with next
            if status in [401, 403, 404]:
                await trigger_cooldown(key, status)
                async with state_lock:
                    stats["retried_requests"] += 1
                # No backoff here — move immediately to the next key
                continue

            # Rate limit or server error — cooldown this key then backoff before retry
            await trigger_cooldown(key, status)
            async with state_lock:
                stats["retried_requests"] += 1
            # Strategy 4: exponential backoff — 1.5s, 2.3s, 3.4s … capped at BACKOFF_MAX
            backoff = min(BACKOFF_BASE ** attempt, BACKOFF_MAX)
            await asyncio.sleep(backoff)
            continue

    async with state_lock:
        stats["failed_requests"] += 1
    return JSONResponse(
        content={"type": "error", "error": {"type": "api_error",
                 "message": f"Max retries ({MAX_RETRIES_PER_REQUEST}) reached. All keys busy."}},
        status_code=500
    )


if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=11434, log_level="warning")