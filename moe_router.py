import ollama
import psutil
from rag_pipeline import KnowledgeBase

class MoERouter:
    def __init__(self):
        self.front_model = "gemma4:e4b"
        self.heavy_advisor = "qwen3.6:35b-a3b"
        self.safe_advisor = "qwen3.5:9b"
        
        self.ram_threshold_gb = 25.0 
        
        print("Initializing Knowledge Base...")
        self.rag_db = KnowledgeBase()
        
        self.gemma_system_prompt = """You are speaker part of personal assistant Julia, in the role of fast, front-line Unity C# assistant. 
Your job is to answer simple syntax, UI, and basic scripting questions. You can analyze images if provided.
If the user asks a complex architectural question, requires deep documentation, or if you are unsure, reply EXACTLY with: <ESCALATE>
so, you will be able to ask your supervisor and it will try to give answer. You can also learn from that."""

        self.qwen_system_prompt = """You are advisor part of personal assistant Julia, the role of Senior Unity Architect. You step in when the front-line model is unsure. 
You will be provided with context from the official Unity documentation. 
Use the context to provide a highly detailed, perfectly structured, and accurate answer."""

    def check_available_ram(self):
        available_bytes = psutil.virtual_memory().available
        return available_bytes / (1024 ** 3)

    # Added image_path parameter
    def chat(self, user_query, image_path=None, stream_callback=None):
        if stream_callback:
            stream_callback("\n[System: Front-Hand skimming documentation...]\n", "System")

        # SHALLOW RAG: Get only the top 1 result for speed
        shallow_context = self.rag_db.search(user_query, top_k=1)
        gemma_query = f"CONTEXT:\n{shallow_context}\n\nUSER QUESTION:\n{user_query}"

        # Build the user message
        user_message = {'role': 'user', 'content': gemma_query}
        if image_path:
            user_message['images'] = [image_path]

        try:
            gemma_response = ollama.chat(
                model=self.front_model,
                messages=[
                    {'role': 'system', 'content': self.gemma_system_prompt},
                    user_message
                ]
            )
            reply = gemma_response['message']['content'].strip()
            
            if "<ESCALATE>" in reply:
                if stream_callback:
                    stream_callback("\n[System: Task complex. Escaping to Advisor...]\n", "System")
                return self._call_advisor(user_query, user_message, stream_callback)
            
            if stream_callback:
                import time
                for char in reply:
                    stream_callback(char, "Gemma (Front-Hand)")
                    time.sleep(0.005)
            return reply

        except Exception as e:
            if stream_callback:
                stream_callback(f"\n[System Error: {e}. Falling back to Advisor.]\n", "System")
            return self._call_advisor(user_query, user_message, stream_callback)
        
    # Accept the pre-built user_message (which includes the image)
    def _call_advisor(self, user_query, user_message, stream_callback):
        if stream_callback:
            stream_callback("[System: Advisor diving deep into Knowledge Base...]\n", "System")
            
        # DEEP RAG: Get the top 5 results for maximum context
        deep_context = self.rag_db.search(user_query, top_k=5)
        
        available_ram = self.check_available_ram()
        if available_ram >= self.ram_threshold_gb:
            active_model = self.heavy_advisor
        else:
            active_model = self.safe_advisor
            if stream_callback:
                stream_callback(f"[System Warning: Low RAM ({available_ram:.1f}GB). Using Safe Advisor.]\n", "System")

        # Overwrite the Gemma shallow prompt with the new Deep prompt
        advisor_message = user_message.copy()
        advisor_message['content'] = f"CONTEXT:\n{deep_context}\n\nUSER QUESTION:\n{user_query}"
        
        stream = ollama.chat(
            model=active_model,
            messages=[
                {'role': 'system', 'content': self.qwen_system_prompt},
                advisor_message
            ],
            stream=True
        )
        
        full_response = ""
        for chunk in stream:
            token = chunk['message']['content']
            full_response += token
            if stream_callback:
                stream_callback(token, "Qwen (Advisor + RAG)")
                
        return full_response