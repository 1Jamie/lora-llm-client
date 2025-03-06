import logging
import time
import threading
from typing import Dict, Any, List, Optional

from model_loader import ModelLoader

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Agent:
    def __init__(
        self,
        model_loader: ModelLoader,
        meshtastic_client,  # Can be either MeshtasticClient or MeshtasticMqttClient
        system_prompt: str = "You are a helpful AI assistant.",
        max_conversation_length: int = 10
    ):
        """
        Initialize the conversational agent
        
        Args:
            model_loader: Initialized ModelLoader instance
            meshtastic_client: Initialized Meshtastic client instance
            system_prompt: System prompt to guide the LLM's behavior
            max_conversation_length: Maximum length of conversation history
        """
        self.model_loader = model_loader
        self.meshtastic_client = meshtastic_client
        self.system_prompt = system_prompt
        self.max_conversation_length = max_conversation_length
        
        # Conversation history
        self.conversations = {}  # User ID -> conversation history
    
    def shutdown(self):
        """
        Shutdown the agent
        """
        logger.info("Shutting down agent")
        if hasattr(self.meshtastic_client, 'disconnect') and callable(self.meshtastic_client.disconnect):
            self.meshtastic_client.disconnect()
    
    def process_message(self, message):
        """
        Process a message from the Meshtastic client
        
        Args:
            message: Message object from the Meshtastic client
            
        Returns:
            str: Response text or None if no response should be sent
        """
        try:
            # Extract message data
            text = message.get('text', '')
            from_id = message.get('from_id', 'unknown')
            
            # Skip empty messages
            if not text:
                logger.warning("Empty message received")
                return None
            
            # Skip messages that are too short (likely noise)
            if len(text.strip()) < 2:
                logger.warning(f"Message too short, ignoring: {text}")
                return None
            
            # Skip system messages and status updates
            if text.startswith("📢") or text.startswith("System:"):
                logger.info(f"Ignoring system message: {text}")
                return None
            
            # Generate response
            logger.info(f"Generating response for message from {from_id}: {text[:50]}...")
            response = self.generate_response(text, user_id=from_id)
            
            if response:
                logger.info(f"Generated response for {from_id}: {response[:50]}...")
                return response
            else:
                logger.warning("Failed to generate response")
                return "I'm sorry, I couldn't generate a response at this time."
            
        except Exception as e:
            logger.error(f"Error processing message: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return "I encountered an error processing your message. Please try again."
    
    def generate_response(self, message, user_id=None):
        """
        Generate a response to a message
        """
        try:
            # Skip empty messages
            if not message:
                logger.warning("Empty message received")
                return None
            
            # Skip messages that are too short (likely noise)
            if len(message.strip()) < 2:
                logger.warning(f"Message too short, ignoring: {message}")
                return None
            
            # Skip system messages and status updates
            if message.startswith("📢") or message.startswith("System:"):
                logger.info(f"Ignoring system message: {message}")
                return None
            
            # Get or create conversation for this user
            if user_id is None:
                user_id = "default"
            
            if user_id not in self.conversations:
                logger.info(f"Creating new conversation for user {user_id}")
                self.conversations[user_id] = []
            
            # Add user message to conversation
            self.conversations[user_id].append({"role": "user", "content": message})
            
            # Truncate conversation if it's too long
            if len(self.conversations[user_id]) > self.max_conversation_length:
                # Keep system message if present, and recent messages
                if self.conversations[user_id][0]["role"] == "system":
                    self.conversations[user_id] = [self.conversations[user_id][0]] + self.conversations[user_id][-(self.max_conversation_length-1):]
                else:
                    self.conversations[user_id] = self.conversations[user_id][-self.max_conversation_length:]
            
            # Prepare conversation for model
            conversation = self.conversations[user_id].copy()
            
            # Add system message if not present
            if len(conversation) == 0 or conversation[0]["role"] != "system":
                conversation.insert(0, {"role": "system", "content": self.system_prompt})
            
            # Generate response
            logger.debug(f"Generating response for: {message}")
            response = self.model_loader.generate_response(conversation)
            
            # Add assistant response to conversation
            if response:
                self.conversations[user_id].append({"role": "assistant", "content": response})
                logger.info(f"Generated response: {response[:100]}...")
            else:
                logger.warning("Failed to generate response")
            
            return response
        
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            return "I'm sorry, I encountered an error processing your message."
