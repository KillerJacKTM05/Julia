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
        
        self.chat_history_file = "chat_history.json"
        self.token_queue = queue.Queue()
        self.history_data = [] # Stores clean {"role": "User/Julia", "text": "..."} blocks
        self.is_thinking = False
        # Audio State Variables
        self.tts_enabled = False
        self.audio = AudioEngine(self.handle_audio_callback)
        
        self.build_ui()
        self.setup_hotkey()
        
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
        
        self.btn_settings = ctk.CTkButton(self.top_bar, text="⚙️ Settings", width=80, command=self.open_settings)
        self.btn_settings.pack(side="right", padx=10, pady=5)
        
        self.btn_new_chat = ctk.CTkButton(self.top_bar, text="➕ New Chat", width=80, fg_color="#2ECC71", hover_color="#27AE60", command=self.start_new_chat)
        self.btn_new_chat.pack(side="left", padx=10, pady=5)

        # Chat Display
        self.chat_display = ctk.CTkTextbox(self.main_frame, state="disabled", font=("Consolas", 14), wrap="word")
        self.chat_display.grid(row=1, column=0, sticky="nsew", pady=(0, 5))
        
        self.chat_display.tag_config("User", foreground="#FFFFFF")
        self.chat_display.tag_config("Gemma (Front-Hand)", foreground="#4DB8FF")
        self.chat_display.tag_config("Qwen (Advisor + RAG)", foreground="#B180FF")
        self.chat_display.tag_config("System", foreground="#FF9933")

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
        self.btn_mic = ctk.CTkButton(self.input_frame, text="🎙️", width=40, height=40, fg_color="#555555", hover_color="#777777", command=self.toggle_mic)
        self.btn_mic.grid(row=0, column=0, padx=(10, 0), pady=10, sticky="n")

        # Column 1: Attach Button
        self.btn_attach = ctk.CTkButton(self.input_frame, text="📎", width=40, height=40, command=self.attach_image)
        self.btn_attach.grid(row=0, column=1, padx=(5, 5), pady=10, sticky="n")

        # Column 2: The Textbox (Removed the duplicate declaration)
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
        self.chat_display.configure(state="normal")
        self.chat_display.delete('1.0', 'end')
        self.chat_display.insert('end', "System: Started a new conversation.\n\n", "System")
        self.chat_display.configure(state="disabled")
        # Add a visual divider to the JSON history without deleting past chats
        self.history_data.append({"role": "System", "text": "\n--- New Conversation ---\n"})
        self.save_history()
        
    def attach_image(self):
        file_path = filedialog.askopenfilename(title="Select an Image", filetypes=[("Image files", "*.png *.jpg *.jpeg")])
        if file_path:
            self.current_image_path = file_path
            self.btn_attach.configure(fg_color="#2ECC71", text="🖼️") 
            self.input_box.delete("0.0", "end")
            self.input_box.insert("0.0", f"[Attached: {os.path.basename(file_path)}] ")

    def send_message(self):
        user_text = self.input_box.get("0.0", "end").strip()
        
        # Strip attachment text if it's there
        if self.current_image_path and user_text.startswith("[Attached:"):
            user_text = user_text.split("]", 1)[-1].strip()

        if not user_text and not self.current_image_path: return
        if not hasattr(self, 'router'): return
        
        self.input_box.delete("0.0", "end")
        
        display_text = f"\nYou: {user_text}"
        if self.current_image_path:
            display_text += f" [Attached: {os.path.basename(self.current_image_path)}]"
        display_text += "\n"
        
        self.append_text(display_text, "User")
        
        image_to_send = self.current_image_path
        self.current_image_path = None
        self.btn_attach.configure(fg_color=["#3a7ebf", "#1f538d"], text="📎")
        
        # Start Progress Bar
        self.progress.grid()
        self.progress.start()
        
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
        
        if getattr(self, 'tts_enabled', False):
            self.audio.speak(full_answer)

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
                else:
                    # It's a spoken query! Put it in the box and hit send.
                    self.input_box.delete("0.0", "end")
                    self.input_box.insert("0.0", token)
                    self.send_message()
                continue
                
            self._insert_text(token, tag)
                
        self.after(50, self.check_queue)

    def _insert_text(self, text, tag):
        self.chat_display.configure(state="normal")
        self.chat_display.insert("end", text, tag)
        self.chat_display.configure(state="disabled")
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

    def handle_audio_callback(self, command_or_text):
        """Receives text from the AudioEngine thread safely."""
        self.token_queue.put((command_or_text, "AudioCMD"))
        
    def force_show(self):
        self.deiconify()
        self.attributes('-topmost', True)
        self.attributes('-topmost', False)
        self.input_box.focus()

    def quit_app(self):
        """Safely shuts down all threads and icons to prevent bgerror crashes."""
        self.audio.stop_listening()
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        self.quit() # Halts the Tkinter mainloop
        self.destroy() # Destroys the window

    def open_settings(self):
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Julia Core Settings")
        settings_window.geometry("550x750")
        settings_window.attributes('-topmost', True)
        
        # 1. Always On Top Toggle
        self.always_on_top = getattr(self, 'always_on_top', False)
        def toggle_top():
            self.always_on_top = not self.always_on_top
            self.attributes('-topmost', self.always_on_top)
            
        sw_top = ctk.CTkSwitch(settings_window, text="Pin Window Above Unity", command=toggle_top)
        sw_top.pack(pady=(20, 10), padx=20, anchor="w")
        if self.always_on_top: sw_top.select()

        # 2. RAM Safety Threshold Slider
        lbl_ram = ctk.CTkLabel(settings_window, text="Heavy Advisor RAM Threshold (GB):", font=("Arial", 12, "bold"))
        lbl_ram.pack(padx=20, anchor="w")
        
        ram_val_label = ctk.CTkLabel(settings_window, text="")
        ram_val_label.pack(padx=20, anchor="w")
        
        ram_slider = ctk.CTkSlider(settings_window, from_=10, to=40, number_of_steps=30)
        ram_slider.pack(fill="x", padx=20, pady=5)
        
        if hasattr(self, 'router'):
            ram_slider.set(self.router.ram_threshold_gb)
            ram_val_label.configure(text=f"Current: {self.router.ram_threshold_gb} GB")
            
        def update_ram(value):
            if hasattr(self, 'router'):
                self.router.ram_threshold_gb = round(float(value), 1)
                ram_val_label.configure(text=f"Current: {self.router.ram_threshold_gb} GB")
        ram_slider.configure(command=update_ram)

        # 3. Dynamic Prompt Editors
        lbl_g_prompt = ctk.CTkLabel(settings_window, text="Front-Hand (Gemma) System Prompt:", font=("Arial", 12, "bold"))
        lbl_g_prompt.pack(pady=(20, 5), padx=20, anchor="w")
        txt_g_prompt = ctk.CTkTextbox(settings_window, height=100, wrap="word")
        txt_g_prompt.pack(fill="x", padx=20)
        if hasattr(self, 'router'): txt_g_prompt.insert("0.0", self.router.gemma_system_prompt)

        lbl_q_prompt = ctk.CTkLabel(settings_window, text="Advisor (Qwen) System Prompt:", font=("Arial", 12, "bold"))
        lbl_q_prompt.pack(pady=(20, 5), padx=20, anchor="w")
        txt_q_prompt = ctk.CTkTextbox(settings_window, height=100, wrap="word")
        txt_q_prompt.pack(fill="x", padx=20)
        if hasattr(self, 'router'): txt_q_prompt.insert("0.0", self.router.qwen_system_prompt)
        
        # 4. Audio Settings
        lbl_audio = ctk.CTkLabel(settings_window, text="Audio Integration:", font=("Arial", 12, "bold"))
        lbl_audio.pack(padx=20, pady=(20, 0), anchor="w")

        def toggle_tts():
            self.tts_enabled = not getattr(self, 'tts_enabled', False)
        sw_tts = ctk.CTkSwitch(settings_window, text="Julia Speaks Answers (TTS)", command=toggle_tts)
        sw_tts.pack(pady=5, padx=20, anchor="w")
        if getattr(self, 'tts_enabled', False): sw_tts.select()
        
        def change_voice(choice):
            self.audio.set_voice(choice)
        opt_voice = ctk.CTkOptionMenu(settings_window, values=["Female", "Male"], command=change_voice)
        opt_voice.pack(pady=5, padx=20, anchor="w")
        opt_voice.set("Female")
        
        # Customizable Wake Response Input
        lbl_wake = ctk.CTkLabel(settings_window, text="Wake Greeting:", font=("Arial", 12))
        lbl_wake.pack(padx=20, pady=(10, 0), anchor="w")
        
        txt_wake = ctk.CTkEntry(settings_window, width=250)
        txt_wake.pack(padx=20, pady=5, anchor="w")
        if hasattr(self, 'audio'):
            txt_wake.insert(0, self.audio.wake_response)
            
        # Save Button
        def save_settings():
            if hasattr(self, 'router'):
                self.router.gemma_system_prompt = txt_g_prompt.get("0.0", "end").strip()
                self.router.qwen_system_prompt = txt_q_prompt.get("0.0", "end").strip()
                
            if hasattr(self, 'audio'):
                self.audio.set_wake_response(txt_wake.get())
                
            settings_window.destroy()
            self.append_text("System: Core Settings Updated.\n\n", "System")

        btn_save = ctk.CTkButton(settings_window, text="Apply & Save", fg_color="#2ECC71", hover_color="#27AE60", command=save_settings)
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
        self.chat_display.configure(state="normal")
        self.chat_display.delete('1.0', 'end')
        self.chat_display.configure(state="disabled")
        self.history_data = []
        self.save_history()
        self.refresh_history_sidebar()
        self.append_text("System: History Cleared.\n\n", "System")

if __name__ == "__main__":
    app = UnityJuliaUI()
    app.mainloop()