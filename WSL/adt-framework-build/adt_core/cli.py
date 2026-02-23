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
from datetime import datetime
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
                'ts': datetime.utcnow().isoformat() + 'Z',
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

def main():
    parser = argparse.ArgumentParser(prog='adt', description='ADT Framework CLI')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # connect group
    connect_parser = subparsers.add_parser('connect', help='Manage remote access')
    connect_sub = connect_parser.add_subparsers(dest='subcommand', help='Connect subcommands')
    
    share_parser = connect_sub.add_parser('share', help='Expose local instance to the internet')
    share_parser.add_argument('--port', type=int, default=5000, help='Local port to expose (default: 5000)')
    share_parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmation prompts')
    
    args = parser.parse_args()

    if args.command == 'connect':
        if args.subcommand == 'share':
            share_command(args)
        else:
            connect_parser.print_help()
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
