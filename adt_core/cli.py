import argparse
import os
import subprocess
import sys
import platform
import shutil
import requests
import json
import time
import re
from datetime import datetime, timezone
from adt_sdk.client import ADTClient

def get_cloudflared_url():
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    base_url = 'https://github.com/cloudflare/cloudflared/releases/latest/download/'
    
    if system == 'linux':
        if 'arm' in machine or 'aarch' in machine:
            return base_url + 'cloudflared-linux-arm64'
        return base_url + 'cloudflared-linux-amd64'
    elif system == 'darwin':
        if 'arm' in machine or 'aarch' in machine:
            return base_url + 'cloudflared-darwin-arm64.tgz'
        return base_url + 'cloudflared-darwin-amd64.tgz'
    elif system == 'windows':
        return base_url + 'cloudflared-windows-amd64.exe'
    
    return None

def download_cloudflared(dest_path):
    url = get_cloudflared_url()
    if not url:
        print(f'Unsupported platform: {platform.system()} {platform.machine()}')
        return False
    
    print(f'Downloading cloudflared from {url}...')
    try:
        response = requests.get(url, stream=True)
        response.raise_for_status()
        with open(dest_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)
        
        if platform.system() != 'Windows':
            os.chmod(dest_path, 0o755)
        return True
    except Exception as e:
        print(f'Download failed: {e}')
        return False

