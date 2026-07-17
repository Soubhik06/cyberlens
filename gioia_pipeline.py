import os
import re
import sys
import json
import time
import datetime
import random
import argparse
import requests
import pandas as pd
import threading
import asyncio
import aiohttp
import hashlib
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

# CONCURRENCY SWITCH: Set to 1 for Free Tier (sequential batching), >1 for Paid Tier (parallel API calls)
CONCURRENCY_LIMIT = 1

class DynamicSemaphore:
    def __init__(self, initial_limit):
        self.limit = max(1, initial_limit)
        self.current_concurrency = 0
        self.lock = asyncio.Lock()
        self.success_streak = 0
        self.max_limit = max(1, initial_limit)

    async def acquire(self):
        while True:
            async with self.lock:
                if self.current_concurrency < self.limit:
                    self.current_concurrency += 1
                    return
            await asyncio.sleep(0.05)

    async def release(self):
        async with self.lock:
            self.current_concurrency = max(0, self.current_concurrency - 1)

    async def report_success(self):
        async with self.lock:
            self.success_streak += 1
            if self.success_streak >= 10:
                if self.limit < self.max_limit:
                    self.limit += 1
                    print(f"[DYNAMIC CONCURRENCY] Success streak of 10. Increasing limit to {self.limit}")
                self.success_streak = 0

    async def report_rate_limit(self):
        async with self.lock:
            self.success_streak = 0
            old_limit = self.limit
            self.limit = max(1, self.limit // 2)
            if self.limit != old_limit:
                print(f"[DYNAMIC CONCURRENCY] Rate limit hit. Decreasing limit from {old_limit} to {self.limit}")

    async def __aenter__(self):
        await self.acquire()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release()


# CONSTANTS AT TOP OF FILE
EXCEL_PATH = "data/all_data.xlsx"
TXT_FOLDER = "data/txt"
OUTPUT_FOLDER = "gioia_output"
MAX_RECORDS = 400          # hard cap, never exceed
MAX_VICTIM = 280           # within the 400 cap
MAX_NEAR_MISS = 120        # within the 400 cap
MAX_WORDS_PER_RECORD = 400 # truncate long texts

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
MODEL_FAST = "llama-3.1-8b-instant"     # agents 2,3
MODEL_SMART = "llama-3.3-70b-versatile" # agents 4,5,6

# CATEGORY DETECTOR & NORMALIZERS

CATEGORY_MAP = {
    'upi': 'UPI and Digital Payment Fraud',
    'phonpe': 'UPI and Digital Payment Fraud',
    'google pay': 'UPI and Digital Payment Fraud',
    'paytm': 'UPI and Digital Payment Fraud',
    'qr code': 'UPI and Digital Payment Fraud',
    'collect request': 'UPI and Digital Payment Fraud',
    'phishing': 'Phishing, Vishing, and Smishing',
    'vishing': 'Phishing, Vishing, and Smishing',
    'smishing': 'Phishing, Vishing, and Smishing',
    'digital arrest': 'Digital Arrest Scam',
    'impersonation': 'Digital Arrest Scam',
    'video call': 'Digital Arrest Scam',
    'otp': 'OTP and Authentication Fraud',
    'sim swap': 'OTP and Authentication Fraud',
    'kyc': 'OTP and Authentication Fraud',
    'loan app': 'Online Lending and Loan App Fraud',
    'lending': 'Online Lending and Loan App Fraud',
    'investment': 'Investment and Trading Fraud',
    'stock': 'Investment and Trading Fraud',
    'trading': 'Investment and Trading Fraud',
    'task': 'Investment and Trading Fraud',
    'romance': 'Social Engineering and Romance/Sextortion',
    'sextortion': 'Social Engineering and Romance/Sextortion',
    'dating': 'Social Engineering and Romance/Sextortion',
    'identity': 'Identity Theft and Data Breach',
    'data breach': 'Identity Theft and Data Breach',
    'aadhaar': 'Emerging and Miscellaneous Fraud Types',
    'deepfake': 'Emerging and Miscellaneous Fraud Types',
    'ransomware': 'Ransomware and Malware',
    'malware': 'Ransomware and Malware',
    'e-commerce': 'E-Commerce and Delivery Fraud',
    'delivery': 'E-Commerce and Delivery Fraud',
    'shopping': 'E-Commerce and Delivery Fraud',
    'cyber stalking': 'Emerging and Miscellaneous Fraud Types',
    'cybercrime': 'General Cybercrime / Cyber Fraud Terms',
    'cyber fraud': 'General Cybercrime / Cyber Fraud Terms'
}

def detect_fraud_category(research_question):
    q = research_question.lower()
    for keyword, category in CATEGORY_MAP.items():
        if keyword in q:
            return category
    return 'General Cybercrime / Cyber Fraud Terms'

def normalize_narrative_type(value):
    v = str(value).strip().upper()
    if 'VICTIM' in v:
        return 'VICTIM'
    if 'NEAR' in v or 'MISS' in v:
        return 'NEAR-MISS'
    if 'THIRD' in v or 'PARTY' in v:
        return 'THIRD-PARTY'
    return 'UNKNOWN'

def parse_date_safe(val):
    try:
        d = pd.to_datetime(str(val), errors='coerce', dayfirst=True)
        if pd.notna(d) and 2014 <= d.year <= 2025:
            return d
        return None
    except:
        return None

def generate_run_id(research_question):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = re.sub(r'[^a-z0-9\s-]', '', research_question.lower())
    slug = re.sub(r'[\s-]+', '_', slug).strip('_')
    slug = slug[:50]
    return f"{timestamp}_{slug}"

# GROQ API AND JSON EXTRACTORS

# API Key list initialization for dynamic rotation
def load_groq_api_keys():
    keys = [GROQ_API_KEY]
    try:
        env_path = ".env"
        if os.path.exists(env_path):
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip('"').strip("'")
                        if k in ("GROQ_API_KEY_1", "GROQ_API_KEY_2", "GROQ_API_KEY") and v:
                            if v not in keys:
                                keys.append(v)
    except Exception as e:
        print(f"Warning: Could not parse .env file: {e}")
    return keys

API_KEYS = load_groq_api_keys()
CURRENT_KEY_INDEX = 0

def get_current_api_key():
    global CURRENT_KEY_INDEX
    return API_KEYS[CURRENT_KEY_INDEX % len(API_KEYS)]

def rotate_api_key():
    global CURRENT_KEY_INDEX
    if len(API_KEYS) > 1:
        CURRENT_KEY_INDEX += 1
        new_key = get_current_api_key()
        masked = new_key[:8] + "..." + new_key[-8:] if len(new_key) > 16 else "..."
        print(f"[API KEY ROTATION] Switching to API key: {masked}")
    else:
        print("[API KEY ROTATION] Only one API key available. Cannot rotate.")

key_lock = asyncio.Lock()

async def call_groq(session, system_prompt, user_message, model, max_tokens=2000, progress_callback=None, dynamic_sem=None):
    url = "https://api.groq.com/openai/v1/chat/completions"
    
    attempt = 0
    max_attempts = 6
    backoff = 4.0
    
    while attempt < max_attempts:
        current_key = get_current_api_key()
        headers = {
            "Authorization": f"Bearer {current_key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            "temperature": 0.3,
            "max_tokens": max_tokens
        }
        try:
            async with session.post(url, headers=headers, json=payload, timeout=60) as r:
                if r.status == 429:
                    if dynamic_sem:
                        await dynamic_sem.report_rate_limit()
                    delay = backoff + random.uniform(0.1, 1.0)
                    print(f"[RATE LIMIT 429] Attempt {attempt+1}/{max_attempts} failed with 429. Rotating key and waiting {delay:.2f} seconds...")
                    async with key_lock:
                        if get_current_api_key() == current_key:
                            rotate_api_key()
                    if progress_callback:
                        try:
                            if asyncio.iscoroutinefunction(progress_callback):
                                await progress_callback(is_waiting=True, est_time_remaining_add=delay)
                            else:
                                progress_callback(is_waiting=True, est_time_remaining_add=delay)
                        except Exception as cb_err:
                            print(f"Error in progress callback: {cb_err}")
                    await asyncio.sleep(delay)
                    if progress_callback:
                        try:
                            if asyncio.iscoroutinefunction(progress_callback):
                                await progress_callback(is_waiting=False)
                            else:
                                progress_callback(is_waiting=False)
                        except Exception as cb_err:
                            print(f"Error in progress callback: {cb_err}")
                    backoff = min(90.0, backoff * 2.0)
                    attempt += 1
                    continue
                    
                if r.status != 200:
                    text = await r.text()
                    print(f"[API ERROR DETAILS] Status: {r.status}, Response: {text}")
                r.raise_for_status()
                if dynamic_sem:
                    await dynamic_sem.report_success()
                res_json = await r.json()
                return res_json["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[API ERROR] Attempt {attempt+1}/{max_attempts} failed: {e}")
            delay = 2.0
            await asyncio.sleep(delay)
            attempt += 1
            
    return None


def clean_llm_json_string(text):
    # Remove markdown code fences if present
    text = re.sub(r'^```json\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'^```\s*', '', text)
    text = re.sub(r'\s*```$', '', text)
    text = text.strip()
    
    # Escape raw control characters inside double quotes (like literal newlines and tabs)
    result = []
    in_string = False
    escape = False
    for char in text:
        if char == '"' and not escape:
            in_string = not in_string
            result.append(char)
        elif in_string:
            if char == '\\' and not escape:
                escape = True
                result.append(char)
            else:
                if escape:
                    escape = False
                    result.append(char)
                else:
                    if char == '\n':
                        result.append('\\n')
                    elif char == '\r':
                        result.append('\\r')
                    elif char == '\t':
                        result.append('\\t')
                    else:
                        result.append(char)
        else:
            result.append(char)
            
    return "".join(result)

def strip_trailing_commas(json_str):
    json_str = re.sub(r',\s*\]', ']', json_str)
    json_str = re.sub(r',\s*\}', '}', json_str)
    return json_str

def extract_json(text):
    if not text:
        return None
        
    cleaned = clean_llm_json_string(text)
    cleaned = strip_trailing_commas(cleaned)
    
    # Method 1: direct parse of cleaned string
    try:
        return json.loads(cleaned)
    except:
        pass
        
    # Method 2: find outermost { } in cleaned string
    try:
        s = cleaned.find('{')
        e = cleaned.rfind('}') + 1
        if s != -1 and e > s:
            return json.loads(cleaned[s:e])
    except:
        pass
        
    # Method 3: find outermost [ ] in cleaned string
    try:
        s = cleaned.find('[')
        e = cleaned.rfind(']') + 1
        if s != -1 and e > s:
            return json.loads(cleaned[s:e])
    except:
        pass
        
    # Method 4: fallback to original text find { }
    try:
        s = text.find('{')
        e = text.rfind('}') + 1
        if s != -1 and e > s:
            return json.loads(text[s:e])
    except:
        pass
        
    return None

# STAGE 1: INTAKE AGENT (PURE PYTHON)

def run_intake_agent(research_question, max_records=400, filter_category=True):
    print("[AGENT 1] Initializing Intake Agent...")
    detected_category = detect_fraud_category(research_question)
    
    excel_path = EXCEL_PATH
    if not os.path.exists(excel_path) and os.path.exists("data/txt/all_data.xlsx"):
        excel_path = "data/txt/all_data.xlsx"
    if not os.path.exists(excel_path) and os.path.exists("data/all_data.xlsx"):
        excel_path = "data/all_data.xlsx"
        
    txt_folder = TXT_FOLDER
    if not os.path.exists(txt_folder) and os.path.exists("data/txt"):
        txt_folder = "data/txt"
        
    if not os.path.exists(excel_path):
        raise FileNotFoundError(f"Excel file not found at {excel_path}")
        
    xl = pd.ExcelFile(excel_path)
    
    # --- Category Filter Helper ---
    def row_matches_category(row_obj, detected_cat):
        cat_val = str(row_obj.get("Fraud Category", "")).strip().lower()
        subcat_val = str(row_obj.get("Fraud Subcategory", "")).strip().lower()
        detected_cat_lower = detected_cat.lower().strip()
        
        if cat_val == detected_cat_lower:
            return True
            
        words = [w for w in re.findall(r'[a-z0-9]+', detected_cat_lower) if w]
        stopwords = {'and', 'or', 'the', 'of', 'in', 'fraud', 'frauds', 'scam', 'scams', 'types', 'general', 'terms', 'payment', 'digital', 'cyber', 'cybercrime'}
        meaningful_words = [w for w in words if w not in stopwords]
        search_words = meaningful_words if meaningful_words else words
        
        for w in search_words:
            if w in subcat_val:
                return True
        return False

    records = []
    after_cat = 0
    after_type = 0
    victim_count = 0
    near_miss_count = 0
    third_party_count = 0
    after_date = 0

    # --- Load Stream A ---
    sheet_a = "stream_a_scraped"
    if sheet_a not in xl.sheet_names:
        raise ValueError(f"Sheet '{sheet_a}' not found in Excel file.")
    df_a = pd.read_excel(xl, sheet_name=sheet_a)
    len_a = len(df_a)

    for idx, row in df_a.iterrows():
        if filter_category and not row_matches_category(row, detected_category):
            continue
        after_cat += 1
        
        raw_type = row.get("Narrative Type", "")
        normalized_type = normalize_narrative_type(raw_type)
        if normalized_type not in ("VICTIM", "NEAR-MISS", "THIRD-PARTY"):
            continue
        after_type += 1
        if normalized_type == "VICTIM":
            victim_count += 1
        elif normalized_type == "NEAR-MISS":
            near_miss_count += 1
        else:
            third_party_count += 1
            
        raw_date = row.get("Original Date")
        parsed_dt = parse_date_safe(raw_date)
        if parsed_dt is None:
            continue
        after_date += 1
        
        uid = str(row.get("Unique ID", "")).strip()
        if not uid:
            continue
            
        txt_file = str(row.get("TXT File Name", "")).strip()
        text_content = ""
        
        if txt_file:
            possible_paths = [
                os.path.join(txt_folder, txt_file),
                os.path.join("data", "txt", txt_file),
                os.path.join("data", txt_file)
            ]
            for path in possible_paths:
                if os.path.exists(path):
                    try:
                        with open(path, "r", encoding="utf-8", errors="ignore") as f:
                            text_content = f.read().strip()
                        if text_content:
                            break
                    except:
                        pass
        
        if not text_content:
            text_content = str(row.get("Notes", "")).strip()
            
        if not text_content:
            continue
            
        words = text_content.split()
        truncated_text = " ".join(words[:MAX_WORDS_PER_RECORD])
        
        records.append({
            "id": uid,
            "source": "web_scraping",
            "date": parsed_dt.strftime("%Y-%m-%d"),
            "year": parsed_dt.year,
            "title": str(row.get("Title/Headline", "")).strip(),
            "narrative_type": normalized_type,
            "fraud_category": detected_category,
            "text": truncated_text
        })

    # --- Load ProQuest ---
    sheet_b = "Proquest"
    len_p = 0
    if sheet_b in xl.sheet_names:
        df_b = pd.read_excel(xl, sheet_name=sheet_b)
        len_p = len(df_b)
        for idx, row in df_b.iterrows():
            if filter_category and not row_matches_category(row, detected_category):
                continue
            after_cat += 1
            
            raw_type = row.get("Narrative Type", "")
            normalized_type = normalize_narrative_type(raw_type)
            if normalized_type not in ("VICTIM", "NEAR-MISS", "THIRD-PARTY"):
                continue
            after_type += 1
            if normalized_type == "VICTIM":
                victim_count += 1
            elif normalized_type == "NEAR-MISS":
                near_miss_count += 1
            else:
                third_party_count += 1
                
            raw_date = row.get("Original Date")
            parsed_dt = parse_date_safe(raw_date)
            if parsed_dt is None:
                continue
            after_date += 1
            
            uid = str(row.get("Unique-ID", "")).strip()
            if not uid:
                continue
                
            text_content = str(row.get("Notes", "")).strip()
            if not text_content:
                continue
                
            words = text_content.split()
            truncated_text = " ".join(words[:MAX_WORDS_PER_RECORD])
            
            records.append({
                "id": uid,
                "source": "proquest",
                "date": parsed_dt.strftime("%Y-%m-%d"),
                "year": parsed_dt.year,
                "title": str(row.get("Title/Headline", "")).strip(),
                "narrative_type": normalized_type,
                "fraud_category": detected_category,
                "text": truncated_text
            })

    # --- Smart Sampling ---
    # Combine all valid narrative types: VICTIM, NEAR-MISS, and THIRD-PARTY
    matching_records = [r for r in records if r['narrative_type'] in ('VICTIM', 'NEAR-MISS', 'THIRD-PARTY')]
    matching_records.sort(key=lambda x: x['id'])  # sort first for deterministic stability
    
    # Deterministic sample using a local random generator seeded with the research question
    seed_hash = hashlib.sha256(research_question.encode('utf-8')).hexdigest()
    seed_int = int(seed_hash[:8], 16)
    local_rng = random.Random(seed_int)
    
    if len(matching_records) > max_records:
        final_records = local_rng.sample(matching_records, max_records)
    else:
        final_records = matching_records
        
    final_records.sort(key=lambda x: x['id'])  # sort back for neat, reproducible order
    
    # Export the selected chunks to selected_500_chunks.csv for verification
    csv_filename = "selected_500_chunks.csv"
    try:
        df_final = pd.DataFrame(final_records)
        cols_to_save = [c for c in ["id", "source", "date", "title", "narrative_type", "text"] if c in df_final.columns]
        df_final[cols_to_save].to_csv(csv_filename, index=False, encoding="utf-8")
        print(f"[AGENT 1] Successfully exported {len(final_records)} selected chunks to {csv_filename}")
    except Exception as csv_err:
        print(f"[AGENT 1 WARNING] Could not write {csv_filename} (file might be locked/open in Excel): {csv_err}")
        # Try fallback name
        fallback_filename = "selected_500_chunks_fallback.csv"
        try:
            df_final[cols_to_save].to_csv(fallback_filename, index=False, encoding="utf-8")
            print(f"[AGENT 1] Successfully saved fallback copy to {fallback_filename}")
        except Exception as fb_err:
            print(f"[AGENT 1 ERROR] Fallback save failed: {fb_err}")
        
    web_count = sum(1 for r in final_records if r["source"] == "web_scraping")
    pq_count = sum(1 for r in final_records if r["source"] == "proquest")
    
    final_victim = sum(1 for r in final_records if r["narrative_type"] == "VICTIM")
    final_near_miss = sum(1 for r in final_records if r["narrative_type"] == "NEAR-MISS")
    final_third_party = sum(1 for r in final_records if r["narrative_type"] == "THIRD-PARTY")
    
    # Summary Output
    print(f"\n========== AGENT 1 SUMMARY ==========")
    print(f"Research Question: {research_question}")
    print(f"Detected Category: {detected_category}")
    print(f"-------------------------------------")
    print(f"Stream A raw rows:      {len_a}")
    print(f"ProQuest raw rows:      {len_p}")
    print(f"After category filter:  {after_cat}")
    print(f"After type filter:      {after_type}")
    print(f"  - VICTIM:             {victim_count}")
    print(f"  - NEAR-MISS:          {near_miss_count}")
    print(f"  - THIRD-PARTY:        {third_party_count}")
    print(f"After date validation:  {after_date}")
    print(f"-------------------------------------")
    print(f"Final sample:           {len(final_records)}")
    print(f"  - VICTIM:             {final_victim}")
    print(f"  - NEAR-MISS:          {final_near_miss}")
    print(f"  - THIRD-PARTY:        {final_third_party}")
    print(f"  - From web scraping:  {web_count}")
    print(f"  - From ProQuest:      {pq_count}")
    print(f"======================================\n")
    
    return final_records

# STAGE 2: EXTRACTION AGENT

async def run_extraction_agent(chunks, research_question, detected_category, output_dir=None, progress_callback=None, concurrency_limit=1):
    print(f"[AGENT 2] Starting Extraction Agent. Screening {len(chunks)} chunks for relevance...")
    
    batch_size = 5
    relevant_records = []
    processed_decisions = []
    processed_ids = set()
    
    # Checkpoint resumption
    inter_path = None
    if output_dir:
        inter_path = os.path.join(output_dir, "stage2_intermediate.json")
        if os.path.exists(inter_path):
            try:
                with open(inter_path, "r", encoding="utf-8") as f:
                    saved_decisions = json.load(f)
                    if isinstance(saved_decisions, list):
                        processed_decisions = saved_decisions
                        processed_ids = {r.get("id") for r in saved_decisions if isinstance(r, dict) and r.get("id")}
                        print(f"[AGENT 2 RESUME] Loaded {len(processed_decisions)} intermediate decisions. Already processed: {len(processed_ids)} chunks.")
            except Exception as e:
                print(f"[AGENT 2 RESUME WARNING] Could not load stage2_intermediate.json: {e}")
                
    unprocessed_chunks = [c for c in chunks if c.get("id") not in processed_ids]
    total_unprocessed = len(unprocessed_chunks)
    
    if total_unprocessed == 0:
        print("[AGENT 2] All records already processed (resumed).")
        # Extract only the relevant records from processed_decisions
        for r in processed_decisions:
            if r.get("relevant", False):
                r_copy = r.copy()
                r_copy.pop("relevant", None)
                relevant_records.append(r_copy)
        return relevant_records

    total_records = len(chunks)
    total_batches = (total_unprocessed + batch_size - 1) // batch_size
    
    dynamic_sem = DynamicSemaphore(concurrency_limit)
    
    system_prompt_batched = f"""You are a research assistant screening text excerpts for a qualitative Gioia methodology study on {detected_category} in India (2014-2025).

Research Question: {research_question}

A record is RELEVANT if it contains ANY of:
- A specific {detected_category} incident or personal victim/near-miss experience
- Description of fraud method or modus operandi related to {detected_category}
- Victim emotions, psychological impact, or behavioral responses
- Financial or personal consequences to victim
- Institutional response (police, bank, court, RBI, NPCI) to {detected_category}
- Near-miss: person recognized and avoided fraud

A record is NOT RELEVANT if it is:
- General news with no personal experience angle
- About a completely different fraud type
- Non-Indian context with no India relevance
- Pure statistics with no narrative element
- Duplicate of another record's content

You will receive a JSON list of records to evaluate.
For each record, evaluate its relevance.
Respond with ONLY a JSON array of objects, each containing:
- "id": (must match the input record id exactly)
- "relevant": (boolean true/false)
- "reason": (concise explanation, one sentence max)

Format example:
[
  {{"id": "id1", "relevant": true, "reason": "describes personal UPI fraud experience"}},
  {{"id": "id2", "relevant": false, "reason": "generic statistics without personal narrative"}}
]"""

    processed_chunks_count = len(processed_ids)
    processed_batches_count = 0
    progress_lock = asyncio.Lock()

    async def save_stage_data_sync(filepath, data):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    async def save_stage_data_async(filepath, data):
        await asyncio.to_thread(save_stage_data_sync, filepath, data)

    async def process_sub_batch(session, sub_chunks, attempt_depth=0):
        if output_dir and os.path.exists(os.path.join(output_dir, "cancelled")):
            raise ValueError("Pipeline stopped by user")
        if not sub_chunks:
            return []
        
        batch_input = [{"id": r["id"], "text": r["text"]} for r in sub_chunks]
        user_message = json.dumps(batch_input, indent=2)
        
        async with dynamic_sem:
            res_text = await call_groq(
                session, system_prompt_batched, user_message, MODEL_FAST,
                progress_callback=progress_callback, dynamic_sem=dynamic_sem
            )
            
        res_json = extract_json(res_text)
        
        # Split fallback logic
        if res_json is None and len(sub_chunks) > 1 and attempt_depth < 3:
            print(f"[BATCH FALLBACK] Batch of size {len(sub_chunks)} failed/too large. Splitting in half...")
            mid = len(sub_chunks) // 2
            left_task = process_sub_batch(session, sub_chunks[:mid], attempt_depth + 1)
            right_task = process_sub_batch(session, sub_chunks[mid:], attempt_depth + 1)
            left, right = await asyncio.gather(left_task, right_task)
            return left + right
            
        results_list = []
        res_map = {}
        if isinstance(res_json, list):
            for item in res_json:
                if isinstance(item, dict) and "id" in item:
                    res_map[item["id"]] = item
                    
        for r in sub_chunks:
            r_id = r["id"]
            decision = res_map.get(r_id, {})
            is_relevant = decision.get("relevant", False)
            reason = decision.get("reason", "No reason provided by model or parsing failed")
            
            r_copy = r.copy()
            r_copy["relevant"] = is_relevant
            r_copy["relevance_reason"] = reason
            results_list.append(r_copy)
            
        return results_list

    async def process_batch_with_progress(session, batch):
        nonlocal processed_chunks_count, processed_batches_count
        batch_results = await process_sub_batch(session, batch)
        
        async with progress_lock:
            processed_decisions.extend(batch_results)
            processed_chunks_count += len(batch)
            processed_batches_count += 1
            
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(processed=processed_chunks_count, batch_idx=processed_batches_count)
                    else:
                        progress_callback(processed=processed_chunks_count, batch_idx=processed_batches_count)
                except Exception as cb_err:
                    print(f"Error in progress callback: {cb_err}")
                    
            if inter_path:
                await save_stage_data_async(inter_path, processed_decisions)
                
            if processed_batches_count % 5 == 0 or processed_chunks_count == total_records:
                relevant_so_far = sum(1 for d in processed_decisions if d.get("relevant", False))
                print(f"[AGENT 2 PROGRESS] Processed {processed_chunks_count}/{total_records} chunks. Relevant so far: {relevant_so_far}")

    # Process all unprocessed chunks in parallel batches using a single ClientSession
    async with aiohttp.ClientSession() as session:
        tasks = []
        for b_idx in range(total_batches):
            start_idx = b_idx * batch_size
            end_idx = min(start_idx + batch_size, total_unprocessed)
            batch = unprocessed_chunks[start_idx:end_idx]
            tasks.append(process_batch_with_progress(session, batch))
        
        await asyncio.gather(*tasks)

    # Filter out relevant records to return
    for r in processed_decisions:
        if r.get("relevant", False):
            r_copy = r.copy()
            r_copy.pop("relevant", None)
            relevant_records.append(r_copy)
            
    print(f"[AGENT 2] Extraction complete. Kept {len(relevant_records)}/{len(chunks)} records.")
    return relevant_records


# STAGE 3: FIRST ORDER CODING AGENT

async def run_first_order_coding_agent(relevant_records, research_question, detected_category, output_dir, progress_callback=None, concurrency_limit=1):
    # Fix 1: flatten if nested list of lists
    if relevant_records and isinstance(relevant_records[0], list):
        relevant_records = [item for sublist in relevant_records for item in sublist]
    
    # Fix 2: unwrap if double-wrapped in dict
    if isinstance(relevant_records, dict):
        relevant_records = [relevant_records]
    
    # Fix 3: keep only valid dicts
    relevant_records = [r for r in relevant_records if isinstance(r, dict) and 'text' in r]
    
    if not relevant_records:
        print("[AGENT 3] No valid records to process")
        return []
    
    print(f"[AGENT 3] Processing {len(relevant_records)} valid records...")
    
    batch_size = 5
    first_order_codes = []
    processed_ids = set()
    
    inter_path = os.path.join(output_dir, "stage3_intermediate.json")
    if os.path.exists(inter_path):
        try:
            with open(inter_path, "r", encoding="utf-8") as f:
                saved_codes = json.load(f)
                if isinstance(saved_codes, list):
                    first_order_codes = saved_codes
                    processed_ids = {c.get("chunk_id") for c in saved_codes if isinstance(c, dict) and c.get("chunk_id")}
                    print(f"[AGENT 3 RESUME] Loaded {len(first_order_codes)} intermediate codes from {len(processed_ids)} processed records.")
        except Exception as e:
            print(f"[AGENT 3 RESUME WARNING] Could not load stage3_intermediate.json: {e}")

    unprocessed_records = [r for r in relevant_records if r.get("id") not in processed_ids]
    total_unprocessed = len(unprocessed_records)
    
    if total_unprocessed == 0:
        print("[AGENT 3] All records already processed (resumed).")
        return first_order_codes
        
    total_records = len(relevant_records)
    total_batches = (total_unprocessed + batch_size - 1) // batch_size
    
    dynamic_sem = DynamicSemaphore(concurrency_limit)
    
    system_prompt_batched = f"""You are conducting qualitative coding for a Gioia methodology study on {detected_category} in India.

Research Question: {research_question}

You will receive a JSON list of records to code.
For each record, generate 1-3 FIRST-ORDER CODES and extract the single most powerful informant quote.

First-order codes must:
- Use language close to the actual text
- Be specific to {detected_category} when possible
- Capture WHO did WHAT (victim, fraudster, institution)
- Be 3-7 words each
- Reflect the informant's perspective

Good code examples:
- "victim deceived by urgency pressure"
- "fraudster posed as authority figure"
- "victim lost savings before realizing fraud"
- "bank refused to refund victim losses"
- "near-miss due to prior fraud awareness"

Extract the single most powerful quote (1-2 sentences) from the text that best represents the experience.

Respond with ONLY a JSON object mapping each record's ID to its coding result, like this:
{{
  "record_id_1": {{
    "codes": ["code1", "code2"],
    "key_quote": "exact quote from text"
  }},
  "record_id_2": {{
    "codes": ["code1"],
    "key_quote": "another quote"
  }}
}}"""

    processed_chunks_count = len(processed_ids)
    processed_batches_count = 0
    progress_lock = asyncio.Lock()

    async def save_stage_data_sync(filepath, data):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    async def save_stage_data_async(filepath, data):
        await asyncio.to_thread(save_stage_data_sync, filepath, data)

    async def process_sub_batch(session, sub_chunks, attempt_depth=0):
        if output_dir and os.path.exists(os.path.join(output_dir, "cancelled")):
            raise ValueError("Pipeline stopped by user")
        if not sub_chunks:
            return []
        
        batch_input = [{"id": r["id"], "narrative_type": r["narrative_type"], "text": r["text"]} for r in sub_chunks]
        user_message = json.dumps(batch_input, indent=2)
        
        async with dynamic_sem:
            res_text = await call_groq(
                session, system_prompt_batched, user_message, MODEL_FAST,
                progress_callback=progress_callback, dynamic_sem=dynamic_sem
            )
            
        res_json = extract_json(res_text)
        
        # Split fallback logic
        if (res_json is None or not isinstance(res_json, dict)) and len(sub_chunks) > 1 and attempt_depth < 3:
            print(f"[BATCH FALLBACK] Batch of size {len(sub_chunks)} failed/too large. Splitting in half...")
            mid = len(sub_chunks) // 2
            left_task = process_sub_batch(session, sub_chunks[:mid], attempt_depth + 1)
            right_task = process_sub_batch(session, sub_chunks[mid:], attempt_depth + 1)
            left, right = await asyncio.gather(left_task, right_task)
            return left + right
            
        results_list = []
        for r in sub_chunks:
            r_id = r["id"]
            decision = res_json.get(r_id, {}) if isinstance(res_json, dict) else {}
            codes = decision.get("codes", [])
            key_quote = decision.get("key_quote", "")
            
            if not codes:
                codes = ["uncategorized qualitative concept"]
                
            for c in codes:
                c_str = str(c).strip() if c is not None else ""
                if c_str:
                    results_list.append({
                        "code": c_str,
                        "key_quote": str(key_quote or "").strip(),
                        "chunk_id": r["id"],
                        "date": r["date"],
                        "narrative_type": r["narrative_type"],
                        "source": r["source"],
                        "chunk_text": r["text"]
                    })
        return results_list

    async def process_batch_with_progress(session, batch):
        nonlocal processed_chunks_count, processed_batches_count
        batch_results = await process_sub_batch(session, batch)
        
        async with progress_lock:
            first_order_codes.extend(batch_results)
            processed_chunks_count += len(batch)
            processed_batches_count += 1
            
            if progress_callback:
                try:
                    if asyncio.iscoroutinefunction(progress_callback):
                        await progress_callback(processed=processed_chunks_count, batch_idx=processed_batches_count)
                    else:
                        progress_callback(processed=processed_chunks_count, batch_idx=processed_batches_count)
                except Exception as cb_err:
                    print(f"Error in progress callback: {cb_err}")
                    
            await save_stage_data_async(inter_path, first_order_codes)
            
            if processed_batches_count % 5 == 0 or processed_chunks_count == total_records:
                print(f"[AGENT 3 PROGRESS] Processed {processed_chunks_count}/{total_records} chunks. Codes generated: {len(first_order_codes)}")

    # Process all unprocessed chunks in parallel batches using a single ClientSession
    async with aiohttp.ClientSession() as session:
        tasks = []
        for b_idx in range(total_batches):
            start_idx = b_idx * batch_size
            end_idx = min(start_idx + batch_size, total_unprocessed)
            batch = unprocessed_records[start_idx:end_idx]
            tasks.append(process_batch_with_progress(session, batch))
            
        await asyncio.gather(*tasks)
        
    return first_order_codes


# STAGE 4: SECOND ORDER CODING AGENT

async def run_second_order_coding_agent(session, first_order_codes, research_question, detected_category):
    print("[AGENT 4] Starting Second-Order Coding Agent...")
    if not first_order_codes:
        print("[AGENT 4 ERROR] No first-order codes found to process. Cannot proceed.")
        return []
        
    # --- Deduplication Helper ---
    def deduplicate_code_strings(code_strings):
        unique_strings = []
        seen_sets = []
        for s in code_strings:
            words = set(re.findall(r'[a-z0-9]+', s.lower()))
            if not words:
                continue
            is_duplicate = False
            for seen_set in seen_sets:
                intersection = words.intersection(seen_set)
                union = words.union(seen_set)
                similarity = len(intersection) / len(union) if union else 0.0
                if similarity > 0.75:
                     is_duplicate = True
                     break
            if not is_duplicate:
                unique_strings.append(s)
                seen_sets.append(words)
        return unique_strings

    all_unique_code_strings = sorted(list(set([c["code"] for c in first_order_codes])))
    unique_codes = deduplicate_code_strings(all_unique_code_strings)
    
    # Cap at 80 codes
    step = max(1, len(unique_codes) // 80)
    sampled_codes = unique_codes[::step][:80]
    
    numbered = [f"{i+1}. {code}" for i, code in enumerate(sampled_codes)]
    codes_string = "\n".join(numbered)
    
    print(f"[AGENT 4] Grouping {len(sampled_codes)} sampled codes into second-order themes...")
    
    system_prompt = f"""You are an expert qualitative researcher applying Gioia methodology to study {detected_category} in India (2014-2025).

Research Question: {research_question}

You will receive numbered first-order codes extracted from victim and near-miss accounts.

Group them into 5-8 SECOND-ORDER THEMES.

Second-order themes must:
- Directly explain the PERSISTENCE of the fraud/crime under study rather than merely describing its channels or tactics.
- Be conceptually distinct, theoretically meaningful, and sufficiently abstract (not just categories of fraud).
- Retain participant language origins while raising the level of theoretical abstraction using researcher language.
- Total themes: minimum 5, maximum 8.

For each theme provide:
- theme_name: 4-7 words, highly conceptual, focused on explaining persistence (e.g., "Cognitive Leverage & Emotional Exploitation", "Attacker Agility & Tactical Plasticity", "Systemic Friction & Usability Gaps").
- description: 2-3 sentences explaining the underlying qualitative pattern and how it explains why this fraud/crime persists over time.
- first_order_codes: list of code numbers belonging to this theme

IMPORTANT: Use Gioia methodology terminology.
NEVER use: open coding, axial coding, selective coding (Grounded Theory).
ALWAYS use: first-order codes, second-order themes, aggregate dimensions.

Respond with ONLY this JSON, nothing else:
{{"themes": [
  {{
    "theme_name": "...",
    "description": "...",
    "first_order_codes": [1, 3, 7]
  }}
]}}"""

    user_message = f"First-order codes:\n{codes_string}"
    
    res_text = await call_groq(session, system_prompt, user_message, MODEL_SMART, max_tokens=4000)
    res_json = extract_json(res_text)
    
    if res_json is None:
        print("[JSON ERROR] Retry with stricter prompt for Agent 4...")
        retry_prompt = system_prompt + "\n\nYou must respond with valid JSON only. No markdown block, no backticks."
        res_text = await call_groq(session, retry_prompt, user_message, MODEL_SMART, max_tokens=4000)
        res_json = extract_json(res_text)
        if res_json is None:
            raise ValueError("Failed to parse valid JSON from Agent 4")
            
    themes = res_json.get("themes", [])
    mapped_themes = []
    assigned_indices = set()
    
    for t in themes:
        theme_name = t.get("theme_name", "")
        description = t.get("description", "")
        code_nums = t.get("first_order_codes", [])
        
        theme_codes_data = []
        for num in code_nums:
            idx = num - 1
            if 0 <= idx < len(sampled_codes):
                code_str = sampled_codes[idx]
                assigned_indices.add(idx)
                matches = [c for c in first_order_codes if c["code"] == code_str]
                for match in matches:
                    theme_codes_data.append(match)
                    
        mapped_themes.append({
            "theme_name": theme_name,
            "description": description,
            "codes": theme_codes_data
        })
        
    all_indices = set(range(len(sampled_codes)))
    orphan_indices = all_indices - assigned_indices
    if orphan_indices:
        print(f"[AGENT 4 WARNING] Found {len(orphan_indices)} orphaned first-order codes not assigned to themes. Creating fallback theme.")
        orphan_codes_data = []
        for idx in orphan_indices:
            code_str = sampled_codes[idx]
            matches = [c for c in first_order_codes if c["code"] == code_str]
            for match in matches:
                orphan_codes_data.append(match)
                
        mapped_themes.append({
            "theme_name": "Uncategorized Fraud Characteristics",
            "description": f"Qualitative codes capturing unique, contextual details of {detected_category} that do not aggregate into larger patterns.",
            "codes": orphan_codes_data
        })
        
    return mapped_themes

# STAGE 5: DIMENSION AGENT

async def run_dimension_agent(session, themes_list, research_question, detected_category):
    print("[AGENT 5] Starting Dimension Agent...")
    if not themes_list:
        print("[AGENT 5 ERROR] No second-order themes found. Cannot proceed.")
        return {}
        
    themes_input = []
    for t in themes_list:
        themes_input.append({
            "theme_name": t["theme_name"],
            "description": t["description"]
        })
        
    system_prompt = f"""You are building the theoretical framework for an academic paper on {detected_category} in India, using Gioia methodology. Target journal: MIS Quarterly, Information Systems Research, or equivalent.

Research Question: {research_question}

You will receive second-order themes from qualitative analysis of victim and near-miss accounts of {detected_category} in India between 2014 and 2025.

Build exactly 3 AGGREGATE DIMENSIONS representing explanatory constructs:
1. Cognitive-Tactical Asymmetry (capturing user cognitive fatigue, interface trust bias, real-time urgency, and tactical usability gaps).
2. Structural-Regulatory Latency (capturing siloed information delay, institutional response speed gap, burner identity registries, and enclave immunity).
3. Adaptive Feedback Loop (capturing re-investment of fraud revenue, AI-driven template optimization, and defensive shifting of the security burden).

For each dimension:
- dimension_name: must be one of the three constructs specified above.
- theoretical_concept: what theory this dimension contributes to (e.g., Protection Motivation Theory, Routine Activity Theory, Co-evolutionary Theory).
- themes_included: list of theme names mapped to this dimension
- theoretical_implication: what this means for theory and practice in information systems

Also provide:
- proposed_title: academic paper title focused on co-evolutionary explanation of fraud/crime persistence
- theoretical_contribution: 3-sentence statement of what this study adds to knowledge regarding socio-technical persistence of cybercrime
- theoretical_mechanism: a detailed description of the causal cycle explaining how Dimension 1 creates conditions for Dimension 2, which reinforces Dimension 3, which feeds back to strengthen Dimension 1.

Respond with ONLY this JSON:
{{"aggregate_dimensions": [
  {{
    "dimension_name": "...",
    "theoretical_concept": "...",
    "themes_included": ["theme_name_1", "theme_name_2"],
    "theoretical_implication": "..."
  }}
],
  "proposed_title": "...",
  "theoretical_contribution": "...",
  "theoretical_mechanism": "..."}}"""

    user_message = f"Second-Order Themes:\n{json.dumps(themes_input, indent=2)}"
    
    res_text = await call_groq(session, system_prompt, user_message, MODEL_SMART, max_tokens=2000)
    res_json = extract_json(res_text)
    if res_json is None:
        print("[JSON ERROR] Retry with stricter prompt for Agent 5...")
        retry_prompt = system_prompt + "\n\nYou must respond with valid JSON only. No markdown block, no backticks."
        res_text = await call_groq(session, retry_prompt, user_message, MODEL_SMART, max_tokens=2000)
        res_json = extract_json(res_text)
        if res_json is None:
            raise ValueError("Failed to parse valid JSON from Agent 5")
    return res_json

# STAGE 6: NARRATIVE AGENT

async def run_narrative_agent(session, first_order_codes, themes_list, dimensions_data, research_question, detected_category, stats):
    print("[AGENT 6] Starting Narrative Agent...")
    
    # Keywords matching helper
    cat_words = [w for w in re.findall(r'[a-z0-9]+', detected_category.lower()) if w]
    stopwords = {'and', 'or', 'the', 'of', 'in', 'fraud', 'frauds', 'scam', 'scams', 'types', 'general', 'terms', 'payment', 'digital', 'cyber', 'cybercrime'}
    keywords = [w for w in cat_words if w not in stopwords]
    if not keywords:
        keywords = cat_words
        
    filtered_quotes = []
    seen_quotes = set()
    for item in first_order_codes:
        code = item.get("code", "")
        quote = str(item.get("key_quote") or "").strip()
        if not quote or quote in seen_quotes:
            continue
        text = item.get("chunk_text", "").lower()
        if any(kw in text for kw in keywords):
            seen_quotes.add(quote)
            filtered_quotes.append({
                "code": code,
                "quote": quote,
                "year": item.get("date", "unknown").split("-")[0] if "-" in item.get("date", "") else "unknown",
                "source": item.get("chunk_id", "unknown"),
                "narrative_type": item.get("narrative_type", "unknown")
            })
            
    # Temporal spread phases
    phase1 = []
    phase2 = []
    phase3 = []
    for q in filtered_quotes:
        try:
            yr = int(q["year"])
            if 2014 <= yr <= 2016:
                phase1.append(q)
            elif 2017 <= yr <= 2020:
                phase2.append(q)
            elif 2021 <= yr <= 2025:
                phase3.append(q)
        except:
            pass
            
    temporal_str = f"Phase 1 (2014-2016) quotes:\n{json.dumps(phase1[:5], indent=2)}\n\n"
    temporal_str += f"Phase 2 (2017-2020) quotes:\n{json.dumps(phase2[:5], indent=2)}\n\n"
    temporal_str += f"Phase 3 (2021-2025) quotes:\n{json.dumps(phase3[:5], indent=2)}"
    
    structure_context = {
        "aggregate_dimensions": dimensions_data.get("aggregate_dimensions", []),
        "themes": [{
            "theme_name": t["theme_name"],
            "description": t["description"],
            "representative_first_order_codes": [c["code"] for c in t["codes"][:5]]
        } for t in themes_list]
    }
    
    system_prompt = f"""You are writing the methods and findings sections of an academic paper on {detected_category} in India using Gioia methodology. Target: top IS or management journal (e.g., MIS Quarterly, Information Systems Research).

Research Question: {research_question}

CRITICAL TERMINOLOGY RULES:
Never use: open coding, axial coding, selective coding, theoretical sampling (Grounded Theory).
Always use: first-order codes, second-order themes, aggregate dimensions, data structure (Gioia).
Reference: Gioia et al. (2013) ORM 16(1) 15-31.

EXACT STATISTICS TO USE (do not change these):
- Total records screened: {stats['total_records']}
- Relevant excerpts retained: {stats['relevant_count']}
- First-order codes generated: {stats['codes_count']}
- Second-order themes identified: {stats['themes_count']}
- Aggregate dimensions: {stats['dimensions_count']}
- Data sources: Indian media (web scraping) and ProQuest newspaper databases
- Time period: 2014-2025
- Fraud category studied: {detected_category}

Write these three outputs:

1. DATA STRUCTURE TABLE (markdown):
Three columns:
First-Order Codes | Second-Order Themes | Aggregate Dimensions
Show minimum 15 rows, covering all three dimensions. Ensure the codes are participant-centric and the themes are conceptually abstract.
Each row = one first-order code mapped up.

2. METHODS PARAGRAPH (200 words):
- State the qualitative Gioia methodology (Gioia et al., 2013)
- Mention both data sources (web scraping and ProQuest)
- Use EXACT statistics provided above
- Describe three-level coding procedure using correct Gioia terms only
- Mention ethical considerations briefly

3. FINDINGS SECTION (800 words):
Must be structured exactly into the following sections:
- **Introduction**: Introduce the research question and summary of findings.
- **Overview of Data Structure**: Briefly introduce the Gioia dimensions.
- **Dimension 1: Cognitive-Tactical Asymmetry**: Introduce theoretically, explain constituent themes, include 1-2 representative quotes, and explain the temporal evolution (mechanisms that evolved vs. stayed constant).
- **Dimension 2: Structural-Regulatory Latency**: Introduce theoretically, explain constituent themes, include 1-2 representative quotes, and explain temporal dynamics.
- **Dimension 3: Adaptive Feedback Loop**: Introduce theoretically, explain constituent themes, include 1-2 representative quotes, and explain temporal dynamics.
- **Interaction Between Dimensions**: Explain the causal feedback cycle linking the three dimensions.
- **Longitudinal Co-evolutionary Analysis**: Identify adaptations of attackers vs. institutional learning over time.
- **Emergent Theoretical Model & Conclusion**: Integrate Protection Motivation Theory and Routine Activity Theory, introducing the concept of "Co-Evolutionary Defensive Friction" and answering the research question.

Use formal, analytical prose (matching MISQ style, avoiding generic summaries). No bullet points.

Respond with ONLY this JSON:
{{"data_structure_table": "markdown string",
  "methods_paragraph": "...",
  "findings_section": "..."}}"""

    user_message = f"Gioia Coding Structure:\n{json.dumps(structure_context, indent=2)}\n\nTemporal Quotes Map:\n{temporal_str}"
    
    res_text = await call_groq(session, system_prompt, user_message, MODEL_SMART, max_tokens=4000)
    res_json = extract_json(res_text)
    if res_json is None:
        print("[JSON ERROR] Retry with stricter prompt for Agent 6...")
        retry_prompt = system_prompt + "\n\nYou must respond with valid JSON only. No markdown block, no backticks."
        res_text = await call_groq(session, retry_prompt, user_message, MODEL_SMART, max_tokens=4000)
        res_json = extract_json(res_text)
        if res_json is None:
            raise ValueError("Failed to parse valid JSON from Agent 6")
    return res_json


# COMPATIBILITY CLASS FOR WEB APP (FastAPI)

class GioiaPipeline:
    def __init__(self, research_question, fraud_category=None, run_id=None, max_records=400, filter_category=True):
        self.research_question = research_question
        self.fraud_category = fraud_category
        self.max_records = max_records
        self.filter_category = filter_category
        
        if run_id:
            self.run_id = run_id
        else:
            self.run_id = generate_run_id(research_question)
            
        if 'backend' in sys.modules:
            self.output_dir = os.path.join("gioia_outputs", self.run_id)
        else:
            self.output_dir = os.path.join(OUTPUT_FOLDER, self.run_id)
            
        os.makedirs(self.output_dir, exist_ok=True)
        self.metadata_path = os.path.join(self.output_dir, "metadata.json")
        
    def load_metadata(self):
        if os.path.exists(self.metadata_path):
            try:
                with open(self.metadata_path, "r", encoding="utf-8") as f:
                    meta = json.load(f)
                    if "max_records" in meta:
                        self.max_records = int(meta["max_records"])
                    if "filter_category" in meta:
                        self.filter_category = bool(meta["filter_category"])
                    return meta
            except:
                pass
        return {
            "run_id": self.run_id,
            "research_question": self.research_question,
            "fraud_category": self.fraud_category,
            "max_records": self.max_records,
            "filter_category": self.filter_category,
            "status": "running",
            "current_stage": 1,
            "updated_at": datetime.datetime.now().isoformat(),
            "stats": {
                "chunks_count": 0,
                "excerpts_count": 0,
                "first_order_count": 0,
                "themes_count": 0,
                "dimensions_count": 0
            }
        }
        
    def save_metadata(self, metadata):
        with open(self.metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)
            
    def save_stage_data(self, stage_num, data):
        filename = f"stage{stage_num}_data.json"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
            
    def load_stage_data(self, stage_num):
        filename = f"stage{stage_num}_data.json"
        filepath = os.path.join(self.output_dir, filename)
        if stage_num == 3 and not os.path.exists(filepath):
            alt_path = os.path.join(self.output_dir, "first_order_codes.json")
            if os.path.exists(alt_path):
                filepath = alt_path
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        return []
        
    def save_stage_text(self, stage_num, text):
        filename = f"stage{stage_num}_narrative.txt"
        filepath = os.path.join(self.output_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(text)
            
    def load_stage_text(self, stage_num):
        filename = f"stage{stage_num}_narrative.txt"
        filepath = os.path.join(self.output_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        return ""
        
    def load_stage_text_file(self, filename):
        filepath = os.path.join(self.output_dir, filename)
        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                return f.read()
        return ""
        
    def get_all_results(self):
        return {
            "metadata": self.load_metadata(),
            "chunks": self.load_stage_data(1) or [],
            "excerpts": self.load_stage_data(2) or [],
            "first_order": self.load_stage_data(3) or [],
            "second_order": self.load_stage_data(4) or [],
            "dimensions": self.load_stage_data(5) or [],
            "narrative": self.load_stage_text(6) or ""
        }
        
    def make_progress_callback(self, stage_total_records, total_batches, start_time):
        state = {
            "processed": 0,
            "batch_idx": 0,
            "is_waiting": False,
            "cooldown_addition": 0.0
        }
        
        def callback(processed=None, batch_idx=None, is_waiting=None, est_time_remaining_add=0.0):
            if processed is not None:
                state["processed"] = processed
            if batch_idx is not None:
                state["batch_idx"] = batch_idx
            if is_waiting is not None:
                state["is_waiting"] = is_waiting
            if est_time_remaining_add > 0:
                state["cooldown_addition"] += est_time_remaining_add
                
            elapsed = time.time() - start_time
            if state["batch_idx"] > 0:
                avg_time_per_batch = elapsed / state["batch_idx"]
                remaining_batches = total_batches - state["batch_idx"]
                est_time = remaining_batches * avg_time_per_batch
            else:
                remaining_batches = total_batches - state["batch_idx"]
                est_time = remaining_batches * 6.0 # assume 6s per batch
                
            if state["is_waiting"]:
                est_time += state["cooldown_addition"]
                
            est_time = max(0, int(est_time))
            
            metadata = self.load_metadata()
            metadata["stats"]["processed_records"] = state["processed"]
            metadata["stats"]["total_records"] = stage_total_records
            metadata["stats"]["current_batch"] = state["batch_idx"]
            metadata["stats"]["total_batches"] = total_batches
            metadata["stats"]["est_time_remaining"] = est_time
            metadata["stats"]["rate_limit_waiting"] = state["is_waiting"]
            metadata["updated_at"] = datetime.datetime.now().isoformat()
            self.save_metadata(metadata)
            
        return callback

    def run(self, start_stage=1):
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            
        if loop.is_running():
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(asyncio.run, self.run_async(start_stage))
                return future.result()
        else:
            return loop.run_until_complete(self.run_async(start_stage))

    def check_cancellation(self):
        if os.path.exists(os.path.join(self.output_dir, "cancelled")):
            raise ValueError("Pipeline stopped by user")

    async def run_async(self, start_stage=1):
        self.check_cancellation()
        metadata = self.load_metadata()
        metadata["status"] = "running"
        metadata["error"] = None
        metadata["updated_at"] = datetime.datetime.now().isoformat()
        self.save_metadata(metadata)
        
        detected_category = detect_fraud_category(self.research_question)
        self.fraud_category = detected_category
        metadata["fraud_category"] = detected_category
        self.save_metadata(metadata)
        
        # --- Automatic Resumption in CLI/Full Runs ---
        if start_stage == 1:
            if os.path.exists(os.path.join(self.output_dir, "second_order_themes.json")):
                print("Resuming from Agent 5...")
                start_stage = 5
            elif os.path.exists(os.path.join(self.output_dir, "first_order_codes.json")):
                print("Resuming from Agent 4...")
                start_stage = 4
            elif os.path.exists(os.path.join(self.output_dir, "stage2_data.json")):
                print("Resuming from Agent 3...")
                start_stage = 3
            elif os.path.exists(os.path.join(self.output_dir, "stage1_data.json")):
                print("Resuming from Agent 2...")
                start_stage = 2
                
        try:
            # Stage 1: Intake
            if start_stage <= 1:
                self.check_cancellation()
                print(f"[STAGE 1] Running Intake Agent for run {self.run_id}...")
                metadata["current_stage"] = 1
                self.save_metadata(metadata)
                
                chunks = await asyncio.to_thread(run_intake_agent, self.research_question, self.max_records, self.filter_category)
                self.save_stage_data(1, chunks)
                
                metadata["stats"]["chunks_count"] = len(chunks)
                self.save_metadata(metadata)
                print(f"[STAGE 1] Intake complete. {len(chunks)} chunks retrieved.")
                
            # Stage 2: Extraction
            if start_stage <= 2:
                self.check_cancellation()
                print(f"[STAGE 2] Running Extraction Agent...")
                metadata["current_stage"] = 2
                self.save_metadata(metadata)
                
                chunks = self.load_stage_data(1)
                
                batch_size = 5
                total_batches = (len(chunks) + batch_size - 1) // batch_size
                progress_cb = self.make_progress_callback(len(chunks), total_batches, time.time())
                
                excerpts = await run_extraction_agent(
                    chunks, self.research_question, detected_category, self.output_dir,
                    progress_callback=progress_cb, concurrency_limit=CONCURRENCY_LIMIT
                )
                self.save_stage_data(2, excerpts)
                
                with open(os.path.join(self.output_dir, "relevant_excerpts.json"), "w", encoding="utf-8") as f:
                    json.dump(excerpts, f, indent=2)
                
                metadata = self.load_metadata()
                metadata["stats"]["excerpts_count"] = len(excerpts)
                self.save_metadata(metadata)
                print(f"[STAGE 2] Extraction complete. {len(excerpts)} excerpts found.")
                
            # Stage 3: First Order Coding
            if start_stage <= 3:
                self.check_cancellation()
                print(f"[STAGE 3] Running First Order Coding Agent...")
                metadata["current_stage"] = 3
                self.save_metadata(metadata)
                
                excerpts = self.load_stage_data(2)
                
                batch_size = 5
                total_batches = (len(excerpts) + batch_size - 1) // batch_size
                progress_cb = self.make_progress_callback(len(excerpts), total_batches, time.time())
                
                first_order = await run_first_order_coding_agent(
                    excerpts, self.research_question, detected_category, self.output_dir,
                    progress_callback=progress_cb, concurrency_limit=CONCURRENCY_LIMIT
                )
                self.save_stage_data(3, first_order)
                
                with open(os.path.join(self.output_dir, "first_order_codes.json"), "w", encoding="utf-8") as f:
                    json.dump(first_order, f, indent=2)
                    
                metadata = self.load_metadata()
                metadata["stats"]["first_order_count"] = len(first_order)
                self.save_metadata(metadata)
                print(f"[STAGE 3] First Order Coding complete. {len(first_order)} codes generated.")
                
            # Stages 4, 5, 6 require a ClientSession
            async with aiohttp.ClientSession() as session:
                # Stage 4: Second Order Coding
                if start_stage <= 4:
                    self.check_cancellation()
                    print(f"[STAGE 4] Running Second Order Coding Agent...")
                    metadata["current_stage"] = 4
                    self.save_metadata(metadata)
                    
                    first_order = self.load_stage_data(3)
                    second_order = await run_second_order_coding_agent(session, first_order, self.research_question, detected_category)
                    self.save_stage_data(4, second_order)
                    
                    with open(os.path.join(self.output_dir, "second_order_themes.json"), "w", encoding="utf-8") as f:
                        json.dump(second_order, f, indent=2)
                        
                    metadata["stats"]["themes_count"] = len(second_order)
                    self.save_metadata(metadata)
                    print(f"[STAGE 4] Second Order Coding complete. {len(second_order)} themes created.")
                    
                # Stage 5: Dimension Agent
                if start_stage <= 5:
                    self.check_cancellation()
                    print(f"[STAGE 5] Running Dimension Agent...")
                    metadata["current_stage"] = 5
                    self.save_metadata(metadata)
                    
                    second_order = self.load_stage_data(4)
                    dimensions = await run_dimension_agent(session, second_order, self.research_question, detected_category)
                    
                    self.save_stage_data("5_raw", dimensions)
                    
                    frontend_dimensions = []
                    for dim in dimensions.get("aggregate_dimensions", []):
                        frontend_dimensions.append({
                            "dimension_name": dim.get("dimension_name", ""),
                            "themes": dim.get("themes_included", []),
                            "theoretical_explanation": f"Concept: {dim.get('theoretical_concept', '')}\nImplication: {dim.get('theoretical_implication', '')}"
                        })
                    self.save_stage_data(5, frontend_dimensions)
                    
                    with open(os.path.join(self.output_dir, "aggregate_dimensions.json"), "w", encoding="utf-8") as f:
                        json.dump(dimensions, f, indent=2)
                        
                    metadata["stats"]["dimensions_count"] = len(dimensions.get("aggregate_dimensions", []))
                    self.save_metadata(metadata)
                    print(f"[STAGE 5] Dimension Analysis complete.")
                    
                # Stage 6: Narrative Agent
                if start_stage <= 6:
                    self.check_cancellation()
                    print(f"[STAGE 6] Running Narrative Agent...")
                    metadata["current_stage"] = 6
                    self.save_metadata(metadata)
                    
                    first_order = self.load_stage_data(3)
                    second_order = self.load_stage_data(4)
                    dimensions = self.load_stage_data("5_raw")
                    
                    stats_for_narrative = {
                        "total_records": metadata["stats"]["chunks_count"],
                        "relevant_count": metadata["stats"]["excerpts_count"],
                        "codes_count": metadata["stats"]["first_order_count"],
                        "themes_count": metadata["stats"]["themes_count"],
                        "dimensions_count": metadata["stats"]["dimensions_count"]
                    }
                    
                    narrative = await run_narrative_agent(session, first_order, second_order, dimensions, self.research_question, detected_category, stats_for_narrative)
                    
                    narrative_combined = f"{narrative.get('methods_paragraph', '')}\n\n{narrative.get('findings_section', '')}"
                    self.save_stage_text(6, narrative_combined)
                    
                    with open(os.path.join(self.output_dir, "gioia_data_structure.md"), "w", encoding="utf-8") as f:
                        f.write(narrative.get("data_structure_table", ""))
                    with open(os.path.join(self.output_dir, "methods_paragraph.txt"), "w", encoding="utf-8") as f:
                        f.write(narrative.get("methods_paragraph", ""))
                    with open(os.path.join(self.output_dir, "findings_section.txt"), "w", encoding="utf-8") as f:
                        f.write(narrative.get("findings_section", ""))
                        
                    print(f"[STAGE 6] Narrative generation complete.")
                    
            # Finish Pipeline
            metadata["status"] = "complete"
            metadata["current_stage"] = 6
            metadata["updated_at"] = datetime.datetime.now().isoformat()
            self.save_metadata(metadata)
            
            # Save a complete summary output
            full_out = {
                "research_question": self.research_question,
                "first_order_codes": self.load_stage_data(3),
                "second_order_themes": self.load_stage_data(4),
                "aggregate_dimensions": self.load_stage_data("5_raw"),
                "narrative": {
                    "data_structure_table": self.load_stage_text_file("gioia_data_structure.md"),
                    "methods_paragraph": self.load_stage_text_file("methods_paragraph.txt"),
                    "findings_section": self.load_stage_text_file("findings_section.txt")
                },
                "stats": {
                    "total_records": metadata["stats"]["chunks_count"],
                    "chunks_analyzed": metadata["stats"]["chunks_count"],
                    "relevant_chunks": metadata["stats"]["excerpts_count"],
                    "first_order_codes_count": metadata["stats"]["first_order_count"],
                    "second_order_themes_count": metadata["stats"]["themes_count"],
                    "aggregate_dimensions_count": metadata["stats"]["dimensions_count"]
                }
            }
            with open(os.path.join(self.output_dir, "full_pipeline_output.json"), "w", encoding="utf-8") as f:
                json.dump(full_out, f, indent=2)
                
            print(f"[SUCCESS] Gioia Pipeline completed successfully for run {self.run_id}!")
            
            total = metadata["stats"]["chunks_count"]
            relevant = metadata["stats"]["excerpts_count"]
            pct = (relevant / total * 100) if total > 0 else 0
            codes = metadata["stats"]["first_order_count"]
            themes = metadata["stats"]["themes_count"]
            dims = metadata["stats"]["dimensions_count"]
            
            print(f"\n========== PIPELINE COMPLETE ==========")
            print(f"Category analyzed:    {detected_category}")
            print(f"Research question:    {self.research_question[:60]}...")
            print(f"---------------------------------------")
            print(f"Records screened:     {total}")
            print(f"Relevant kept:        {relevant} ({pct:.1f}%)")
            print(f"First-order codes:    {codes}")
            print(f"Second-order themes:  {themes}")
            print(f"Aggregate dimensions: {dims}")
            print(f"---------------------------------------")
            print(f"Output files saved to: {self.output_dir}/")
            print(f"========================================\n")
            
        except Exception as e:
            metadata["status"] = "failed"
            metadata["error"] = str(e)
            metadata["updated_at"] = datetime.datetime.now().isoformat()
            self.save_metadata(metadata)
            print(f"[ERROR] Gioia Pipeline failed at stage {metadata['current_stage']}: {e}")
            raise e

# STANDALONE CLI RUNNER

def main():
    parser = argparse.ArgumentParser(description="Run Gioia Qualitative Research Pipeline")
    parser.add_argument("--question", type=str, required=True, help="The research question")
    parser.add_argument("--run_id", type=str, required=True, help="Unique identifier for the run")
    parser.add_argument("--max_records", type=int, default=400, help="Max records/chunks to intake")
    parser.add_argument("--no_filter", action="store_true", help="Disable category filtering during intake")
    args = parser.parse_args()
    
    pipeline = GioiaPipeline(
        research_question=args.question,
        run_id=args.run_id,
        max_records=args.max_records,
        filter_category=not args.no_filter
    )
    pipeline.run()

if __name__ == "__main__":
    main()

