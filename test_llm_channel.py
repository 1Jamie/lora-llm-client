#!/usr/bin/env python3
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

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        # Subscribe to the response channel
        client.subscribe(f"{args.llm_response_channel}#")
    else:
        logger.error(f"Failed to connect to MQTT broker, return code: {rc}")

def on_message(client, userdata, msg):
    logger.info(f"Received message on topic: {msg.topic}")
    try:
        payload = json.loads(msg.payload.decode())
        logger.info(f"Response: {payload}")
    except json.JSONDecodeError:
        logger.info(f"Raw response: {msg.payload.decode()}")
    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")

def main():
    global args
    parser = argparse.ArgumentParser(description="Test LLM channel communication")
    parser.add_argument("--mqtt-host", type=str, default="10.0.0.159", help="MQTT broker host")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port")
    parser.add_argument("--mqtt-username", type=str, default="something", help="MQTT username")
    parser.add_argument("--mqtt-password", type=str, default="something", help="MQTT password")
    parser.add_argument("--llm-channel", type=str, default="msh/US/2/json/llm/", help="LLM channel topic")
    parser.add_argument("--llm-response-channel", type=str, default="msh/US/2/json/llmres/", help="LLM response channel topic")
    parser.add_argument("--message", type=str, default="Hello from test script!", help="Message to send")
    args = parser.parse_args()
    
    # Create MQTT client
    client = mqtt.Client()
    client.username_pw_set(args.mqtt_username, args.mqtt_password)
    client.on_connect = on_connect
    client.on_message = on_message
    
    try:
        # Connect to MQTT broker
        logger.info(f"Connecting to MQTT broker at {args.mqtt_host}:{args.mqtt_port}")
        client.connect(args.mqtt_host, args.mqtt_port, 60)
        
        # Start the loop
        client.loop_start()
        
        # Wait for connection
        time.sleep(1)
        
        # Prepare message
        message = {
            "from": "test_script",
            "to": "llm",
            "id": f"test_{int(datetime.now().timestamp())}",
            "time": int(datetime.now().timestamp()),
            "text": args.message
        }
        
        # Send message
        topic = args.llm_channel
        payload = json.dumps(message)
        logger.info(f"Sending message to topic: {topic}")
        logger.info(f"Payload: {payload}")
        result = client.publish(topic, payload, qos=1)
        
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info("Message sent successfully")
        else:
            logger.error(f"Failed to send message: {result}")
        
        # Wait for response
        logger.info("Waiting for response (press Ctrl+C to exit)...")
        while True:
            time.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Test terminated by user")
    except Exception as e:
        logger.error(f"Error: {str(e)}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()
