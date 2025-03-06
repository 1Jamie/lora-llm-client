#!/usr/bin/env python3
"""
Simulate a Meshtastic node for testing the LLM agent
This script simulates a Meshtastic node that can send and receive messages via MQTT.
It's useful for testing the LLM agent without physical Meshtastic devices.
"""

import os
import sys
import json
import time
import logging
import argparse
import threading
import random
from datetime import datetime
import paho.mqtt.client as mqtt

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MeshtasticNodeSimulator:
    def __init__(self, node_id=None, host="localhost", port=1883, username=None, password=None):
        # Generate a random node ID if not provided
        if node_id:
            # Strip leading ! if present
            self.node_id = node_id.lstrip('!')
        else:
            # Generate a random 8-character hex node ID
            self.node_id = ''.join(random.choice('0123456789abcdef') for _ in range(8))
            
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.connected = False
        self.known_nodes = {}
        self.auto_respond = False
        self.running = True
        
    def connect(self):
        """Connect to the MQTT broker"""
        try:
            # Create MQTT client with our node ID
            client_id = f"meshtastic_{self.node_id}"
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
            logger.info(f"Connected to MQTT broker as node !{self.node_id}")
            
            # Subscribe to direct messages for our node
            direct_topic = f"msh/d/!{self.node_id}/#"
            logger.info(f"Subscribing to direct messages: {direct_topic}")
            self.client.subscribe(direct_topic)
            
            # Subscribe to broadcast messages
            broadcast_topic = "msh/b/#"
            logger.info(f"Subscribing to broadcast messages: {broadcast_topic}")
            self.client.subscribe(broadcast_topic)
            
            # Subscribe to LLM channel messages
            llm_topic = "msh/+/+/json/llmres/#"
            logger.info(f"Subscribing to LLM response channel: {llm_topic}")
            self.client.subscribe(llm_topic)
            
            # Announce our presence
            self._announce_presence()
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
            
            # Determine message type
            is_direct = f"d/!{self.node_id}" in topic
            is_broadcast = "b/" in topic
            is_llm_response = "llmres" in topic
            
            # Try to parse as JSON
            try:
                payload = json.loads(msg.payload.decode())
                logger.info(f"JSON payload: {json.dumps(payload, indent=2)}")
                
                # Extract sender information if available
                if "from" in payload:
                    sender_id = payload["from"]
                    if sender_id not in self.known_nodes:
                        self.known_nodes[sender_id] = {
                            "last_seen": datetime.now(),
                            "messages": 1
                        }
                    else:
                        self.known_nodes[sender_id]["last_seen"] = datetime.now()
                        self.known_nodes[sender_id]["messages"] += 1
                    
                # Auto-respond if enabled
                if self.auto_respond and is_direct:
                    text = payload.get("text", "")
                    logger.info(f"Auto-responding to direct message: {text}")
                    self.send_direct_message(sender_id, f"Auto-response from !{self.node_id}: I received '{text}'")
                    
            except json.JSONDecodeError:
                # Not JSON, try to parse as plain text
                text = msg.payload.decode()
                logger.info(f"Text message: {text}")
                
                # Auto-respond if enabled
                if self.auto_respond and is_direct:
                    logger.info(f"Auto-responding to direct message: {text}")
                    if "/" in topic:
                        parts = topic.split("/")
                        if len(parts) >= 3:
                            sender_id = parts[2].lstrip('!')
                            self.send_direct_message(sender_id, f"Auto-response from !{self.node_id}: I received '{text}'")
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            
    def _announce_presence(self):
        """Announce this node's presence on the network"""
        try:
            # Create a node info message
            node_info = {
                "id": self.node_id,
                "name": f"Simulated Node {self.node_id[:4]}",
                "hardware": "Simulator",
                "firmware": "SimMeshtastic v1.0",
                "time": int(time.time())
            }
            
            # Publish to the node info topic
            topic = f"msh/n/!{self.node_id}/json"
            self.client.publish(topic, json.dumps(node_info), qos=1, retain=True)
            logger.info(f"Announced presence as node !{self.node_id}")
            
        except Exception as e:
            logger.error(f"Error announcing presence: {str(e)}")
            
    def send_broadcast_message(self, message):
        """Send a broadcast message to all nodes"""
        if not self.connected or not self.client:
            logger.error("Not connected to MQTT broker")
            return False
            
        try:
            # Create message payload
            payload = {
                "from": self.node_id,
                "id": f"{self.node_id}_{int(time.time())}",
                "type": "text",
                "time": int(time.time()),
                "text": message
            }
            
            # Topic format for broadcast messages
            topic = "msh/b/json"
            
            logger.info(f"Sending broadcast message: {message}")
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("Broadcast message sent successfully")
                return True
            else:
                logger.error(f"Failed to send broadcast message: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending broadcast message: {str(e)}")
            return False
            
    def send_direct_message(self, to_node_id, message):
        """Send a direct message to a specific node"""
        if not self.connected or not self.client:
            logger.error("Not connected to MQTT broker")
            return False
            
        try:
            # Make sure node_id starts with !
            if not to_node_id.startswith("!"):
                to_node_id = f"!{to_node_id}"
                
            # Strip the leading ! for the actual ID in the payload
            actual_id = to_node_id.lstrip('!')
                
            # Create message payload
            payload = {
                "from": self.node_id,
                "to": actual_id,
                "id": f"{self.node_id}_{int(time.time())}",
                "type": "text",
                "time": int(time.time()),
                "text": message
            }
            
            # Topic format for direct messages
            topic = f"msh/d/{to_node_id}/json"
            
            logger.info(f"Sending direct message to {to_node_id}: {message}")
            result = self.client.publish(topic, json.dumps(payload), qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("Direct message sent successfully")
                return True
            else:
                logger.error(f"Failed to send direct message: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending direct message: {str(e)}")
            return False
            
    def send_llm_message(self, message, channel="msh/us/2/json/llm"):
        """Send a message to the LLM channel"""
        if not self.connected or not self.client:
            logger.error("Not connected to MQTT broker")
            return False
            
        try:
            # Create message payload
            payload = {
                "from": self.node_id,
                "to": "llm",
                "id": f"{self.node_id}_{int(time.time())}",
                "time": int(time.time()),
                "text": message
            }
            
            logger.info(f"Sending message to LLM channel {channel}: {message}")
            result = self.client.publish(channel, json.dumps(payload), qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("LLM message sent successfully")
                return True
            else:
                logger.error(f"Failed to send LLM message: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending LLM message: {str(e)}")
            return False
            
    def list_known_nodes(self):
        """List all nodes discovered during this session"""
        if not self.known_nodes:
            logger.info("No other nodes discovered yet")
            return
            
        logger.info("\n=== Known Nodes ===")
        for node_id, info in self.known_nodes.items():
            logger.info(f"Node: !{node_id}")
            logger.info(f"  Last Seen: {info['last_seen'].strftime('%Y-%m-%d %H:%M:%S')}")
            logger.info(f"  Messages: {info['messages']}")
        logger.info("")
            
    def show_node_info(self):
        """Show information about this simulated node"""
        logger.info("\n=== Simulated Node Info ===")
        logger.info(f"Node ID: !{self.node_id}")
        logger.info(f"MQTT Broker: {self.host}:{self.port}")
        logger.info(f"Connected: {self.connected}")
        logger.info(f"Auto-respond: {self.auto_respond}")
        logger.info(f"Known nodes: {len(self.known_nodes)}")
        logger.info("")
            
    def interactive_mode(self):
        """Run in interactive mode, accepting commands from the console"""
        logger.info("\n=== Interactive Mode ===")
        logger.info("Commands:")
        logger.info("  b <message> - Send broadcast message")
        logger.info("  d <node_id> <message> - Send direct message")
        logger.info("  l <message> - Send message to LLM channel")
        logger.info("  n - List known nodes")
        logger.info("  i - Show node info")
        logger.info("  a - Toggle auto-respond")
        logger.info("  q - Quit")
        logger.info("")
        
        while self.running:
            try:
                cmd = input("Command: ").strip()
                
                if not cmd:
                    continue
                    
                parts = cmd.split(maxsplit=2)
                cmd_type = parts[0].lower()
                
                if cmd_type == 'q':
                    logger.info("Quitting interactive mode")
                    self.running = False
                    
                elif cmd_type == 'b' and len(parts) >= 2:
                    message = parts[1]
                    self.send_broadcast_message(message)
                    
                elif cmd_type == 'd' and len(parts) >= 3:
                    node_id = parts[1]
                    message = parts[2]
                    self.send_direct_message(node_id, message)
                    
                elif cmd_type == 'l' and len(parts) >= 2:
                    message = parts[1]
                    self.send_llm_message(message)
                    
                elif cmd_type == 'n':
                    self.list_known_nodes()
                    
                elif cmd_type == 'i':
                    self.show_node_info()
                    
                elif cmd_type == 'a':
                    self.auto_respond = not self.auto_respond
                    logger.info(f"Auto-respond: {self.auto_respond}")
                    
                else:
                    logger.info("Unknown command or missing parameters")
                    
            except KeyboardInterrupt:
                logger.info("\nQuitting interactive mode")
                self.running = False
                
            except Exception as e:
                logger.error(f"Error processing command: {str(e)}")
                
    def disconnect(self):
        """Disconnect from the MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("Disconnected from MQTT broker")

def main():
    parser = argparse.ArgumentParser(description="Simulate a Meshtastic node for testing")
    parser.add_argument("--node-id", type=str, help="Custom node ID (without leading !)")
    parser.add_argument("--mqtt-host", type=str, default="localhost", help="MQTT broker hostname")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt-username", type=str, help="MQTT username")
    parser.add_argument("--mqtt-password", type=str, help="MQTT password")
    parser.add_argument("--auto-respond", action="store_true", help="Automatically respond to direct messages")
    parser.add_argument("--message", type=str, help="Message to send at startup")
    parser.add_argument("--broadcast", action="store_true", help="Send startup message as broadcast")
    parser.add_argument("--agent-id", type=str, help="Agent node ID for direct messages")
    parser.add_argument("--non-interactive", action="store_true", help="Run in non-interactive mode")
    args = parser.parse_args()
    
    # Create the simulator
    simulator = MeshtasticNodeSimulator(
        node_id=args.node_id,
        host=args.mqtt_host,
        port=args.mqtt_port,
        username=args.mqtt_username,
        password=args.mqtt_password
    )
    
    # Set auto-respond
    simulator.auto_respond = args.auto_respond
    
    try:
        # Connect to MQTT broker
        if not simulator.connect():
            logger.error("Failed to connect to MQTT broker. Exiting.")
            return 1
            
        # Display node info
        simulator.show_node_info()
        
        # Send startup message if provided
        if args.message:
            if args.broadcast:
                logger.info("Sending broadcast startup message")
                simulator.send_broadcast_message(args.message)
            elif args.agent_id:
                logger.info(f"Sending direct startup message to agent {args.agent_id}")
                simulator.send_direct_message(args.agent_id, args.message)
            else:
                logger.info("Sending startup message to LLM channel")
                simulator.send_llm_message(args.message)
                
        # Run in interactive or non-interactive mode
        if not args.non_interactive:
            simulator.interactive_mode()
        else:
            logger.info("Running in non-interactive mode. Press Ctrl+C to exit.")
            while simulator.running:
                time.sleep(1)
                
    except KeyboardInterrupt:
        logger.info("Simulation interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return 1
    finally:
        simulator.disconnect()
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
