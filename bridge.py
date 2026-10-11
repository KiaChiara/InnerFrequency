#!/usr/bin/env python3
"""
Inner Frequency — bridge between the browser page and SuperCollider.

  browser  --WebSocket-->  bridge.py  --OSC-->  SuperCollider (MRT2)
  browser  <--WebSocket--  bridge.py  <--OSC--  SuperCollider (beats, level)

It also serves the page: open http://localhost:8000

Dependencies:  installed by install_mrt2.sh in ~/magenta-realtime/.venv
Start:         ~/magenta-realtime/.venv/bin/python bridge.py
"""
import argparse
import asyncio
import functools
import http.server
import json
import pathlib
import threading
import webbrowser

from pythonosc.dispatcher import Dispatcher
from pythonosc.osc_server import AsyncIOOSCUDPServer
from pythonosc.udp_client import SimpleUDPClient
from websockets.asyncio.server import broadcast, serve

HERE = pathlib.Path(__file__).resolve().parent
clients = set()


class QuietPage(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def end_headers(self):
        # never let the browser keep an old copy of the page
        self.send_header("Cache-Control", "no-store, must-revalidate")
        self.send_header("Pragma", "no-cache")
        self.send_header("Expires", "0")
        super().end_headers()


def start_http(port):
    server = http.server.ThreadingHTTPServer(("0.0.0.0", port), functools.partial(QuietPage, directory=str(HERE)))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def to_osc(v):
    """JSON -> OSC types: ints stay ints, the rest float or string."""
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float, str)):
        return v
    return str(v)


async def main():
    ap = argparse.ArgumentParser(description="WebSocket <-> OSC bridge for Inner Frequency")
    ap.add_argument("--http", type=int, default=8000, help="page port (default 8000)")
    ap.add_argument("--ws", type=int, default=8765, help="WebSocket port (default 8765)")
    ap.add_argument("--sc-host", default="127.0.0.1", help="SuperCollider address (default 127.0.0.1)")
    ap.add_argument("--sc-port", type=int, default=57120, help="sclang port (default 57120)")
    ap.add_argument("--osc-in", type=int, default=57200, help="port for messages coming from SuperCollider")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--verbose", action="store_true", help="print every message")
    args = ap.parse_args()

    sc = SimpleUDPClient(args.sc_host, args.sc_port)

    # --- from SuperCollider to the browser ---
    def from_sc(addr, *values):
        msg = json.dumps({"addr": addr, "args": list(values)})
        if args.verbose and addr != "/if/level":
            print("SC ->", msg)
        broadcast(clients, msg)

    disp = Dispatcher()
    disp.map("/if/*", from_sc)
    osc_server = AsyncIOOSCUDPServer(("127.0.0.1", args.osc_in), disp, asyncio.get_running_loop())
    transport, _ = await osc_server.create_serve_endpoint()

    # --- from the browser to SuperCollider ---
    async def handler(ws):
        clients.add(ws)
        print(f"Page connected ({len(clients)} open)")
        try:
            async for raw in ws:
                try:
                    m = json.loads(raw)
                    addr = m["addr"]
                    values = [to_osc(v) for v in m.get("args", [])]
                except (ValueError, KeyError, TypeError):
                    continue
                if not isinstance(addr, str) or not addr.startswith("/if/"):
                    continue
                if args.verbose and addr not in ("/if/noteon", "/if/noteoff"):
                    print("-> SC", addr, values)
                sc.send_message(addr, values)
        finally:
            clients.discard(ws)
            print(f"Page disconnected ({len(clients)} open)")

    start_http(args.http)
    url = f"http://localhost:{args.http}/"
    async with serve(handler, "0.0.0.0", args.ws):
        print(f"Page:          {url}")
        print(f"WebSocket:     ws://localhost:{args.ws}")
        print(f"OSC to SC:     {args.sc_host}:{args.sc_port}")
        print(f"OSC from SC:   127.0.0.1:{args.osc_in}")
        print("Ctrl+C to quit.")
        if not args.no_browser:
            webbrowser.open(url)
        try:
            await asyncio.Future()
        finally:
            transport.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
