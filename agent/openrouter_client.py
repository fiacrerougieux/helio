"""
OpenRouter API client for chat completions.
Compatible with OllamaClient interface.
"""

import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
from typing import List, Dict, Optional


class OpenRouterClient:
    """OpenRouter API client with Ollama-compatible interface."""

    def __init__(self, model: str = "openai/gpt-oss-120b"):
        """
        Initialize OpenRouter client.

        Args:
            model: Model identifier (default: "openai/gpt-oss-120b")

        Environment:
            OPENROUTER_API_KEY: Your OpenRouter API key
        """
        self.base_url = "https://openrouter.ai/api/v1"
        self.model = model
        self.api_key = os.environ.get("OPENROUTER_API_KEY")

        if not self.api_key:
            raise ValueError(
                "OPENROUTER_API_KEY environment variable not set.\n"
                "Get your key at: https://openrouter.ai/keys\n"
                "Then set it with: setx OPENROUTER_API_KEY your-key-here"
            )

    def chat(
        self,
        messages: List[Dict[str, str]],
        stream: bool = False,
        temperature: float = 0.7,
        response_schema: Optional[Dict] = None,
        **kwargs
    ) -> Dict | str:
        """
        Send chat request to OpenRouter API.

        Args:
            messages: List of {"role": "user"|"assistant"|"system", "content": "..."}
            stream: Whether to stream response (not implemented)
            temperature: Sampling temperature
            response_schema: Optional JSON schema for structured output
            **kwargs: Additional options (top_k, seed, etc.)

        Returns:
            If response_schema: Returns the assistant's message content as a string
            Otherwise: {"message": {"role": "assistant", "content": "..."}, ...} (Ollama-compatible format)
        """
        url = f"{self.base_url}/chat/completions"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/fiacrerougieux/sun-sleuth-dev",
            "X-Title": "Helio - PV Simulation Companion"
        }

        # Build OpenAI-compatible payload
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }

        # Add structured output support
        if response_schema:
            payload["response_format"] = {
                "type": "json_schema",
                "json_schema": {
                    "name": "pv_spec",
                    "strict": True,
                    "schema": response_schema
                }
            }

        # Add optional parameters
        if "top_k" in kwargs:
            # OpenRouter uses top_p, not top_k
            # top_k=1 means greedy, so use top_p=0.1 as approximation
            if kwargs["top_k"] == 1:
                payload["top_p"] = 0.1

        if "seed" in kwargs:
            payload["seed"] = kwargs["seed"]

        try:
            response = requests.post(url, headers=headers, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()

            # Convert OpenAI format to Ollama format
            if "choices" in data and len(data["choices"]) > 0:
                choice = data["choices"][0]
                message = choice.get("message", {})
                content = message.get("content", "")

                # If response_schema was provided, return just the content string
                if response_schema:
                    return content

                # Otherwise return Ollama-compatible format
                return {
                    "message": {
                        "role": message.get("role", "assistant"),
                        "content": content
                    },
                    "done": True,
                    "total_duration": data.get("usage", {}).get("total_tokens", 0),
                    "load_duration": 0,
                    "prompt_eval_count": data.get("usage", {}).get("prompt_tokens", 0),
                    "eval_count": data.get("usage", {}).get("completion_tokens", 0)
                }
            else:
                return {
                    "error": "No response from OpenRouter",
                    "message": {"role": "assistant", "content": "Error: Empty response"}
                }

        except requests.exceptions.RequestException as e:
            error_msg = str(e)
            try:
                error_data = e.response.json() if hasattr(e, 'response') else {}
                error_msg = error_data.get("error", {}).get("message", error_msg)
            except:
                pass

            return {
                "error": error_msg,
                "message": {"role": "assistant", "content": f"Error communicating with OpenRouter: {error_msg}"}
            }

    def generate(self, prompt: str, **kwargs) -> str:
        """Simple generate endpoint for single-turn completions."""
        messages = [{"role": "user", "content": prompt}]
        response = self.chat(messages, **kwargs)
        return response.get("message", {}).get("content", "")

    def test_connection(self) -> bool:
        """Test if OpenRouter API is reachable."""
        try:
            # Simple test with minimal prompt
            response = self.chat(
                messages=[{"role": "user", "content": "test"}],
                temperature=0.0
            )
            return "error" not in response
        except Exception as e:
            print(f"Cannot connect to OpenRouter: {e}")
            return False