def share_command(args):
    # 1. Check dependency
    cloudflared_bin = shutil.which('cloudflared')
    if not cloudflared_bin:
        home_bin = os.path.expanduser('~/.adt/bin')
        os.makedirs(home_bin, exist_ok=True)
        ext = '.exe' if platform.system() == 'Windows' else ''
        cloudflared_bin = os.path.join(home_bin, 'cloudflared' + ext)
        
        if not os.path.exists(cloudflared_bin):
            print('cloudflared not found in PATH.')
            if not args.yes:
                try:
                    confirm = input('Download it to ~/.adt/bin? [y/N] ')
                    if confirm.lower() != 'y':
                        print('Aborted.')
                        return
                except EOFError:
                    print('Non-interactive mode. Use --yes to auto-download.')
                    return
            if not download_cloudflared(cloudflared_bin):
                return
    
    # 2. Start Tunnel
    port = args.port
    print(f'Exposing http://localhost:{port} via Cloudflare Tunnel...')
    
    process = subprocess.Popen(
        [cloudflared_bin, 'tunnel', '--url', f'http://localhost:{port}'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    url = None
    try:
        start_time = time.time()
        while time.time() - start_time < 30:
            line = process.stderr.readline()
            if not line:
                break
            match = re.search(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com', line)
            if match:
                url = match.group(0)
                break
        
        if url:
            print('\n' + '='*60)
            print(f'REMOTE ACCESS ACTIVE')
            print(f'Public URL: {url}')
            print('='*60 + '\n')
            print('Requests are being forwarded to your local instance.')
            print('Press Ctrl+C to stop sharing.')
            
            client = ADTClient(agent_name=os.environ.get('ADT_AGENT', 'CLI'), 
                               role=os.environ.get('ADT_ROLE', 'user'))
            client.log_event({
                'event_id': f'evt_{int(time.time())}_connect_share',
                'ts': datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
                'agent': os.environ.get('ADT_AGENT', 'CLI'),
                'role': os.environ.get('ADT_ROLE', 'user'),
                'action_type': 'connect_share',
                'description': f'Started remote access tunnel: {url}',
                'spec_ref': 'SPEC-024',
                'authorized': True,
                'tier': 3
            })
            process.wait()
        else:
            print('Failed to capture tunnel URL. Is cloudflared working?')
            process.terminate()
            
    except KeyboardInterrupt:
        print('\nStopping tunnel...')
        process.terminate()
    except Exception as e:
        print(f'Error: {e}')
        process.terminate()

def shatterglass_command(args):
    PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    ADS_PATH = os.path.join(PROJECT_ROOT, "_cortex", "ads", "events.jsonl")
    
    from adt_core.ads.logger import ADSLogger
    from adt_core.ads.schema import ADSEventSchema
    logger = ADSLogger(ADS_PATH)

    sovereign_paths = [
        "config/specs.json",
        "config/jurisdictions.json",
        "config/dttp.json",
        "_cortex/AI_PROTOCOL.md",
        "_cortex/MASTER_PLAN.md"
    ]
    
    if args.subcommand == 'activate':
        print("\n" + "!" * 60)
        print("WARNING: SHATTERGLASS PROTOCOL ACTIVATION")
        print("This will temporarily grant write access to sovereign files.")
        print("!" * 60 + "\n")
        
        try:
            confirm = input('Type SHATTERGLASS to confirm: ')
            if confirm != 'SHATTERGLASS':
                print('Aborted.')
                return
        except EOFError:
            print('Aborted (non-interactive).')
            return

        reason = args.reason or "No reason provided."
        print(f'Activating Shatterglass for {args.timeout} minutes...')
        
        # chmod sovereign files
        modified_files = []
        for p in sovereign_paths:
            full_path = os.path.join(PROJECT_ROOT, p)
            if os.path.exists(full_path):
                try:
                    os.chmod(full_path, 0o664)
                    modified_files.append(p)
                except Exception as e:
                    print(f'Failed to chmod {p}: {e}')

        session_id = f"sg_{int(time.time())}"
        
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("sg_act"),
            agent="HUMAN",
            role="Collaborator",
            action_type="shatterglass_activated",
            description=f"Shatterglass Protocol activated. Reason: {reason}",
            spec_ref="SPEC-027",
            authorized=True,
            tier=1,
            action_data={
                "session_id": session_id,
                "timeout_minutes": args.timeout,
                "modified_files": modified_files
            }
        )
        logger.log(event)
        print(f'Shatterglass active. Session: {session_id}')
        
        # Start watchdog (simplified: background process that sleeps and then deactivates)
        # In a real system, this would be a more robust service.
        if platform.system() != 'Windows':
            subprocess.Popen(
                [sys.executable, __file__, 'shatterglass', 'deactivate', '--auto', '--session', session_id, '--delay', str(args.timeout * 60)],
                start_new_session=True
            )
            print(f'Watchdog timer started ({args.timeout}m).')

    elif args.subcommand == 'deactivate':
        is_auto = args.auto
        session_id = args.session or "unknown"
        
        if args.delay:
            time.sleep(float(args.delay))

        # Restore permissions
        for p in sovereign_paths:
            full_path = os.path.join(PROJECT_ROOT, p)
            if os.path.exists(full_path):
                try:
                    os.chmod(full_path, 0o644)
                except:
                    pass

        event_type = "shatterglass_auto_expired" if is_auto else "shatterglass_deactivated"
        description = "Shatterglass window auto-expired." if is_auto else "Shatterglass Protocol deactivated by human."
        
        event = ADSEventSchema.create_event(
            event_id=ADSEventSchema.generate_id("sg_deact"),
            agent="SYSTEM" if is_auto else "HUMAN",
            role="Sentry" if is_auto else "Collaborator",
            action_type=event_type,
            description=description,
            spec_ref="SPEC-027",
            authorized=True,
            tier=1,
            action_data={"session_id": session_id}
        )
        logger.log(event)
        print(f'Shatterglass deactivated. Event: {event_type}')

def main():
    parser = argparse.ArgumentParser(prog='adt', description='ADT Framework CLI')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # connect group
    connect_parser = subparsers.add_parser('connect', help='Manage remote access')
    connect_sub = connect_parser.add_subparsers(dest='subcommand', help='Connect subcommands')
    
    share_parser = connect_sub.add_parser('share', help='Expose local instance to the internet')
    share_parser.add_argument('--port', type=int, default=5000, help='Local port to expose (default: 5000)')
    share_parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompts')
    
    # shatterglass group
    sg_parser = subparsers.add_parser('shatterglass', help='Emergency privilege escalation')
    sg_sub = sg_parser.add_subparsers(dest='subcommand', help='Shatterglass subcommands')
    
    act_parser = sg_sub.add_parser('activate', help='Activate shatterglass protocol')
    act_parser.add_argument('--reason', '-r', help='Reason for activation')
    act_parser.add_argument('--timeout', '-t', type=int, default=15, help='Timeout in minutes (default: 15)')
    
    deact_parser = sg_sub.add_parser('deactivate', help='Deactivate shatterglass protocol')
    deact_parser.add_argument('--auto', action='store_true', help=argparse.SUPPRESS)
    deact_parser.add_argument('--session', help=argparse.SUPPRESS)
    deact_parser.add_argument('--delay', help=argparse.SUPPRESS)

    args = parser.parse_args()

    if args.command == 'connect':
        if args.subcommand == 'share':
            share_command(args)
        else:
            connect_parser.print_help()
    elif args.command == 'shatterglass':
        shatterglass_command(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
