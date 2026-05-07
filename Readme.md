# JULIA 
## V0.5.2 (UI & Voice Integration)
ORACLE is an offline, local MoE (Mixture of Experts) desktop assistant featuring an "Advisor Logic" architecture. 

A fast, front-line LLM (`gemma4:e4b`) handles basic tasks and UI queries using Shallow RAG. When confidence drops, or queries become architecturally complex, it automatically escalates to a heavy "Advisor" model (`qwen3.6:35b-a3b`) equipped with Deep RAG context. 

**Key Features:**
* **Dynamic Memory Safeguard:** Automatically monitors RAM and downgrades to a safe model (`qwen3.5:9b`) to prevent system crashes.
* **Native Desktop UI:** A hotkey-toggled (`Ctrl+Alt+L`), thread-safe GUI with chat history, dynamic settings, and system tray integration.
* **Offline Voice Engine:** Fully local Speech-to-Text and Text-to-Speech (SAPI5). Features a customizable wake-word (e.g., "Julia") and a continuous conversation window for hands-free coding.

## Requirements
* Python Environment (Anaconda Recommended)
* Microsoft MarkItDown (CLI/Python)
* Ollama with the following pulled models:
  -> `qwen3.6:35b-a3b`
  -> `gemma4:e4b`
  -> `qwen3.5:9b`
* Required Python Libraries:
  `pip install ollama customtkinter chromadb langchain langchain-huggingface sentence-transformers psutil pystray keyboard pillow tqdm SpeechRecognition pyttsx3 pyaudio pywin32`

## How to use run.bat?
Please change the `C:\Users\USERNAME\...` path inside the `.bat` file to match your current Windows user and Anaconda environment path. Running the batch file will boot the engine in the background—look for the "J" icon in your system tray or press `Ctrl+Alt+L` to open the interface.
