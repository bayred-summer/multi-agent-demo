"""Minimal test script for Gemini SDK v1 provider."""

import os
from src.invoke import invoke

def main():
    # Set adapter to sdk (google-genai)
    # Ensure GEMINI_API_KEY is set in environment if testing for real
    
    prompt = "Hello, who are you?"
    print(f"--- Calling Gemini SDK with prompt: {prompt} ---")
    
    try:
        result = invoke(
            "gemini",
            prompt,
            provider_options={
                "adapter": "sdk",
                "model": "gemini-2.0-flash",
            }
        )
        print("
--- Result ---")
        print(f"Text: {result['text']}")
        print(f"Session ID: {result['session_id']}")
        print(f"Elapsed: {result['elapsed_ms']}ms")
    except ImportError as e:
        print(f"
ImportError: {e}")
    except Exception as e:
        print(f"
Error: {e}")

if __name__ == "__main__":
    main()
