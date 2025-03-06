#!/usr/bin/env python3
"""
Configure Meshtastic Device for LLM Agent Communication
This script configures a Meshtastic device for use with the LLM agent system.
It sets up the appropriate MQTT configuration and channel settings for optimal communication.
"""

import os
import sys
import time
import json
import logging
import argparse
import meshtastic
import meshtastic.tcp_interface
import meshtastic.serial_interface
from meshtastic.__init__ import LOCAL_ADDR
from pubsub import pub

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Default device interface (serial) - can be overridden via command line
DEFAULT_INTERFACE = "serial"
DEFAULT_TCP_HOST = "localhost"
DEFAULT_TCP_PORT = 4403

class MeshtasticConfigurator:
    def __init__(self, interface_type=DEFAULT_INTERFACE, tcp_host=DEFAULT_TCP_HOST, 
                 tcp_port=DEFAULT_TCP_PORT, serial_port=None):
        self.interface_type = interface_type.lower()
        self.tcp_host = tcp_host
        self.tcp_port = tcp_port
        self.serial_port = serial_port
        self.interface = None
        self.config_applied = False
        self.device_info = {}
        
    def connect(self):
        """Connect to the Meshtastic device"""
        try:
            logger.info(f"Connecting to Meshtastic device via {self.interface_type}...")
            
            if self.interface_type == "tcp":
                # Connect via TCP
                self.interface = meshtastic.tcp_interface.TCPInterface(
                    hostname=self.tcp_host, 
                    port=self.tcp_port
                )
                logger.info(f"Connected to device via TCP at {self.tcp_host}:{self.tcp_port}")
            else:
                # Connect via serial
                self.interface = meshtastic.serial_interface.SerialInterface(
                    devPath=self.serial_port
                )
                logger.info(f"Connected to device via Serial at {self.serial_port or 'auto-detected port'}")
                
            # Subscribe to node info updates
            pub.subscribe(self._on_node_info, "meshtastic.node.info")
            
            # Wait for the node info
            logger.info("Waiting for device information...")
            time.sleep(2)
            
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to Meshtastic device: {str(e)}")
            return False
            
    def _on_node_info(self, packet, interface):
        """Callback for node info packets"""
        try:
            if packet.get('from') == LOCAL_ADDR:
                my_node_num = packet.get('from')
                user = packet.get('user', {})
                self.device_info = {
                    'node_id': my_node_num,
                    'long_name': user.get('longName', 'Unknown'),
                    'short_name': user.get('shortName', 'Unknown'),
                    'hardware_model': packet.get('deviceMetrics', {}).get('hardware', 'Unknown'),
                    'firmware_version': packet.get('deviceMetrics', {}).get('firmwareVersion', 'Unknown'),
                }
                logger.info(f"Device Info: {json.dumps(self.device_info, indent=2)}")
        except Exception as e:
            logger.error(f"Error processing node info: {str(e)}")
            
    def configure_mqtt(self, mqtt_server, mqtt_username=None, mqtt_password=None, 
                       mqtt_enabled=True, mqtt_port=1883, encryption_enabled=True):
        """Configure MQTT settings on the device"""
        if not self.interface:
            logger.error("Not connected to a Meshtastic device")
            return False
            
        try:
            logger.info(f"Configuring MQTT settings: Server={mqtt_server}:{mqtt_port}, Enabled={mqtt_enabled}")
            
            # Get the current device config
            orig_mqtt = self.interface.getConfig("mqtt")
            
            # Construct the new MQTT config
            mqtt_config = {
                'address': mqtt_server,
                'username': mqtt_username or '',
                'password': mqtt_password or '',
                'enabled': mqtt_enabled,
                'port': mqtt_port,
                'encryption_enabled': encryption_enabled
            }
            
            # Check if we need to update
            config_changed = (orig_mqtt.get('address') != mqtt_config['address'] or
                             orig_mqtt.get('username') != mqtt_config['username'] or
                             orig_mqtt.get('password') != mqtt_config['password'] or
                             orig_mqtt.get('enabled') != mqtt_config['enabled'] or
                             orig_mqtt.get('port') != mqtt_config['port'] or
                             orig_mqtt.get('encryption_enabled') != mqtt_config['encryption_enabled'])
            
            if config_changed:
                logger.info("Applying new MQTT configuration...")
                self.interface.setMQTT(**mqtt_config)
                logger.info("MQTT configuration updated successfully")
                return True
            else:
                logger.info("MQTT configuration already matches desired settings")
                return True
                
        except Exception as e:
            logger.error(f"Error configuring MQTT: {str(e)}")
            return False
            
    def configure_channel(self, channel_name="LLM", modem_config=9, psk=None, 
                         downlink_enabled=True, uplink_enabled=True, index=0):
        """Configure a channel for LLM communication"""
        if not self.interface:
            logger.error("Not connected to a Meshtastic device")
            return False
            
        try:
            # Get existing channels
            channels = self.interface.getChannelByName(None)
            
            # Check if the LLM channel already exists
            channel_exists = False
            for ch in channels:
                if ch.settings.name == channel_name:
                    channel_exists = True
                    logger.info(f"Channel '{channel_name}' already exists")
                    break
                    
            if not channel_exists:
                logger.info(f"Creating channel '{channel_name}' with index {index}")
                
                # Create new channel settings
                settings = meshtastic.Channel.ChannelSettings()
                settings.name = channel_name
                settings.modem_config = modem_config  # Long range, slow speed for maximum range
                
                # Set PSK if provided
                if psk:
                    if isinstance(psk, str):
                        if len(psk) == 16:  # 16 byte hex string
                            settings.psk = bytes.fromhex(psk)
                        else:
                            # Use the string as a seed for the PSK
                            import hashlib
                            h = hashlib.sha256()
                            h.update(psk.encode())
                            settings.psk = h.digest()[:16]  # Take first 16 bytes of hash
                    else:
                        # Assume it's already bytes
                        settings.psk = psk
                
                # Configure role
                role = meshtastic.Channel.Role()
                role.uplink_enabled = uplink_enabled
                role.downlink_enabled = downlink_enabled
                
                # Create the channel
                self.interface.setChannel(index, settings, role)
                logger.info(f"Channel '{channel_name}' created successfully")
                
                # Wait for a bit to allow the operation to complete
                time.sleep(2)
                
            # Verify channel was created
            updated_channels = self.interface.getChannelByName(None)
            for ch in updated_channels:
                if ch.settings.name == channel_name:
                    logger.info(f"Channel verification successful: {ch.settings}")
                    return True
                    
            if not channel_exists:
                logger.error(f"Failed to verify channel '{channel_name}' creation")
                return False
                
            return True
                
        except Exception as e:
            logger.error(f"Error configuring channel: {str(e)}")
            return False
            
    def save_configuration(self):
        """Save the current configuration to the device"""
        if not self.interface:
            logger.error("Not connected to a Meshtastic device")
            return False
            
        try:
            logger.info("Saving configuration to device...")
            self.interface.writeConfig()
            logger.info("Configuration saved successfully")
            self.config_applied = True
            return True
        except Exception as e:
            logger.error(f"Error saving configuration: {str(e)}")
            return False
            
    def print_device_info(self):
        """Print information about the connected device"""
        if not self.device_info:
            logger.warning("Device information not available yet")
            return
            
        logger.info("\n=== Device Information ===")
        logger.info(f"Node ID: {self.device_info.get('node_id', 'Unknown')}")
        logger.info(f"Name: {self.device_info.get('long_name', 'Unknown')}")
        logger.info(f"Hardware: {self.device_info.get('hardware_model', 'Unknown')}")
        logger.info(f"Firmware: {self.device_info.get('firmware_version', 'Unknown')}")
        
        # Print MQTT settings
        if self.interface:
            try:
                mqtt_config = self.interface.getConfig("mqtt")
                logger.info("\n=== MQTT Configuration ===")
                logger.info(f"Server: {mqtt_config.get('address', 'Not set')}")
                logger.info(f"Port: {mqtt_config.get('port', 1883)}")
                logger.info(f"Enabled: {mqtt_config.get('enabled', False)}")
                logger.info(f"Username: {mqtt_config.get('username', 'Not set')}")
                logger.info(f"Password: {'*****' if mqtt_config.get('password') else 'Not set'}")
                logger.info(f"Encryption: {mqtt_config.get('encryption_enabled', True)}")
                
                # Print channel information
                channels = self.interface.getChannelByName(None)
                if channels:
                    logger.info("\n=== Channels ===")
                    for i, ch in enumerate(channels):
                        if hasattr(ch, 'settings') and hasattr(ch, 'role'):
                            logger.info(f"Channel {i}: {ch.settings.name}")
                            logger.info(f"  Modem Config: {ch.settings.modem_config}")
                            logger.info(f"  PSK: {'Set' if ch.settings.psk else 'Not set'}")
                            logger.info(f"  Uplink: {ch.role.uplink_enabled}")
                            logger.info(f"  Downlink: {ch.role.downlink_enabled}")
            except Exception as e:
                logger.error(f"Error retrieving config details: {str(e)}")
                
    def reset_mqtt_config(self):
        """Reset the MQTT configuration to factory defaults"""
        if not self.interface:
            logger.error("Not connected to a Meshtastic device")
            return False
            
        try:
            logger.info("Resetting MQTT configuration to defaults...")
            
            # Empty MQTT configuration (disables MQTT)
            mqtt_config = {
                'address': '',
                'username': '',
                'password': '',
                'enabled': False,
                'port': 1883,
                'encryption_enabled': True
            }
            
            self.interface.setMQTT(**mqtt_config)
            logger.info("MQTT configuration reset successfully")
            return True
                
        except Exception as e:
            logger.error(f"Error resetting MQTT configuration: {str(e)}")
            return False
            
    def disconnect(self):
        """Disconnect from the device"""
        if self.interface:
            logger.info("Disconnecting from Meshtastic device...")
            self.interface.close()
            logger.info("Disconnected")
            
