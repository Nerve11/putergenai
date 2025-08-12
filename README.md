# PutergenAI: Python SDK for Puter.js

[![Python Version](https://img.shields.io/badge/Python-Version-3.11-blue)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-Passed-brightgreen)](https://github.com/your-repo/putergenai/actions/workflows/tests.yml)

## Overview

PutergenAI is a lightweight, robust Python SDK for interacting with the Puter.js API, an open-source cloud operating system focused on privacy and AI capabilities. This SDK provides a clean interface for AI chat completions (supporting multiple models like GPT, Claude, Grok, etc.), file system operations (read/write/delete), and utility AI functions (text-to-image, image-to-text, text-to-speech).

### Recent Updates (v0.1.01)
- Improved input sanitization and security throughout the SDK
- Added `.gitignore` for Python, screenshots, and development artifacts
- Added `requirements.txt` (only `requests` required)
- Enhanced error handling and logging
- Updated documentation and versioning

## Installation

Install via pip (recommended for production):

```bash
pip install putergenai
```

For development, clone the repo and install locally:

```bash
git clone https://github.com/nerve11/putergenai.git
cd putergenai
pip install -e .
```

Dependencies:
- `requests` (>=2.32.0) for HTTP communication.

No other external libs are required, keeping the footprint small. Tested on Python 3.8–3.12 across Linux, macOS, and Windows.

**Pro Tip**: Use a virtual environment (e.g., `venv` or `poetry`) to isolate dependencies. If you encounter SSL issues, ensure your system's CA certificates are up-to-date.

**New:** See `.gitignore` and `requirements.txt` for project setup and dependency management.

## Quick Start

```python
from putergenai import PuterClient

# Initialize and login
client = PuterClient()
client.login("your_username", "your_password")

# AI Chat example (non-streaming)
messages = [{"role": "user", "content": "What is the meaning of life?"}]
response = client.ai_chat(messages=messages, options={"model": "gpt-5"}, strict_model=True)
print("Response:", response["response"]["result"]["message"]["content"])
print("Used Model:", response["used_model"])

# Streaming example
gen = client.ai_chat(messages=messages, options={"model": "claude-sonnet-4", "stream": True})
for content, used_model in gen:
    print(content, end='', flush=True)
print("\nUsed Model:", used_model)

# File system example
client.fs_write("test.txt", "Hello, Puter!")
content = client.fs_read("test.txt").decode('utf-8')
print("File content:", content)
client.fs_delete("test.txt")
```

This snippet demonstrates authentication, AI chat (with model enforcement), and basic FS ops. Run with `test_mode=True` to simulate without costs.

**Best Practice**: Always wrap API calls in try-except blocks to handle `ValueError` for authentication issues or network errors. For production, implement exponential backoff on retries.

**Security Note:** All user inputs and file paths are now sanitized. Sensitive data is never logged. See the updated `client.py` for details.

## API Syntax and Reference

The SDK centers around the `PuterClient` class. All methods are synchronous for simplicity; for async, wrap in `asyncio` or use threading.

### Initialization
```python
client = PuterClient(token="optional_pre_existing_token")
```
- If `token` is provided, skips login. Otherwise, call `login()`.

### Authentication
```python
client.login(username: str, password: str) -> str
```
- Returns the auth token.
- Raises `ValueError` on failure (e.g., invalid credentials).

### AI Chat
```python
client.ai_chat(
    messages: List[Dict[str, Any]],
    options: Optional[Dict[str, Any]] = None,
    test_mode: bool = False,
    image_url: Optional[Union[str, List[str]]] = None,
    prompt: Optional[Union[str, List[Dict[str, Any]]]] = None,
    strict_model: bool = False
) -> Union[Dict[str, Any], Generator[tuple[str, str], None, None]]
```
- **messages**: List of chat messages (e.g., `[{"role": "user", "content": "Hi"}]`).
- **options**: Dict with `model` (str, e.g., "gpt-5"), `stream` (bool), `temperature` (float 0-2).
- **test_mode**: Use test API (no credits consumed).
- **image_url**: For vision models (e.g., GPT-4o).
- **prompt**: Alternative to messages for simple queries.
- **strict_model**: If True, raises error on model fallback.
- **Returns**:
  - Non-stream: `{"response": dict, "used_model": str}`.
  - Stream: Generator yielding `(content_chunk, used_model)`.

**Syntax Notes**:
- Models are passed explicitly in payload for reliability.
- Handles server fallbacks (e.g., GPT-5 → GPT-4.1-nano) with warnings or errors.
- Retries up to 3 times on availability issues, auto-enabling `test_mode` if needed.

### File System Operations
```python
client.fs_write(path: str, content: Union[str, bytes, Any]) -> Dict[str, Any]
client.fs_read(path: str) -> bytes
client.fs_delete(path: str) -> None
```
- `path`: Cloud path (e.g., "test.txt").
- `content`: String, bytes, or file-like object.
- Raises `ValueError` or `requests.RequestException` on failure.

### Other AI Utilities
```python
client.ai_img2txt(image: Union[str, Any], test_mode: bool = False) -> str
client.ai_txt2img(prompt: str, test_mode: bool = False) -> str
client.ai_txt2speech(text: str, options: Optional[Dict[str, Any]] = None) -> bytes
```
- `ai_img2txt`: OCR from URL or file.
- `ai_txt2img`: Generates image URL from prompt.
- `ai_txt2speech`: Returns MP3 bytes.

**Error Handling**: All methods raise exceptions on failure. Use try-except for resilience.

## Use Cases


### 1. **Interactive AI Chat Bot** (e.g., Customer Support)
Use streaming for real-time responses. Handle model fallbacks for reliability.
```python
messages = [{"role": "system", "content": "You are a helpful assistant."}]
while True:
    user_input = input("You: ")
    if user_input == "exit": break
    messages.append({"role": "user", "content": user_input})
    gen = client.ai_chat(messages, options={"model": "gpt-5", "stream": True}, strict_model=False)
    print("Assistant: ", end='')
    for content, _ in gen:
        print(content, end='', flush=True)
    print()
```

**Why it works**: Streaming reduces latency; `strict_model=False` ensures uptime if GPT-5 is unavailable.

### 2. **File Backup Tool** (Cloud Storage Integration)
Sync local files to Puter.js FS.
```python
def backup_file(local_path: str, cloud_path: str):
    with open(local_path, 'rb') as f:
        client.fs_write(cloud_path, f)
    print(f"Backed up {local_path} to {cloud_path}")
```

**Pro Tip**: Implement hashing (e.g., SHA-256) to avoid unnecessary uploads. Use threading for large files.

### 3. **AI Content Generation Pipeline** (e.g., Blog Post Generator)
Generate text, convert to speech, and store.
```python
prompt = "Write a blog post about AI ethics."
response = client.ai_chat(prompt=prompt, options={"model": "claude-3-5-sonnet"})
content = response["response"]["result"]["message"]["content"]
client.fs_write("blog_post.txt", content)
audio = client.ai_txt2speech(content)
with open("blog_post.mp3", "wb") as f:
    f.write(audio)
```

**Best Practice**: Batch requests for high-volume use; monitor costs via Puter.js dashboard.

### 4. **Vision-Based Analysis** (e.g., Image Description)
```python
description = client.ai_img2txt("https://example.com/image.jpg", test_mode=True)
print("Image description:", description)
```

**Limitation Note**: Vision models (e.g., GPT-4o) may require specific drivers; test with `test_mode=True` first.


## Error Handling and Best Practices

- **Common Errors**:
    - `ValueError`: Invalid credentials or model mismatch (with `strict_model=True`).
    - `requests.RequestException`: Network issues; implement retries with exponential backoff.
    - Model fallback: Server may use a different model (e.g., GPT-5 → GPT-4.1-nano); check `used_model` in response.

- **Best Practices**:
    - **Security**: Never hardcode credentials; use environment variables (e.g., `os.getenv("PUTER_USERNAME")`). All user input is sanitized.
    - **Performance**: For streaming, use in async contexts (e.g., `asyncio`) to avoid blocking.
    - **Costs**: Always set `test_mode=True` in dev; monitor usage via Puter.js API.
    - **Testing**: Write unit tests for your integration (e.g., mock responses with `responses` lib).
    - **Versioning**: Pin to a specific SDK version in `requirements.txt` (e.g., `putergenai==0.1.01`).
    - **Scalability**: For multi-user apps, pool clients or use session tokens.

If you encounter issues, check logs (enable DEBUG via `logging.basicConfig(level=logging.DEBUG)`) and verify your Puter.js account status. Contributions welcome—see below.

## Contributing

Fork the repo, create a branch (`git checkout -b feature/xyz`), commit changes, and open a PR. Follow PEP 8 for style. Include tests (use `unittest`) and update docs if needed.

Run tests:
```bash
python -m unittest discover tests
```

## License

MIT License. See [LICENSE](LICENSE) for details.

## Acknowledgments

Built on top of Puter.js—kudos to the team for an innovative API. Inspired by real-world needs for privacy-focused AI tools.

**Maintainer's**:
- Nerve11 (@Nerve11)
- BubblesTheDev (@kernferm)
- **Last Updated**: August 12, 2025  
- **Version**: 0.1.03  

- If this SDK saves you time, star the repo! Questions? Open an issue.

# PutergenAI GUI Application

This repository includes a CustomTkinter-based GUI for PutergenAI, allowing you to chat with AI models, generate images, and manage your Puter.js account visually.

## Features
- Login with Puter credentials
- Select from multiple AI models (chat and image)
- Use 4 free image generation APIs: Hugging Face, Replicate, DeepAI, OpenAI
- Enter and save API keys for image generation APIs
- Popup notification when selecting a free API, reminding you to add your API key
- Section for entering and saving API keys appears when needed
- Chat and image generation (API and local)
- Sign Out button to log out and return to login screen
- Window resizing is disabled for a consistent experience

## How to Use
1. **Run the app:**
   ```bash
   python example.py
   ```
2. **Login:** Enter your Puter username and password.
3. **Select Model:** Choose an AI model for chat or image tasks.
4. **Select Image Generation API:** Pick one of the free APIs. A popup will remind you to add your API key.
5. **Enter API Key:** When prompted, enter your API key in the provided field and click "Save Key".
6. **Chat or Generate Images:** Use the chat box and buttons to interact with the AI or generate images.
7. **Sign Out:** Click the Sign Out button to log out and return to the login screen.

## Requirements
- Python 3.8+
- `putergenai` (see SDK instructions above)
- `customtkinter`, `Pillow`, `requests`

Install dependencies:
```bash
pip install customtkinter pillow requests putergenai
```

## Notes
- API keys are required for Hugging Face, Replicate, and OpenAI image generation. DeepAI may work with a demo key.
- Window size is fixed (800x600) and cannot be resized.
- All user input is sanitized for security.

For SDK usage and advanced features, see below.

## GUI Example Usage

Below is a sample workflow using the included `example.py` GUI application:

```python
from putergenai import PuterClient
import customtkinter as ctk
import tkinter as tk
import tkinter.messagebox as mbox

# Launch the GUI
if __name__ == "__main__":
    PuterApp().mainloop()
```

### Main Features in the GUI
- **Login:** Enter your Puter credentials to access chat and image features.
- **Model Selection:** Choose from available AI models (chat and image).
- **Image Generation API Selection:** Pick from Hugging Face, Replicate, DeepAI, or OpenAI. A popup will remind you to add your API key.
- **API Key Entry:** When a free API is selected, a section appears to enter and save your API key.
- **Chat & Image Generation:** Use the chat box and buttons to interact with the AI or generate images (API/local).
- **Sign Out:** Click the Sign Out button to log out and return to the login screen.
- **Window Size:** The window is fixed at 800x600 and cannot be resized.

### Example GUI Flow
1. Run the app: `python example.py`
2. Login with your Puter username and password.
3. Select a model and an image generation API.
4. Enter your API key if prompted and save it.
5. Type a message or image prompt and use the buttons to chat or generate images.
6. Sign out when finished.

---
