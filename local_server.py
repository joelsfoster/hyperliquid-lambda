#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local server for testing TradingView webhooks with ngrok

This server simulates the AWS Lambda environment by receiving webhooks,
processing them through the lambda_function handler, and returning responses.
"""

from http.server import BaseHTTPRequestHandler, HTTPServer
import json
import logging
import os
import time
import requests
import threading
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Import the lambda handler
from src.lambda_function import lambda_handler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
)
logger = logging.getLogger('hyperliquid-webhook-server')

class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        try:
            # Get content length from headers
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            
            # Log the received data
            logger.info(f"Received webhook: {post_data.decode('utf-8')}")
            
            # Create a mock Lambda event
            event = {
                "body": post_data.decode('utf-8'),
                "requestContext": {
                    "identity": {
                        "sourceIp": self.client_address[0]
                    }
                }
            }
            
            # Log source IP for debugging
            logger.info(f"Source IP: {self.client_address[0]}")
            
            # Process with Lambda handler
            result = lambda_handler(event, None)
            
            # Log the result
            logger.info(f"Response: {result.get('body', '{}')}")
            
            # Send response
            self.send_response(result.get('statusCode', 200))
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(result.get('body', '{}').encode('utf-8'))
            
        except Exception as e:
            # Log and return any errors
            logger.error(f"Error processing webhook: {str(e)}")
            self.send_response(500)
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({"status": "error", "message": str(e)}).encode('utf-8'))

def get_ngrok_url():
    """
    Get the public ngrok URL by querying the ngrok API
    """
    max_attempts = 10
    attempts = 0
    
    while attempts < max_attempts:
        try:
            response = requests.get("http://127.0.0.1:4040/api/tunnels")
            if response.status_code == 200:
                tunnels = response.json()["tunnels"]
                if tunnels:
                    for tunnel in tunnels:
                        if tunnel["proto"] == "https":
                            return tunnel["public_url"]
                    # If no HTTPS tunnel found, return the first one
                    return tunnels[0]["public_url"]
            
            logger.info("Waiting for ngrok to start...")
            attempts += 1
            time.sleep(2)
        except Exception as e:
            logger.warning(f"Error getting ngrok URL: {str(e)}")
            attempts += 1
            time.sleep(2)
    
    return None

def monitor_ngrok():
    """
    Monitor for ngrok URL and print it when available
    """
    time.sleep(2)  # Give server a moment to start
    ngrok_url = get_ngrok_url()
    
    if ngrok_url:
        logger.info("=" * 70)
        logger.info(f"NGROK URL: {ngrok_url}")
        logger.info("Use this URL in your TradingView webhook configuration")
        logger.info("=" * 70)
    else:
        logger.warning("Could not detect ngrok URL. Make sure ngrok is running with: ngrok http 80")
        logger.warning("If ngrok is already running, you can find your URL in the ngrok console")

def run(server_class=HTTPServer, handler_class=WebhookHandler, port=80):
    """
    Run the webhook server on the specified port
    """
    server_address = ('', port)
    
    try:
        httpd = server_class(server_address, handler_class)
        logger.info(f'Starting webhook server on port {port}...')
        logger.info(f'Make sure ngrok is running with: ngrok http {port}')
        
        # Start a thread to monitor ngrok and print the URL
        ngrok_thread = threading.Thread(target=monitor_ngrok)
        ngrok_thread.daemon = True
        ngrok_thread.start()
        
        logger.info(f'Set up TradingView webhooks to point to your ngrok URL (will be displayed when available)')
        logger.info(f'Make sure to set WEBHOOK_PASSWORD in your .env file')
        httpd.serve_forever()
    except PermissionError:
        logger.error(f"Permission denied: Cannot use port {port}. Try running with sudo or use a port > 1024.")
        logger.info("Alternatively, you can run: sudo python local_server.py")
        exit(1)
    except OSError as e:
        if e.errno == 48:  # Address already in use
            logger.error(f"Port {port} is already in use. Try a different port.")
        else:
            logger.error(f"Error starting server: {str(e)}")
        exit(1)

if __name__ == '__main__':
    run()
