#!/usr/bin/env python3
"""
Test direct messaging with the Meshtastic LLM Agent
This script tests the agent's ability to receive and respond to direct messages.
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

class AgentDirectMessagingTester:
    def __init__(self, host, port, username=None, password=None):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.client = None
        self.nodes = {}
        self.agent_id = None
        self.my_id = f"test_{int(time.time())}"
        self.last_response_time = None
        self.received_response = False
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
            
            # Subscribe to direct messages to our test ID
            logger.info(f"Subscribing to direct messages for test client {self.my_id}")
            self.client.subscribe(f"msh/d/!{self.my_id}/#")
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
                    
                    # Check if this looks like an agent response
                    if node_id != self.my_id and self.agent_id is None:
                        logger.info(f"Potential agent detected: {node_id}")
                        self.agent_id = node_id
                    
                    # Check if this is a response to our message
                    if node_id == self.agent_id:
                        logger.info(f"Received response from agent: {payload.get('text', '')}")
                        self.last_response_time = datetime.now()
                        self.received_response = True
                    
                    # Update node tracking
                    if node_id not in self.nodes:
                        self.nodes[node_id] = {
                            "last_seen": datetime.now(),
                            "messages": 1
                        }
                    else:
                        self.nodes[node_id]["last_seen"] = datetime.now()
                        self.nodes[node_id]["messages"] += 1
                        
            except json.JSONDecodeError:
                # Not JSON, check if it's a direct message response
                if "d/!" in topic and self.agent_id is not None:
                    logger.info(f"Received direct message: {msg.payload.decode()}")
                    self.last_response_time = datetime.now()
                    self.received_response = True
                else:
                    logger.info(f"Raw payload: {msg.payload.decode()}")
                
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            
    def discover_agent(self, timeout=20):
        """Try to discover the agent node ID by observing messages"""
        if self.agent_id:
            logger.info(f"Agent already discovered: {self.agent_id}")
            return self.agent_id
            
        logger.info(f"Attempting to discover agent (timeout: {timeout}s)...")
        
        # Wait and observe messages to identify the agent
        start_time = time.time()
        while (time.time() - start_time) < timeout and not self.agent_id:
            time.sleep(1)
            
        if self.agent_id:
            logger.info(f"Agent discovered: {self.agent_id}")
            return self.agent_id
        else:
            logger.warning("Agent not discovered within timeout period")
            return None
            
    def send_direct_message(self, node_id, message):
        """Send a direct message to a specific node"""
        if not self.connected or not self.client:
            logger.error("Not connected to MQTT broker")
            return False
            
        try:
            # Make sure node_id starts with !
            if not node_id.startswith("!"):
                node_id = f"!{node_id}"
            
            # Create a structured message
            timestamp = int(time.time())
            json_message = {
                "from": self.my_id,
                "to": node_id.lstrip('!'),
                "id": f"test_{timestamp}",
                "time": timestamp,
                "text": message
            }
            
            # Topic format for direct messages
            topic = f"msh/d/{node_id}/json"
            
            logger.info(f"Sending direct message to {node_id}: {message}")
            result = self.client.publish(topic, json.dumps(json_message), qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("Direct message sent successfully")
                return True
            else:
                logger.error(f"Failed to send direct message: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending direct message: {str(e)}")
            return False
    
    def send_llm_channel_message(self, channel, message):
        """Send a message to the LLM channel"""
        if not self.connected or not self.client:
            logger.error("Not connected to MQTT broker")
            return False
            
        try:
            # Create a structured message
            timestamp = int(time.time())
            json_message = {
                "from": self.my_id,
                "to": "llm",
                "id": f"test_{timestamp}",
                "time": timestamp,
                "text": message
            }
            
            logger.info(f"Sending message to LLM channel {channel}: {message}")
            result = self.client.publish(channel, json.dumps(json_message), qos=1)
            
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                logger.info("LLM channel message sent successfully")
                return True
            else:
                logger.error(f"Failed to send LLM channel message: {result}")
                return False
                
        except Exception as e:
            logger.error(f"Error sending LLM channel message: {str(e)}")
            return False
            
    def wait_for_response(self, timeout=30):
        """Wait for a response from the agent"""
        logger.info(f"Waiting for response (timeout: {timeout}s)...")
        
        self.received_response = False
        start_time = time.time()
        
        while (time.time() - start_time) < timeout and not self.received_response:
            time.sleep(1)
            
        if self.received_response:
            response_time = (self.last_response_time - datetime.fromtimestamp(start_time)).total_seconds()
            logger.info(f"Response received after {response_time:.2f} seconds")
            return True
        else:
            logger.warning("No response received within timeout period")
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
            if node_id == self.agent_id:
                logger.info(f"  Role: AGENT")
                
        logger.info("")
            
    def disconnect(self):
        """Disconnect from the MQTT broker"""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
            logger.info("Disconnected from MQTT broker")
            
    def test_direct_messaging(self, agent_id=None, test_message="Hello LLM Agent, this is a test message"):
        """Run a complete test of direct messaging with the agent"""
        # Set agent ID if provided
        if agent_id:
            if not agent_id.startswith("!"):
                agent_id = f"!{agent_id}"
            self.agent_id = agent_id
            logger.info(f"Using provided agent ID: {self.agent_id}")
            
        # Try to discover the agent if not provided
        if not self.agent_id:
            if not self.discover_agent(timeout=15):
                logger.warning("Agent not discovered. Will try sending to LLM channel instead.")
                # Try using LLM channel as fallback
                logger.info("Sending test message to LLM channel")
                if self.send_llm_channel_message("msh/us/2/json/llm", test_message):
                    return self.wait_for_response(timeout=30)
                else:
                    logger.error("Failed to send message to LLM channel")
                    return False
                
        # Send a direct message to the agent
        logger.info(f"Sending test message to agent {self.agent_id}")
        if not self.send_direct_message(self.agent_id, test_message):
            logger.error("Failed to send direct message to agent")
            return False
            
        # Wait for a response
        return self.wait_for_response(timeout=30)

def main():
    parser = argparse.ArgumentParser(description="Test direct messaging with the Meshtastic LLM Agent")
    parser.add_argument("--mqtt-host", type=str, default="localhost", help="MQTT broker hostname")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt-username", type=str, help="MQTT username")
    parser.add_argument("--mqtt-password", type=str, help="MQTT password")
    parser.add_argument("--agent-id", type=str, help="Agent node ID (if known)")
    parser.add_argument("--message", type=str, default="Hello LLM Agent, this is a test message", help="Test message to send")
    parser.add_argument("--discover-only", action="store_true", help="Only discover nodes without sending messages")
    parser.add_argument("--timeout", type=int, default=60, help="Overall test timeout in seconds")
    args = parser.parse_args()
    
    tester = AgentDirectMessagingTester(
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
            
        if args.discover_only:
            # Just discover nodes
            logger.info(f"Discovering nodes for {args.timeout} seconds...")
            time.sleep(args.timeout)
            tester.list_active_nodes()
        else:
            # Run the direct messaging test
            result = tester.test_direct_messaging(args.agent_id, args.message)
            
            # List discovered nodes
            tester.list_active_nodes()
            
            # Report test result
            if result:
                logger.info("✅ Direct messaging test PASSED")
                logger.info("The agent successfully received and responded to a direct message")
            else:
                logger.error("❌ Direct messaging test FAILED")
                logger.error("The agent did not respond to the direct message within the timeout period")
                return 1
        
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
