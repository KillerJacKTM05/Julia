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

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

class UnityOracleUI(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Unity Oracle (MoE)")
        self.geometry("900x650")
        self.minsize(600, 500)
        
        self.chat_history_file = "chat_history.json"
        self.token_queue = queue.Queue()
        self.history_data = [] # Now stores clean {"role": "User/Oracle", "text": "..."} blocks
        self.is_thinking = False
        
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
        self.append_text("System: Oracle is Ready. Press Ctrl+Alt+L to toggle.\n\n", "System")
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
        font = ImageFont.truetype("DejaVuSerif-Bold.ttf", 36)
        text = "O"
        # Get exact bounding box
        bbox = draw.textbbox((0, 0), text, font=font)
        w = bbox[2] - bbox[0]
        h = bbox[3] - bbox[1]
        # Center it
        position = ((64 - w) // 2, (64 - h) // 2)
        draw.text(position, text, fill="white", font=font)
        
        menu = pystray.Menu(
            pystray.MenuItem("Show Oracle", lambda: self.token_queue.put(("[SHOW]", "Command"))),
            pystray.MenuItem("Quit", lambda: self.token_queue.put(("[QUIT]", "Command")))
        )
        self.tray_icon = pystray.Icon("UnityOracle", image, "Unity Oracle", menu)
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
        self.input_frame.grid_columnconfigure(1, weight=1)
        self.current_image_path = None 

        self.btn_attach = ctk.CTkButton(self.input_frame, text="📎", width=40, height=40, command=self.attach_image)
        self.btn_attach.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="n")

        # Replaced CTkEntry with CTkTextbox for wrapping and multi-line
        self.input_box = ctk.CTkTextbox(self.input_frame, height=60, wrap="word", font=("Arial", 14))
        self.input_box.grid(row=0, column=1, sticky="ew", padx=5, pady=10)
        self.input_box.insert("0.0", "Ask the Oracle... (Shift+Enter for new line)")
        self.input_box.bind("<FocusIn>", self.clear_placeholder)
        self.input_box.bind("<Return>", self.handle_return)
        self.input_box.bind("<Shift-Return>", self.handle_shift_return)

        self.btn_send = ctk.CTkButton(self.input_frame, text="Send", width=60, height=40, command=self.send_message)
        self.btn_send.grid(row=0, column=2, padx=(5, 10), pady=10, sticky="n")

    # Input & Threading Handling
    def clear_placeholder(self, event):
        if "Ask the Oracle" in self.input_box.get("0.0", "end"):
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
        self.token_queue.put(("Oracle: ", "System"))
        
        # Get full answer while streaming to UI
        full_answer = self.router.chat(user_text, image_path=image_path, stream_callback=self.handle_stream)
        
        # Add a clean closing message so you know it's done
        self.token_queue.put(("\n\n[System: Task Completed]\n\n", "System"))
        self.token_queue.put(("[DONE]", "Command")) # Signal to stop progress bar
        
        self.history_data.append({"role": "User", "text": display_text})
        self.history_data.append({"role": "Oracle", "text": f"Oracle: {full_answer}\n"})
        self.save_history()
        self.refresh_history_sidebar()

    def handle_stream(self, token, model_name):
        self.token_queue.put((token, model_name))

    def check_queue(self):
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

    def force_show(self):
        self.deiconify()
        self.attributes('-topmost', True)
        self.attributes('-topmost', False)
        self.input_box.focus()

    def quit_app(self):
        if hasattr(self, 'tray_icon'):
            self.tray_icon.stop()
        self.destroy()

    def open_settings(self):
        settings_window = ctk.CTkToplevel(self)
        settings_window.title("Oracle Core Settings")
        settings_window.geometry("550x650")
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

        # Save Button
        def save_settings():
            if hasattr(self, 'router'):
                self.router.gemma_system_prompt = txt_g_prompt.get("0.0", "end").strip()
                self.router.qwen_system_prompt = txt_q_prompt.get("0.0", "end").strip()
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
        # Clear existing buttons
        for widget in self.history_list.winfo_children():
            widget.destroy()
            
        # Create a button for each user prompt in history
        user_queries = [item["text"] for item in self.history_data if item["role"] == "User"]
        for idx, query in enumerate(reversed(user_queries)):
            short_title = query.replace("You: ", "").strip()[:20] + "..."
            btn = ctk.CTkButton(self.history_list, text=short_title, anchor="w", fg_color="transparent", 
                                hover_color="#333333", text_color="#AAAAAA")
            btn.pack(fill="x", pady=2)

    def clear_history(self):
        self.chat_display.configure(state="normal")
        self.chat_display.delete('1.0', 'end')
        self.chat_display.configure(state="disabled")
        self.history_data = []
        self.save_history()
        self.refresh_history_sidebar()
        self.append_text("System: History Cleared.\n\n", "System")

if __name__ == "__main__":
    app = UnityOracleUI()
    app.mainloop()