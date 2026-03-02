import argparse
import asyncio
import os
import sys
from getpass import getpass
from pathlib import Path
from typing import Optional

from .putergenai import PuterClient

TOKEN_FILE = Path.home() / ".puter_token"


def save_token(token: str):
    try:
        with open(TOKEN_FILE, "w") as f:
            f.write(token)
        print(f"Token saved to {TOKEN_FILE}")
    except Exception as e:
        print(f"Warning: Could not save token to file: {e}")


def load_token() -> Optional[str]:
    if os.environ.get("PUTER_API_TOKEN"):
        return os.environ["PUTER_API_TOKEN"]
    if TOKEN_FILE.exists():
        try:
            with open(TOKEN_FILE, "r") as f:
                return f.read().strip()
        except Exception:
            return None
    return None


async def login(args):
    print("Puter.com Login")
    username = input("Username: ")
    password = getpass("Password: ")

    async with PuterClient() as client:
        try:
            token = await client.login(username, password)
            save_token(token)
            print("Login successful!")
        except Exception as e:
            print(f"Login failed: {e}")
            sys.exit(1)


async def chat(args):
    token = load_token()
    if not token:
        print("Not logged in. Please run 'puter login' or set PUTER_API_TOKEN.")
        sys.exit(1)

    async with PuterClient(token=token) as client:
        print(f"Starting chat with model {args.model} (type 'exit' to quit)")
        print("-" * 50)

        while True:
            try:
                prompt = input("You: ")
                if prompt.lower() in ("exit", "quit"):
                    break
                if not prompt.strip():
                    continue

                print("AI: ", end="", flush=True)
                if args.stream:
                    async for chunk, _ in await client.ai_chat(
                        prompt, options={"model": args.model, "stream": True}
                    ):
                        print(chunk, end="", flush=True)
                    print()
                else:
                    result = await client.ai_chat(
                        prompt, options={"model": args.model, "stream": False}
                    )
                    # Attempt to extract content from various response formats
                    content = "No response content found."

                    if isinstance(result, dict):
                        res = result.get("response", {})

                        # Claude/OpenAI standard format
                        if "choices" in res and res["choices"]:
                            content = res["choices"][0].get("message", {}).get("content", "")
                        # Puter specific format
                        elif "result" in res:
                            result_data = res["result"]
                            if isinstance(result_data, dict) and "message" in result_data:
                                content = result_data["message"].get("content", "")
                            elif isinstance(result_data, str):
                                content = result_data
                        elif "text" in res:
                            content = res["text"]

                    print(content)

            except KeyboardInterrupt:
                print("\nExiting...")
                break
            except Exception as e:
                print(f"\nError: {e}")


async def list_models(args):
    token = load_token()
    # Token not strictly required for some public endpoints but good practice
    async with PuterClient(token=token) as client:
        try:
            models = await client.get_available_models()
            print(f"Available Models ({len(models.get('models', []))}):")
            for m in models.get("models", []):
                if isinstance(m, dict):
                    print(f" - {m.get('id', 'unknown')}")
                else:
                    print(f" - {m}")
        except Exception as e:
            print(f"Error fetching models: {e}")


async def kv_cmd(args):
    token = load_token()
    if not token:
        print("Not logged in. Please run 'puter login'.")
        sys.exit(1)

    async with PuterClient(token=token) as client:
        try:
            if args.kv_action == "set":
                # Value is passed as string, but Puter KV might accept JSON?
                # For CLI simplicity, treat as string.
                await client.kv_set(args.key, args.value)
                print(f"OK: Set {args.key}")
            elif args.kv_action == "get":
                val = await client.kv_get(args.key)
                if val is None:
                    print("(null)")
                else:
                    print(val)
            elif args.kv_action == "delete":
                success = await client.kv_delete(args.key)
                print(f"Deleted: {success}")
            elif args.kv_action == "list":
                keys = await client.kv_list()
                print("Keys:")
                for k in keys:
                    print(f" - {k}")
        except Exception as e:
            print(f"KV Error: {e}")


def main():
    parser = argparse.ArgumentParser(description="Puter CLI Tool")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Login
    subparsers.add_parser("login", help="Login to Puter and save token")

    # Chat
    chat_parser = subparsers.add_parser("chat", help="Start an AI chat session")
    chat_parser.add_argument(
        "--model", default="gpt-4o-mini", help="Model to use (default: gpt-4o-mini)"
    )
    chat_parser.add_argument(
        "--no-stream", action="store_false", dest="stream", help="Disable streaming response"
    )

    # Models
    subparsers.add_parser("models", help="List all available AI models")

    # KV
    kv_parser = subparsers.add_parser("kv", help="Key-Value Store operations")
    kv_sub = kv_parser.add_subparsers(dest="kv_action", required=True)

    kv_set = kv_sub.add_parser("set", help="Set a value")
    kv_set.add_argument("key", help="Key name")
    kv_set.add_argument("value", help="Value to store")

    kv_get = kv_sub.add_parser("get", help="Get a value")
    kv_get.add_argument("key", help="Key name")

    kv_del = kv_sub.add_parser("delete", help="Delete a key")
    kv_del.add_argument("key", help="Key name")

    kv_list = kv_sub.add_parser("list", help="List all keys")

    args = parser.parse_args()

    if args.command == "login":
        asyncio.run(login(args))
    elif args.command == "chat":
        asyncio.run(chat(args))
    elif args.command == "models":
        asyncio.run(list_models(args))
    elif args.command == "kv":
        asyncio.run(kv_cmd(args))


if __name__ == "__main__":
    main()
