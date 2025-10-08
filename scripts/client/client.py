#!/usr/bin/env python3
import sys
import socket
import items import ItemsDB

OVPN_MGMT_HOST = "127.0.0.1"
OVPN_MGMT_PORT = "11528"
LISTFILE = "/opt/scripts/client/blocklist"


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

    def block(self) -> bool:
        print(f"Blocking client with CN {self.cn}")
        try:
            with socket.create_connection(telnet_creds, timeout=5) as s:
                s.sendall((f"kill {self.cn}" + "\r\n").encode())

            print(f"Command to kill client {self.cn} sent")
        except Exception as e:
            print(
                """
                This exception happened during OVPN client session killing.
                Cowardly refusing to proceed.
                """
            )
            print(e)

        try:
            Client.db.add(self.cn)  # idempotent!
            print(f"Client {self.cn} blocked.")
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
        print(f"Unblocking client with CN {self.cn}")
        try:
            if Client.db.remove(self.cn):  # idempotent!
                print(f"Client {self.cn} unblocked and may connect.")
                return True
            else:
                print(f"Client {self.cn} was not in the blocklist.")
                return False
        except Exception as e:
            print(
                """
                This exception happened while removing client from blocklist.
                Cowardly refusing to proceed.
                """
            )
            print(e)
