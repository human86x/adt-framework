import os
import sys
import socket
import select
import logging
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

# SPEC-045: Browser-to-socket bridge service
# Runs as adt_human, proxies TCP 5001 -> /run/adt/panel.sock
# Physically blocks agents (adt_agent) from direct socket access.

logging.basicConfig(level=logging.INFO, format='%(asctime)s [BRIDGE] %(levelname)s: %(message)s')
logger = logging.getLogger(__name__)

# Default paths for production
ADC_UNIX_SOCKET = os.environ.get("ADC_UNIX_SOCKET", "/run/adt/panel.sock")
LISTEN_HOST = "127.0.0.1"
LISTEN_PORT = int(os.environ.get("ADC_BRIDGE_PORT", 5001))

class PanelBridgeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.proxy_request("GET")

    def do_POST(self):
        self.proxy_request("POST")

    def do_PUT(self):
        self.proxy_request("PUT")

    def do_DELETE(self):
        self.proxy_request("DELETE")

    def do_PATCH(self):
        self.proxy_request("PATCH")

    def do_OPTIONS(self):
        # Handle CORS preflight
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "tauri://localhost")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, PATCH, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Agent")
        self.send_header("Access-Control-Allow-Credentials", "true")
        self.end_headers()

    def proxy_request(self, method):
        """Proxies the request to the Unix socket."""
        if not os.path.exists(ADC_UNIX_SOCKET):
            logger.error(f"Unix socket not found: {ADC_UNIX_SOCKET}")
            self.send_error(503, "Operational Center offline (socket missing)")
            return

        try:
            # Connect to Unix socket
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(ADC_UNIX_SOCKET)
            
            # Reconstruct request line
            path = self.path
            request_line = f"{method} {path} HTTP/1.1\r\n"
            sock.sendall(request_line.encode())
            
            # Send headers
            for key, val in self.headers.items():
                header_line = f"{key}: {val}\r\n"
                sock.sendall(header_line.encode())
            
            sock.sendall(b"\r\n")
            
            # Send body if present
            content_length = self.headers.get('Content-Length')
            if content_length:
                body = self.rfile.read(int(content_length))
                sock.sendall(body)
                
            # Receive response headers from Unix socket
            sock.setblocking(0)
            response_data = b""
            header_end = -1
            while True:
                ready = select.select([sock], [], [], 90.0)
                if ready[0]:
                    chunk = sock.recv(4096)
                    if not chunk:
                        break
                    response_data += chunk
                    header_end = response_data.find(b"\r\n\r\n")
                    if header_end != -1:
                        break
                else:
                    break
            
            # Send response back to browser
            if header_end != -1:
                headers_part = response_data[:header_end].decode('utf-8', errors='ignore')
                body_part = response_data[header_end+4:]
                
                lines = headers_part.split("\r\n")
                if not lines[0]:
                     self.send_error(502, "Bad Gateway (Invalid response from socket)")
                     sock.close()
                     return
                     
                status_line = lines[0].split(" ", 2)
                if len(status_line) < 2:
                     self.send_error(502, "Bad Gateway (Invalid status line from socket)")
                     sock.close()
                     return
                     
                status_code = int(status_line[1])
                
                # Check headers to see if it is SSE
                is_sse = False
                headers_to_send = []
                for line in lines[1:]:
                    if ": " in line:
                        k, v = line.split(": ", 1)
                        if k.lower() not in ["connection", "access-control-allow-origin", "access-control-allow-credentials"]:
                            headers_to_send.append((k, v))
                        if k.lower() == "content-type" and "text/event-stream" in v.lower():
                            is_sse = True
                
                self.send_response(status_code)
                for k, v in headers_to_send:
                    self.send_header(k, v)
                
                # Ensure CORS
                self.send_header("Access-Control-Allow-Origin", "tauri://localhost")
                self.send_header("Access-Control-Allow-Credentials", "true")
                self.end_headers()
                self.wfile.flush()
                
                if body_part:
                    self.wfile.write(body_part)
                    self.wfile.flush()
                
                sock.setblocking(0)
                try:
                    while True:
                        # Use None for timeout if SSE to avoid timing out on read, otherwise 45s
                        timeout = None if is_sse else 45.0
                        ready = select.select([sock], [], [], timeout)
                        if ready[0]:
                            chunk = sock.recv(4096)
                            if not chunk:
                                break
                            self.wfile.write(chunk)
                            self.wfile.flush()
                        else:
                            break
                except Exception as stream_err:
                    logger.warning(f"Stream closed or error: {stream_err}")
                
                sock.close()
            else:
                self.send_error(502, "Bad Gateway (Empty or malformed response from socket)")
                sock.close()
        except Exception as e:
            logger.exception(f"Bridge error: {e}")
            self.send_error(502, f"Bridge error: {str(e)}")

def run_bridge():
    logger.info(f"Starting Panel Bridge: http://{LISTEN_HOST}:{LISTEN_PORT} -> {ADC_UNIX_SOCKET}")
    httpd = ThreadingHTTPServer((LISTEN_HOST, LISTEN_PORT), PanelBridgeHandler)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    httpd.server_close()

if __name__ == "__main__":
    run_bridge()
