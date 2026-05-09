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
        self.recognizer.dynamic_energy_threshold = False
        self.recognizer.energy_threshold = 300

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
            print("\n[System] Calibrating microphone...")
            self.recognizer.adjust_for_ambient_noise(source, duration=1.5)
            print("[System] Ready. Waiting for wake word 'Julia'.\n")
            
        while self.is_listening:
            try:
                # Passive background listening
                with mic as source:
                    audio = self.recognizer.listen(source, timeout=2, phrase_time_limit=4)
                
                text = self.recognizer.recognize_google(audio).lower()
                print(f"[Passive]: {text}") 
                
                if "julia" in text:
                    print("\n*** WAKE WORD DETECTED ***") 
                    self.speak(self.wake_response)
                    self.ui_callback("[SHOW_UI]") 
                    
                    while self.tts_busy.is_set():
                        time.sleep(0.2)
                    
                    print(">>> [Dictation OPEN] Speak naturally. Say 'stop listening' to close mic.")
                    
                    # Dictation Loop: Capture and stream chunks instantly
                    while True:
                        try:
                            with mic as source:
                                audio_chunk = self.recognizer.listen(source, timeout=3, phrase_time_limit=10)
                                
                            chunk_text = self.recognizer.recognize_google(audio_chunk).lower()
                            print(f"[Dictated]: {chunk_text}")
                            
                            # Check for the kill-switch phrase
                            if "stop listening" in chunk_text or "end of message" in chunk_text:
                                clean_chunk = chunk_text.replace("stop listening", "").replace("end of message", "").strip()
                                if clean_chunk:
                                    self.ui_callback(f"[APPEND_INPUT] {clean_chunk}")
                                    
                                print(">>> [Dictation Closed] Returning to passive state.\n")
                                break # Terminate dictation mode
                                
                            # Stream the chunk directly to the UI immediately
                            self.ui_callback(f"[APPEND_INPUT] {chunk_text}")
                            
                        except sr.WaitTimeoutError:
                            # User paused to think. Continue looping.
                            continue
                        except sr.UnknownValueError:
                            continue
                        except Exception as e:
                            print(f"[Dictation Error]: {e}")
                            break
                            
            except sr.WaitTimeoutError:
                continue 
            except sr.UnknownValueError:
                continue 
            except Exception:
                pass

    def _process_recorded_audio(self, text):
        print(f"\n[FINAL DICTATION]: \"{text}\"\n")
        
        # Note: Length checks added to prevent accidental system commands if dictated during a long sentence.
        if "new chat" in text and len(text) < 15:
            self.speak("Starting fresh.")
            self.ui_callback("[CMD_NEW_CHAT]")
        elif ("clear" in text or "delete" in text) and len(text) < 15:
            self.speak("History wiped.")
            self.ui_callback("[CMD_CLEAR_CHAT]")
        elif ("close" in text or "hide" in text) and len(text) < 15:
            self.speak("Going to sleep.")
            self.ui_callback("[CMD_HIDE]")
        else:
            # Route standard dictated text to the UI input box instead of auto-sending
            self.ui_callback(f"[FILL_INPUT] {text}")

    def start_listening(self):
        if not self.is_listening:
            self.is_listening = True
            self._listen_thread = threading.Thread(target=self._audio_loop, daemon=True)
            self._listen_thread.start()

    def stop_listening(self):
        self.is_listening = False
        self.awaiting_followup = False
        print("[Audio] Microphone offline.")