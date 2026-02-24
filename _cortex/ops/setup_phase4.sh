#!/bin/bash
# ADT Framework Phase 4 Setup Script: Permission Switch
# This script must be run as ROOT by the human.
# References: SPEC-014, SPEC-015

set -e

PROJECT_ROOT="/home/human/Projects/adt-framework"
ADT_PORT=5001
DTTP_PORT=5002

# 1. Check for root
if [ "$EUID" -ne 0 ]; then
  echo "Please run as root"
  exit 1
fi

echo "--- ADT Framework Phase 4 Setup Started ---"

# 2. Create users
echo "Creating system users: agent, dttp..."
id -u agent &>/dev/null || useradd -r -m -s /bin/bash agent
id -u dttp &>/dev/null || useradd -r -m -s /bin/bash dttp

# 3. Project ownership and permissions
echo "Setting project ownership to dttp:dttp..."
chown -R dttp:dttp "$PROJECT_ROOT"
chmod -R u+rwX,g+rX,o+rX "$PROJECT_ROOT"

# Ensure _cortex/ads/ is writable by dttp
chmod -R 775 "$PROJECT_ROOT/_cortex/ads"

# 4. Credential isolation
echo "Setting up /etc/dttp/..."
mkdir -p /etc/dttp
if [ ! -f /etc/dttp/secrets.json ]; then
  echo '{"ssh": {}, "ftp": {}}' > /etc/dttp/secrets.json
fi
chown dttp:dttp /etc/dttp/secrets.json
chmod 600 /etc/dttp/secrets.json

# 5. Sudo configuration
echo "Configuring sudo for agent user..."
echo "agent ALL=(dttp) NOPASSWD: $PROJECT_ROOT/venv/bin/python3 $PROJECT_ROOT/adt_sdk/hooks/dttp_request.py" > /etc/sudoers.d/adt-dttp
# Also allow starting services (optional, maybe human only)
# echo "human ALL=(dttp) NOPASSWD: /usr/bin/systemctl restart adt-dttp" >> /etc/sudoers.d/adt-dttp

# 6. Network restrictions
echo "Applying iptables rules for agent user..."
# Block SSH (22)
iptables -A OUTPUT -m owner --uid-owner agent -p tcp --dport 22 -j DROP
# Block FTP (21)
iptables -A OUTPUT -m owner --uid-owner agent -p tcp --dport 21 -j DROP
# Block standard HTTP/HTTPS (optional, maybe allow for AI APIs)
# iptables -A OUTPUT -m owner --uid-owner agent -p tcp --dport 80 -j DROP
# iptables -A OUTPUT -m owner --uid-owner agent -p tcp --dport 443 -j DROP

# Save iptables rules if iptables-persistent is installed
if command -v netfilter-persistent &> /dev/null; then
  netfilter-persistent save
fi

echo "--- Phase 4 Setup Complete ---"
echo "Next steps for Human:"
echo "1. Populate /etc/dttp/secrets.json with real credentials."
echo "2. Redact credentials from any world-readable project files."
echo "3. Restart DTTP and Operational Center as 'dttp' user."
echo "4. Launch AI tools as 'agent' user: sudo -u agent <tool>"
