#!/usr/bin/env python3
"""
Test MQTT messaging for Meshtastic
This script sends and receives messages over MQTT to test Meshtastic communication.
"""

import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
import paho.mqtt.client as mqtt

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MQTTMessageTester:
    def __init__(self, host, port, username=None, password=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.nodes = {}
        self.connected = False
        
    def connect(self):
        """Connect to the MQTT broker"""
        try:
            # Create MQTT client
            client_id = f"meshtastic_test_{int(time.time())}"
            self.client = mqtt.Client(client_id=client_id)
            
            # Set callbacks
            self.client.on_connect = self._on_connect
            self.client.on_message = self._on_message
            self.client.on_disconnect = self._on_disconnect
            
            # Set authentication if provided
            if self.username and self.password:
                logger.info(f"Using authentication with username: {self.username}")
                self.client.username_pw_set(self.username, self.password)
            
            # Connect to broker
            logger.info(f"Connecting to MQTT broker at {self.host}:{self.port}")
            self.client.connect(self.host, self.port, keepalive=60)
            
            # Start loop in a non-blocking way
            self.client.loop_start()
            
            # Wait for connection to establish
            start_time = time.time()
            while not self.connected and (time.time() - start_time) < 5:
                time.sleep(0.1)
                
            if not self.connected:
                logger.error("Failed to connect to MQTT broker")
                return False
                
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to MQTT broker: {str(e)}")
            return False
            
    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker"""
        if rc == 0:
            self.connected = True
            logger.info("Connected to MQTT broker successfully")
            
            # Subscribe to all Meshtastic messages
            logger.info("Subscribing to Meshtastic topics")
            self.client.subscribe("msh/#")
        else:
            logger.error(f"Failed to connect to MQTT broker with result code {rc}")
            self.connected = False
            
    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker"""
        self.connected = False
        if rc != 0:
            logger.warning(f"Unexpected disconnection from MQTT broker, code: {rc}")
        else:
            logger.info("Disconnected from MQTT broker")
            
    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received from the broker"""
        try:
            topic = msg.topic
            logger.info(f"Received message on topic: {topic}")
            
            # Try to parse as JSON
            try:
                payload = json.loads(msg.payload.decode())
                logger.info(f"JSON payload: {json.dumps(payload, indent=2)}")
                
                # Extract node information if available
                if "id" in payload and "from" in payload:
                    node_id = payload["from"]
                    if node_id not in self.nodes:
                        self.nodes[node_id] = {
                            "last_seen": datetime.now(),
                            "messages": 1
                        }
                    else:
                        self.nodes[node_id]["last_seen"] = datetime.now()
                        self.nodes[node_id]["messages"] += 1
                        
            except json.JSONDecodeError:
                # Not JSON, just print the raw payload
                raw_payload = msg.payload.decode()
                logger.info(f"Raw payload: {raw_payload}")
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            
    def send_broadcast_message(self, message):
        """Send a broadcast message to all nodes"""
        if not self.connected or not self.client:
            logger.error("Not connected to MQTT broker")
            return False
            
        try:
            # Topic format for broadcast text messages
            topic = "msh/b/t"
            
            logger.info(f"Sending broadcast message: {message}")
            result = self.client.publish(topic, message, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("Broadcast message sent successfully")
                return True
            else:
                logger.error(f"Failed to send broadcast message: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending broadcast message: {str(e)}")
            return False
            
    def send_direct_message(self, node_id, message):
        """Send a direct message to a specific node"""
        if not self.connected or not self.client:
            logger.error("Not connected to MQTT broker")
            return False
            
        try:
            # Make sure node_id starts with !
            if not node_id.startswith("!"):
                node_id = f"!{node_id}"
                
            # Topic format for direct messages: msh/d/<node_id>/t
            topic = f"msh/d/{node_id}/t"
            
            logger.info(f"Sending direct message to {node_id}: {message}")
            result = self.client.publish(topic, message, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("Direct message sent successfully")
                return True
            else:
                logger.error(f"Failed to send direct message: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending direct message: {str(e)}")
            return False
            
    def send_channel_message(self, channel, message):
        """Send a message to a specific channel"""
        if not self.connected or not self.client:
            logger.error("Not connected to MQTT broker")
            return False
            
        try:
            # Topic format for channel messages: msh/c/<channel>/t
            topic = f"msh/c/{channel}/t"
            
            logger.info(f"Sending message to channel {channel}: {message}")
            result = self.client.publish(topic, message, qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("Channel message sent successfully")
                return True
            else:
                logger.error(f"Failed to send channel message: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending channel message: {str(e)}")
            return False
            
    def list_active_nodes(self):
        """List all active nodes discovered during this session"""
        if not self.nodes:
            logger.info("No nodes discovered yet")
            return
            
        logger.info("\n=== Active Nodes ===")
        for node_id, info in self.nodes.items():
            logger.info(f"Node: {node_id}")
            logger.info(f"  Last Seen: {info['last_seen'].strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"  Messages: {info['messages']}")
            
    def disconnect(self):
        """Disconnect from the MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("Disconnected from MQTT broker")

def main():
    parser = argparse.ArgumentParser(description="Test MQTT messaging for Meshtastic")
    parser.add_argument("--mqtt-host", type=str, default="localhost", help="MQTT broker hostname")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt-username", type=str, help="MQTT username")
    parser.add_argument("--mqtt-password", type=str, help="MQTT password")
    parser.add_argument("--message", type=str, help="Message to send")
    parser.add_argument("--node", type=str, help="Node ID for direct message")
    parser.add_argument("--channel", type=str, help="Channel name for channel message")
    parser.add_argument("--listen-only", action="store_true", help="Just listen for messages without sending")
    parser.add_argument("--duration", type=int, default=30, help="How long to listen for messages (seconds)")
    args = parser.parse_args()
    
    tester = MQTTMessageTester(
        host=args.mqtt_host,
        port=args.mqtt_port,
        username=args.mqtt_username,
        password=args.mqtt_password
    )
    
    try:
        # Connect to MQTT broker
        if not tester.connect():
            logger.error("Failed to connect to MQTT broker. Exiting.")
            return 1
            
        # Send message if specified
        if not args.listen_only and args.message:
            if args.node:
                tester.send_direct_message(args.node, args.message)
            elif args.channel:
                tester.send_channel_message(args.channel, args.message)
            else:
                tester.send_broadcast_message(args.message)
        
        # Listen for the specified duration
        logger.info(f"Listening for messages for {args.duration} seconds...")
        time.sleep(args.duration)
        
        # Display discovered nodes
        tester.list_active_nodes()
        
        logger.info("Test completed")
        
    except KeyboardInterrupt:
        logger.info("Test interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return 1
    finally:
        tester.disconnect()
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
