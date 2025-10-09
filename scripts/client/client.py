#!/usr/bin/env python3
import sys
import socket
import os
from items import ItemsDB
from pexpect import spawn, TIMEOUT, EOF

OVPN_MGMT_HOST = os.getenv("OVPN_MGMT_HOST", "127.0.0.1")
OVPN_MGMT_PORT = os.getenv("OVPN_MGMT_PORT", "11528")
LISTFILE = os.getenv("OVPN_BLOCKLIST", "/tmp/scripts/client/blocklist")


class Client:
    telnet_creds = OVPN_MGMT_HOST, OVPN_MGMT_PORT
    db = ItemsDB(LISTFILE)

    def __init__(self, cn):
        if isinstance(cn, str):
            if "=" in cn:
                raise ValueError('CN should only contain name itself, not "CN=" prefix')
            self.cn = cn
        else:
            raise ValueError("CN is not a string!")

    def kill_client(self, cn: str) -> str | None:
        cmd = f"telnet {' '.join(Client.telnet_creds)}"
        print("  Connecting through " + cmd)
        with spawn(cmd, timeout=5) as p:
            try:
                print(f"  Trying to kill the client {cn}")
                p.expect(
                    ">INFO:OpenVPN Management Interface Version 1 -- type 'help' for more info",
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
        print(f"Blocking client with CN {self.cn}: ")
        try:
            if self.kill_client(self.cn):
                print(f"  Command to kill client {self.cn} sent")
        except Exception as e:
            print(
                """
                This exception happened during OVPN client session killing.
                Cowardly refusing to proceed.
                """
            )
            print(e)
            return False
        try:
            Client.db.add(self.cn)  # idempotent!
            print(f"  Client {self.cn} blocked.")
            return True
        except Exception as e:
            print(
                """
                This exception happened while adding dead client to blocklist.
                Cowardly refusing to proceed.
                """
            )
            print(e)

    def unblock(self) -> bool:
        print(f"Unblocking client with CN {self.cn}: ")
        try:
            if Client.db.remove(self.cn):  # idempotent!
                print(f"  Client {self.cn} unblocked and may connect.")
                return True
            else:
                print(f"  Client {self.cn} was not in the blocklist.")
                return False
        except Exception as e:
            print(
                """
                This exception happened while removing client from blocklist.
                Cowardly refusing to proceed.
                """
            )
            print(e)
            return False
