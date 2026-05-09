import re
import ollama
import psutil
import requests
import time
from rag_pipeline import KnowledgeBase

class MoERouter:
    def __init__(self):
        # Fetch dynamically downloaded models
        self.available_models = self.get_local_models()
        
        # Set defaults, but gracefully fall back to whatever is installed
        self.front_model = "gemma4:e4b" if "gemma4:e4b" in self.available_models else (self.available_models[0] if self.available_models else "")
        self.heavy_advisor = "qwen3.6:35b-a3b" if "qwen3.6:35b-a3b" in self.available_models else self.front_model
        self.safe_advisor = "qwen3.5:9b" if "qwen3.5:9b" in self.available_models else self.front_model
        
        self.ram_threshold_gb = 25.0 
        
        print("Initializing Knowledge Base...")
        self.rag_db = KnowledgeBase()
        
        self.gemma_system_prompt = """
You are Gemma, the front-hand reasoning assistant of Julia.
You are NOT merely a router.
You should attempt to solve the problem first.

Behavior rules:
1. Think step-by-step internally.
2. Wrap reasoning inside:
<think>
...
</think>

3. Estimate your confidence from 0.0 to 1.0.

4. If the task is:
- highly architectural
- uncertain
- requires deep Unity expertise
- or confidence < 0.75

then output:
<escalate>true</escalate>

Otherwise:
<escalate>false</escalate>

5. Always provide a useful draft answer inside:
<draft>
...
</draft>

6. Final format:
<think>
reasoning
</think>

<confidence>
0.82
</confidence>

<escalate>false</escalate>

<draft>
your answer
</draft>
"""

        self.qwen_system_prompt = """You are advisor part of personal assistant Julia, the role of Senior Unity Architect. You step in when the front-line model is unsure.
        Before answering:
1. Think step-by-step.
2. Analyze possible bugs carefully.
3. Explain reasoning internally.

Wrap ALL internal reasoning inside:
<think>
...
</think>
Then provide the final answer normally.
You will be provided with context from the official Unity documentation. 
Use the context to provide a highly detailed, perfectly structured, and accurate answer."""
    
    def get_local_models(self):
        """Scans the local Ollama instance for downloaded models."""
        try:
            models = ollama.list()
            return [m['model'] for m in models['models']]
        except Exception as e:
            print(f"[Warning] Could not fetch Ollama models: {e}")
            return []
        
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
            stream = ollama.chat(
                model=self.front_model,
                messages=[
                    {'role': 'system', 'content': self.gemma_system_prompt},
                    user_message
                ],
                stream=True
            )
        
            full_response = ""       
            for chunk in stream:
                token = chunk['message']['content']
                full_response += token
        
                if stream_callback:
                    stream_callback(token, "Gemma (Front-Hand)")
        
            # Parse escalation
            lower = full_response.lower()
            should_escalate = bool(re.search(r'<escalate>\s*true\s*</escalate>', lower))
        
            # Extract draft robustly
            draft_answer = full_response
            draft_match = re.search(r'<draft>(.*?)</draft>', full_response, flags=re.DOTALL | re.IGNORECASE)
            
            if draft_match:
                draft_answer = draft_match.group(1).strip()
        
            # Escalate if needed  
            if should_escalate:
        
                if stream_callback:
                    stream_callback(
                        "\n[System: Task complex. Escaping to Advisor...]\n",
                        "System"
                    )
        
                return self._call_advisor(
                    user_query,
                    user_message,
                    stream_callback,
                    draft_answer=draft_answer,
                    front_reasoning=full_response
                )
        
            return draft_answer
        
        except Exception as e:
            if stream_callback:
                stream_callback(f"\n[System Error: {e}. Falling back to Advisor.]\n", "System")
            return self._call_advisor(user_query, user_message, stream_callback)
        
    # Accept the pre-built user_message (which includes the image)
    def _call_advisor(self, user_query, user_message, stream_callback, draft_answer="", front_reasoning=""):
        if stream_callback:
            stream_callback("[System: Advisor diving deep into Knowledge Base...]\n", "System")
            
        try:
            # We use an empty generate request with keep_alive=0 to wipe it from memory
            requests.post('http://localhost:11434/api/generate', json={
                "model": self.front_model,
                "keep_alive": 0 
            }, timeout=5)
            
            # Give Windows exactly 1.5 seconds to dump the VRAM/RAM before measuring it
            time.sleep(1.5)
            
        except Exception as e:
            print(f"[System Warning] Could not manually evict model: {e}")
            
        # Process RAG while memory finishes settling
        deep_context = self.rag_db.search(user_query, top_k=5)
        
        # MEASURE RAM
        available_ram = self.check_available_ram()
        
        # Determine the active model dynamically
        if not self.heavy_advisor or self.heavy_advisor == self.front_model:
            active_model = self.front_model
            if stream_callback:
                stream_callback("System Warning: Advisor missing. Front-Hand taking over with Deep RAG.\n", "System")
        elif available_ram >= self.ram_threshold_gb:
            active_model = self.heavy_advisor
        else:
            active_model = self.safe_advisor
            if stream_callback:
                stream_callback(f"[System Warning: Low RAM ({available_ram:.1f}GB). Using Safe Advisor.]\n", "System")

        advisor_message = user_message.copy()
        advisor_message['content'] = f"""
            UNITY DOCUMENTATION CONTEXT:
            {deep_context}
            
            FRONT MODEL REASONING:
            {front_reasoning}
            
            FRONT MODEL DRAFT:
            {draft_answer}
            
            USER QUESTION:
            {user_query}
            
            Your task:
            1. Analyze the front model reasoning.
            2. Correct mistakes if necessary.
            3. Expand the answer deeply.
            4. Preserve useful insights.
            """
        
        try:
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
            
        except Exception as e:
            # fallback: If the heavy model crashes (e.g., OOM), the Front-Hand tries to answer using the Deep context.
            if stream_callback:
                stream_callback(f"\nSystem Error: Advisor failed ({e}). Front-Hand attempting\n", "System")
            
            stream = ollama.chat(model=self.front_model, messages=[{'role': 'system', 'content': self.qwen_system_prompt}, advisor_message], stream=True)
            full_response = ""
            for chunk in stream:
                token = chunk['message']['content']
                full_response += token
                if stream_callback:
                    stream_callback(token, "Gemma (Front-Hand)")
            return full_response