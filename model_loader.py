import os
import logging
from typing import Union, Optional, List, Dict, Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, Pipeline, TextIteratorStreamer
from transformers import pipeline

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class ModelLoader:
    def __init__(
        self,
        model_id: str,
        local_path: Optional[str] = None,
        use_gguf: bool = False,
        device: str = "cuda" if torch.cuda.is_available() else "cpu",
        **kwargs
    ):
        self.model_id = model_id
        self.local_path = local_path
        self.use_gguf = use_gguf
        self.device = device
        self.kwargs = kwargs
        
        self.model = None
        self.tokenizer = None
        self.pipeline = None
        
        logger.info(f"Initializing model loader for {model_id}")
        logger.info(f"Using device: {device}")

    def load_model(self):
        """
        Load the model either using transformers or llama-cpp-python based on format
        """
        if self.use_gguf:
            return self._load_gguf_model()
        else:
            return self._load_transformers_model()
    
    def _load_transformers_model(self):
        """
        Load model using HuggingFace transformers
        """
        logger.info("Loading model with transformers (safetensors format)")
        
        # Determine the model path (local or from HuggingFace)
        model_path = self.local_path if self.local_path else self.model_id
        
        try:
            # Load tokenizer
            logger.info(f"Loading tokenizer from {model_path}")
            self.tokenizer = AutoTokenizer.from_pretrained(
                model_path,
                trust_remote_code=True,
                padding_side="left"
            )
            
            # Ensure the tokenizer has the necessary special tokens
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
                
            # Load model with appropriate configurations for efficient inference
            logger.info(f"Loading model from {model_path}")
            self.model = AutoModelForCausalLM.from_pretrained(
                model_path,
                torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                device_map="auto",
                trust_remote_code=True,
                load_in_4bit=True if self.device == "cuda" else False,
            )
            
            # Create pipeline with proper settings for the specific model family
            if "qwen" in model_path.lower() or "deepseek" in model_path.lower():
                logger.info("Detected Qwen/DeepSeek model, using specialized settings")
                
                # Define a custom generation function for Qwen/DeepSeek models
                def generate_text(prompt, max_new_tokens=512, temperature=0.7, top_p=0.9):
                    inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
                    
                    # Generate with appropriate parameters
                    outputs = self.model.generate(
                        **inputs,
                        max_new_tokens=max_new_tokens,
                        temperature=temperature,
                        top_p=top_p,
                        do_sample=temperature > 0,
                        pad_token_id=self.tokenizer.pad_token_id
                    )
                    
                    # Decode the generated tokens
                    generated_text = self.tokenizer.decode(
                        outputs[0][inputs["input_ids"].shape[1]:], 
                        skip_special_tokens=True
                    )
                    
                    return generated_text
                
                # Store the custom generate function
                self.pipeline = generate_text
            else:
                # Standard pipeline for other models
                self.pipeline = pipeline(
                    "text-generation",
                    model=self.model,
                    tokenizer=self.tokenizer,
                    torch_dtype=torch.float16 if self.device == "cuda" else torch.float32,
                    device_map="auto",
                    return_full_text=False
                )
            
            logger.info("Successfully loaded model with transformers")
            return True
            
        except Exception as e:
            logger.error(f"Error loading model with transformers: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def _load_gguf_model(self):
        """
        Load model using llama-cpp-python (for GGUF format)
        """
        logger.info("Loading model with llama-cpp-python (GGUF format)")
        
        try:
            from llama_cpp import Llama
            
            # Ensure we have a local path for GGUF format
            if not self.local_path:
                logger.error("No local path provided for GGUF model")
                logger.info("Please download the model first with: python download_model.py --gguf")
                raise ValueError("Local path must be provided for GGUF models")
            
            # Check if the model file exists
            if not os.path.exists(self.local_path):
                logger.error(f"Model file not found at: {self.local_path}")
                logger.info("Please download the model first with: python download_model.py --gguf")
                raise FileNotFoundError(f"GGUF model file not found: {self.local_path}")
            
            # Log model file size and path
            file_size_bytes = os.path.getsize(self.local_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            logger.info(f"Loading GGUF model from {self.local_path} ({file_size_mb:.2f} MB)")
            
            # Load the model with appropriate settings
            self.model = Llama(
                model_path=self.local_path,
                n_gpu_layers=-1,       # Use all available GPU layers
                n_ctx=4096,            # Context window size
                n_batch=512,           # Batch size for prompt processing
                verbose=False          # Disable verbose output
            )
            
            # Create a wrapper function to match the transformers interface
            def generate_text(prompt, max_new_tokens=100, temperature=0.7, top_p=0.9):
                result = self.model(
                    prompt,
                    max_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    echo=False
                )
                return result["choices"][0]["text"]
            
            # Store the generate function as our "pipeline"
            self.pipeline = generate_text
            
            logger.info("Successfully loaded model with llama-cpp-python")
            return True
            
        except ImportError as e:
            logger.error(f"Error importing llama-cpp-python: {str(e)}")
            logger.info("Try installing with: pip install llama-cpp-python")
            return False
        except (ValueError, FileNotFoundError) as e:
            # These errors are already logged above
            return False
        except Exception as e:
            logger.error(f"Error loading model with llama-cpp-python: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return False
    
    def generate(self, prompt: str, max_new_tokens: int = 512, temperature: float = 0.7, top_p: float = 0.9) -> str:
        """
        Generate text with the loaded model
        """
        if not self.pipeline:
            raise RuntimeError("Model not loaded. Call load_model() first.")
        
        try:
            if self.use_gguf or isinstance(self.pipeline, type(lambda: None)):
                # For GGUF models or custom generation functions
                result = self.pipeline(prompt, max_new_tokens=max_new_tokens, temperature=temperature, top_p=top_p)
                return result
            else:
                # For transformers pipeline
                result = self.pipeline(
                    prompt,
                    max_new_tokens=max_new_tokens,
                    temperature=temperature,
                    top_p=top_p,
                    num_return_sequences=1,
                    do_sample=temperature > 0,
                    pad_token_id=self.tokenizer.eos_token_id
                )
                return result[0]["generated_text"]
                
        except Exception as e:
            logger.error(f"Error generating text: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error generating response: {str(e)}"

    def generate_response(self, conversation: List[Dict[str, str]], max_new_tokens: int = 512, temperature: float = 0.7, top_p: float = 0.9) -> str:
        """
        Generate a response to a conversation in the format expected by the agent
        
        Args:
            conversation: List of conversation messages in the format [{"role": "system", "content": "..."}, {"role": "user", "content": "..."}, ...]
            max_new_tokens: Maximum number of tokens to generate
            temperature: Temperature for sampling
            top_p: Top-p for nucleus sampling
            
        Returns:
            str: Generated response
        """
        if not self.pipeline:
            raise RuntimeError("Model not loaded. Call load_model() first.")
            
        try:
            # Format the conversation into a prompt
            prompt = ""
            for message in conversation:
                role = message["role"]
                content = message["content"]
                
                if role == "system":
                    prompt += f"{content}\n\n"
                elif role == "user":
                    prompt += f"Human: {content}\n"
                elif role == "assistant":
                    prompt += f"Assistant: {content}\n"
            
            # Add the final assistant prefix
            prompt += "Assistant: "
            
            # Generate response
            raw_response = self.generate(prompt, max_new_tokens, temperature, top_p)
            
            # Clean up the response
            response = self._clean_response(raw_response)
            
            return response
            
        except Exception as e:
            logger.error(f"Error generating response: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return f"Error generating response: {str(e)}"

    def _clean_response(self, response: str) -> str:
        """
        Clean the model's response
        
        Args:
            response: Raw response from the model
            
        Returns:
            str: Cleaned response
        """
        # Check if response is None or empty
        if not response:
            return "I apologize, but I couldn't generate a response."
            
        # Remove any trailing "Human:" or similar
        if "Human:" in response:
            response = response.split("Human:")[0]
        
        # Remove any "Assistant:" prefix that might be included
        if response.startswith("Assistant:"):
            response = response[len("Assistant:"):].strip()
            
        return response.strip()
