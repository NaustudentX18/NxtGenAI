#!/usr/bin/env python3
# =============================================================================
# PentestGPT-lite — Pentest Tool Runner
# =============================================================================
# MIT License — Copyright (c) 2026 DINA OKTARIANA
#
# Wraps external pentest binaries (nmap, hydra, aireplay-ng, sqlmap, arp-scan)
# as Python-callable functions that return structured result dicts.
#
# Design principles:
#   - Every tool call is subprocess-based (no raw os.system) for safety
#   - Timeout on every call — tools can never block indefinitely
#   - Tool unavailable → voice alert "Tool down—skipping", log to report
#   - Output is truncated to 4000 chars before being returned/logged
#   - No internet required — all tools are local binaries
#
# Tool → binary mapping:
#   nmap_scan   → nmap (installed by setup.sh)
#   wifi_crack  → airmon-ng, airodump-ng, aireplay-ng, aircrack-ng
#   web_pentest → sqlmap (installed by setup.sh)
#   arp_spoof   → arpspoof (dsniff) or python Scapy fallback
#   sqlmap_scan → sqlmap
#   hydra_brute → hydra
# =============================================================================

import configparser
import logging
import os
import subprocess
import tempfile
import time
from typing import Callable, List, Optional

log = logging.getLogger(__name__)

# Maximum bytes read from subprocess stdout/stderr
MAX_OUTPUT_BYTES = 4096

# Default subprocess timeout (seconds) per tool call
DEFAULT_TIMEOUT = 120


# =============================================================================
# Helper: run a subprocess with timeout + output capture
# =============================================================================
def _run(
    cmd: list,
    timeout: int = DEFAULT_TIMEOUT,
    status_cb: Optional[Callable[[str], None]] = None,
    env: Optional[dict] = None,
) -> tuple[int, str]:
    """
    Run `cmd` as a subprocess. Returns (returncode, stdout+stderr combined).
    Streams output in 1 KB chunks so OLED status can update live.
    Never raises — returns (-1, error_message) on any exception.
    """
    log.info("Running: %s", " ".join(cmd))
    if status_cb:
        status_cb(" ".join(cmd[:3]))

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            env=env or os.environ.copy(),
            text=True,
            bufsize=1,  # Line buffered
        )
        output_parts: list[str] = []
        start = time.monotonic()

        for line in proc.stdout:  # type: ignore[union-attr]
            output_parts.append(line)
            # Collect up to MAX_OUTPUT_BYTES then discard further output
            if sum(len(p) for p in output_parts) >= MAX_OUTPUT_BYTES:
                output_parts.append("...[output truncated]...")
                proc.stdout.read()  # Drain remaining
                break
            # Check wall-clock timeout
            if time.monotonic() - start > timeout:
                proc.kill()
                output_parts.append(f"\n[TIMEOUT after {timeout}s]")
                break
            # Live status callback (every ~10 lines)
            if status_cb and len(output_parts) % 10 == 0:
                status_cb(line.strip()[:20])

        proc.wait(timeout=5)
        return proc.returncode, "".join(output_parts)

    except FileNotFoundError:
        msg = f"Binary not found: {cmd[0]}"
        log.error(msg)
        return -1, msg
    except subprocess.TimeoutExpired:
        msg = f"Timeout after {timeout}s"
        log.warning(msg)
        return -1, msg
    except Exception as exc:
        log.error("Subprocess error (%s): %s", " ".join(cmd), exc)
        return -1, str(exc)


def _tool_result(tool: str, cmd: list, rc: int, output: str,
                 risk: int = 3) -> dict:
    """
    Build a standardised result dict for inclusion in reports.
    """
    return {
        "tool":    tool,
        "command": " ".join(cmd),
        "rc":      rc,
        "output":  output[:4000],
        "risk":    risk,
        "success": rc == 0,
    }


