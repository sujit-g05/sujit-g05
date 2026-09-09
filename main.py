import tkinter as tk
from tkinter import scrolledtext, ttk
from PIL import Image, ImageTk
import threading
import queue
import pyttsx3
import speech_recognition as sr
import requests
import json

# Configure Ollama settings
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3" # You can change this to phi3 or another local model

class AssistantGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Anime AI Assistant")
        self.root.geometry("800x600")
        self.root.configure(bg="#2c3e50")

        # Load custom fonts and styles here if needed
        self.style = ttk.Style()
        self.style.configure("TButton", padding=6, relief="flat", background="#3498db")

        # Main layout: Left for avatar, Right for chat
        self.main_frame = tk.Frame(root, bg="#2c3e50")
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=20, pady=20)

        # Avatar Frame (Left)
        self.avatar_frame = tk.Frame(self.main_frame, bg="#34495e", width=300, height=500)
        self.avatar_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 20))
        self.avatar_frame.pack_propagate(False) # Don't shrink

        self.avatar_label = tk.Label(self.avatar_frame, text="[Avatar Image Placeholder]", bg="#34495e", fg="white", font=("Arial", 14))
        self.avatar_label.pack(expand=True)

        # Try loading an image if available
        try:
            # We'll expect the user to place an 'avatar.png' in the same directory
            image = Image.open("avatar.png")
            # Resize image to fit
            image = image.resize((250, 400), Image.Resampling.LANCZOS)
            self.avatar_img = ImageTk.PhotoImage(image)
            self.avatar_label.configure(image=self.avatar_img, text="")
        except FileNotFoundError:
            pass # Fall back to text placeholder

        # Chat Frame (Right)
        self.chat_frame = tk.Frame(self.main_frame, bg="#2c3e50")
        self.chat_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # Chat History
        self.chat_history = scrolledtext.ScrolledText(
            self.chat_frame,
            wrap=tk.WORD,
            bg="#ecf0f1",
            fg="#2c3e50",
            font=("Arial", 12),
            state=tk.DISABLED
        )
        self.chat_history.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        # Input Frame (Bottom of Chat)
        self.input_frame = tk.Frame(self.chat_frame, bg="#2c3e50")
        self.input_frame.pack(fill=tk.X)

        self.user_input = tk.Entry(
            self.input_frame,
            font=("Arial", 12),
            bg="#ecf0f1",
            fg="#2c3e50"
        )
        self.user_input.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=8, padx=(0, 10))
        self.user_input.bind("<Return>", lambda event: self.send_message())

        # Buttons
        self.send_button = ttk.Button(self.input_frame, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.LEFT)

        self.listen_button = ttk.Button(self.input_frame, text="🎤 Listen", command=self.toggle_listen)
        self.listen_button.pack(side=tk.LEFT, padx=(10, 0))

        # Status Label
        self.status_label = tk.Label(
            self.chat_frame,
            text="Ready",
            bg="#2c3e50",
            fg="#bdc3c7",
            font=("Arial", 10),
            anchor="w"
        )
        self.status_label.pack(fill=tk.X, pady=(5, 0))

        self.message_queue = queue.Queue()
        self.root.after(100, self.process_queue)

        # Initialize STT
        self.recognizer = sr.Recognizer()
        self.is_listening = False

    def append_to_chat(self, text, sender="System"):
        self.chat_history.configure(state=tk.NORMAL)
        if sender == "You":
            self.chat_history.insert(tk.END, f"You: {text}\n\n", "user")
        elif sender == "Assistant":
            self.chat_history.insert(tk.END, f"Assistant: {text}\n\n", "assistant")
        else:
            self.chat_history.insert(tk.END, f"{text}\n\n", "system")

        self.chat_history.configure(state=tk.DISABLED)
        self.chat_history.see(tk.END)

    def send_message(self):
        text = self.user_input.get().strip()
        if text:
            self.append_to_chat(text, "You")
            self.user_input.delete(0, tk.END)
            self.status_label.config(text="Thinking...")
            self.send_button.config(state=tk.DISABLED)

            # Run LLM request in a separate thread
            threading.Thread(target=self.query_llm, args=(text,), daemon=True).start()

    def query_llm(self, prompt):
        # We give her a persona in the prompt
        system_prompt = "You are a helpful, cute anime girl AI assistant running locally on my laptop. You can help with coding, cad modeling, studying, and other tasks. Keep responses concise and natural."
        full_prompt = f"{system_prompt}\n\nUser: {prompt}\nAssistant:"

        try:
            data = {
                "model": OLLAMA_MODEL,
                "prompt": full_prompt,
                "stream": False
            }
            response = requests.post(OLLAMA_URL, json=data)
            if response.status_code == 200:
                result = response.json()
                reply = result.get("response", "I'm sorry, I couldn't generate a response.")
                self.message_queue.put(("llm_response", reply))
            else:
                self.message_queue.put(("llm_response", f"Error connecting to Ollama: HTTP {response.status_code}. Make sure Ollama is running."))
        except requests.exceptions.RequestException as e:
            self.message_queue.put(("llm_response", f"Connection error: {e}. Is Ollama running?"))


    def toggle_listen(self):
        if not self.is_listening:
            self.is_listening = True
            self.listen_button.config(text="⏹ Stop Listening")
            self.status_label.config(text="Listening for voice input...")
            # Run in separate thread to not freeze GUI
            threading.Thread(target=self.listen_thread, daemon=True).start()
        else:
            self.is_listening = False
            self.listen_button.config(text="🎤 Listen")
            self.status_label.config(text="Ready")

    def listen_thread(self):
        with sr.Microphone() as source:
            self.recognizer.adjust_for_ambient_noise(source, duration=1)
            while self.is_listening:
                try:
                    # Listen in small chunks so we can interrupt it
                    audio = self.recognizer.listen(source, timeout=1, phrase_time_limit=5)
                    self.message_queue.put(("status", "Processing speech..."))

                    # Using sphinx for offline recognition
                    try:
                        text = self.recognizer.recognize_sphinx(audio)
                        if text:
                            self.message_queue.put(("voice_input", text))
                    except sr.UnknownValueError:
                        pass # Could not understand
                    except sr.RequestError as e:
                        self.message_queue.put(("status", f"Sphinx error: {e}"))
                except sr.WaitTimeoutError:
                    continue # Loop back and check self.is_listening
                except Exception as e:
                    print(f"Audio Error: {e}")
                    break

        self.message_queue.put(("status", "Ready"))
        self.message_queue.put(("listen_button", "🎤 Listen"))
        self.is_listening = False

    def speak(self, text):
        def _speak():
            # Initialize TTS Engine inside the thread to avoid COM errors on Windows
            tts_engine = pyttsx3.init()
            # Try to find a female voice (anime girl aesthetic)
            voices = tts_engine.getProperty('voices')
            for voice in voices:
                if "female" in voice.name.lower() or "zira" in voice.name.lower():
                    tts_engine.setProperty('voice', voice.id)
                    break

            tts_engine.setProperty('rate', 150) # Slightly slower/clearer
            tts_engine.say(text)
            tts_engine.runAndWait()
        threading.Thread(target=_speak, daemon=True).start()

    def process_queue(self):
        """Process messages from other threads (e.g., speech recognition)."""
        try:
            while True:
                msg = self.message_queue.get_nowait()
                msg_type, content = msg
                if msg_type == "chat":
                    self.append_to_chat(content, "You")
                elif msg_type == "status":
                    self.status_label.config(text=content)
                elif msg_type == "voice_input":
                    self.user_input.delete(0, tk.END)
                    self.user_input.insert(0, content)
                    self.send_message()
                elif msg_type == "listen_button":
                    self.listen_button.config(text=content)
                elif msg_type == "llm_response":
                    self.append_to_chat(content, "Assistant")
                    self.status_label.config(text="Ready")
                    self.send_button.config(state=tk.NORMAL)
                    self.speak(content)
        except queue.Empty:
            pass
        finally:
            self.root.after(100, self.process_queue)

if __name__ == "__main__":
    root = tk.Tk()
    app = AssistantGUI(root)
    root.mainloop()
