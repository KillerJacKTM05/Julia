import pyttsx3
import speech_recognition as sr
import threading
import queue
import time
import re

class AudioEngine:
    def __init__(self, ui_callback):
        self.ui_callback = ui_callback 
        self.is_listening = False
        self._listen_thread = None
        self.awaiting_followup = False
        self.wake_response = "Yes?" 
        
        self.tts_busy = threading.Event()
        
        self.tts_queue = queue.Queue()
        self._tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
        self._tts_thread.start()
        
        self.recognizer = sr.Recognizer()
        self.recognizer.pause_threshold = 1.5 
        self.recognizer.dynamic_energy_threshold = True 

    def _tts_worker(self):
        import pythoncom
        pythoncom.CoInitialize() 
        
        tts_engine = pyttsx3.init()
        tts_engine.setProperty('rate', 170)
        
        while True:
            item = self.tts_queue.get()
            
            if isinstance(item, tuple) and item[0] == "[SET_VOICE]":
                voices = tts_engine.getProperty('voices')
                gender = item[1].lower()
                if gender == "female" and len(voices) > 1:
                    tts_engine.setProperty('voice', voices[1].id)
                elif voices:
                    tts_engine.setProperty('voice', voices[0].id)
            elif isinstance(item, str):
                try:
                    self.tts_busy.set() # Lock the audio system
                    tts_engine.say(item)
                    tts_engine.runAndWait()
                except Exception as e:
                    print(f"[TTS Error]: {e}")
                finally:
                    self.tts_busy.clear() # Unlock the audio system
                    
            self.tts_queue.task_done()

    def set_voice(self, gender):
        self.tts_queue.put(("[SET_VOICE]", gender))

    def speak(self, text):
        clean_text = re.sub(r'[*#`_]', '', text)
        self.tts_queue.put(clean_text)

    def set_wake_response(self, text):
        if text.strip():
            self.wake_response = text.strip()

    def set_awaiting_followup(self, state):
        self.awaiting_followup = state

    def _audio_loop(self):
        mic = sr.Microphone()
        with mic as source:
            print("[Audio] Calibrating mic to room noise...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1.5)
            print("[Audio] Ready. Say 'Julia' to wake...")
            
        while self.is_listening:
            try:
                # Continuous Conversation Bypass
                if self.awaiting_followup:
                    print("[Audio] Follow-up window open. Speak now...")
                    with mic as source:
                        # FIX: phrase_time_limit=None lets you talk as long as you want
                        audio_cmd = self.recognizer.listen(source, timeout=10, phrase_time_limit=None)
                    self.awaiting_followup = False 
                    self._process_recorded_audio(audio_cmd)
                    continue

                # Standard Wake Word Mode
                with mic as source:
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=4)
                
                text = self.recognizer.recognize_google(audio).lower()
                
                if "Julia" in text:
                    print(f"[Heard Wake]: {text}") 
                    self.speak(self.wake_response)
                    self.ui_callback("[SHOW_UI]") 
                    
                    # FIX: Wait patiently for the TTS to finish saying "Yes?"
                    while self.tts_busy.is_set():
                        time.sleep(0.2)
                    
                    with mic as source:
                        print("[Audio] Julia awake. Listening for query...")
                        # FIX: phrase_time_limit=None lets you talk as long as you want
                        audio_cmd = self.recognizer.listen(source, timeout=5, phrase_time_limit=None)
                    self._process_recorded_audio(audio_cmd)
                            
            except sr.WaitTimeoutError:
                if self.awaiting_followup:
                    print("[Audio] Follow-up window closed.")
                    self.awaiting_followup = False
                continue 
            except sr.UnknownValueError:
                continue 
            except Exception as e:
                print(f"[Audio Error]: {e}")

    def _process_recorded_audio(self, audio_data):
        try:
            query = self.recognizer.recognize_google(audio_data).lower()
            print(f"[Heard Query]: {query}")
            
            if "new chat" in query:
                self.speak("Starting fresh.")
                self.ui_callback("[CMD_NEW_CHAT]")
            elif "clear" in query or "delete" in query:
                self.speak("History wiped.")
                self.ui_callback("[CMD_CLEAR_CHAT]")
            elif "close" in query or "hide" in query:
                self.speak("Going to sleep.")
                self.ui_callback("[CMD_HIDE]")
            else:
                self.ui_callback(query)
        except sr.UnknownValueError:
            print("[Audio] Could not understand audio.")

    def start_listening(self):
        if not self.is_listening:
            self.is_listening = True
            self._listen_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._listen_thread.start()

    def stop_listening(self):
        self.is_listening = False
        self.awaiting_followup = False
        print("[Audio] Microphone offline.")