# =============================================================================
# ToolRunner class
# =============================================================================
class ToolRunner:
    """
    Pentest tool executor.
    Each public method corresponds to one AI action (see ai_core.py tool_map).
    """

    def __init__(self, cfg: configparser.ConfigParser):
        self.cfg      = cfg
        self.wordlist = cfg.get("paths", "rockyou",   fallback="/home/pi/wordlists/rockyou.txt")
        self.common   = cfg.get("paths", "common10k", fallback="/home/pi/wordlists/10k-common.txt")
        self.iface    = cfg.get("wifi",  "interface", fallback="wlan0")
        self.reports  = cfg.get("paths", "reports",   fallback="/home/pi/reports/")

    # ── Network Recon (nmap) ─────────────────────────────────────────────────
    def network_recon(
        self,
        target: str = "192.168.1.0/24",
        status_cb: Optional[Callable] = None,
    ) -> List[dict]:
        """
        ARP discovery → nmap SYN scan on discovered hosts.
        Risk: 3 (passive / read-only on own network).

        nmap flags used:
          -sn   : Ping sweep (host discovery, no port scan)
          -sS   : SYN scan (half-open, stealthy — requires root)
          -T3   : Timing template (normal — avoids detection)
          --open: Only show open ports
          -oX - : XML output to stdout (parseable)
        """
        results: list[dict] = []

        # 1. Ping sweep to find live hosts
        ping_cmd = ["nmap", "-sn", "--host-timeout", "10s", target]
        rc, out  = _run(ping_cmd, timeout=60, status_cb=status_cb)
        results.append(_tool_result("nmap_ping", ping_cmd, rc, out, risk=2))

        if rc != 0:
            log.warning("nmap ping sweep failed — skipping port scan.")
            return results

        # 2. Full SYN scan on discovered subnet
        scan_cmd = ["nmap", "-sS", "-T3", "--open", "-p", "22,80,443,8080,3306",
                    "--host-timeout", "30s", target]
        rc2, out2 = _run(scan_cmd, timeout=90, status_cb=status_cb)
        results.append(_tool_result("nmap_syn", scan_cmd, rc2, out2, risk=3))

        return results

    # ── WiFi Crack (aircrack-ng suite) ───────────────────────────────────────
    def wifi_crack(
        self,
        iface: Optional[str] = None,
        capture_timeout: int = 60,
        wordlist: Optional[str] = None,
        status_cb: Optional[Callable] = None,
    ) -> List[dict]:
        """
        WPA2 handshake capture + dictionary crack.
        Risk: 7 (requires monitor mode; active deauth frame).

        Steps:
          1. Enable monitor mode (airmon-ng start wlan0)
          2. Scan for access points (airodump-ng --output-format cap)
          3. Targeted capture on highest-signal AP
          4. Deauth client to force handshake (aireplay-ng -0)
          5. Crack .cap file with aircrack-ng + wordlist

        NOTE: Deauth (step 4) briefly disconnects clients. Only use on
        your own network. Risk score 7 means AI will confirm before running.
        """
        results: list[dict] = []
        iface    = iface or self.iface
        wordlist = wordlist or self.wordlist

        # Temporary directory for .cap files
        with tempfile.TemporaryDirectory() as tmpdir:
            cap_prefix = os.path.join(tmpdir, "handshake")

            # Step 1: Start monitor mode
            mon_cmd = ["airmon-ng", "start", iface]
            rc, out = _run(mon_cmd, timeout=15, status_cb=status_cb)
            results.append(_tool_result("airmon-ng_start", mon_cmd, rc, out, risk=5))
            mon_iface = f"{iface}mon"  # Typically appended with "mon"

            if rc != 0:
                log.error("airmon-ng failed — aborting WiFi crack.")
                return results

            # Step 2: Capture beacon frames (scan)
            dump_cmd = [
                "airodump-ng", "--output-format", "cap",
                "--write", cap_prefix,
                "--write-interval", "1",
                mon_iface,
            ]
            # airodump-ng runs until killed — cap at capture_timeout
            rc2, out2 = _run(dump_cmd, timeout=capture_timeout,
                             status_cb=status_cb)
            results.append(_tool_result("airodump-ng", dump_cmd, rc2, out2, risk=4))

            # Step 3: Deauth (1 packet burst — forces handshake)
            deauth_cmd = ["aireplay-ng", "-0", "1", "-a", "FF:FF:FF:FF:FF:FF",
                          mon_iface]
            rc3, out3 = _run(deauth_cmd, timeout=10, status_cb=status_cb)
            results.append(_tool_result("aireplay-ng_deauth", deauth_cmd,
                                        rc3, out3, risk=7))

            # Step 4: Crack captured .cap with aircrack-ng
            cap_files = [
                f for f in os.listdir(tmpdir)
                if f.endswith(".cap") and os.path.getsize(os.path.join(tmpdir, f)) > 0
            ]
            if cap_files and os.path.exists(wordlist):
                cap_path = os.path.join(tmpdir, cap_files[0])
                crack_cmd = ["aircrack-ng", "-w", wordlist, cap_path]
                rc4, out4 = _run(crack_cmd, timeout=300, status_cb=status_cb)
                results.append(_tool_result("aircrack-ng", crack_cmd,
                                            rc4, out4, risk=6))
            else:
                log.warning("No .cap file captured or wordlist missing.")
                results.append({
                    "tool":    "aircrack-ng",
                    "command": "skipped",
                    "output":  "No capture file or wordlist not found.",
                    "risk":    6, "success": False,
                })

            # Step 5: Restore managed mode
            stop_cmd = ["airmon-ng", "stop", mon_iface]
            _run(stop_cmd, timeout=10)

        return results

    # ── Web Pentest (sqlmap + header analysis) ────────────────────────────────
    def web_pentest(
        self,
        target: str = "http://127.0.0.1",
        status_cb: Optional[Callable] = None,
    ) -> List[dict]:
        """
        Automated web application security assessment.
        Risk: 5 (active requests to target — may trigger WAF/IDS).

        Tools:
          - curl: fetch headers (server, X-Frame-Options, CSP, etc.)
          - sqlmap: SQL injection detection (--level 1, read-only)
          - dirb / custom wordlist: directory enumeration (optional)
        """
        results: list[dict] = []

        # 1. Header grab with curl
        hdr_cmd = ["curl", "-s", "-I", "--max-time", "10", target]
        rc, out = _run(hdr_cmd, timeout=15, status_cb=status_cb)
        results.append(_tool_result("curl_headers", hdr_cmd, rc, out, risk=2))

        # 2. sqlmap (read-only, level 1, no forms — just URL parameters)
        # NOTE: --batch skips all interactive prompts (required for headless)
        sql_cmd = [
            "sqlmap", "--url", target,
            "--level", "1", "--risk", "1",
            "--batch", "--smart",
            "--output-dir", self.reports,
        ]
        rc2, out2 = _run(sql_cmd, timeout=120, status_cb=status_cb)
        results.append(_tool_result("sqlmap", sql_cmd, rc2, out2, risk=5))

        return results

    # ── ARP Spoofing ──────────────────────────────────────────────────────────
    def arp_spoof(
        self,
        target_ip: str = "192.168.1.1",
        gateway_ip: str = "192.168.1.254",
        duration: int = 10,
        status_cb: Optional[Callable] = None,
    ) -> List[dict]:
        """
        ARP cache poisoning (MitM position setup).
        Risk: 8 — disruptive, requires IP forwarding enabled.

        Requires: arpspoof (dsniff) or python-scapy.
        Only runs if risk threshold allows (max_risk_score >= 8).

        WARNING: This will interrupt network traffic for `duration` seconds.
        Only use on your own network with explicit permission.
        """
        results: list[dict] = []

        # Enable IP forwarding (required for MitM — doesn't drop packets)
        fwd_cmd = ["sh", "-c", "echo 1 > /proc/sys/net/ipv4/ip_forward"]
        rc, out = _run(fwd_cmd, timeout=5)
        results.append(_tool_result("ip_forward", fwd_cmd, rc, out, risk=4))

        # Run arpspoof bidirectionally (target → gateway + gateway → target)
        spoof_cmd = [
            "timeout", str(duration),
            "arpspoof", "-i", self.iface,
            "-t", target_ip, gateway_ip,
        ]
        rc2, out2 = _run(spoof_cmd, timeout=duration + 5, status_cb=status_cb)
        results.append(_tool_result("arpspoof", spoof_cmd, rc2, out2, risk=8))

        # Disable IP forwarding after capture
        stop_fwd = ["sh", "-c", "echo 0 > /proc/sys/net/ipv4/ip_forward"]
        _run(stop_fwd, timeout=5)

        return results

    # ── sqlmap (standalone — called by AI directly) ───────────────────────────
    def sqlmap_scan(
        self,
        target: str = "http://127.0.0.1",
        level: int = 1,
        status_cb: Optional[Callable] = None,
    ) -> List[dict]:
        """
        sqlmap SQL injection test.
        Risk: 5 (active — sends payloads to target).
        """
        sql_cmd = [
            "sqlmap", "--url", target,
            "--level", str(max(1, min(5, level))),
            "--risk", "1",
            "--batch", "--smart",
            "--output-dir", self.reports,
        ]
        rc, out = _run(sql_cmd, timeout=120, status_cb=status_cb)
        return [_tool_result("sqlmap", sql_cmd, rc, out, risk=5)]

    # ── Hydra brute force ─────────────────────────────────────────────────────
    def hydra_brute(
        self,
        target: str = "192.168.1.1",
        service: str = "ssh",
        username: str = "admin",
        wordlist: Optional[str] = None,
        status_cb: Optional[Callable] = None,
    ) -> List[dict]:
        """
        Dictionary brute-force via Hydra.
        Risk: 6 (active login attempts — will appear in target logs).

        Supported services: ssh, ftp, http-get, http-post-form, smb, telnet
        """
        wordlist = wordlist or self.common  # Prefer 10k list for speed

        if not os.path.exists(wordlist):
            return [{
                "tool":    "hydra",
                "command": "skipped",
                "output":  f"Wordlist not found: {wordlist}",
                "risk":    6, "success": False,
            }]

        hyd_cmd = [
            "hydra",
            "-l", username,
            "-P", wordlist,
            "-t", "4",            # 4 parallel tasks (gentle — Pi CPU)
            "-f",                  # Stop after first valid password
            f"{target}", service,
        ]
        rc, out = _run(hyd_cmd, timeout=180, status_cb=status_cb)
        return [_tool_result("hydra", hyd_cmd, rc, out, risk=6)]
