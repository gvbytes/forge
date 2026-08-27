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
            # Simple### File: solution.py