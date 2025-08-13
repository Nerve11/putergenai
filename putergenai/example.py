import sys
import logging
import re
import os
from putergenai import PuterClient
import requests
from PIL import Image, ImageDraw, ImageFont
import customtkinter as ctk
import tkinter as tk
import tkinter.messagebox as mbox
from cryptography.fernet import Fernet
import stat

def generate_local_image(prompt, filename='local_image.png', bg_color='#496d89', font_size=32, text_color='#ffff00'):
    width, height = 600, 300
    img = Image.new('RGB', (width, height), color=bg_color)
    d = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("arial.ttf", font_size)
    except (IOError, FileNotFoundError):
        font = ImageFont.load_default()
    # Center the text
    try:
        bbox = d.textbbox((0, 0), prompt, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
    except AttributeError:
        # Fallback for older Pillow
        text_width, text_height = font.getsize(prompt)
    x = (width - text_width) // 2
    y = (height - text_height) // 2
    d.text((x, y), prompt, fill=text_color, font=font)
    img.save(filename)
    return filename


def sanitize_string(s, allow_empty=False, allow_path=False):
    """
    Sanitize a string input.
    Parameters:
        s (str): Input string to sanitize.
        allow_empty (bool): If False, raises error on empty string.
        allow_path (bool): If True, allows path-like characters.
    Returns:
        str: Sanitized string.
    Raises:
        ValueError: If input is not valid.
    """
    if not isinstance(s, str):
        raise ValueError("Input must be a string.")
    s = s.strip()
    if not allow_empty and not s:
        raise ValueError("Input cannot be empty.")
    if allow_path:
        pattern = r'^[\w\-\.\/]+$'
        if not re.match(pattern, s):
            raise ValueError("Input contains invalid characters for path.")
    return s


def sanitize_float(val, min_value=0.0, max_value=2.0, default=0.7):
    try:
        f = float(val)
    except (ValueError, TypeError):
        f = default
    if f < min_value or f > max_value:
        raise ValueError(f"Value must be between {min_value} and {max_value}.")
    return f


# --- CustomTkinter GUI ---
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

class PuterApp(ctk.CTk):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._load_encryption_key()
        self.api_keys = self._load_api_keys()
        # ... rest of your __init__ code ...

    def _load_encryption_key(self):
        self._key_file = "api_keys.key"
        env_key = os.environ.get("PUTERGENAI_FERNET_KEY")
        if env_key:
            self._fernet_key = env_key.encode()
        elif os.path.exists(self._key_file):
            with open(self._key_file, "rb") as f:
                self._fernet_key = f.read()
        else:
            self._fernet_key = Fernet.generate_key()
            with open(self._key_file, "wb") as f:
                f.write(self._fernet_key)
            # Restrict permissions to user only (Windows)
            try:
                os.chmod(self._key_file, stat.S_IREAD | stat.S_IWRITE)
            except Exception as e:
                print(f"Warning: Could not set permissions on {self._key_file}: {e}")
        self._fernet = Fernet(self._fernet_key)

    def _encrypt(self, plaintext):
        return self._fernet.encrypt(plaintext.encode()).decode()

    def _decrypt(self, ciphertext):
        return self._fernet.decrypt(ciphertext.encode()).decode()

    def _load_api_keys(self):
        api_keys = {}
        if os.path.exists("api_keys.cfg"):
            try:
                with open("api_keys.cfg", "r") as f:
                    for line in f:
                        if "=" in line:
                            k, v = line.strip().split("=", 1)
                            try:
                                api_keys[k] = self._decrypt(v)
                            except Exception:
                                continue
            except Exception as e:
                print(f"Error loading API keys: {e}")
        return api_keys

    def _build_main(self):
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.pack(fill="both", expand=True)

        # Model selection
        ctk.CTkLabel(self.main_frame, text="Select Model", font=("Arial", 18)).pack(pady=10)
        self.models = list(self.client.model_to_driver.keys())
        self.model_var = ctk.StringVar(value=self.models[0])
        self.model_menu = ctk.CTkOptionMenu(self.main_frame, variable=self.model_var, values=[
            f"{m} {'[Image]' if m in self.image_models or any(x in m.lower() for x in ['vision','image','img']) else ''}" for m in self.models
        ])
        self.model_menu.pack(pady=5)

        # API selection dropdown
        ctk.CTkLabel(self.main_frame, text="Select Image Generation API", font=("Arial", 14)).pack(pady=5)
        self.api_var = ctk.StringVar(value=self.api_options[0])
        def on_api_select(choice):
            if choice in ["Hugging Face", "Replicate", "DeepAI", "OpenAI"]:
                mbox.showinfo("API Key Required", f"You selected {choice}. You will need to add an API key to use image generation.")
                self.api_key_entry.delete(0, tk.END)
                self.api_key_entry.insert("0", self.api_keys.get(choice, ""))
                self.api_key_section.pack(pady=5)
            else:
                self.api_key_section.pack_forget()
        self.api_menu = ctk.CTkOptionMenu(self.main_frame, variable=self.api_var, values=self.api_options, command=on_api_select)
        self.api_menu.pack(pady=5)

        # Section for API key entry
        self.api_key_section = ctk.CTkFrame(self.main_frame)
        ctk.CTkLabel(self.api_key_section, text="Enter API Key:").pack(side="left", padx=5)
        self.api_key_entry = ctk.CTkEntry(self.api_key_section, show="*")
        self.api_key_entry.pack(side="left", padx=5)
        def save_api_key():
            selected_api = self.api_var.get()
            key = self.api_key_entry.get()
            self.api_keys[selected_api] = key
            self._save_api_keys()
            mbox.showinfo("API Key Saved", f"API key for {selected_api} saved.")
        ctk.CTkButton(self.api_key_section, text="Save Key", command=save_api_key).pack(side="left", padx=5)

        # Chat and image controls
        self.chat_frame = ctk.CTkFrame(self.main_frame)
        self.chat_frame.pack(fill="both", expand=True, padx=10, pady=10)
        self.chat_box = ctk.CTkTextbox(self.chat_frame, width=700, height=300)
        self.chat_box.pack(pady=5)

        self.prompt_entry = ctk.CTkEntry(self.chat_frame, placeholder_text="Type your message or image prompt...")
        self.prompt_entry.pack(fill="x", pady=5)
        self.prompt_entry.bind("<Return>", lambda event: self._send_chat())

        self.button_frame = ctk.CTkFrame(self.chat_frame)
        self.button_frame.pack(fill="x", pady=5)
        ctk.CTkButton(self.button_frame, text="Send Chat", command=self._send_chat).pack(side="left", padx=5)
        ctk.CTkButton(self.button_frame, text="Generate Image (API)", command=self._send_image_api).pack(side="left", padx=5)
        ctk.CTkButton(self.button_frame, text="Generate Image (Local)", command=self._send_image_local).pack(side="left", padx=5)
        ctk.CTkButton(self.button_frame, text="Sign Out", command=self._sign_out, fg_color="#d9534f", text_color="white").pack(side="right", padx=5)
    # Sign Out button will be added in _build_main

    def _sign_out(self):
        # Clear user session and return to login screen
        self.client = None
        self.selected_model = None
        self.messages = []
        self.options = {}
        self.api_online = None
        self.main_frame.pack_forget()
        self._build_login()

        self.status_label = ctk.CTkLabel(self.chat_frame, text="", text_color="yellow")
        self.status_label.pack(pady=5)
        self.status_label.pack(pady=5)
    def _get_api_key(self, api_name):
        if self.api_keys.get(api_name):
            return self.api_keys[api_name]
        # Popup for API key entry (use customtkinter for consistency)
        key_win = ctk.CTkToplevel(self)
        key_win.title(f"Enter {api_name} API Key")
        key_win.geometry("350x120")
        ctk.CTkLabel(key_win, text=f"{api_name} API Key:").pack(pady=10)
        key_entry = ctk.CTkEntry(key_win, show="*")
        key_entry.pack(pady=5)
        result = {"key": None}
        def save_key():
            result["key"] = key_entry.get()
            self.api_keys[api_name] = result["key"]
            self._save_api_keys()
            key_win.destroy()
        ctk.CTkButton(key_win, text="Save", command=save_key).pack(pady=10)
        key_win.wait_window()
        return result["key"]

    def _send_image_api(self):
        prompt = self.prompt_entry.get()
        if not prompt:
            self.status_label.configure(text="Prompt cannot be empty.")
            return
        api_choice = self.api_var.get()
        self.notify_api_signup()
        try:
            if api_choice == "Hugging Face":
                key = self._get_api_key("Hugging Face")
                if not key:
                    self.status_label.configure(text="No Hugging Face API key provided.", text_color="red")
                    return
                # Hugging Face Stable Diffusion endpoint
                url = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-2"
                headers = {"Authorization": f"Bearer {key}"}
                data = {"inputs": prompt}
                import requests
                resp = requests.post(url, headers=headers, json=data)
                if resp.status_code == 200:
                    # Save image from response
                    fname = "hf_image.png"
                    with open(fname, "wb") as f:
                        f.write(resp.content)
                    self.chat_box.insert("end", f"[Hugging Face] Prompt: {prompt}\nSaved as: {fname}\n\n")
                    self.status_label.configure(text=f"Image saved as {fname}.", text_color="green")
                else:
                    self.chat_box.insert("end", f"[Hugging Face] Error: {resp.text}\n\n")
                    self.status_label.configure(text="Hugging Face API error.", text_color="red")
            elif api_choice == "Replicate":
                key = self._get_api_key("Replicate")
                if not key:
                    self.status_label.configure(text="No Replicate API key provided.", text_color="red")
                    return
                url = "https://api.replicate.com/v1/predictions"
                headers = {"Authorization": f"Token {key}", "Content-Type": "application/json"}
                data = {
                    "version": "a9758cb8c6c7e0e6c7e0e6c7e0e6c7e0e6c7e0e6c7e0e6c7e0e6c7e0e6c7e0e6", # SDXL
                    "input": {"prompt": prompt}
                }
                import requests
                resp = requests.post(url, headers=headers, json=data)
                if resp.status_code == 201:
                    output = resp.json()["urls"]["get"]
                    self.chat_box.insert("end", f"[Replicate] Prompt: {prompt}\nResult URL: {output}\n\n")
                    self.status_label.configure(text="Replicate request submitted.", text_color="green")
                else:
                    self.chat_box.insert("end", f"[Replicate] Error: {resp.text}\n\n")
                    self.status_label.configure(text="Replicate API error.", text_color="red")
            elif api_choice == "DeepAI":
                key = self._get_api_key("DeepAI")
                if not key:
                    self.status_label.configure(text="No DeepAI API key provided.", text_color="red")
                    return
                url = "https://api.deepai.org/api/text2img"
                headers = {"api-key": key}
                data = {"text": prompt}
                resp = requests.post(url, headers=headers, data=data)
                if resp.status_code == 200:
                    output = resp.json().get("output_url")
                    self.chat_box.insert("end", f"[DeepAI] Prompt: {prompt}\nImage URL: {output}\n\n")
                    self.status_label.configure(text="DeepAI image generated.", text_color="green")
                else:
                    self.chat_box.insert("end", f"[DeepAI] Error: {resp.text}\n\n")
                    self.status_label.configure(text="DeepAI API error.", text_color="red")
            elif api_choice == "OpenAI":
                key = self._get_api_key("OpenAI")
                if not key:
                    self.status_label.configure(text="No OpenAI API key provided.", text_color="red")
                    return
                url = "https://api.openai.com/v1/images/generations"
                headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
                data = {"prompt": prompt, "n": 1, "size": "512x512"}
                import requests
                resp = requests.post(url, headers=headers, json=data)
                if resp.status_code == 200:
                    output = resp.json()["data"][0]["url"]
                    self.chat_box.insert("end", f"[OpenAI] Prompt: {prompt}\nImage URL: {output}\n\n")
                    self.status_label.configure(text="OpenAI image generated.", text_color="green")
                else:
                    self.chat_box.insert("end", f"[OpenAI] Error: {resp.text}\n\n")
                    self.status_label.configure(text="OpenAI API error.", text_color="red")
        except Exception as e:
            self.chat_box.insert("end", f"[Image API] Error: {e}\n\n")
            self.status_label.configure(text=f"Image API error: {e}", text_color="red")
    def notify_api_signup(self):
        mbox.showinfo(
            "Free API Notice",
            "To use most free image generation APIs (Hugging Face, Replicate, OpenAI, etc.), you will likely need to create a free account and obtain an API key. DeepAI may work without signup for basic use."
        )
    def __init__(self):
        super().__init__()
        self.title("PuterGenAI Chat & Image GUI")
        self.geometry("800x600")
        self.resizable(False, False)
        self.client = None
        self.models = []
        self.image_models = [
                'gpt-4o', 'gpt-4o-mini', 'gpt-4.1', 'gpt-4.1-mini', 'gpt-4.1-nano',
                'gpt-5', 'gpt-5-mini', 'gpt-5-nano', 'gpt-5-chat-latest',
                'claude-sonnet-4', 'claude-opus-4', 'claude-3-7-sonnet', 'claude-3-5-sonnet',
                'gemini-2.0-flash', 'gemini-1.5-flash', 'meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo',
                'meta-llama/Meta-Llama-3.1-70B-Instruct-Turbo', 'meta-llama/Meta-Llama-3.1-405B-Instruct-Turbo',
                'mistral-large-latest', 'pixtral-large-latest', 'codestral-latest', 'google/gemma-2-27b-it', 'grok-beta'
            ]
        self.selected_model = None
        self.messages = []
        self.options = {}
        self.api_online = None
        self.api_keys = {"Hugging Face": None, "Replicate": None, "OpenAI": None}
        self.api_options = ["Hugging Face", "Replicate", "DeepAI", "OpenAI"]
        self._build_menu_native()
        self._build_login()

    def _build_menu_native(self):
        self.menu_native = tk.Menu(self)
        # File menu
        file_menu = tk.Menu(self.menu_native, tearoff=0)
        file_menu.add_command(label="Exit", command=self._exit_app)
        self.menu_native.add_cascade(label="File", menu=file_menu)
        # Info menu
        info_menu = tk.Menu(self.menu_native, tearoff=0)
        info_menu.add_command(label="About", command=self._show_info)
        self.menu_native.add_cascade(label="Info", menu=info_menu)
        # API Status menu
        api_menu = tk.Menu(self.menu_native, tearoff=0)
        api_menu.add_command(label="Check Image API", command=self._check_api_status)
        self.menu_native.add_cascade(label="API Status", menu=api_menu)
        self.configure(menu=self.menu_native)

    def _exit_app(self):
        self.destroy()

    def _check_api_status(self):
        # Try a dummy image prompt to check API status
        try:
            image_url = self.client.ai_txt2img("test") if self.client else None
            if image_url:
                mbox.showinfo("API Status", "Image API is ONLINE.")
            else:
                mbox.showwarning("API Status", "Image API is OFFLINE or unavailable.")
        except Exception as e:
            mbox.showwarning("API Status", f"Image API is OFFLINE or unavailable.\nError: {e}")

    # Removed simulated menubar frame

    def _show_info(self):
        info = (
            "PuterGenAI GUI\n"
            "- Login with your Puter credentials.\n"
            "- Select a model (models marked [Image] may support image generation).\n"
            "- Chat, generate images via API or locally.\n"
            "- API image generation may be unavailable for some models/accounts.\n"
            "- Local image generation always works.\n"
            "- Status and errors are shown below the chat box."
        )
        mbox.showinfo("Info", info)

    def _build_login(self):
        self.login_frame = ctk.CTkFrame(self)
        self.login_frame.pack(expand=True)
        ctk.CTkLabel(self.login_frame, text="Login to PuterGenAI", font=("Arial", 24)).pack(pady=20)
        self.username_entry = ctk.CTkEntry(self.login_frame, placeholder_text="Username")
        self.username_entry.pack(pady=10)
        self.password_entry = ctk.CTkEntry(self.login_frame, placeholder_text="Password", show="*")
        self.password_entry.pack(pady=10)
        self.login_status = ctk.CTkLabel(self.login_frame, text="", text_color="red")
        self.login_status.pack(pady=5)
        ctk.CTkButton(self.login_frame, text="Login", command=self._login).pack(pady=20)

    def _login(self):
        username = self.username_entry.get()
        password = self.password_entry.get()
        try:
            self.client = PuterClient()
            self.client.login(sanitize_string(username), sanitize_string(password))
            # Check image generation access
            has_image_access = False
            try:
                test_url = self.client.ai_txt2img("access test")
                if test_url:
                    has_image_access = True
            except Exception:
                has_image_access = False
            note = "You have access to image generation via API." if has_image_access else "You do NOT have access to image generation via API. Use local image generation instead."
            self.login_status.configure(text="Login successful!", text_color="green")
            mbox.showinfo("Image Generation Access", note)
            self.login_frame.pack_forget()
            self._build_main()
        except Exception as e:
            self.login_status.configure(text=f"Login failed: {e}", text_color="red")


    def _send_chat(self):
        prompt = self.prompt_entry.get()
        if not prompt:
            self.status_label.configure(text="Prompt cannot be empty.")
            return
        self.selected_model = self.model_var.get().split()[0]
        self.options = {
            "model": self.selected_model,
            "stream": False,
            "temperature": 0.7
        }
        self.messages.append({"role": "user", "content": prompt})
        try:
            result = self.client.ai_chat(messages=self.messages, options=self.options)
            content = result["response"].get('result', {}).get('message', {}).get('content', '')
            used_model = result["used_model"]
            self.chat_box.insert("end", f"You: {prompt}\nAssistant: {content}\n[Model: {used_model}]\n\n")
            self.messages.append({"role": "assistant", "content": content})
            self.status_label.configure(text="Chat response received.", text_color="green")
        except Exception as e:
            self.status_label.configure(text=f"Chat error: {e}", text_color="red")

    def _send_image(self):
        prompt = self.prompt_entry.get()
        if not prompt:
            self.status_label.configure(text="Prompt cannot be empty.")
            return
        try:
            image_url = self.client.ai_txt2img(prompt)
            if image_url:
                self.api_online = True
                self.chat_box.insert("end", f"[Image API] Prompt: {prompt}\nImage URL: {image_url}\n\n")
                self.status_label.configure(text="Image generated via API.", text_color="green")
                mbox.showinfo("API Status", "Image API is ONLINE.")
            else:
                self.api_online = False
                self.chat_box.insert("end", f"[Image API] Prompt: {prompt}\nImage generation failed.\n\n")
                self.status_label.configure(text="Image generation failed.", text_color="red")
                mbox.showwarning("API Status", "Image API is OFFLINE or unavailable.")
        except Exception as e:
            self.api_online = False
            self.chat_box.insert("end", f"[Image API] Error: {e}\n\n")
            self.status_label.configure(text=f"Image API error: {e}", text_color="red")
            mbox.showwarning("API Status", f"Image API is OFFLINE or unavailable.\nError: {e}")

    def _send_image_local(self):
        self.notify_api_signup()
        prompt = self.prompt_entry.get()
        if not prompt:
            self.status_label.configure(text="Prompt cannot be empty.")
            return
        # Popup for options
        options_win = tk.Toplevel(self)
        options_win.title("Local Image Options")
        options_win.geometry("400x350")

        bg_label = tk.Label(options_win, text="Background Color (hex)")
        bg_label.pack(pady=5)
        bg_entry = tk.Entry(options_win)
        bg_entry.insert(0, "#496d89")
        bg_entry.pack(pady=5)

        font_label = tk.Label(options_win, text="Font Size")
        font_label.pack(pady=5)
        font_entry = tk.Entry(options_win)
        font_entry.insert(0, "32")
        font_entry.pack(pady=5)

        text_label = tk.Label(options_win, text="Text Color (hex)")
        text_label.pack(pady=5)
        text_entry = tk.Entry(options_win)
        text_entry.insert(0, "#ffff00")
        text_entry.pack(pady=5)

        file_label = tk.Label(options_win, text="Filename")
        file_label.pack(pady=5)
        file_entry = tk.Entry(options_win)
        file_entry.insert(0, "local_image.png")
        file_entry.pack(pady=5)

        def generate_and_close():
            bg_color = bg_entry.get() or "#496d89"
            try:
                font_size = int(font_entry.get() or 32)
            except ValueError:
                font_size = 32
            text_color = text_entry.get() or "#ffff00"
            filename = file_entry.get() or "local_image.png"
            fname = generate_local_image(prompt, filename, bg_color, font_size, text_color)
            self.chat_box.insert("end", f"[Image Local] Prompt: {prompt}\nSaved as: {fname}\n\n")
            self.status_label.configure(text=f"Local image saved as {fname}.", text_color="green")
            options_win.destroy()

        gen_btn = tk.Button(options_win, text="Generate", command=generate_and_close)
        gen_btn.pack(pady=10)

# --- Flask Secure Cookie Example ---
from flask import Flask, make_response, request
from cryptography.fernet import Fernet

app = Flask("Secure Example")
fernet = Fernet(Fernet.generate_key())

@app.route('/')
def index():
    password = request.args.get("password")
    if password:
        encrypted = fernet.encrypt(password.encode()).decode()
        resp = make_response("Password received (encrypted in cookie)")
        resp.set_cookie("password", encrypted, secure=True, httponly=True)
        return resp
    return "No password provided"

# Uncomment below to run Flask app
# if __name__ == "__main__":
#     app.run(debug=True)

if __name__ == "__main__":
    PuterApp().mainloop()