def main():
    parser = argparse.ArgumentParser(description="Configure a Meshtastic device for LLM agent communication")
    
    # Connection options
    connection_group = parser.add_argument_group('Connection Options')
    connection_group.add_argument("--interface", type=str, choices=["serial", "tcp"], default=DEFAULT_INTERFACE,
                                 help="Interface type to connect to the device (serial or tcp)")
    connection_group.add_argument("--tcp-host", type=str, default=DEFAULT_TCP_HOST,
                                 help="TCP hostname for TCP interface")
    connection_group.add_argument("--tcp-port", type=int, default=DEFAULT_TCP_PORT,
                                 help="TCP port for TCP interface")
    connection_group.add_argument("--serial-port", type=str,
                                 help="Serial port for the device (if not specified, auto-detect)")
    
    # MQTT configuration
    mqtt_group = parser.add_argument_group('MQTT Configuration')
    mqtt_group.add_argument("--mqtt-server", type=str,
                           help="MQTT broker address (IP/hostname)")
    mqtt_group.add_argument("--mqtt-port", type=int, default=1883,
                           help="MQTT broker port")
    mqtt_group.add_argument("--mqtt-username", type=str,
                           help="MQTT username for authentication")
    mqtt_group.add_argument("--mqtt-password", type=str,
                           help="MQTT password for authentication")
    mqtt_group.add_argument("--disable-mqtt", action="store_true",
                           help="Disable MQTT (overrides other MQTT settings)")
    mqtt_group.add_argument("--disable-mqtt-encryption", action="store_true",
                           help="Disable MQTT encryption")
    
    # Channel configuration
    channel_group = parser.add_argument_group('Channel Configuration')
    channel_group.add_argument("--channel-name", type=str, default="LLM",
                              help="Name for the LLM communication channel")
    channel_group.add_argument("--channel-index", type=int, default=0,
                              help="Channel index (0-7)")
    channel_group.add_argument("--channel-psk", type=str,
                              help="Pre-shared key for the channel (16 byte hex string or text seed)")
    channel_group.add_argument("--modem-config", type=int, default=9,
                              help="Modem config (0-13, higher is longer range but slower)")
    
    # Actions
    action_group = parser.add_argument_group('Actions')
    action_group.add_argument("--info-only", action="store_true",
                             help="Show device info without making any changes")
    action_group.add_argument("--reset-mqtt", action="store_true",
                             help="Reset MQTT configuration to factory defaults")
    
    args = parser.parse_args()
    
    # Check if we actually need to do any configuration
    if not (args.mqtt_server or args.info_only or args.reset_mqtt):
        parser.print_help()
        logger.error("No configuration actions specified. Exiting.")
        return 1
    
    # Create the configurator
    configurator = MeshtasticConfigurator(
        interface_type=args.interface,
        tcp_host=args.tcp_host,
        tcp_port=args.tcp_port,
        serial_port=args.serial_port
    )
    
    try:
        # Connect to the device
        if not configurator.connect():
            logger.error("Failed to connect to Meshtastic device. Exiting.")
            return 1
            
        # Wait a moment for all device info to be received
        time.sleep(2)
        
        # Show current device info
        configurator.print_device_info()
        
        # If info-only mode, exit here
        if args.info_only:
            logger.info("Info-only mode, no configuration changes made.")
            return 0
            
        # Reset MQTT if requested
        if args.reset_mqtt:
            if configurator.reset_mqtt_config():
                configurator.save_configuration()
            return 0
            
        # Configure MQTT
        if args.mqtt_server:
            mqtt_enabled = not args.disable_mqtt
            encryption_enabled = not args.disable_mqtt_encryption
            
            configurator.configure_mqtt(
                mqtt_server=args.mqtt_server,
                mqtt_port=args.mqtt_port,
                mqtt_username=args.mqtt_username,
                mqtt_password=args.mqtt_password,
                mqtt_enabled=mqtt_enabled,
                encryption_enabled=encryption_enabled
            )
            
        # Configure channel
        configurator.configure_channel(
            channel_name=args.channel_name,
            modem_config=args.modem_config,
            psk=args.channel_psk,
            index=args.channel_index
        )
        
        # Save configuration to device
        configurator.save_configuration()
        
        # Show updated device info
        logger.info("\nUpdated device configuration:")
        configurator.print_device_info()
        
        logger.info("\nConfiguration complete! Device is now ready for LLM agent communication.")
        
    except KeyboardInterrupt:
        logger.info("Configuration interrupted by user")
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return 1
    finally:
        configurator.disconnect()
        
    return 0

if __name__ == "__main__":
    sys.exit(main())
