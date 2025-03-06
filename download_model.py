#!/usr/bin/env python3
import os
import argparse
import logging
import requests
from pathlib import Path
from tqdm import tqdm
from transformers import AutoTokenizer, AutoModelForCausalLM

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_file(url, output_path):
    """Download a file with progress bar"""
    response = requests.get(url, stream=True)
    response.raise_for_status()
    
    total_size = int(response.headers.get('content-length', 0))
    block_size = 1024  # 1 Kibibyte
    
    with open(output_path, 'wb') as file, tqdm(
            desc=output_path.name,
            total=total_size,
            unit='iB',
            unit_scale=True,
            unit_divisor=1024,
    ) as bar:
        for data in response.iter_content(block_size):
            size = file.write(data)
            bar.update(size)

def main():
    parser = argparse.ArgumentParser(description="Download model from HuggingFace")
    parser.add_argument("--model", type=str, default="TheBloke/Mistral-7B-Instruct-v0.2-GGUF", 
                        help="Model ID on HuggingFace")
    parser.add_argument("--output-dir", type=str, default="./models", 
                        help="Directory to save the model")
    parser.add_argument("--gguf", action="store_true", 
                        help="Download GGUF model directly")
    parser.add_argument("--gguf-file", type=str, default="mistral-7b-instruct-v0.2.Q4_K_M.gguf",
                        help="GGUF file name to download")
    parser.add_argument("--hf-token", type=str, default=None,
                        help="HuggingFace token for private repos")
    args = parser.parse_args()
    
    model_id = args.model
    output_dir = args.output_dir
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    logger.info(f"Downloading model {model_id} to {output_dir}")
    
    try:
        if args.gguf:
            # Download GGUF model directly
            logger.info(f"Downloading GGUF model file: {args.gguf_file}")
            output_path = Path(output_dir) / args.gguf_file
            
            # Direct URL for a HuggingFace file
            url = f"https://huggingface.co/{model_id}/resolve/main/{args.gguf_file}"
            
            # Include token if provided (for private repos)
            headers = {}
            if args.hf_token:
                headers['Authorization'] = f"Bearer {args.hf_token}"
            
            logger.info(f"Downloading from {url}")
            response = requests.get(url, headers=headers, stream=True)
            total_size = int(response.headers.get('content-length', 0))
            logger.info(f"Total file size: {total_size / (1024 * 1024):.2f} MB")
            
            download_file(url, output_path)
            logger.info(f"GGUF model successfully downloaded to {output_path}")
        else:
            # Download using transformers
            logger.info("Downloading tokenizer...")
            tokenizer = AutoTokenizer.from_pretrained(model_id)
            tokenizer.save_pretrained(os.path.join(output_dir, os.path.basename(model_id)))
            
            logger.info("Downloading model...")
            model = AutoModelForCausalLM.from_pretrained(model_id, trust_remote_code=True)
            model.save_pretrained(os.path.join(output_dir, os.path.basename(model_id)))
            
            logger.info(f"Model and tokenizer successfully downloaded to {output_dir}")
        
    except Exception as e:
        logger.error(f"Error downloading model: {str(e)}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
