#!/bin/bash
# may redo in Python later

LOGFILE="${OVPN_VERIFY_LOG:-/opt/scripts/client/tls_verify.log}"
BLOCKLIST="${OVPN_BLOCKLIST:-/opt/scripts/client/blocklist}"

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
