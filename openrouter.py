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

OPENROUTER_KEYS_STRING = "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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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,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"

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