#!/usr/bin/env python3
# client.py
import sys
import socket
import os
import subprocess
import logging
import logging.handlers
from items import ItemsDB
from pexpect import spawn, TIMEOUT, EOF

OVPN_MGMT_HOST = os.getenv("OVPN_MGMT_HOST", "127.0.0.1")
OVPN_MGMT_PORT = os.getenv("OVPN_MGMT_PORT", "17898")
OVPN_BLOCKLIST = os.getenv("OVPN_BLOCKLIST", "/etc/openvpn/client/blocklist")

# Optional, can be overriden
WG_INT_NAME = os.getenv("WG_INT_NAME", "wg0")
WG_AS_SUDO = bool(os.getenv("WG_AS_SUDO", False))
WG_BIN_PATH = os.getenv("WG_BIN_PATH", "/usr/bin/wg")
WG_QUICK_PATH = os.getenv("WG_BIN_PATH", "/usr/bin/wg-quick")

# LOGGING
BLOCKER_LOG_FILE = os.getenv(
    "BLOCKER_LOG_FILE", "/etc/openvpn/client/blocker/blocker.log"
)
# Root logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # do we need envvar for that?

# Console handler
ch = logging.StreamHandler(sys.stdout)
ch.setLevel(logging.INFO)
ch.setFormatter(
    logging.Formatter(
        "%(asctime)s %(levelname)-5s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
)
logger.addHandler(ch)

# File handler
fh = logging.handlers.RotatingFileHandler(
    BLOCKER_LOG_FILE, maxBytes=10_000_000, backupCount=3, encoding="utf-8"
)
fh.setLevel(logging.DEBUG)
fh.setFormatter(
    logging.Formatter("%(asctime)s %(levelname)-5s %(name)s:%(lineno)d %(message)s")
)
logger.addHandler(fh)

log = logging.getLogger("client")


class WireguardClient:
    WG_PUBKEY_LEN = 44
    WG_EXEC_TIMEOUT = 50.0
    BLOCK_IP = "127.0.0.2"

    def __init__(self, pubkey: str, interface: str = WG_INT_NAME):
        if isinstance(pubkey, str):
            if pubkey[-1] == "=" and len(pubkey) == WireguardClient.WG_PUBKEY_LEN:
                self.pubkey = pubkey
            else:
                raise ValueError(
                    f"Public key should be {WireguardClient.WG_PUBKEY_LEN} symbols long and end with ="
                )
        else:
            raise ValueError("Public key should be a string.")

        self.interface = interface
        log.info("Pubkey: %s  Interface: %s", pubkey, interface)

    def _get_ip(self, sudo: bool = WG_AS_SUDO) -> str | None:
        cmd = [WG_BIN_PATH, "show", self.interface, "dump"]
        if sudo:
            cmd.insert(0, "sudo")

        log.info("Running command: %s", cmd)
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=self.WG_EXEC_TIMEOUT,
            check=False,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                f"{cmd!r} failed (code {proc.returncode}): {proc.stderr.strip()}"
            )
        for line in proc.stdout.splitlines():
            cols = line.split()
            if self.pubkey in cols:
                if len(cols) >= 4:
                    log.info(
                        "Found WG allowedip for client %s: %s", self.pubkey, cols[3]
                    )
                    return cols[3]
                return None
        return None

    def _change_ip(self, new_ip: str, sudo: bool = WG_AS_SUDO) -> str | bool:
        ch_cmd = [
            WG_BIN_PATH,
            "set",
            self.interface,
            "peer",
            self.pubkey,
            "allowed-ips",
            f"{new_ip}/32",
        ]
        save_cmd = [WG_QUICK_PATH, "save", self.interface]
        if sudo:
            ch_cmd.insert(0, "sudo")
            save_cmd.insert(0, "sudo")

        log.info("Running command: %s", ch_cmd)
        ch_int = subprocess.run(
            ch_cmd,
            capture_output=True,
            text=True,
            timeout=self.WG_EXEC_TIMEOUT,
            check=False,
        )

        log.info("Running command: %s", save_cmd)
        save_int = subprocess.run(
            save_cmd,
            capture_output=True,
            text=True,
            timeout=self.WG_EXEC_TIMEOUT,
            check=False,
        )

        if ch_int.returncode != 0:
            raise RuntimeError(
                f"{ch_cmd!r} failed (code {ch_int.returncode}): {ch_int.stderr.strip()}"
            )
        if save_int.returncode != 0:
            raise RuntimeError(
                f"{save_cmd!r} failed (code {save_int.returncode}): {save_int.stderr.strip()}"
            )
        return True

    def block(self) -> bool:
        """
        usage: client.WireguardClient("6cCLfSYbyPcRODrH3yNuxiaqNZ212345YpzB6LAb3nM=").block()
        """
        log.warning("Blocking client %s", self.pubkey)
        return self._change_ip(self.BLOCK_IP)

    def unblock(self, old_ip: str) -> bool:
        """
        usage: client.WireguardClient("6cCLfSYbyPcRODrH3yNuxiaqNZ212345YpzB6LAb3nM=").unblock("10.64.1.7")
        """
        log.warning("Unblocking client %s", self.pubkey)
        return self._change_ip(old_ip)


class OpenVPNClient:
    telnet_creds = OVPN_MGMT_HOST, OVPN_MGMT_PORT
    db = ItemsDB(OVPN_BLOCKLIST)

    def __init__(self, cn):
        if isinstance(cn, str):
            if "=" in cn:
                raise ValueError('CN should only contain name itself, not "CN=" prefix')
            self.cn = cn
        else:
            raise ValueError("CN is not a string!")

    def kill_client(self, cn: str) -> str | None:
        cmd = f"telnet {' '.join(OpenVPNClient.telnet_creds)}"
        log.debug("  Connecting through %s", cmd)
        with spawn(cmd, timeout=5) as p:
            try:
                log.info("  Trying to kill the client %s", cn)
                p.expect(
                    ">INFO:OpenVPN Management",
                    timeout=5,
                )
                p.sendline(f"kill {cn}")
                out = (
                    p.before.decode(errors="replace")
                    if isinstance(p.before, bytes)
                    else p.before
                )
                return out
            except (TIMEOUT, EOF) as exc:
                # partial output is in p.before/p.after
                partial = (
                    p.before.decode(errors="replace")
                    if isinstance(p.before, bytes)
                    else p.before
                )
                raise RuntimeError("interaction failed", exc, partial)

    def block(self) -> bool:
        log.warning("Blocking client with CN %s: ", self.cn)
        try:
            if self.kill_client(self.cn):
                log.info("  Command to kill client %s sent", self.cn)
        except Exception as e:
            log.error(
                """
                This exception happened during OVPN client session killing.
                Cowardly refusing to proceed.
                %r
                """,
                e,
            )
            return False
        try:
            OpenVPNClient.db.add(self.cn)  # idempotent!
            log.warning("  Client %s blocked.", self.cn)
            return True
        except Exception as e:
            log.error(
                """
                This exception happened while adding dead client to blocklist.
                Cowardly refusing to proceed.
                %r
                """,
                e,
            )

    def unblock(self) -> bool:
        log.warning("Unblocking client with CN %s: ", self.cn)
        try:
            if OpenVPNClient.db.remove(self.cn):  # idempotent!
                log.warning("  Client %s unblocked and may connect.", self.cn)
                return True
            else:
                log.info("  Client %s was not in the blocklist.", self.cn)
                return False
        except Exception as e:
            print(
                """
                This exception happened while removing client from blocklist.
                Cowardly refusing to proceed.
                %r
                """,
                e,
            )
            return False
