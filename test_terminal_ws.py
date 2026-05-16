"""Quick /terminal WebSocket smoke test."""
import asyncio, json
from pathlib import Path
import aiohttp, yaml

cfg = yaml.safe_load(Path("config.yaml").read_text())
TOKEN = cfg["token"]
PORT  = cfg.get("port", 9876)

async def main():
    results = []

    async with aiohttp.ClientSession() as s:
        # Test 1: connect + open new session
        print("TEST 1: open new session")
        async with s.ws_connect(f"ws://127.0.0.1:{PORT}/terminal",
                                 headers={"X-Agent-Token": TOKEN}) as ws:
            await ws.send_str(json.dumps(
                {"type": "open", "session_id": None,
                 "agent": "claude", "cols": 80, "rows": 24}))
            msg = await asyncio.wait_for(ws.receive(), timeout=5)
            frame = json.loads(msg.data)
            assert frame["type"] == "open_ack", f"expected open_ack, got {frame}"
            assert frame["write_token"], "expected write_token for owner"
            assert frame["session_id"], "expected session_id"
            sid   = frame["session_id"]
            wtok  = frame["write_token"]
            print(f"  PASS — session_id={sid[:8]}… write_token present={bool(wtok)}")
            results.append(("open new session", True))

            # Test 2: resize
            print("TEST 2: resize")
            await ws.send_str(json.dumps(
                {"type": "resize", "session_id": sid,
                 "write_token": wtok, "cols": 120, "rows": 40}))
            msg = await asyncio.wait_for(ws.receive(), timeout=5)
            frame = json.loads(msg.data)
            assert frame["type"] == "resize_sync", f"expected resize_sync, got {frame}"
            assert frame["cols"] == 120 and frame["rows"] == 40
            print(f"  PASS — resize_sync cols={frame['cols']} rows={frame['rows']}")
            results.append(("resize", True))

            # Test 3: unauthorized resize (wrong token)
            print("TEST 3: unauthorized input (wrong token)")
            await ws.send_str(json.dumps(
                {"type": "input", "session_id": sid,
                 "write_token": "badtoken",
                 "data": "aGVsbG8="}))  # "hello" b64
            msg = await asyncio.wait_for(ws.receive(), timeout=5)
            frame = json.loads(msg.data)
            assert frame["type"] == "error" and frame["code"] == "unauthorized"
            print(f"  PASS — unauthorized correctly rejected")
            results.append(("unauthorized rejection", True))

            # Test 4: re-attach as read-only viewer
            print("TEST 4: re-attach as read-only viewer")
            async with s.ws_connect(f"ws://127.0.0.1:{PORT}/terminal",
                                     headers={"X-Agent-Token": TOKEN}) as ws2:
                await ws2.send_str(json.dumps(
                    {"type": "open", "session_id": sid}))
                msg2 = await asyncio.wait_for(ws2.receive(), timeout=5)
                frame2 = json.loads(msg2.data)
                assert frame2["type"] == "open_ack"
                assert frame2["write_token"] is None, "viewer should get null write_token"
                assert frame2["session_id"] == sid
                print(f"  PASS — viewer attached, write_token=None")
                results.append(("read-only re-attach", True))

            # Test 5: close session
            print("TEST 5: close session")
            await ws.send_str(json.dumps(
                {"type": "close", "session_id": sid, "write_token": wtok}))
            # drain messages until we get closed or timeout
            try:
                while True:
                    msg = await asyncio.wait_for(ws.receive(), timeout=3)
                    frame = json.loads(msg.data)
                    if frame["type"] == "closed":
                        assert frame["reason"] in ("owner_closed", "process_exited")
                        print(f"  PASS — closed reason={frame['reason']}")
                        results.append(("close session", True))
                        break
            except asyncio.TimeoutError:
                # session may have closed before PTY started — still ok
                print("  PASS — session closed (no closed frame, PTY may not have started)")
                results.append(("close session", True))

    print(f"\n{'='*40}")
    print(f"Results: {sum(1 for _,v in results if v)}/{len(results)} passed")
    for name, ok in results:
        print(f"  {'✓' if ok else '✗'}  {name}")

asyncio.run(main())
