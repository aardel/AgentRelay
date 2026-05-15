#!/usr/bin/env python3
"""AgentRelay — native desktop app (no browser)."""

from __future__ import annotations

import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from agentrelay import DEFAULT_CONFIG, Config
from config_io import update_settings
from relay_client import (
    SKILL_TARGETS,
    approve_request,
    build_agent_snippet,
    connect_peer,
    fetch_pending,
    fetch_setup,
    install_all_skills,
    install_skill,
    is_skill_installed,
    launch_agent,
    relay_running,
    remove_all_skills,
    remove_skill,
    send_to_peer,
    skill_names,
    start_relay,
    stop_relay,
)


def _project_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
    return Path(__file__).resolve().parent


ROOT = _project_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class AgentRelayApp(tk.Tk):
    def __init__(self, config_path: Path) -> None:
        super().__init__()
        self.config_path = config_path
        self.cfg = Config.load(config_path)
        self.title("AgentRelay")
        self.minsize(420, 480)
        self.geometry("480x600")
        self._apply_style()
        self._build()
        self.after(300, self.refresh)
        self.after(5000, self._tick)
        self.after(500, self._poll_deliveries)

    def _apply_style(self) -> None:
        self.configure(bg="#f5f5f7")
        style = ttk.Style()
        if sys.platform == "win32":
            style.theme_use("vista")
        style.configure("Title.TLabel", font=("Segoe UI", 16, "bold"))
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground="#6e6e73")
        style.configure("Card.TLabelframe", padding=12)
        style.configure("Card.TLabelframe.Label", font=("Segoe UI", 11, "bold"))

    def _build(self) -> None:
        pad = {"padx": 14, "pady": 5}
        top = ttk.Frame(self, padding=14)
        top.pack(fill=tk.X)
        ttk.Label(top, text="AgentRelay", style="Title.TLabel").pack(anchor=tk.W)
        ttk.Label(top, text="Connect your computers so agents can work together",
                  style="Sub.TLabel").pack(anchor=tk.W, pady=(2, 8))

        bar = ttk.Frame(top)
        bar.pack(fill=tk.X)
        self.status_var = tk.StringVar(value="Stopped")
        ttk.Label(bar, textvariable=self.status_var).pack(side=tk.LEFT)
        self.btn_relay = ttk.Button(bar, text="Start", command=self._toggle_relay)
        self.btn_relay.pack(side=tk.RIGHT)

        # This computer
        pc = ttk.LabelFrame(self, text="This computer", style="Card.TLabelframe", padding=10)
        pc.pack(fill=tk.X, **pad)
        row = ttk.Frame(pc)
        row.pack(fill=tk.X)
        ttk.Label(row, text="Name").pack(side=tk.LEFT)
        self.name_var = tk.StringVar(value=self.cfg.node_name)
        ttk.Entry(row, textvariable=self.name_var, width=22).pack(side=tk.RIGHT)
        self.addr_var = tk.StringVar()
        ttk.Label(pc, textvariable=self.addr_var, style="Sub.TLabel").pack(anchor=tk.W, pady=(4, 0))

        # Agents — dropdown + Launch
        ag = ttk.LabelFrame(self, text="Agents on this computer", style="Card.TLabelframe", padding=10)
        ag.pack(fill=tk.X, **pad)
        ag_row = ttk.Frame(ag)
        ag_row.pack(fill=tk.X)
        self._agent_ids: list[str] = []
        self.agent_var = tk.StringVar()
        self.agent_combo = ttk.Combobox(ag_row, textvariable=self.agent_var,
                                        state="readonly", width=30)
        self.agent_combo.pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(ag_row, text="Launch", command=self._on_launch_selected).pack(
            side=tk.RIGHT, padx=(6, 0))

        # Nearby
        nb = ttk.LabelFrame(self, text="Nearby computers", style="Card.TLabelframe", padding=10)
        nb.pack(fill=tk.X, **pad)
        ttk.Button(nb, text="Refresh", command=self.refresh).pack(anchor=tk.E)
        self.nearby_frame = ttk.Frame(nb)
        self.nearby_frame.pack(fill=tk.X)

        # Pending — inserted dynamically before settings
        self.pending_frame = ttk.LabelFrame(
            self, text="⚡ Connection requests", style="Card.TLabelframe")
        self.pending_inner = ttk.Frame(self.pending_frame, padding=8)
        self.pending_inner.pack(fill=tk.X)

        # Settings
        st = ttk.LabelFrame(self, text="Settings", style="Card.TLabelframe", padding=10)
        st.pack(fill=tk.X, **pad)
        self._settings_frame = st
        wr = ttk.Frame(st)
        wr.pack(fill=tk.X)
        ttk.Label(wr, text="Seconds before auto-send").pack(side=tk.LEFT)
        self.wait_var = tk.StringVar(value="5")
        ttk.Spinbox(wr, from_=1, to=60, textvariable=self.wait_var, width=5).pack(side=tk.RIGHT)
        ttk.Button(st, text="Save settings", command=self._save_settings).pack(
            anchor=tk.E, pady=(6, 0))

        # Skills — two dropdowns + Install/Remove
        sk = ttk.LabelFrame(self, text="Skills", style="Card.TLabelframe", padding=10)
        sk.pack(fill=tk.X, **pad)
        sk_row = ttk.Frame(sk)
        sk_row.pack(fill=tk.X)

        ttk.Label(sk_row, text="Skill").pack(side=tk.LEFT)
        _skill_labels = [lbl for _, lbl in skill_names(ROOT)]
        _skill_keys   = [name for name, _ in skill_names(ROOT)]
        self._skill_keys = _skill_keys
        self.skill_var = tk.StringVar(value=_skill_labels[0] if _skill_labels else "")
        self.skill_combo = ttk.Combobox(sk_row, textvariable=self.skill_var,
                                         values=_skill_labels, state="readonly", width=22)
        self.skill_combo.pack(side=tk.LEFT, padx=(4, 12))
        self.skill_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_skill_status())

        ttk.Label(sk_row, text="For").pack(side=tk.LEFT)
        _targets = list(SKILL_TARGETS.keys())
        self.skill_target_var = tk.StringVar(value=_targets[0])
        self.skill_target_combo = ttk.Combobox(sk_row, textvariable=self.skill_target_var,
                                                values=_targets, state="readonly", width=12)
        self.skill_target_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.skill_target_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_skill_status())

        sk_btn_row = ttk.Frame(sk)
        sk_btn_row.pack(fill=tk.X, pady=(6, 0))
        self.skill_status_var = tk.StringVar(value="")
        ttk.Label(sk_btn_row, textvariable=self.skill_status_var,
                  style="Sub.TLabel").pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(sk_btn_row, text="Remove", command=self._remove_selected_skill).pack(
            side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sk_btn_row, text="Install", command=self._install_selected_skill).pack(
            side=tk.RIGHT)

        sk_all_row = ttk.Frame(sk)
        sk_all_row.pack(fill=tk.X, pady=(4, 0))
        ttk.Button(sk_all_row, text="Remove All", command=self._remove_all_skills).pack(
            side=tk.RIGHT, padx=(4, 0))
        ttk.Button(sk_all_row, text="Install All", command=self._install_all_skills).pack(
            side=tk.RIGHT)

        # Prompt — send a message to any peer agent directly from the GUI
        pm = ttk.LabelFrame(self, text="Send a message", style="Card.TLabelframe", padding=10)
        pm.pack(fill=tk.X, **pad)
        pm_top = ttk.Frame(pm)
        pm_top.pack(fill=tk.X)
        ttk.Label(pm_top, text="To").pack(side=tk.LEFT)
        self.prompt_peer_var = tk.StringVar()
        self.prompt_peer_combo = ttk.Combobox(pm_top, textvariable=self.prompt_peer_var,
                                               state="readonly", width=14)
        self.prompt_peer_combo.pack(side=tk.LEFT, padx=(4, 8))
        ttk.Label(pm_top, text="Agent").pack(side=tk.LEFT)
        self.prompt_agent_var = tk.StringVar()
        self.prompt_agent_combo = ttk.Combobox(pm_top, textvariable=self.prompt_agent_var,
                                                state="readonly", width=16)
        self.prompt_agent_combo.pack(side=tk.LEFT, padx=(4, 0))
        self.prompt_peer_combo.bind("<<ComboboxSelected>>", lambda _: self._refresh_prompt_agents())
        self.prompt_text = tk.Text(pm, height=4, wrap=tk.WORD,
                                   font=("Segoe UI", 10))
        self.prompt_text.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(pm, text="Send", command=self._send_prompt).pack(
            anchor=tk.E, pady=(4, 0))

        self._nearby_peers: list[dict] = []

        self.footer = tk.StringVar()
        self._delivery_active = False
        ttk.Label(self, textvariable=self.footer, style="Sub.TLabel", padding=6).pack(fill=tk.X)

        # Populate skill status on first load
        self._refresh_skill_status()

    # ── Relay toggle ──────────────────────────────────────────────────────────

    def _toggle_relay(self) -> None:
        self.btn_relay.configure(state=tk.DISABLED)
        if relay_running(self.cfg):
            stop_relay(self.cfg)
            self.footer.set("Stopped background service")
        else:
            if start_relay(self.config_path):
                self.footer.set("Background service started")
            else:
                messagebox.showerror("AgentRelay", "Could not start the service")
        self.cfg = Config.load(self.config_path)
        self.btn_relay.configure(state=tk.NORMAL)
        self.refresh()

    # ── Settings ──────────────────────────────────────────────────────────────

    def _save_settings(self) -> None:
        try:
            wait = int(self.wait_var.get())
        except ValueError:
            wait = 5
        self.cfg = update_settings(
            path=self.config_path,
            node_name=self.name_var.get().strip() or None,
            wait_before_send_seconds=wait,
        )
        self.footer.set("Settings saved")

    # ── Agents ────────────────────────────────────────────────────────────────

    def _on_launch_selected(self) -> None:
        label = self.agent_var.get()
        if not label or not self._agent_ids:
            return
        labels = list(self.agent_combo["values"])
        try:
            idx = labels.index(label)
            agent_id = self._agent_ids[idx]
        except (ValueError, IndexError):
            return
        self.cfg = Config.load(self.config_path)
        msg = launch_agent(self.cfg, agent_id)
        self.footer.set(msg)

    # ── Skills ────────────────────────────────────────────────────────────────

    def _selected_skill_key(self) -> str | None:
        label = self.skill_var.get()
        labels = list(self.skill_combo["values"])
        try:
            idx = labels.index(label)
            return self._skill_keys[idx]
        except (ValueError, IndexError):
            return None

    def _refresh_skill_status(self) -> None:
        name = self._selected_skill_key()
        target = self.skill_target_var.get()
        if not name:
            self.skill_status_var.set("")
            return
        installed = is_skill_installed(name, target)
        self.skill_status_var.set("✓ Installed" if installed else "Not installed")

    def _install_selected_skill(self) -> None:
        name = self._selected_skill_key()
        target = self.skill_target_var.get()
        if not name:
            return
        msg = install_skill(name, ROOT, target)
        self.footer.set(msg)
        self._refresh_skill_status()

    def _remove_selected_skill(self) -> None:
        name = self._selected_skill_key()
        target = self.skill_target_var.get()
        if not name:
            return
        msg = remove_skill(name, target)
        self.footer.set(msg)
        self._refresh_skill_status()

    def _install_all_skills(self) -> None:
        target = self.skill_target_var.get()
        results = install_all_skills(ROOT, target)
        self.footer.set(f"Installed {len(results)} skills for {target}")
        self._refresh_skill_status()

    def _remove_all_skills(self) -> None:
        target = self.skill_target_var.get()
        results = remove_all_skills(ROOT, target)
        self.footer.set(f"Removed {len(results)} skills from {target}")
        self._refresh_skill_status()

    # ── Prompt window ─────────────────────────────────────────────────────────

    def _refresh_prompt_agents(self) -> None:
        peer_name = self.prompt_peer_var.get()
        peer = next((p for p in self._nearby_peers if p["name"] == peer_name), None)
        agents = peer["_agents_list"] if peer else []
        self.prompt_agent_combo["values"] = agents
        self.prompt_agent_var.set(agents[0] if agents else "")

    def _send_prompt(self) -> None:
        peer_name = self.prompt_peer_var.get()
        agent = self.prompt_agent_var.get() or None
        text = self.prompt_text.get("1.0", tk.END).strip()
        if not peer_name:
            messagebox.showwarning("AgentRelay", "Select a peer first.")
            return
        if not text:
            messagebox.showwarning("AgentRelay", "Enter a message to send.")
            return
        peer = next((p for p in self._nearby_peers if p["name"] == peer_name), None)
        if not peer:
            messagebox.showerror("AgentRelay", f"Peer not found: {peer_name}")
            return
        addr, port = peer["address"], peer["port"]
        self.footer.set(f"Sending to {peer_name}…")
        self.prompt_text.configure(state=tk.DISABLED)

        def _work():
            ok, msg = send_to_peer(self.cfg, addr, port, text, agent)
            def _done():
                self.prompt_text.configure(state=tk.NORMAL)
                if ok:
                    self.prompt_text.delete("1.0", tk.END)
                self.footer.set(
                    f"Sent to {peer_name}" if ok else f"Failed: {msg}"
                )
            self.after(0, _done)

        threading.Thread(target=_work, daemon=True).start()

    # ── GUI delivery (interactive agent window focus + typing) ────────────────

    def _poll_deliveries(self) -> None:
        """Poll the daemon for queued window-delivery items every 500 ms."""
        def _check():
            try:
                from relay_client import _run, _api
                _, data = _run(_api(
                    self.cfg.port, self.cfg.token, "GET", "/pending-deliveries"))
                items = data.get("deliveries") or []
                if items:
                    self.after(0, lambda: self._process_deliveries(items))
            except Exception:
                pass
        threading.Thread(target=_check, daemon=True).start()
        self.after(500, self._poll_deliveries)

    def _process_deliveries(self, items: list) -> None:
        for item in items:
            threading.Thread(target=self._deliver, args=(item,), daemon=True).start()

    def _deliver(self, item: dict) -> None:
        """Focus the target agent window and paste the prompt via ctypes.

        The GUI process holds foreground activation permission, so
        SetForegroundWindow works here even when Chrome Remote Desktop is
        active (where the daemon's pyautogui path would fail).
        """
        if sys.platform != "win32":
            return
        import ctypes
        import ctypes.wintypes
        import subprocess
        import time

        prompt = item["prompt"]
        title_hint = item.get("title_hint", "").lower()
        wait_seconds = item.get("wait_seconds", 5)

        # Save and overwrite clipboard with the prompt
        try:
            import pyperclip
            prev_clip = pyperclip.paste()
            pyperclip.copy(prompt)
        except Exception:
            prev_clip = None

        # Locate target window
        hwnd = None
        if title_hint:
            try:
                import pygetwindow as gw
                matches = [w for w in gw.getAllWindows()
                           if title_hint in w.title.lower()]
                if not matches:
                    # Fall back to any WindowsTerminal window
                    out = subprocess.check_output(
                        ["powershell", "-NoProfile", "-Command",
                         "(Get-Process WindowsTerminal"
                         " -ErrorAction SilentlyContinue).Id"],
                        text=True, timeout=3,
                    ).strip()
                    pids = {int(p) for p in out.splitlines() if p.strip().isdigit()}
                    GetPID = ctypes.windll.user32.GetWindowThreadProcessId
                    for w in gw.getAllWindows():
                        if not w.title:
                            continue
                        pid = ctypes.wintypes.DWORD()
                        GetPID(w._hWnd, ctypes.byref(pid))
                        if pid.value in pids:
                            matches.append(w)
                if matches:
                    hwnd = matches[0]._hWnd
            except Exception:
                pass

        if hwnd:
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            time.sleep(0.4)

        # Ctrl+V to paste
        ke = ctypes.windll.user32.keybd_event
        VK_CONTROL, VK_V, KEYEVENTF_KEYUP = 0x11, 0x56, 0x0002
        ke(VK_CONTROL, 0, 0, 0)
        ke(VK_V, 0, 0, 0)
        ke(VK_V, 0, KEYEVENTF_KEYUP, 0)
        ke(VK_CONTROL, 0, KEYEVENTF_KEYUP, 0)

        # Wait, then press Enter to submit
        time.sleep(max(1, wait_seconds))
        VK_RETURN = 0x0D
        ke(VK_RETURN, 0, 0, 0)
        ke(VK_RETURN, 0, KEYEVENTF_KEYUP, 0)

        # Restore clipboard
        if prev_clip is not None:
            time.sleep(0.3)
            try:
                pyperclip.copy(prev_clip)
            except Exception:
                pass

        label = title_hint or "window"
        self.after(0, lambda: self.footer.set(f"Delivered to '{label}' via GUI"))

    # ── Peers ─────────────────────────────────────────────────────────────────

    def _on_connect(self, peer: str) -> None:
        self.footer.set(
            f"Waiting for {peer} to accept… "
            f"Open AgentRelay on {peer} and click Allow."
        )
        self.update_idletasks()

        def _work():
            ok, msg = connect_peer(self.cfg, self.config_path, peer)
            self.after(0, lambda: self._on_connect_done(ok, msg, peer))

        threading.Thread(target=_work, daemon=True).start()

    def _on_connect_done(self, ok: bool, msg: str, peer: str) -> None:
        self.cfg = Config.load(self.config_path)
        self.footer.set(msg)
        if not ok:
            messagebox.showwarning("AgentRelay", msg)
        self.refresh()

    def _on_reject(self, request_id: str) -> None:
        from relay_client import _run, _api
        _run(_api(self.cfg.port, self.cfg.token, "POST", "/pair/reject",
                  {"request_id": request_id}))
        self.refresh()

    def _on_approve(self, rid: str, peer: str) -> None:
        approve_request(self.cfg, self.config_path, rid, peer)
        self.cfg = Config.load(self.config_path)
        self.footer.set(f"Allowed {peer}")
        self.refresh()

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        self.cfg = Config.load(self.config_path)
        data = fetch_setup(self.cfg, self.config_path)
        running = data.get("relay_running", False)
        self.status_var.set("Running" if running else "Stopped")
        self.btn_relay.configure(text="Stop" if running else "Start")
        self.name_var.set(data.get("node", self.cfg.node_name))
        addr = data.get("address") or ""
        self.addr_var.set(f"On your network at {addr}" if addr else "")
        self.wait_var.set(str(data.get("wait_before_send_seconds", 5)))

        # Populate agent dropdown
        agents = data.get("agents") or []
        self._agent_ids = [a["id"] for a in agents]
        labels = [a.get("label", a["id"]) for a in agents]
        self.agent_combo["values"] = labels
        if labels and not self.agent_var.get():
            self.agent_combo.current(0)

        # Nearby computers
        for w in self.nearby_frame.winfo_children():
            w.destroy()
        nearby = data.get("nearby") or []

        # Store for prompt window lookups; keep agents as a list
        self._nearby_peers = []
        for p in nearby:
            agents_raw = p.get("agents", "")
            if isinstance(agents_raw, list):
                agents_list = agents_raw
            else:
                agents_list = [a.strip() for a in str(agents_raw).split(",") if a.strip()]
            self._nearby_peers.append({**p, "_agents_list": agents_list})

        connected_names = [p["name"] for p in nearby if p.get("connected")]
        prev_peer = self.prompt_peer_var.get()
        self.prompt_peer_combo["values"] = connected_names
        if prev_peer not in connected_names:
            self.prompt_peer_var.set(connected_names[0] if connected_names else "")
            self._refresh_prompt_agents()

        if not nearby:
            ttk.Label(
                self.nearby_frame,
                text="No other computers found. Start AgentRelay on them too.",
            ).pack(anchor=tk.W)
        for p in nearby:
            row = ttk.Frame(self.nearby_frame)
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=p["name"]).pack(side=tk.LEFT)
            if p.get("connected"):
                ttk.Label(row, text="Connected", foreground="#248a3d").pack(side=tk.RIGHT)
            else:
                ttk.Button(
                    row, text="Connect",
                    command=lambda n=p["name"]: self._on_connect(n),
                ).pack(side=tk.RIGHT)

        # Pending connection requests
        pending = fetch_pending(self.cfg)
        if pending:
            self.pending_frame.pack(fill=tk.X, padx=14, pady=6,
                                    before=self._settings_frame)
            for w in self.pending_inner.winfo_children():
                w.destroy()
            for p in pending:
                row = ttk.Frame(self.pending_inner)
                row.pack(fill=tk.X, pady=4)
                ttk.Label(
                    row,
                    text=f"{p['from_node']} wants to connect",
                    font=("Segoe UI", 10, "bold"),
                ).pack(side=tk.LEFT)
                ttk.Button(
                    row, text="Allow",
                    command=lambda i=p["id"], n=p["from_node"]: self._on_approve(i, n),
                ).pack(side=tk.RIGHT, padx=(8, 0))
                ttk.Button(
                    row, text="Reject",
                    command=lambda i=p["id"]: self._on_reject(i),
                ).pack(side=tk.RIGHT)
        else:
            self.pending_frame.pack_forget()

        self._refresh_skill_status()

    def _tick(self) -> None:
        self.refresh()
        self.after(5000, self._tick)


def _run_daemon(config_path: Path) -> None:
    import asyncio
    from agentrelay import Config, amain
    cfg = Config.load(config_path)
    asyncio.run(amain(cfg))


def main() -> None:
    i = sys.argv.index("--config") if "--config" in sys.argv else -1
    config_path = Path(sys.argv[i + 1]) if i >= 0 else DEFAULT_CONFIG

    if "--relay-daemon" in sys.argv:
        _run_daemon(config_path)
        return
    if not config_path.exists():
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "AgentRelay",
                "No settings found.\nRun install once, or: agentrelay --init",
            )
        except tk.TclError:
            print("No settings found. Run: agentrelay --init", file=sys.stderr)
        sys.exit(1)
    app = AgentRelayApp(config_path)
    app.mainloop()


if __name__ == "__main__":
    main()
