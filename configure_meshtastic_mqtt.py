#!/usr/bin/env python3
"""
Configure a Meshtastic device to use MQTT.
This script connects to a Meshtastic device via serial or IP and configures it to use MQTT.
"""

import sys
import time
import logging
import argparse
import socket
import meshtastic
import meshtastic.serial_interface
import meshtastic.tcp_interface
from pubsub import pub

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def onConnection(interface, topic=pub.AUTO_TOPIC):
    """Callback for when we connect to a Meshtastic device"""
    logger.info(f"Connected to Meshtastic device: {interface.myInfo.my_node_num}")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Configure Meshtastic Device for MQTT")
    parser.add_argument("--device", type=str, help="Serial device (e.g., /dev/ttyUSB0)")
    parser.add_argument("--host", type=str, help="IP address of the Meshtastic device")
    parser.add_argument("--mqtt-server", type=str, required=True, help="MQTT broker address")
    parser.add_argument("--mqtt-port", type=int, default=1883, help="MQTT broker port (default: 1883)")
    parser.add_argument("--mqtt-username", type=str, help="MQTT username")
    parser.add_argument("--mqtt-password", type=str, help="MQTT password")
    parser.add_argument("--mqtt-encryption", type=bool, default=False, help="Enable MQTT encryption")
    args = parser.parse_args()
    
    if not args.device and not args.host:
        logger.error("You must specify either --device or --host")
        return 1
    
    if args.device and args.host:
        logger.error("You can only specify one of --device or --host, not both")
        return 1
    
    try:
        # Subscribe to connection event
        pub.subscribe(onConnection, "meshtastic.connection.established")
        
        # Connect to the device
        if args.device:
            logger.info(f"Connecting to Meshtastic device via serial: {args.device}")
            interface = meshtastic.serial_interface.SerialInterface(args.device)
        else:
            logger.info(f"Connecting to Meshtastic device via TCP: {args.host}")
            interface = meshtastic.tcp_interface.TCPInterface(args.host)
        
        # Wait for connection to establish
        time.sleep(2)
        
        # Get current MQTT settings
        logger.info("Current MQTT settings:")
        mqtt_config = interface.getConfig("mqtt")
        if mqtt_config:
            logger.info(f"  Server: {mqtt_config.get('address', 'Not set')}")
            logger.info(f"  Port: {mqtt_config.get('port', 'Not set')}")
            logger.info(f"  Username: {mqtt_config.get('username', 'Not set')}")
            logger.info(f"  Password: {'Set' if mqtt_config.get('password') else 'Not set'}")
            logger.info(f"  Encryption: {mqtt_config.get('encryption', False)}")
            logger.info(f"  Enabled: {mqtt_config.get('enabled', False)}")
        else:
            logger.info("  No MQTT configuration found")
        
        # Configure MQTT
        logger.info(f"Setting MQTT server to: {args.mqtt_server}:{args.mqtt_port}")
        
        # Build MQTT configuration
        mqtt_config = {
            "address": args.mqtt_server,
            "port": args.mqtt_port,
            "enabled": True
        }
        
        if args.mqtt_username:
            mqtt_config["username"] = args.mqtt_username
            logger.info(f"Setting MQTT username to: {args.mqtt_username}")
        
        if args.mqtt_password:
            mqtt_config["password"] = args.mqtt_password
            logger.info("Setting MQTT password")
        
        if args.mqtt_encryption:
            mqtt_config["encryption"] = True
            logger.info("Enabling MQTT encryption")
        
        # Set the configuration
        interface.setConfig("mqtt", mqtt_config)
        logger.info("MQTT configuration sent to device")
        
        # Wait for configuration to be applied
        time.sleep(2)
        
        # Verify the configuration
        logger.info("Verifying MQTT configuration:")
        mqtt_config = interface.getConfig("mqtt")
        if mqtt_config:
            logger.info(f"  Server: {mqtt_config.get('address', 'Not set')}")
            logger.info(f"  Port: {mqtt_config.get('port', 'Not set')}")
            logger.info(f"  Username: {mqtt_config.get('username', 'Not set')}")
            logger.info(f"  Password: {'Set' if mqtt_config.get('password') else 'Not set'}")
            logger.info(f"  Encryption: {mqtt_config.get('encryption', False)}")
            logger.info(f"  Enabled: {mqtt_config.get('enabled', False)}")
            
            if mqtt_config.get('enabled', False):
                logger.info("✅ MQTT is enabled on the device")
            else:
                logger.warning("⚠️ MQTT is not enabled on the device")
        else:
            logger.error("❌ Failed to retrieve MQTT configuration")
        
        # Get the local IP address to help with configuration
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            
            logger.info(f"\nYour local IP address is: {local_ip}")
            logger.info("Make sure your MQTT broker is running on this IP and accessible")
            logger.info(f"The Meshtastic device will try to connect to: {args.mqtt_server}:{args.mqtt_port}")
        except:
            pass
        
        logger.info("\nConfiguration complete. The device may need to be rebooted to apply changes.")
        logger.info("To reboot the device, use: meshtastic --reboot")
        
    except Exception as e:
        logger.error(f"Error configuring device: {str(e)}")
        return 1
        
    finally:
        # Close the interface
        if 'interface' in locals():
            interface.close()
            
    return 0

if __name__ == "__main__":
    sys.exit(main())
