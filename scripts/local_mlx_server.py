"""Local MLX inference server for Qwen3.x models (runs on localhost:18080).

Usage:
    python scripts/local_mlx_server.py --model-path /Users/siva/models/qwen3.6-35b-4bit

This starts a lightweight HTTP server that accepts POST /generate with a prompt
and returns the model's text response. The DATA Pro API routes "mlx" backend
requests here when Local MLX is selected in Settings.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from uvicorn import Config, Server


class GenerateRequest(BaseModel):
    prompt: str
    max_tokens: int = 2048
    temperature: float = 0.2


app = FastAPI(title="Local MLX Inference")

_model = None
_processor = None
_device = None


def _load_model(model_path: str):
    """Lazy-load the model on first request."""
    global _model, _processor, _device

    if _model is not None:
        return

    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer

    path = Path(model_path)
    if not path.exists():
        raise FileNotFoundError(f"Model path not found: {model_path}")

    print(f"[mlx-server] Loading model from {model_path} ...", file=sys.stderr, flush=True)
    _tokenizer = AutoTokenizer.from_pretrained(str(path), trust_remote_code=True)
    _model = AutoModelForCausalLM.from_pretrained(
        str(path),
        torch_dtype=torch.float16,
        device_map="auto",
        load_in_4bit=True,
    )
    _processor = _tokenizer
    print(f"[mlx-server] Model loaded.", file=sys.stderr, flush=True)


@app.post("/generate")
async def generate(req: GenerateRequest):
    if _model is None:
        try:
            model_path = app.state.model_path
        except AttributeError:
            raise HTTPException(status_code=503, detail="Model not configured")
        _load_model(model_path)

    messages = [{"role": "user", "content": req.prompt}]
    text = _processor.apply_chat_template(
        messages, tokenize=False, add_generation_prompt=True
    )
    inputs = _processor(text, return_tensors="pt").to(_model.device)

    with torch.no_grad():
        outputs = _model.generate(
            **inputs,
            max_new_tokens=req.max_tokens,
            temperature=max(req.temperature, 0.01),
            do_sample=req.temperature > 0.01,
        )

    generated_ids = outputs[:, inputs["input_ids"].shape[1]:]
    response = _processor.decode(generated_ids[0], skip_special_tokens=True)
    return {"response": response}


def main():
    parser = argparse.ArgumentParser(description="Local MLX inference server")
    parser.add_argument(
        "--model-path", required=True, help="Path to the model directory"
    )
    parser.add_argument("--port", type=int, default=18080)
    args = parser.parse_args()

    app.state.model_path = args.model_path
    config = Config(app=app, host="127.0.0.1", port=args.port, log_level="warning")
    server = Server(config)
    print(f"[mlx-server] Listening on 127.0.0.1:{args.port}", file=sys.stderr, flush=True)
    server.run()


if __name__ == "__main__":
    main()
