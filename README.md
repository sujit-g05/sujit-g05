# Anime AI Assistant

An offline, local AI assistant with a graphical user interface. This assistant helps you with tasks like coding, CAD modeling, and studying, using a custom cute anime girl persona.

It features:
- **100% Offline Capability**: Runs entirely on your local machine without needing an active internet connection.
- **Local LLM Integration**: Uses Ollama for natural language generation.
- **Voice Interactions**: Offline Speech-to-Text (STT) via Sphinx and Text-to-Speech (TTS) via pyttsx3.
- **Customizable Avatar**: Display your own visual avatar in the UI.

## Prerequisites

To run this assistant locally, you need to install the following tools:

### 1. Install System Dependencies
If you are on Linux, you may need to install audio dependencies for PyAudio and Sphinx:
```bash
sudo apt-get install portaudio19-dev python3-pyaudio python3-tk
```
For Windows/macOS, PyAudio usually installs via pip without extra system packages, but follow OS-specific instructions if errors occur.

### 2. Install Ollama (For Local AI)
Ollama is used to run the large language model locally.
1. Download and install Ollama from [ollama.com](https://ollama.com/).
2. Once installed, open a terminal and pull a lightweight model (e.g., `llama3` or `phi3`):
```bash
ollama run llama3
```
*Note: Make sure Ollama is running in the background before starting the Python app.*

### 3. Setup Python Environment
1. Clone this repository (or download the files).
2. (Optional) Create a virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```
3. Install the required Python packages:
```bash
pip install -r requirements.txt
```

## Customizing the Avatar

To give your assistant a visual appearance:
1. Find an image of a cute anime girl (or any character you prefer).
2. Save the image as `avatar.png` in the same directory as `main.py`.
3. The application will automatically detect and display this image in the left panel. If the image is not found, a text placeholder is shown.

## Running the Assistant

1. Ensure Ollama is running locally (usually starts automatically, or run `ollama serve`).
2. Run the main script:
```bash
python main.py
```
3. You can interact by typing in the chat box or clicking the `🎤 Listen` button to speak to the assistant!
