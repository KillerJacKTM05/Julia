import customtkinter as ctk
import keyboard
import threading
import queue
import json
import os
import pystray
from PIL import Image, ImageDraw, ImageFont
from customtkinter import filedialog
from moe_router import MoERouter 
from audio_engine import AudioEngine

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class UnityJuliaUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Julia (MoE)")
        self.geometry("900x650")
        self.minsize(600, 500)
        
        # Try to load custom PNG icons. Fall back to None if they don't exist.
        try:
            self.icn_mic = ctk.CTkImage(Image.open("icons/microphone.png"), size=(20, 20))
            self.icn_clip = ctk.CTkImage(Image.open("icons/paperclip.png"), size=(20, 20))
            self.icn_settings = ctk.CTkImage(Image.open("icons/settings.png"), size=(20, 20))
            self.icn_new = ctk.CTkImage(Image.open("icons/new-chat.png"), size=(20, 20))
            self.icn_clipBoard = ctk.CTkImage(Image.open("icons/clipboard.png"), size=(20, 20))
            self.icn_code = ctk.CTkImage(Image.open("icons/code.png"), size=(20, 20))
        except Exception as e:
            print(f"[UI Warning] Icons missing: {e}")
            self.icn_clipBoard = self.icn_code = self.icn_mic = self.icn_clip = self.icn_settings = self.icn_new = None
        
        self.chat_history_file = "chat_history.json"
        self.token_queue = queue.Queue()
        self.history_data = [] # Stores clean {"role": "User/Julia", "text": "..."} blocks
        self.is_thinking = False
        self.in_code_block = False 
        self.current_code_box = None
        self._token_buffer = ""
        self.in_thought_block = False
        self.embedded_code_blocks = []
        # Audio State Variables
        self.tts_enabled = False
        self.audio = AudioEngine(self.handle_audio_callback)
        
        self.build_ui()
        self.setup_hotkey()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        # Start background tasks
        self.check_queue()
        threading.Thread(target=self.initialize_router, daemon=True).start()
        threading.Thread(target=self.setup_tray_icon, daemon=True).start()

    # Background Initialization
    def initialize_router(self):
        self.append_text("System: Booting Knowledge Base...\n", "System")
        self.router = MoERouter()
        self.append_text("System: Julia is Ready. Press Ctrl+Alt+L to toggle.\n\n", "System")
        self.load_history()

    def setup_tray_icon(self):
        image = Image.new('RGBA', (64, 64), (20, 30, 50, 255))
        draw = ImageDraw.Draw(image)
        # Outer eye (ellipse)
        draw.ellipse((8, 20, 56, 44), outline="white", width=3)
        # Inner iris
        draw.ellipse((24, 26, 40, 42), fill="white")
        # Pupil
        draw.ellipse((28, 30, 36, 38), fill=(20, 30, 50))
        
        # Load a serif font (replace with actual path)
        font = ImageFont.truetype("C:/Windows/Fonts/COPRGTL.TTF", 36)
        text = "J"
        # Get exact bounding box
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        # Center it
        position = ((64 - w) // 2, (64 - h) // 2)
        draw.text(position, text, fill="white", font=font)
        
        menu = pystray.Menu(
            pystray.MenuItem("Show Julia", lambda: self.token_queue.put(("[SHOW]", "Command"))),
            pystray.MenuItem("Quit", lambda: self.token_queue.put(("[QUIT]", "Command")))
        )
        self.tray_icon = pystray.Icon("Julia", image, "Julia", menu)
        self.tray_icon.run()

    # Building the UI
    def build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # A. Sidebar (History Buttons)
        self.sidebar = ctk.CTkFrame(self, width=220, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_rowconfigure(2, weight=1)
        
        self.lbl_history = ctk.CTkLabel(self.sidebar, text="Chat History", font=("Arial", 16, "bold"))
        self.lbl_history.grid(row=0, column=0, pady=10, padx=10)
        
        # Scrollable area for history buttons
        self.history_list = ctk.CTkScrollableFrame(self.sidebar, fg_color="transparent")
        self.history_list.grid(row=2, column=0, sticky="nsew", padx=10, pady=5)
        
        self.btn_clear = ctk.CTkButton(self.sidebar, text="Clear History", fg_color="#990000", hover_color="#660000", command=self.clear_history)
        self.btn_clear.grid(row=3, column=0, pady=10, padx=10)

        # B. Main Chat Area
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main_frame.grid_rowconfigure(1, weight=1) # Chat display takes space
        self.main_frame.grid_columnconfigure(0, weight=1)

        # Top Bar (Settings)
        self.top_bar = ctk.CTkFrame(self.main_frame, height=40, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, sticky="ew")
        
        txt_new = " New Chat" if self.icn_new else "➕ New Chat"
        self.btn_new_chat = ctk.CTkButton(self.top_bar, image=self.icn_new, text=txt_new, width=80, fg_color="#2ECC71", hover_color="#27AE60", command=self.start_new_chat)
        self.btn_new_chat.pack(side="left", padx=10, pady=5)
        
        txt_set = " Settings" if self.icn_settings else "⚙️ Settings"
        self.btn_settings = ctk.CTkButton(self.top_bar, image=self.icn_settings, text=txt_set, width=80, command=self.open_settings)
        self.btn_settings.pack(side="right", padx=10, pady=5)

        # Chat Display
        self.chat_display = ctk.CTkTextbox(self.main_frame, state="disabled", font=("Consolas", 14), wrap="word")
        self.chat_display.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        
        self.chat_display.tag_config("User", foreground="#FFFFFF")
        self.chat_display.tag_config("Gemma (Front-Hand)", foreground="#4DB8FF")
        self.chat_display.tag_config("Qwen (Advisor + RAG)", foreground="#B180FF")
        self.chat_display.tag_config("System", foreground="#FF9933")
        self.chat_display.tag_config("Thought", foreground="#888888")
        
        # 1. Let CustomTkinter handle the text color safely
        self.chat_display.tag_config("CodeBlock", foreground="#A6E22E")     
        # 2. Force the raw underlying Tkinter widget to apply the monospace font
        self.chat_display._textbox.tag_configure("CodeBlock", font=("Consolas", 14, "bold"))
        self.chat_display._textbox.tag_configure("Thought", font=("Arial", 12, "italic"))
        
        # Visual Feedback (Progress Bar)
        self.progress = ctk.CTkProgressBar(self.main_frame, mode="indeterminate", height=4)
        self.progress.grid(row=2, column=0, sticky="ew", padx=10, pady=2)
        self.progress.grid_remove() # Hide initially

        # C. Input Area (Multi-line Textbox)
        self.input_frame = ctk.CTkFrame(self.main_frame, height=80)
        self.input_frame.grid(row=3, column=0, sticky="ew", pady=(5, 0))
        
        # We want the text box (which will be in column 2) to expand and take up empty space
        self.input_frame.grid_columnconfigure(2, weight=1)
        self.current_image_path = None 

        # Column 0: Mic Button
        txt_mic = "" if self.icn_mic else "🎙️"
        self.btn_mic = ctk.CTkButton(self.input_frame, image=self.icn_mic, text=txt_mic, width=40, height=40, fg_color="#555555", hover_color="#777777", command=self.toggle_mic)
        self.btn_mic.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="n")

        # Column 1: Attach Button
        txt_clip = "" if self.icn_clip else "📎"
        self.btn_attach = ctk.CTkButton(self.input_frame, image=self.icn_clip, text=txt_clip, width=40, height=40, command=self.attach_image)
        self.btn_attach.grid(row=0, column=1, padx=(5, 5), pady=10, sticky="n")

        # Column 2: The Textbox
        self.input_box = ctk.CTkTextbox(self.input_frame, height=60, wrap="word", font=("Arial", 14))
        self.input_box.grid(row=0, column=2, sticky="ew", padx=5, pady=10)
        
        self.input_box.insert("0.0", "Ask Julia... (Shift+Enter for new line)")
        self.input_box.bind("<FocusIn>", self.clear_placeholder)
        self.input_box.bind("<Return>", self.handle_return)
        self.input_box.bind("<Shift-Return>", self.handle_shift_return)

        # Column 3: Send Button
        self.btn_send = ctk.CTkButton(self.input_frame, text="Send", width=60, height=40, command=self.send_message)
        self.btn_send.grid(row=0, column=3, padx=(5, 10), pady=10, sticky="n")

    # Input & Threading Handling
    def clear_placeholder(self, event):
        if "Ask the Julia" in self.input_box.get("0.0", "end"):
            self.input_box.delete("0.0", "end")

    def handle_return(self, event):
        self.send_message()
        return "break" # Prevent default new line on Enter

    def handle_shift_return(self, event):
        return # Allow default new line on Shift+Enter
    
    def start_new_chat(self):
        if hasattr(self, 'embedded_code_blocks'):
            for block in self.embedded_code_blocks:
                try:
                    block.destroy()
                except Exception:
                    pass
            self.embedded_code_blocks.clear()
            
        # Execute the standard chat display deletion
        self.chat_display.configure(state="normal")
        self.chat_display.delete("0.0", "end")
        self.chat_display.insert('end', "System: Started a new conversation.\n\n", "System")
        self.chat_display.configure(state="disabled")
        # Add a visual divider to the JSON history without deleting past chats
        self.history_data.append({"role": "System", "text": "\n--- New Conversation ---\n"})
        self.save_history()
        
    def attach_image(self):
        # Allow code and text files alongside images
        file_path = filedialog.askopenfilename(
            title="Select a File", 
            filetypes=[("All Supported", "*.png *.jpg *.jpeg *.txt *.cs *.py *.json"),
                       ("Images", "*.png *.jpg *.jpeg"),
                       ("Code/Text", "*.txt *.cs *.py *.json")]
        )
        if file_path:
            self.current_image_path = file_path # (We reuse the variable name for simplicity)
            # Visually change icon to a document if it's text
            icon_text = "📄" if file_path.endswith(('.txt', '.cs', '.py', '.json')) else "🖼️"
            self.btn_attach.configure(fg_color="#2ECC71", text=icon_text) 
            self.input_box.delete("0.0", "end")
            self.input_box.insert("0.0", f"[Attached: {os.path.basename(file_path)}] ")
            
    def on_closing(self):
        # 1. Terminate the Audio Engine
        if hasattr(self, 'audio'):
            self.audio.stop_listening()
            
        # 2. Kill the System Tray Icon (CRITICAL FIX)
        if hasattr(self, 'tray_icon') and self.tray_icon is not None:
            try:
                self.tray_icon.stop()
            except Exception as e:
                print(f"[System] Tray icon cleanup bypassed: {e}")

        # 3. Destroy the Tkinter Interface
        self.quit()      # Stops the mainloop
        self.destroy()   # Destroys the widgets
        
        # 4. The "Nuclear Option" for Spyder/Anaconda
        # Because pystray and pyttsx3 COM objects resist shutting down in Spyder, 
        # we must force the OS to immediately terminate the background process.
        import os
        os._exit(0)
        
    def send_message(self):
        user_text = self.input_box.get("0.0", "end").strip()
        image_to_send = None # Safely default to None
        
        if self.current_image_path:
            filename = os.path.basename(self.current_image_path)
            if f"[Attached: {filename}]" in user_text:
                user_text = user_text.replace(f"[Attached: {filename}]", "").strip()
                
                # Check if it's a code/text file
                if self.current_image_path.endswith(('.txt', '.cs', '.py', '.json')):
                    try:
                        with open(self.current_image_path, 'r', encoding='utf-8') as f:
                            file_content = f.read()
                        user_text += f"\n\n--- Context from {filename} ---\n{file_content}\n--- End Context ---\n"
                        
                        # CRITICAL FIX: Ensure the router never sees this file path!
                        image_to_send = None 
                        
                    except Exception as e:
                        print(f"[System Error] Could not read file: {e}")
                else:
                    # It is a legitimate image; pass the path to the vision model
                    image_to_send = self.current_image_path
            else:
                self.current_image_path = None

        if not user_text and not image_to_send: return
        if not hasattr(self, 'router'): return
        
        self.input_box.delete("0.0", "end")
        
        display_text = f"\nYou: {user_text}"
        if self.current_image_path:
            display_text += f" [Attached: {os.path.basename(self.current_image_path)}]"
        display_text += "\n"
        
        self.append_text(display_text, "User")
        
        # Reset the attachment UI state
        self.current_image_path = None
        reset_text = "" if getattr(self, 'icn_clip', None) else "📎"
        self.btn_attach.configure(fg_color=["#3a7ebf", "#1f538d"], text=reset_text)
        
        # Start Progress Bar
        self.progress.grid()
        self.progress.start()
        
        self.in_code_block = False 
        self.current_code_box = None
        self._token_buffer = ""
        self.in_thought_block = False 
        
        threading.Thread(target=self.run_ai, args=(user_text, image_to_send, display_text), daemon=True).start()

    def run_ai(self, user_text, image_path, display_text):
        self.token_queue.put(("Julia: ", "System"))
        
        # Get full answer while streaming to UI
        full_answer = self.router.chat(user_text, image_path=image_path, stream_callback=self.handle_stream)
        
        # Make Julia speak if enabled
        if getattr(self, 'tts_enabled', False):
            self.audio.speak(full_answer)
            
        # Add a clean closing message so you know it's done
        self.token_queue.put(("\n\n[System: Task Completed]\n\n", "System"))
        self.token_queue.put(("[DONE]", "Command")) # Signal to stop progress bar
        
        self.history_data.append({"role": "User", "text": display_text})
        self.history_data.append({"role": "Julia", "text": f"Julia: {full_answer}\n"})
        self.save_history()
        self.token_queue.put(("[REFRESH_HISTORY]", "Command"))

    def handle_stream(self, token, model_name):
        self.token_queue.put((token, model_name))

    def check_queue(self):
        if not self.winfo_exists(): return
        while not self.token_queue.empty():
            token, tag = self.token_queue.get()
            
            # Catch background commands safely on the main UI thread
            if tag == "Command":
                if token == "[DONE]":
                    self.progress.stop()
                    self.progress.grid_remove()
                    self.is_thinking = False
                elif token == "[TOGGLE]":
                    self.toggle_window()
                elif token == "[SHOW]":
                    self.force_show()
                elif token == "[QUIT]":
                    self.quit_app()
                elif token == "[REFRESH_HISTORY]":
                    self.refresh_history_sidebar()
                continue
            
            if tag == "AudioCMD":
                if token == "[SHOW_UI]":
                    self.force_show()
                elif token == "[CMD_NEW_CHAT]":
                    self.start_new_chat()
                elif token == "[CMD_CLEAR_CHAT]":
                    self.clear_history()
                elif token == "[CMD_HIDE]":
                    self.withdraw()
                elif token.startswith("[FILL_INPUT]"):
                    dictated = token.replace("[FILL_INPUT]", "").strip()
                    current = self.input_box.get("0.0", "end").strip()
                    if current:
                        self.input_box.insert("end", " " + dictated)
                    else:
                        self.input_box.insert("end", dictated.capitalize())
                    self.input_box.focus_set()
                elif token.startswith("[APPEND_INPUT]"):
                    chunk = token.replace("[APPEND_INPUT]", "").strip()
                    current = self.input_box.get("0.0", "end").strip()
                    if current:
                        self.input_box.insert("end", " " + chunk)
                    else:
                        self.input_box.insert("end", chunk.capitalize())
                    self.input_box.see("end")
                    self.input_box.focus_set()
                else:
                    self.input_box.delete("0.0", "end")
                    self.input_box.insert("0.0", token)
                    self.send_message()
                continue
                
            self._insert_text(token, tag)
                
        self._queue_loop_id = self.after(50, self.check_queue)

    def _insert_text(self, text, base_tag):
        self.chat_display.configure(state="normal")
        self._token_buffer += text    
        
        # 1. Silently strip Gemma's operational XML tags so they don't pollute the UI
        hidden_tags = ["<draft>", "</draft>", "<escalate>true</escalate>", "<escalate>false</escalate>"]
        for t in hidden_tags:
            if t in self._token_buffer:
                self._token_buffer = self._token_buffer.replace(t, "\n")
                
        # 2. Wipe out the multi-line confidence block entirely
        import re
        self._token_buffer = re.sub(r'<confidence>.*?</confidence>', '', self._token_buffer, flags=re.DOTALL | re.IGNORECASE )
        while True:
            # ENTER THINK MODE
            if not self.in_thought_block:
                start_idx = self._token_buffer.find("<think>")
    
                if start_idx != -1:
                    # Print everything BEFORE <think>
                    before = self._token_buffer[:start_idx]
                    if before:
                        self._render_content(before, base_tag)
    
                    # Remove processed section + tag
                    self._token_buffer = self._token_buffer[start_idx + len("<think>"):]
    
                    self.in_thought_block = True
    
                    self.chat_display.insert(
                        "end",
                        "\n[Analyzing...]\n",
                        "Thought"
                    )
    
                    continue   
            # EXIT THINK MODE
            else:
                end_idx = self._token_buffer.find("</think>")
    
                if end_idx != -1:
                    thought_text = self._token_buffer[:end_idx]
    
                    if thought_text:
                        self._render_content(thought_text, "Thought")
    
                    self._token_buffer = self._token_buffer[end_idx + len("</think>"):]
                    self.in_thought_block = False
                    
                    # NEW SAFETY RESET: Ensure rogue thought-code doesn't corrupt the main UI
                    self.in_code_block = False 
                    self.current_code_box = None
    
                    self.chat_display.insert("end", "\n[Analysis Complete]\n\n", "Thought")
                    continue
            break    
        # Flush safe content
        if self._token_buffer:
            # DYNAMIC ANTI-TEARING: If an XML tag is opening but hasn't closed, wait.
            if "<" in self._token_buffer:
                last_open = self._token_buffer.rfind("<")
                last_close = self._token_buffer.rfind(">")
                if last_open > last_close: 
                    self.chat_display.configure(state="disabled")
                    return
    
            current_tag = "Thought" if self.in_thought_block else base_tag
    
            self._render_content(self._token_buffer, current_tag)
    
            self._token_buffer = ""
    
        self.chat_display.configure(state="disabled")
        
    def _render_content(self, content, tag):  
        parts = content.split("```")  
        for i, part in enumerate(parts):
    
            if i > 0:
                self.in_code_block = not self.in_code_block
    
                if self.in_code_block:
    
                    self.chat_display.insert("end", "\n")
    
                    code_frame = ctk.CTkFrame(
                        self.chat_display,
                        fg_color="#1E1E1E",
                        corner_radius=8
                    )
    
                    top_bar = ctk.CTkFrame(
                        code_frame,
                        height=30,
                        fg_color="#2D2D2D",
                        corner_radius=8
                    )
                    top_bar.pack(fill="x")
    
                    lbl_lang = ctk.CTkLabel(
                        top_bar,
                        text="💻 Code Snippet",
                        font=("Arial", 12, "bold"),
                        text_color="#CCCCCC"
                    )
                    lbl_lang.pack(side="left", padx=10)
    
                    inner_text = ctk.CTkTextbox(
                        code_frame,
                        height=200,
                        width=550,
                        fg_color="#1E1E1E",
                        text_color="#A6E22E",
                        font=("Consolas", 14),
                        wrap="word"
                    )
                    inner_text.pack(fill="both", expand=True, padx=5, pady=5)
    
                    def copy_to_clipboard(tb=inner_text):
                        self.clipboard_clear()
                        self.clipboard_append(tb.get("1.0", "end-1c"))
    
                    btn_copy = ctk.CTkButton(
                        top_bar,
                        text="📋 Copy",
                        width=50,
                        height=24,
                        fg_color="#444444",
                        hover_color="#555555",
                        command=copy_to_clipboard
                    )
                    btn_copy.pack(side="right", padx=5, pady=3)
    
                    self.chat_display._textbox.window_create(
                        "end",
                        window=code_frame
                    )
    
                    self.chat_display.insert("end", "\n")
    
                    self.current_code_box = inner_text
                    self.embedded_code_blocks.append(code_frame)
    
                else:
                    self.current_code_box = None
                    self.chat_display.insert("end", "\n")
    
            # NORMAL CONTENT
            if part:
    
                if self.in_code_block and self.current_code_box:
    
                    self.current_code_box.insert("end", part)
                    self.current_code_box.see("end")
    
                else:
    
                    self.chat_display.insert("end", part, tag)
                    self.chat_display.see("end")
                    
    def append_text(self, text, tag):
        self.token_queue.put((text, tag))

    # System Logic & Modals
    def setup_hotkey(self):
        # Drop a toggle command into the queue
        keyboard.add_hotkey('ctrl+alt+l', lambda: self.token_queue.put(("[TOGGLE]", "Command")))

    def toggle_window(self):
        if self.state() == "withdrawn":
            self.force_show()
        else:
            self.withdraw()
            
    def toggle_mic(self):
        """Turns the wake-word listener on and off."""
        if self.audio.is_listening:
            self.audio.stop_listening()
            self.btn_mic.configure(fg_color="#555555") # Grey
        else:
            self.audio.start_listening()
            self.btn_mic.configure(fg_color="#E74C3C") # Red (Live)

    def handle_audio_callback(self, command):
        """Processes signals sent from the threaded AudioEngine."""
        self.token_queue.put((command, "AudioCMD"))
        
    def force_show(self):
        self.deiconify()
        self.attributes('-topmost', True)
        self.attributes('-topmost', False)
        self.input_box.focus()

    def quit_app(self):
        """Safely shuts down all threads, icons, and loops."""
        self.on_closing()

    def open_settings(self):
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Oracle Core Settings")
        settings_window.geometry("550x700")
        settings_window.attributes('-topmost', True)
        
        # A scrollable frame so the UI never falls off the screen
        scroll_frame = ctk.CTkScrollableFrame(settings_window, fg_color="transparent")
        scroll_frame.pack(fill="both", expand=True, padx=10, pady=10)
        
        # Always On Top Toggle
        self.always_on_top = getattr(self, 'always_on_top', False)
        def toggle_top():
            self.always_on_top = not self.always_on_top
            self.attributes('-topmost', self.always_on_top)
            
        sw_top = ctk.CTkSwitch(scroll_frame, text="Pin Window Above Unity", command=toggle_top)
        sw_top.pack(pady=(10, 10), padx=20, anchor="w")
        if self.always_on_top: sw_top.select()

        # RAM Safety Threshold Slider
        lbl_ram = ctk.CTkLabel(scroll_frame, text="Heavy Advisor RAM Threshold (GB):", font=("Arial", 12, "bold"))
        lbl_ram.pack(padx=20, anchor="w")
        
        ram_val_label = ctk.CTkLabel(scroll_frame, text="")
        ram_val_label.pack(padx=20, anchor="w")
        
        ram_slider = ctk.CTkSlider(scroll_frame, from_=10, to=40, number_of_steps=30)
        ram_slider.pack(fill="x", padx=20, pady=5)
        
        if hasattr(self, 'router'):
            ram_slider.set(self.router.ram_threshold_gb)
            ram_val_label.configure(text=f"Current: {self.router.ram_threshold_gb} GB")

        def update_ram(value):
            if hasattr(self, 'router'):
                self.router.ram_threshold_gb = round(float(value), 1)
                ram_val_label.configure(text=f"Current: {self.router.ram_threshold_gb} GB")
        ram_slider.configure(command=update_ram)

        # Dynamic Model Selectors
        available_models = []
        if hasattr(self, 'router'):
            available_models = self.router.available_models
        if not available_models: available_models = ["No models found"]
        
        lbl_front = ctk.CTkLabel(scroll_frame, text="Front-Hand Model:", font=("Arial", 12, "bold"))
        lbl_front.pack(padx=20, pady=(15, 0), anchor="w")
        opt_front = ctk.CTkOptionMenu(scroll_frame, values=available_models)
        opt_front.pack(fill="x", padx=20, pady=5)
        if hasattr(self, 'router') and self.router.front_model in available_models:
            opt_front.set(self.router.front_model)

        lbl_adv = ctk.CTkLabel(scroll_frame, text="Heavy Advisor Model:", font=("Arial", 12, "bold"))
        lbl_adv.pack(padx=20, pady=(10, 0), anchor="w")
        opt_adv = ctk.CTkOptionMenu(scroll_frame, values=available_models)
        opt_adv.pack(fill="x", padx=20, pady=5)
        if hasattr(self, 'router') and self.router.heavy_advisor in available_models:
            opt_adv.set(self.router.heavy_advisor)

        # Dynamic Prompt Editors
        lbl_g_prompt = ctk.CTkLabel(scroll_frame, text="Front-Hand System Prompt:", font=("Arial", 12, "bold"))
        lbl_g_prompt.pack(pady=(20, 5), padx=20, anchor="w")
        txt_g_prompt = ctk.CTkTextbox(scroll_frame, height=80, wrap="word")
        txt_g_prompt.pack(fill="x", padx=20)
        if hasattr(self, 'router'): txt_g_prompt.insert("0.0", self.router.gemma_system_prompt)

        lbl_q_prompt = ctk.CTkLabel(scroll_frame, text="Advisor System Prompt:", font=("Arial", 12, "bold"))
        lbl_q_prompt.pack(pady=(15, 5), padx=20, anchor="w")
        txt_q_prompt = ctk.CTkTextbox(scroll_frame, height=80, wrap="word")
        txt_q_prompt.pack(fill="x", padx=20)
        if hasattr(self, 'router'): txt_q_prompt.insert("0.0", self.router.qwen_system_prompt)

        # Audio Settings
        lbl_audio = ctk.CTkLabel(scroll_frame, text="Audio Integration:", font=("Arial", 12, "bold"))
        lbl_audio.pack(padx=20, pady=(20, 0), anchor="w")

        tts_var = ctk.BooleanVar(value=getattr(self, 'tts_enabled', False))
        sw_tts = ctk.CTkSwitch(scroll_frame, text="Julia Speaks Answers (TTS)", variable=tts_var, onvalue=True, offvalue=False)
        sw_tts.pack(pady=5, padx=20, anchor="w")

        
        def change_voice(choice):
            if hasattr(self, 'audio'): self.audio.set_voice(choice)
        opt_voice = ctk.CTkOptionMenu(scroll_frame, values=["Female", "Male"], command=change_voice)
        opt_voice.pack(pady=5, padx=20, anchor="w")
        opt_voice.set("Female")

        lbl_wake = ctk.CTkLabel(scroll_frame, text="Wake Greeting:", font=("Arial", 12))
        lbl_wake.pack(padx=20, pady=(10, 0), anchor="w")
        txt_wake = ctk.CTkEntry(scroll_frame, width=250)
        txt_wake.pack(padx=20, pady=5, anchor="w", fill="x")
        if hasattr(self, 'audio'):
            txt_wake.insert(0, self.audio.wake_response)

        # Save Button
        def save_settings():
            # Grab data from ALL the variables defined above
            if hasattr(self, 'router'):
                self.router.gemma_system_prompt = txt_g_prompt.get("0.0", "end").strip()
                self.router.qwen_system_prompt = txt_q_prompt.get("0.0", "end").strip()
                self.router.front_model = opt_front.get()
                self.router.heavy_advisor = opt_adv.get()
            
            self.tts_enabled = tts_var.get()
            if hasattr(self, 'audio'):
                self.audio.set_wake_response(txt_wake.get())
                
            settings_window.destroy()
            self.append_text("System: Settings & Models Updated.\n\n", "System")

        btn_save = ctk.CTkButton(scroll_frame, text="Apply & Save", fg_color="#2ECC71", hover_color="#27AE60", command=save_settings)
        btn_save.pack(pady=20)

    # Clean Memory Management
    def save_history(self):
        with open(self.chat_history_file, 'w', encoding='utf-8') as f:
            json.dump(self.history_data, f, indent=4)

    def load_history(self):
        if os.path.exists(self.chat_history_file):
            try:
                with open(self.chat_history_file, 'r', encoding='utf-8') as f:
                    self.history_data = json.load(f)
                    for item in self.history_data:
                        tag = "User" if item["role"] == "User" else "Qwen (Advisor + RAG)" # Defaulting color to purple for loaded history
                        self._insert_text(item["text"], tag)
            except Exception:
                pass
        self.refresh_history_sidebar()

    def refresh_history_sidebar(self):
        for widget in self.history_list.winfo_children():
            widget.destroy()
            
        # Create a button for each user prompt
        for idx, item in enumerate(self.history_data):
            if item["role"] == "User":
                short_title = item["text"].replace("You: ", "").replace("\n", "").strip()[:20] + "..."
                # FIX: Pass the specific index to the button command
                btn = ctk.CTkButton(self.history_list, text=short_title, anchor="w", fg_color="transparent", 
                                    hover_color="#333333", text_color="#AAAAAA",
                                    command=lambda i=idx: self.load_specific_chat(i))
                btn.pack(fill="x", pady=2)

    def load_specific_chat(self, index):
        """Clears the screen and displays only the selected conversation."""
        self.chat_display.configure(state="normal")
        self.chat_display.delete('1.0', 'end')
        
        # Insert the User question
        user_msg = self.history_data[index]
        self.chat_display.insert("end", user_msg["text"], "User")
        
        # Try to find and insert the Julia's answer that immediately followed
        if index + 1 < len(self.history_data) and self.history_data[index + 1]["role"] == "Julia":
            Julia_msg = self.history_data[index + 1]
            self.chat_display.insert("end", Julia_msg["text"], "Qwen (Advisor + RAG)")
            
        self.chat_display.configure(state="disabled")
        self.append_text("\n[System: Viewing past conversation]\n\n", "System")

    def clear_history(self):
        if hasattr(self, 'embedded_code_blocks'):
            for block in self.embedded_code_blocks:
                try:
                    block.destroy()
                except Exception:
                    pass
            self.embedded_code_blocks.clear()
            
        # Execute the standard chat display deletion
        self.chat_display.configure(state="normal")
        self.chat_display.delete("0.0", "end")
        self.chat_display.configure(state="disabled")
        self.history_data = []
        self.save_history()
        self.refresh_history_sidebar()
        self.append_text("System: History Cleared.\n\n", "System")

if __name__ == "__main__":
    app = UnityJuliaUI()
    app.mainloop()