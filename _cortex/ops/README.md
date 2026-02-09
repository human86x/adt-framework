# ADT Framework Operations (DevOps)

This directory contains deployment and operational artifacts for the ADT Framework.

## Phase 4: Permission Switch

To activate Level 3 privilege separation (SPEC-014), the human must:

1.  Run `sudo bash setup_phase4.sh`. This creates `agent` and `dttp` users, sets project permissions, and configures `iptables`.
2.  Populate `/etc/dttp/secrets.json` with SSH/FTP credentials.
3.  Install systemd services:
    ```bash
    sudo cp adt-dttp.service /etc/systemd/system/
    sudo cp adt-center.service /etc/systemd/system/
    sudo systemctl daemon-reload
    sudo systemctl enable --now adt-dttp
    sudo systemctl enable --now adt-center
    ```

## Agent Usage

After Phase 4, agents should be launched as the `agent` user:
```bash
sudo -u agent claude
# or
sudo -u agent gemini
```

Agents can ONLY write to the project via the DTTP hook:
```bash
sudo -u dttp venv/bin/python3 adt_sdk/hooks/dttp_request.py --action edit --file ...
```

Note: The `sudo -u dttp` is allowed for the `agent` user without password for the specific hook script (configured in `/etc/sudoers.d/adt-dttp`).

## Monitoring

- DTTP Log: `journalctl -u adt-dttp -f`
- ADT Center Log: `journalctl -u adt-center -f`
- ADS Timeline: Visit `http://localhost:5001/ads`
