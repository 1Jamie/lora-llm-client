#!/usr/bin/env python3
import os
import argparse
import logging
import requests
import shutil
from pathlib import Path
from huggingface_hub import hf_hub_download

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_gguf_model(model_id, filename, output_dir, output_filename=None):
    """
    Download a GGUF model file from Hugging Face
    
    Args:
        model_id: HuggingFace model ID (e.g., 'TheBloke/DeepSeek-LLM-7B-Chat-GGUF')
        filename: Name of the GGUF file (e.g., 'deepseek-llm-7b-chat.Q4_K_M.gguf')
        output_dir: Directory to save the model
        output_filename: Optional name for the output file
    
    Returns:
        str: Path to the downloaded model
    """
    try:
        # Create output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)
        
        logger.info(f"Downloading {filename} from {model_id}")
        
        # Download the model file
        temp_path = hf_hub_download(
            repo_id=model_id,
            filename=filename,
            local_dir=output_dir,
            local_dir_use_symlinks=False
        )
        
        # If output filename is specified, rename the file
        if output_filename:
            final_path = os.path.join(output_dir, output_filename)
            shutil.copy2(temp_path, final_path)
            logger.info(f"Model copied to {final_path}")
            return final_path
        else:
            logger.info(f"Model downloaded successfully to {temp_path}")
            return temp_path
    
    except Exception as e:
        logger.error(f"Error downloading model: {str(e)}")
        raise

def main():
    parser = argparse.ArgumentParser(description="Download GGUF model from HuggingFace")
    parser.add_argument("--model-id", type=str, default="TheBloke/DeepSeek-LLM-7B-Chat-GGUF", 
                        help="Model ID on HuggingFace")
    parser.add_argument("--filename", type=str, default="deepseek-llm-7b-chat.Q4_K_M.gguf", 
                        help="Filename of the GGUF model")
    parser.add_argument("--output-dir", type=str, default="./models", 
                        help="Directory to save the model")
    parser.add_argument("--output-filename", type=str, default="DeepSeek-R1-Distill-Llama-8B-Q4_K_M.gguf",
                        help="Name to save the model file as (defaults to original filename)")
    args = parser.parse_args()
    
    try:
        download_gguf_model(args.model_id, args.filename, args.output_dir, args.output_filename)
        return 0
    except Exception as e:
        logger.error(f"Download failed: {e}")
        return 1

if __name__ == "__main__":
    exit(main())
