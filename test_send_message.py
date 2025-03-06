#!/usr/bin/env python3
import os
import sys
import json
import time
import logging
import argparse
from datetime import datetime
import paho.mqtt.client as mqtt
import meshtastic
import meshtastic.tcp_interface
import meshtastic.serial_interface

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class MessageTester:
    def __init__(self, connection_type, device_address, llm_channel, mqtt_config=None):
        self.connection_type = connection_type
        self.device_address = device_address
        self.llm_channel = llm_channel
        self.mqtt_config = mqtt_config
        self.interface = None
        self.mqtt_client = None
        
    def setup_interface(self):
        """Set up the Meshtastic interface based on connection type"""
        try:
            if self.connection_type.lower() == "serial":
                logger.info(f"Connecting to Meshtastic device on serial port {self.device_address}")
                self.interface = meshtastic.serial_interface.SerialInterface(self.device_address)
                
            elif self.connection_type.lower() == "tcp":
                host, port = self.device_address.split(':') if ':' in self.device_address else (self.device_address, 4403)
                port = int(port)
                logger.info(f"Connecting to Meshtastic device via TCP at {host}:{port}")
                self.interface = meshtastic.tcp_interface.TCPInterface(host, port)
                
            else:
                logger.error(f"Unsupported connection type: {self.connection_type}")
                return False
                
            logger.info("Meshtastic interface connected successfully")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Meshtastic device: {str(e)}")
            return False
            
    def setup_mqtt(self):
        """Set up MQTT client if config is provided"""
        if not self.mqtt_config:
            logger.info("No MQTT configuration provided, skipping MQTT setup")
            return False
            
        try:
            host = self.mqtt_config.get("host", "localhost")
            port = self.mqtt_config.get("port", 1883)
            username = self.mqtt_config.get("username")
            password = self.mqtt_config.get("password")
            
            logger.info(f"Setting up MQTT client to connect to {host}:{port}")
            self.mqtt_client = mqtt.Client()
            
            if username and password:
                self.mqtt_client.username_pw_set(username, password)
                
            self.mqtt_client.on_connect = self._on_mqtt_connect
            self.mqtt_client.on_message = self._on_mqtt_message
            
            logger.info("Connecting to MQTT broker...")
            self.mqtt_client.connect(host, port, 60)
            self.mqtt_client.loop_start()
            
            # Wait a bit to ensure connection is established
            time.sleep(1)
            return True
            
        except Exception as e:
            logger.error(f"Failed to set up MQTT client: {str(e)}")
            return False
            
    def _on_mqtt_connect(self, client, userdata, flags, rc):
        """Callback for when MQTT client connects"""
        if rc == 0:
            logger.info("Connected to MQTT broker")
            # Subscribe to the response topic
            response_topic = f"{self.llm_channel}/response"
            logger.info(f"Subscribing to response topic: {response_topic}")
            client.subscribe(f"{response_topic}/#")
        else:
            logger.error(f"Failed to connect to MQTT broker, return code: {rc}")
            
    def _on_mqtt_message(self, client, userdata, msg):
        """Callback for when MQTT message is received"""
        logger.info(f"Received MQTT message on topic: {msg.topic}")
        try:
            payload = json.loads(msg.payload.decode())
            logger.info(f"MQTT Response: {json.dumps(payload, indent=2)}")
        except json.JSONDecodeError:
            logger.info(f"Raw MQTT response: {msg.payload.decode()}")
        except Exception as e:
            logger.error(f"Error processing MQTT message: {str(e)}")
            
    def send_direct_message(self, to_node_id, text):
        """Send a direct message to a specific node"""
        if not self.interface:
            logger.error("Interface not connected")
            return False
            
        try:
            logger.info(f"Sending direct message to node {to_node_id}: {text}")
            self.interface.sendText(text, destinationId=to_node_id, wantAck=True)
            logger.info("Direct message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send direct message: {str(e)}")
            return False
            
    def send_broadcast_message(self, text):
        """Send a broadcast message to all nodes"""
        if not self.interface:
            logger.error("Interface not connected")
            return False
            
        try:
            logger.info(f"Sending broadcast message: {text}")
            self.interface.sendText(text)
            logger.info("Broadcast message sent successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to send broadcast message: {str(e)}")
            return False
            
    def send_channel_message(self, text):
        """Send a message to the LLM channel"""
        if not self.interface:
            logger.error("Interface not connected")
            return False
            
        try:
            logger.info(f"Sending channel message to {self.llm_channel}: {text}")
            # Format message for the LLM channel
            message = {
                "from": "test_script",
                "to": "llm",
                "id": f"test_{int(datetime.now().timestamp())}",
                "time": int(datetime.now().timestamp()),
                "text": text
            }
            
            # Send via MQTT if available
            if self.mqtt_client:
                result = self.mqtt_client.publish(
                    self.llm_channel, 
                    json.dumps(message), 
                    qos=1
                )
                if result.rc == mqtt.MQTT_ERR_SUCCESS:
                    logger.info("Channel message sent successfully via MQTT")
                    return True
                else:
                    logger.error(f"Failed to send message via MQTT: {result}")
                    
            # Try to send via Meshtastic channel
            channel_name = self.llm_channel.split('/')[-1] if '/' in self.llm_channel else self.llm_channel
            self.interface.sendText(json.dumps(message), channelName=channel_name)
            logger.info("Channel message sent successfully via Meshtastic")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send channel message: {str(e)}")
            return False
            
    def cleanup(self):
        """Clean up resources"""
        if self.mqtt_client:
            logger.info("Disconnecting MQTT client")
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            
        if self.interface:
            logger.info("Closing Meshtastic interface")
            self.interface.close()

