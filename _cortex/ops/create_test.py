import os

test_content = r'''import os
import subprocess
import time
import socket
import threading
import pytest
import shutil
from pathlib import Path

def is_bwrap_available():
    return shutil.which('bwrap') is not None

@pytest.mark.skipif(not is_bwrap_available(), reason='bubblewrap not installed')
class TestNamespaceIsolation:
    def test_network_bridge_to_host(self, tmp_path):
        host_port = 5002
        received_data = []
        def host_server():
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                s.bind(('127.0.0.1', host_port))
                s.listen(1)
                s.settimeout(10)
                try:
                    conn, addr = s.accept()
                    with conn:
                        data = conn.recv(1024)
                        received_data.append(data.decode())
                        conn.sendall(b'HTTP/1.1 200 OK\r\n\r\nHello from Host')
                except socket.timeout:
                    pass
        server_thread = threading.Thread(target=host_server)
        server_thread.start()
        time.sleep(0.5)
        project_root = tmp_path / 'project'
        project_root.mkdir()
        dttp_sock_in_project = project_root / 'dttp.sock'
        host_socat = subprocess.Popen([
            'socat', 
            f'UNIX-LISTEN:{dttp_sock_in_project},fork,reuseaddr', 
            f'TCP:127.0.0.1:{host_port}'
        ])
        time.sleep(0.5)
        try:
            inner_socat_cmd = f'socat TCP-LISTEN:{host_port},fork,reuseaddr,bind=127.0.0.1 UNIX-CONNECT:/project/dttp.sock'
            agent_cmd = 'curl -s http://localhost:5002'
            wrapper_script = f'{inner_socat_cmd} & sleep 1; {agent_cmd}'
            bwrap_cmd = [
                'bwrap', '--unshare-net',
                '--ro-bind', '/usr', '/usr',
                '--ro-bind', '/lib', '/lib',
                '--ro-bind', '/bin', '/bin',
                '--ro-bind', '/etc', '/etc',
                '--bind', str(project_root), '/project',
                '--tmpfs', '/tmp', '--proc', '/proc', '--dev', '/dev',
                '--chdir', '/project',
                '--', '/bin/sh', '-c', wrapper_script
            ]
            result = subprocess.run(bwrap_cmd, capture_output=True, text=True, timeout=15)
            assert 'Hello from Host' in result.stdout
            assert len(received_data) > 0
        finally:
            host_socat.terminate()
            server_thread.join(timeout=1)

    def test_no_external_network(self, tmp_path):
        bwrap_cmd = [
            'bwrap', '--unshare-net',
            '--ro-bind', '/usr', '/usr',
            '--ro-bind', '/lib', '/lib',
            '--ro-bind', '/bin', '/bin',
            '--', 'curl', '-s', '--connect-timeout', '2', 'http://google.com'
        ]
        result = subprocess.run(bwrap_cmd, capture_output=True, text=True)
        assert result.returncode != 0

    def test_filesystem_isolation(self, tmp_path):
        secret_file = tmp_path / 'secret.txt'
        secret_file.write_text('TOP_SECRET')
        project_root = tmp_path / 'project'
        project_root.mkdir()
        bwrap_cmd = [
            'bwrap',
            '--ro-bind', '/usr', '/usr',
            '--ro-bind', '/lib', '/lib',
            '--ro-bind', '/bin', '/bin',
            '--bind', str(project_root), '/project',
            '--chdir', '/project',
            '--', 'cat', str(secret_file)
        ]
        result = subprocess.run(bwrap_cmd, capture_output=True, text=True)
        assert 'No such file or directory' in result.stderr
'''

with open('tests/test_namespace_isolation.py', 'w') as f:
    f.write(test_content)
print('Created tests/test_namespace_isolation.py')