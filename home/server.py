"""
Simple HTTP server that serves a static frontend and provides a factorial API.
"""

import http.server
import socketserver
import urllib.parse
import json

class FactorialHandler(http.server.SimpleHTTPRequestHandler):
    """Handles GET requests for the factorial endpoint and serves static files."""
    def do_GET(self):
        parsed_path = urllib.parse.urlparse(self.path)
        if parsed_path.path == '/factorial':
            query = urllib.parse.parse_qs(parsed_path.query)
            try:
                num = int(query.get('num', [0])[0])
                if num < 0:
                    raise ValueError
            except (ValueError, TypeError):
                self.send_response(400)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Invalid number'}).encode())
                return

            result = 1
            for i in range(2, num + 1):
                result *= i

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'result': result}).encode())
        else:
            super().do_GET()

def run_server(port=8000):
    handler = FactorialHandler
    with socketserver.TCPServer(("", port), handler) as httpd:
        print(f"Serving at http://localhost:{port}")
        httpd.serve_forever()

if __name__ == "__main__":
    run_server()