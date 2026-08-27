"""
Backend server for a simple web application.
This server handles requests and serves a frontend HTML file.
"""
import http.server
import socketserver
import webbrowser
import threading
import os

PORT = 8000

class SimpleAppHandler(http.server.SimpleHTTPRequestHandler):
    """Custom handler to manage web requests."""
    def do_GET(self):
        if self.path == '/':
            # Serve the frontend.html file when the root is accessed
            self.path = '/frontend.html'
            return http.server.SimpleHTTPRequestHandler.do_GET(self)
        
        if self.path == '/api/greet':
            # Simple API endpoint that returns a greeting
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            response = '{"message": "Hello from the Python Backend!"}'
            self.wfile.write(response.encode('utf-8'))
            return

        return http.server.SimpleHTTPRequestHandler.do_GET(self)

def create_frontend():
    """Creates a basic frontend.html file if it doesn't exist."""
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Simple Web App</title>
        <style>
            body { font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0; background-color: #f0f2f5; }
            .card { background: white; padding: 2rem; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); text-align: center; }
            button { padding: 10px 20px; font-size: 16px; cursor: pointer; background-color: #007bff; color: white; border: none; border-radius: 5px; }
            button:hover { background-color: #0056b3; }
            #response { margin-top: 20px; font-weight: bold; color: #333; }
        </style>
    </head>
    <body>
        <The new files provide a minimal web app that calculates factorials via a Python backend.

### File: frontend.html