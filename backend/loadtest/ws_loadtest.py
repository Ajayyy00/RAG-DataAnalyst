"""WebSocket load probe for the realtime analytics socket.

Locust's HTTP user doesn't cover WebSockets, so this standalone asyncio script
opens N concurrent authenticated WS connections and measures connect success +
message throughput. Run after obtaining an access token cookie/value.

Usage:
    python loadtest/ws_loadtest.py --connections 500 --duration 60 \
        --url ws://localhost:8001/api/v1/ws/analytics --token <ACCESS_JWT>
"""

import argparse
import asyncio
import time

import websockets


async def _one(url: str, token: str, deadline: float, stats: dict):
    full = f"{url}?token={token}"
    try:
        async with websockets.connect(full, open_timeout=10) as ws:
            stats["connected"] += 1
            while time.monotonic() < deadline:
                try:
                    await asyncio.wait_for(ws.recv(), timeout=5)
                    stats["messages"] += 1
                except asyncio.TimeoutError:
                    pass
    except Exception:
        stats["failed"] += 1


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://localhost:8001/api/v1/ws/analytics")
    ap.add_argument("--token", required=True)
    ap.add_argument("--connections", type=int, default=100)
    ap.add_argument("--duration", type=int, default=60)
    args = ap.parse_args()

    stats = {"connected": 0, "failed": 0, "messages": 0}
    deadline = time.monotonic() + args.duration
    await asyncio.gather(
        *[_one(args.url, args.token, deadline, stats) for _ in range(args.connections)]
    )
    print(
        f"connections={args.connections} connected={stats['connected']} "
        f"failed={stats['failed']} messages={stats['messages']}"
    )


if __name__ == "__main__":
    asyncio.run(main())