def main():
    parser = argparse.ArgumentParser(description="Test sending messages to the Meshtastic LLM Agent")
    parser.add_argument("--type", choices=["serial", "tcp"], default="tcp", help="Connection type")
    parser.add_argument("--device", type=str, default="10.0.0.133:4403", help="Device address (serial port or IP:port)")
    parser.add_argument("--mqtt-host", type=str, default=None, help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt-username", type=str, default=None, help="MQTT username")
    parser.add_argument("--mqtt-password", type=str, default=None, help="MQTT password")
    parser.add_argument("--llm-channel", type=str, default="msh/us/2/json/llm", help="LLM channel")
    parser.add_argument("--message", type=str, default="Hello from test script!", help="Message to send")
    parser.add_argument("--node-id", type=str, default=None, help="Node ID for direct message")
    parser.add_argument("--mode", choices=["direct", "broadcast", "channel"], default="channel", help="Message mode")
    
    args = parser.parse_args()
    
    # Set up MQTT config if host is provided
    mqtt_config = None
    if args.mqtt_host:
        mqtt_config = {
            "host": args.mqtt_host,
            "port": args.mqtt_port,
            "username": args.mqtt_username,
            "password": args.mqtt_password
        }
    
    tester = MessageTester(
        connection_type=args.type,
        device_address=args.device,
        llm_channel=args.llm_channel,
        mqtt_config=mqtt_config
    )
    
    try:
        # Set up communication interfaces
        if not tester.setup_interface():
            logger.error("Failed to set up Meshtastic interface. Exiting.")
            return
            
        if mqtt_config:
            tester.setup_mqtt()
        
        # Send message based on mode
        if args.mode == "direct":
            if not args.node_id:
                logger.error("Node ID is required for direct messages")
                return
            tester.send_direct_message(args.node_id, args.message)
            
        elif args.mode == "broadcast":
            tester.send_broadcast_message(args.message)
            
        else:  # channel mode
            tester.send_channel_message(args.message)
            
        # Wait for response
        logger.info("Waiting for response (press Ctrl+C to exit)...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Test terminated by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
    finally:
        tester.cleanup()

if __name__ == "__main__":
    main()
