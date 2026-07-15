import os
import time
from google import genai
from google.api_core.exceptions import GoogleAPICallError, ResourceExhausted, InternalServerError, ServiceUnavailable
from dotenv import load_dotenv
from groq import Groq

# Load environment variables
load_dotenv()

class GroqChunkWrapper:
    """Wraps Groq delta content in an object with a .text property to match Gemini's stream chunk API."""
    def __init__(self, text):
        self.text = text

def is_rate_limit_error(e):
    if isinstance(e, ResourceExhausted):
        return True
    err_str = str(e).lower()
    if "429" in err_str or "resource_exhausted" in err_str or "quota" in err_str or "rate limit" in err_str:
        return True
    return False

def is_server_error(e):
    if isinstance(e, (InternalServerError, ServiceUnavailable)):
        return True
    err_str = str(e).lower()
    if "500" in err_str or "503" in err_str or "internal server error" in err_str or "service unavailable" in err_str:
        return True
    return False

def is_forbidden_error(e):
    err_str = str(e).lower()
    if "403" in err_str or "permission denied" in err_str or "permission_denied" in err_str:
        return True
    return False

class GeminiKeyRotator:
    def __init__(self):
        self.keys = []
        main_gemini = os.getenv("GEMINI_API_KEY")
        if main_gemini:
            self.keys.append(main_gemini.strip())
            
        i = 1
        while True:
            key = os.getenv(f"GEMINI_API_KEY_{i}")
            if key:
                key_stripped = key.strip()
                if key_stripped not in self.keys:
                    self.keys.append(key_stripped)
                i += 1
            else:
                break
                
        # Initialize Groq client
        self.groq_keys = []
        main_groq = os.getenv("GROQ_API_KEY")
        if main_groq:
            self.groq_keys.append(main_groq.strip())
            
        i = 1
        while True:
            key = os.getenv(f"GROQ_API_KEY_{i}")
            if key:
                key_stripped = key.strip()
                if key_stripped not in self.groq_keys:
                    self.groq_keys.append(key_stripped)
                i += 1
            else:
                break
                
        if not self.keys and not self.groq_keys:
            raise ValueError("No Gemini or Groq API keys found in environment variables (.env).")
            
        self.current_idx = 0
        self.key_models = {}
        self.current_groq_idx = 0
        
    def _get_groq_client(self):
        if not self.groq_keys:
            return None
        key = self.groq_keys[self.current_groq_idx]
        return Groq(api_key=key)
        
    def _get_client(self):
        key = self.keys[self.current_idx]
        return genai.Client(api_key=key)
        
    def get_model(self):
        if self.current_idx in self.key_models:
            return self.key_models[self.current_idx]
            
        try:
            client = self._get_client()
            models = [m.name for m in client.models.list()]
            priorities = [
                "gemini-2.5-flash",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-3.5-flash"
            ]
            for p in priorities:
                for m in models:
                    if p in m:
                        self.key_models[self.current_idx] = p
                        return p
            self.key_models[self.current_idx] = "gemini-2.5-flash"
            return self.key_models[self.current_idx]
        except Exception:
            return "gemini-2.5-flash"
            
    def _generate_groq(self, prompt):
        attempts = 0
        while True:
            client = self._get_groq_client()
            if not client:
                raise ValueError("Groq client not initialized (check GROQ_API_KEY in .env).")
            print(f"All Gemini keys failed or returned 403. Falling back to Groq index {self.current_groq_idx} (llama-3.3-70b-versatile)...")
            try:
                chat_completion = client.chat.completions.create(
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    model="llama-3.3-70b-versatile",
                )
                return chat_completion.choices[0].message.content
            except Exception as e:
                err_str = str(e).lower()
                is_rate = "429" in err_str or "rate limit" in err_str or "quota" in err_str
                is_forbidden = "403" in err_str or "permission" in err_str
                
                if is_rate or is_forbidden:
                    attempts += 1
                    if attempts >= len(self.groq_keys):
                        raise e
                    else:
                        old_idx = self.current_groq_idx
                        self.current_groq_idx = (self.current_groq_idx + 1) % len(self.groq_keys)
                        print(f"Groq API key index {old_idx} failed or rate limited. Rotating to index {self.current_groq_idx}...")
                        continue
                else:
                    raise e
        
    def _generate_stream_groq(self, prompt):
        attempts = 0
        while True:
            client = self._get_groq_client()
            if not client:
                raise ValueError("Groq client not initialized (check GROQ_API_KEY in .env).")
            print(f"All Gemini keys failed or returned 403. Falling back to Groq stream index {self.current_groq_idx} (llama-3.3-70b-versatile)...")
            try:
                completion = client.chat.completions.create(
                    model="llama-3.3-70b-versatile",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt,
                        }
                    ],
                    stream=True,
                )
                for chunk in completion:
                    content = chunk.choices[0].delta.content
                    if content:
                        yield GroqChunkWrapper(content)
                return
            except Exception as e:
                err_str = str(e).lower()
                is_rate = "429" in err_str or "rate limit" in err_str or "quota" in err_str
                is_forbidden = "403" in err_str or "permission" in err_str
                
                if is_rate or is_forbidden:
                    attempts += 1
                    if attempts >= len(self.groq_keys):
                        raise e
                    else:
                        old_idx = self.current_groq_idx
                        self.current_groq_idx = (self.current_groq_idx + 1) % len(self.groq_keys)
                        print(f"Groq API stream key index {old_idx} failed or rate limited. Rotating to index {self.current_groq_idx}...")
                        continue
                else:
                    raise e
                    
    def generate(self, prompt):
        if not self.keys:
            if self.groq_keys:
                return self._generate_groq(prompt)
            raise ValueError("No API keys configured.")
            
        attempts = 0
        server_retry_delay = 1
        
        while True:
            try:
                client = self._get_client()
                model_name = self.get_model()
                response = client.models.generate_content(
                    model=model_name,
                    contents=prompt
                )
                return response.text
            except Exception as e:
                is_rate = is_rate_limit_error(e)
                is_forbidden = is_forbidden_error(e)
                
                if is_rate or is_forbidden:
                    attempts += 1
                    if attempts >= len(self.keys):
                        # All keys failed or returned 403. Try Groq fallback.
                        if self.groq_keys:
                            try:
                                return self._generate_groq(prompt)
                            except Exception as groq_err:
                                print(f"Groq fallback also failed: {groq_err}")
                        
                        print("All Gemini API keys exhausted and Groq fallback unavailable/failed. Waiting 60 seconds...")
                        time.sleep(60)
                        self.current_idx = 0
                        attempts = 0
                    else:
                        self.current_idx = (self.current_idx + 1) % len(self.keys)
                        reason = "Rate limit / quota hit" if is_rate else "Forbidden (403) error hit"
                        print(f"{reason}. Rotating to Gemini API key index {self.current_idx}...")
                    continue
                elif is_server_error(e):
                    if server_retry_delay > 8:
                        if self.groq_keys:
                            try:
                                return self._generate_groq(prompt)
                            except Exception as groq_err:
                                print(f"Groq fallback also failed: {groq_err}")
                        raise e
                    print(f"Gemini Server error hit. Retrying in {server_retry_delay}s (Exponential Backoff)...")
                    time.sleep(server_retry_delay)
                    server_retry_delay *= 2
                    continue
                else:
                    # Other hard error (e.g. 400 bad request, 404 model not found)
                    if self.groq_keys:
                        try:
                            return self._generate_groq(prompt)
                        except Exception as groq_err:
                            print(f"Groq fallback also failed: {groq_err}")
                    raise e
                    
    def generate_stream(self, prompt):
        if not self.keys:
            if self.groq_keys:
                yield from self._generate_stream_groq(prompt)
                return
            raise ValueError("No API keys configured.")
            
        attempts = 0
        server_retry_delay = 1
        
        while True:
            try:
                client = self._get_client()
                model_name = self.get_model()
                response_stream = client.models.generate_content_stream(
                    model=model_name,
                    contents=prompt
                )
                
                for chunk in response_stream:
                    if chunk.text:
                        yield chunk
                return
            except Exception as e:
                is_rate = is_rate_limit_error(e)
                is_forbidden = is_forbidden_error(e)
                
                if is_rate or is_forbidden:
                    attempts += 1
                    if attempts >= len(self.keys):
                        # All keys failed or returned 403. Try Groq fallback.
                        if self.groq_keys:
                            try:
                                yield from self._generate_stream_groq(prompt)
                                return
                            except Exception as groq_err:
                                print(f"Groq stream fallback also failed: {groq_err}")
                                
                        print("All Gemini API keys exhausted (Stream) and Groq fallback unavailable/failed. Waiting 60 seconds...")
                        time.sleep(60)
                        self.current_idx = 0
                        attempts = 0
                    else:
                        self.current_idx = (self.current_idx + 1) % len(self.keys)
                        reason = "Rate limit / quota hit (Stream)" if is_rate else "Forbidden (403) error hit (Stream)"
                        print(f"{reason}. Rotating to Gemini API key index {self.current_idx}...")
                    continue
                elif is_server_error(e):
                    if server_retry_delay > 8:
                        if self.groq_keys:
                            try:
                                yield from self._generate_stream_groq(prompt)
                                return
                            except Exception as groq_err:
                                print(f"Groq stream fallback also failed: {groq_err}")
                        raise e
                    print(f"Gemini Server error hit (Stream). Retrying in {server_retry_delay}s (Exponential Backoff)...")
                    time.sleep(server_retry_delay)
                    server_retry_delay *= 2
                    continue
                else:
                    if self.groq_keys:
                        try:
                            yield from self._generate_stream_groq(prompt)
                            return
                        except Exception as groq_err:
                            print(f"Groq stream fallback also failed: {groq_err}")
                    raise e

# Single shared instance
gemini = GeminiKeyRotator()
