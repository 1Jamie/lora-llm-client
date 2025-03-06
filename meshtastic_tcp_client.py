#!/usr/bin/env python3
import logging
import time
import threading
import queue
from typing import Dict, Any, List, Optional, Callable

import meshtastic
import meshtastic.tcp_interface

# Setup logging
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MeshtasticTcpClient:
    """Client for interacting with Meshtastic over TCP using the official Python library"""
    
    def __init__(self, host: str, port: int = 4403, private_mode: bool = False):
        """
        Initialize the Meshtastic TCP client
        
        Args:
            host: IP address or hostname of the Meshtastic device
            port: Port of the Meshtastic TCP interface (default: 4403)
            private_mode: If True, only respond to direct messages (default: False)
        """
        self.host = host
        self.port = port
        self.private_mode = private_mode
        
        # Interface
        self.interface = None
        
        # Connection status
        self.connected = False
        
        # Message handling
        self.message_queue = queue.Queue()
        self.message_callback = None
        self.running = False
        self.message_thread = None
        
        # Last message time to avoid duplicates
        self.last_message_time = 0
        
        # Node info
        self.my_node_id = None
        self.my_node_num = None
        self.known_nodes = {}
    
    def connect(self, max_retries=4, retry_delay=2.0) -> bool:
        """
        Connect to the Meshtastic device with retry logic
        
        Args:
            max_retries: Maximum number of connection attempts (default: 4)
            retry_delay: Delay between retries in seconds, increases with each retry
            
        Returns:
            bool: True if connection is successful, False otherwise
        """
        for attempt in range(max_retries + 1):  # +1 because we start with attempt 0
            try:
                if attempt == 0:
                    logger.info(f"Connecting to Meshtastic device at {self.host}:{self.port}")
                else:
                    logger.info(f"Retry attempt {attempt}/{max_retries} connecting to Meshtastic device at {self.host}:{self.port}")
                
                # Connect to the device
                self.interface = meshtastic.tcp_interface.TCPInterface(self.host, self.port)
                
                # Wait for connection to establish (increase waiting time with each retry)
                wait_time = min(2.0 + (attempt * 0.5), 5.0)  # Start with 2s, increase by 0.5s each retry, max 5s
                logger.info(f"Waiting {wait_time:.1f}s for connection to establish...")
                time.sleep(wait_time)
                
                # Set callback for received messages
                self.interface.onReceive = self._on_receive
                
                # Check if we're connected
                try:
                    self.my_node_num = self.interface.myInfo.my_node_num
                    
                    # Get my node ID
                    for node_id, node in self.interface.nodes.items():
                        if node.get('num') == self.my_node_num:
                            self.my_node_id = node_id
                            break
                    
                    logger.info(f"Connected to Meshtastic device, my node ID: {self.my_node_id}, number: {self.my_node_num}")
                    
                    # Get nodes
                    self.known_nodes = self.interface.nodes
                    if self.known_nodes:
                        logger.info(f"Connected nodes: {list(self.known_nodes.keys())}")
                        
                        # Log node details
                        for node_id, node in self.known_nodes.items():
                            user_info = node.get('user', {})
                            long_name = user_info.get('longName', 'Unknown')
                            short_name = user_info.get('shortName', 'Unknown')
                            logger.info(f"Node {node_id}: {long_name} ({short_name})")
                    else:
                        logger.warning("No nodes found")
                    
                    self.connected = True
                    
                    # Log private mode status
                    if self.private_mode:
                        logger.info("Private mode enabled - will only respond to direct messages")
                    else:
                        logger.info("Broadcast mode enabled - will respond to all messages")
                    
                    return True
                    
                except Exception as e:
                    if attempt < max_retries:
                        logger.warning(f"Error getting node info on attempt {attempt+1}: {str(e)}")
                        # Close the interface to clean up before retrying
                        try:
                            self.interface.close()
                        except Exception:
                            pass
                        
                        # Exponential backoff for retries (1s, 2s, 4s, 8s...)
                        current_delay = retry_delay * (2 ** attempt)
                        logger.info(f"Retrying in {current_delay:.1f} seconds...")
                        time.sleep(current_delay)
                        continue
                    else:
                        logger.error(f"Failed to get node info after {max_retries+1} attempts: {str(e)}")
                        return False
                
            except Exception as e:
                if attempt < max_retries:
                    logger.warning(f"Error connecting to Meshtastic device on attempt {attempt+1}: {str(e)}")
                    # Exponential backoff for retries
                    current_delay = retry_delay * (2 ** attempt)
                    logger.info(f"Retrying in {current_delay:.1f} seconds...")
                    time.sleep(current_delay)
                else:
                    logger.error(f"Failed to connect to Meshtastic device after {max_retries+1} attempts: {str(e)}")
                    return False
        
        # If we get here, all retries failed
        return False
    
    def disconnect(self):
        """
        Disconnect from the Meshtastic device
        """
        if self.interface:
            try:
                self.interface.close()
                self.connected = False
                logger.info("Disconnected from Meshtastic device")
            except Exception as e:
                logger.error(f"Error disconnecting from Meshtastic device: {str(e)}")
    
    def _ensure_connected(self, max_retries=2):
        """
        Ensure that we have an active connection to the Meshtastic device.
        Attempts to reconnect if needed.
        
        Args:
            max_retries: Maximum number of reconnection attempts (default: 2)
            
        Returns:
            bool: True if connected (or reconnected), False otherwise
        """
        # Check if we're connected
        if not self.interface or not hasattr(self.interface, 'myInfo'):
            logger.warning("TCP connection lost, attempting to reconnect...")
            reconnected = self.connect(max_retries=max_retries)
            if reconnected:
                logger.info("Successfully reconnected to Meshtastic device")
                return True
            else:
                logger.error("Failed to reconnect to Meshtastic device")
                return False
        return True
    
    def _on_receive(self, packet, interface):
        """
        Callback for when a message is received
        """
        try:
            # Check if this is a text message
            if packet.get('decoded', {}).get('portnum') == 'TEXT_MESSAGE_APP':
                text = packet.get('decoded', {}).get('text', '')
                if text:
                    # Extract sender info
                    from_id = packet.get('fromId', 'unknown')
                    to_id = packet.get('toId', 'broadcast')
                    
                    # Skip messages from ourselves
                    if from_id == self.my_node_id:
                        return
                    
                    # In private mode, only process direct messages sent to us
                    if self.private_mode and to_id != self.my_node_id:
                        logger.info(f"Ignoring message not addressed to us (private mode): from={from_id}, to={to_id}, text={text}")
                        return
                    
                    # Get sender name if available
                    sender = "Unknown"
                    try:
                        if from_id in interface.nodes:
                            user_info = interface.nodes[from_id].get('user', {})
                            sender = user_info.get('longName', user_info.get('shortName', from_id))
                    except Exception:
                        pass
                    
                    # Create message object
                    timestamp = time.time()
                    message = {
                        "text": text,
                        "from_id": from_id,
                        "to_id": to_id,
                        "sender": sender,
                        "timestamp": timestamp,
                        "is_direct": to_id == self.my_node_id
                    }
                    
                    # Check if this is a new message (avoid duplicates)
                    if timestamp > self.last_message_time:
                        self.last_message_time = timestamp
                        
                        # Add to processing queue
                        self.message_queue.put(message)
                        msg_type = "direct" if message["is_direct"] else "broadcast"
                        logger.info(f"Queued {msg_type} message from {sender}: {text}")
                    
        except Exception as e:
            logger.error(f"Error in message handler: {str(e)}")
    
    def send_message(self, message: str, to_id: Optional[str] = None) -> bool:
        """
        Send a message over the Meshtastic network
        
        Args:
            message: Text message to send
            to_id: Node ID to send to (None for broadcast)
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        # First ensure we're connected
        if not self._ensure_connected():
            return False
            
        try:
            # Split message if it's too long (Meshtastic text limit is ~200 bytes)
            max_chunk_size = 190
            
            if len(message) <= max_chunk_size:
                chunks = [message]
            else:
                # Split into chunks
                chunks = []
                for i in range(0, len(message), max_chunk_size):
                    chunk = message[i:i+max_chunk_size]
                    chunks.append(chunk)
            
            # Send each chunk
            for i, chunk in enumerate(chunks):
                if len(chunks) > 1:
                    prefix = f"[{i+1}/{len(chunks)}] "
                    chunk = prefix + chunk
                
                # Determine if this is a direct message
                is_direct = to_id is not None and to_id != "broadcast" and to_id != "^all"
                msg_type = "direct" if is_direct else "broadcast"
                
                logger.info(f"Sending {msg_type} message: {chunk}")
                
                # Send the message
                if is_direct:
                    # Send to specific node
                    self.interface.sendText(chunk, destinationId=to_id)
                else:
                    # Broadcast
                    self.interface.sendText(chunk)
                
                # Brief pause between chunks
                if len(chunks) > 1 and i < len(chunks) - 1:
                    time.sleep(1)
            
            return True
            
        except (BrokenPipeError, ConnectionResetError) as e:
            logger.error(f"Connection error sending message: {str(e)}")
            # Try to reconnect once
            if self._ensure_connected():
                try:
                    # Try once more after reconnection
                    if to_id:
                        self.interface.sendText(message, destinationId=to_id)
                    else:
                        self.interface.sendText(message)
                    return True
                except Exception as retry_e:
                    logger.error(f"Failed to send message after reconnection: {str(retry_e)}")
                    return False
            return False
        except Exception as e:
            logger.error(f"Error sending message: {str(e)}")
            return False
    
    def send_to_channel(self, message: str, channel_name: str) -> bool:
        """
        Send a message to a specific channel over the Meshtastic network
        
        Args:
            message: Text message to send
            channel_name: Channel name to send to
            
        Returns:
            bool: True if message was sent successfully, False otherwise
        """
        # First ensure we're connected
        if not self._ensure_connected():
            return False
            
        try:
            # Split message if it's too long (Meshtastic text limit is ~200 bytes)
            max_chunk_size = 190
            
            if len(message) <= max_chunk_size:
                chunks = [message]
            else:
                # Split into chunks
                chunks = []
                for i in range(0, len(message), max_chunk_size):
                    chunk = message[i:i+max_chunk_size]
                    chunks.append(chunk)
            
            # Attempt to find channel by name
            channel_num = None
            if hasattr(self.interface, 'localNode') and hasattr(self.interface.localNode, 'channels'):
                # Log available channels for debugging
                logger.info("Available channels:")
                for idx, channel in enumerate(self.interface.localNode.channels):
                    if hasattr(channel, 'settings') and hasattr(channel.settings, 'name'):
                        logger.info(f"  Channel {idx}: {channel.settings.name}")
                    else:
                        logger.info(f"  Channel {idx}: <unnamed>")
                
                # Try to find exact match first
                for idx, channel in enumerate(self.interface.localNode.channels):
                    if hasattr(channel, 'settings') and hasattr(channel.settings, 'name'):
                        if channel.settings.name.lower() == channel_name.lower():
                            channel_num = idx
                            logger.info(f"Found exact match for channel {channel_name} at index {channel_num}")
                            break
                
                # If not found, try partial match
                if channel_num is None:
                    for idx, channel in enumerate(self.interface.localNode.channels):
                        if hasattr(channel, 'settings') and hasattr(channel.settings, 'name'):
                            if channel_name.lower() in channel.settings.name.lower():
                                channel_num = idx
                                logger.info(f"Found partial match for channel {channel_name} in {channel.settings.name} at index {channel_num}")
                                break
            
            if channel_num is None:
                # If channel not found, use a hardcoded index
                # The LLM channel is usually on channel 2
                channel_num = 2  # Default to channel 2 for LLM communication
                logger.warning(f"Channel {channel_name} not found in local node, using default channel index {channel_num}")
            
            # Send each chunk to the channel
            for i, chunk in enumerate(chunks):
                try:
                    logger.info(f"Sending message to channel {channel_name} (index {channel_num}): {chunk}")
                    self.interface.sendText(chunk, channelIndex=channel_num)
                    
                    # Add delay between chunks
                    if i < len(chunks) - 1:
                        time.sleep(1)
                        
                except (BrokenPipeError, ConnectionResetError) as e:
                    logger.error(f"Connection error sending message to channel {channel_name}: {str(e)}")
                    
                    # Attempt to reconnect
                    if self._ensure_connected():
                        logger.info(f"Reconnected, retrying message to channel {channel_name}")
                        # Recursive call with one less retry
                        return self.send_to_channel(message, channel_name)
                    else:
                        return False
                        
                except Exception as e:
                    logger.error(f"Error sending message to channel {channel_name}: {str(e)}")
                    return False
                    
            return True
            
        except Exception as e:
            logger.error(f"Error sending message to channel {channel_name}: {str(e)}")
            if self._ensure_connected():
                logger.info(f"Reconnected, retrying message to channel {channel_name}")
                return self.send_to_channel(message, channel_name)
            return False
    
    def set_message_callback(self, callback: Callable[[Dict[str, Any]], str]):
        """
        Set a callback function to process messages
        
        Args:
            callback: Function that takes a message dict and returns a response string
        """
        self.message_callback = callback
    
    def _process_messages(self):
        """
        Process incoming messages from the queue
        """
        while self.running:
            try:
                # Get message from queue with timeout
                message = self.message_queue.get(timeout=1.0)
                
                if self.message_callback:
                    # Process message with callback
                    logger.info(f"Processing message: {message['text']}")
                    response = self.message_callback(message)
                    
                    # Send response back
                    if response:
                        # In private mode or if it was a direct message, respond directly to the sender
                        # Otherwise, broadcast the response
                        if self.private_mode or message.get("is_direct", False):
                            self.send_message(response, message.get("from_id"))
                        else:
                            self.send_message(response)
                
                self.message_queue.task_done()
                
            except queue.Empty:
                # No messages, continue
                pass
            except Exception as e:
                logger.error(f"Error in message processing thread: {str(e)}")
    
    def start(self):
        """
        Start the message processing thread
        """
        if not self.connected:
            logger.error("Cannot start - not connected to Meshtastic device")
            return False
        
        self.running = True
        
        # Start message processing thread
        self.message_thread = threading.Thread(target=self._process_messages)
        self.message_thread.daemon = True
        self.message_thread.start()
        
        logger.info("Message processing started")
        return True
    
    def stop(self):
        """
        Stop the message processing thread
        """
        self.running = False
        
        # Wait for thread to finish
        if self.message_thread and self.message_thread.is_alive():
            self.message_thread.join(timeout=2.0)
        
        logger.info("Message processing stopped")
        
        # Disconnect
        self.disconnect()
    
    def poll_messages(self, interval: float = 2.0) -> Optional[str]:
        """
        Poll for new messages and process them with the callback
        This is a compatibility method for the old interface
        
        Args:
            interval: Time in seconds between polls
            
        Returns:
            Optional response from callback if a new message was processed
        """
        # This method doesn't need to do anything as messages are processed in the background thread
        # It's included for compatibility with the old interface
        return None
    
    def get_node_info(self, node_id: Optional[str] = None) -> Dict:
        """
        Get information about a node
        
        Args:
            node_id: Node ID to get info for (None for all nodes)
            
        Returns:
            Dict with node information
        """
        if not self.connected or not self.interface:
            logger.error("Not connected to Meshtastic device")
            return {}
        
        try:
            if node_id:
                # Get info for specific node
                if node_id in self.interface.nodes:
                    return self.interface.nodes[node_id]
                else:
                    logger.warning(f"Node {node_id} not found")
                    return {}
            else:
                # Get info for all nodes
                return self.interface.nodes
                
        except Exception as e:
            logger.error(f"Error getting node info: {str(e)}")
            return {}
