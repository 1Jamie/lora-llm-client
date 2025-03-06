#!/usr/bin/env python3
import os
import sys
import socket
import time
import logging
import argparse
from datetime import datetime

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class TCPConnectionTester:
    def __init__(self, host, port, max_retries=4, initial_retry_delay=1):
        self.host = host
        self.port = port
        self.max_retries = max_retries
        self.initial_retry_delay = initial_retry_delay
        self.socket = None
        self.connected = False
        
    def connect(self):
        """Attempt to connect to the TCP server with retry logic"""
        retry_count = 0
        retry_delay = self.initial_retry_delay
        
        while retry_count < self.max_retries:
            try:
                if retry_count > 0:
                    logger.info(f"Retry attempt {retry_count} after {retry_delay}s delay...")
                    
                logger.info(f"Attempting to connect to {self.host}:{self.port}")
                self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.socket.settimeout(10)  # 10 second timeout
                self.socket.connect((self.host, self.port))
                self.connected = True
                logger.info(f"Successfully connected to {self.host}:{self.port}")
                return True
                
            except (socket.timeout, ConnectionRefusedError, OSError) as e:
                logger.error(f"Connection attempt failed: {str(e)}")
                if self.socket:
                    self.socket.close()
                    self.socket = None
                
                retry_count += 1
                if retry_count >= self.max_retries:
                    logger.error(f"Maximum retry attempts ({self.max_retries}) reached. Giving up.")
                    return False
                
                # Exponential backoff
                retry_delay *= 2
                time.sleep(retry_delay)
        
        return False
    
    def send_message(self, message):
        """Send a test message through the TCP connection"""
        if not self.connected or not self.socket:
            logger.error("Not connected. Cannot send message.")
            return False
            
        try:
            logger.info(f"Sending test message: {message}")
            self.socket.sendall(message.encode('utf-8'))
            logger.info("Message sent successfully")
            
            # Try to receive a response
            logger.info("Waiting for response...")
            self.socket.settimeout(5)
            response = self.socket.recv(4096)
            logger.info(f"Received response: {response.decode('utf-8', errors='ignore')}")
            return True
            
        except Exception as e:
            logger.error(f"Error sending/receiving message: {str(e)}")
            return False
    
    def test_reconnection(self, num_tests=3, delay_between_tests=2):
        """Test multiple connect-disconnect cycles"""
        logger.info(f"Starting reconnection test with {num_tests} cycles")
        
        for i in range(num_tests):
            logger.info(f"Test cycle {i+1}/{num_tests}")
            
            # Connect
            if not self.connect():
                logger.error(f"Failed to connect in test cycle {i+1}")
                return False
                
            # Wait a bit
            time.sleep(delay_between_tests)
            
            # Disconnect
            if self.socket:
                logger.info("Closing connection")
                self.socket.close()
                self.socket = None
                self.connected = False
            
            # Wait a bit before next cycle
            time.sleep(delay_between_tests)
        
        logger.info("Reconnection test completed successfully")
        return True
    
    def close(self):
        """Close the TCP connection"""
        if self.socket:
            logger.info("Closing connection")
            self.socket.close()
            self.socket = None
            self.connected = False

def main():
    parser = argparse.ArgumentParser(description="Test TCP connection reliability")
    parser.add_argument("--host", type=str, required=True, help="TCP server host")
    parser.add_argument("--port", type=int, required=True, help="TCP server port")
    parser.add_argument("--max-retries", type=int, default=4, help="Maximum retry attempts")
    parser.add_argument("--message", type=str, default="TEST_MESSAGE", help="Test message to send")
    parser.add_argument("--test-reconnection", action="store_true", help="Test multiple reconnections")
    parser.add_argument("--num-reconnects", type=int, default=3, help="Number of reconnection tests")
    
    args = parser.parse_args()
    
    tester = TCPConnectionTester(
        host=args.host,
        port=args.port,
        max_retries=args.max_retries,
        initial_retry_delay=1
    )
    
    try:
        if args.test_reconnection:
            logger.info("Running reconnection test...")
            result = tester.test_reconnection(num_tests=args.num_reconnects)
            if result:
                logger.info("Reconnection test PASSED")
            else:
                logger.error("Reconnection test FAILED")
        else:
            logger.info("Running basic connection test...")
            if tester.connect():
                logger.info("Connection test PASSED")
                
                if args.message:
                    if tester.send_message(args.message):
                        logger.info("Message test PASSED")
                    else:
                        logger.error("Message test FAILED")
            else:
                logger.error("Connection test FAILED")
                
    except KeyboardInterrupt:
        logger.info("Test terminated by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        tester.close()

if __name__ == "__main__":
    main()
