#!/bin/bash

LOGFILE="${OVPN_TLS_LOGFILE:-/etc/openvpn/tls_verify.log}"
BLOCKLIST="${OVPN_TLS_BLOCKLIST:-/etc/openvpn/blocklist}"

if [ "$1" = "0" ]; then
   CLIENT=$(echo "$2" | cut -c 4-)
   echo "Checking client $CLIENT." >> "$LOGFILE"

   if grep -xFq -- "$CLIENT" "$BLOCKLIST"; then
       echo "$CLIENT is blocked; refusing to connect them." >> "$LOGFILE"
       exit 1
   fi
   echo "Allowing client $CLIENT to connect." >> "$LOGFILE"
fi
exit 0
