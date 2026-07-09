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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv

load_dotenv()

# CONCURRENCY SWITCH: Set to 1 for Free Tier (sequential batching), >1 for Paid Tier (parallel API calls)
CONCURRENCY_LIMIT = 1

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

def call_groq(system_prompt, user_message, model, max_tokens=2000, progress_callback=None):
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
            r = requests.post(url, headers=headers, json=payload, timeout=60)
            if r.status_code == 429:
                delay = backoff + random.uniform(0.1, 1.0)
                print(f"[RATE LIMIT 429] Attempt {attempt+1}/{max_attempts} failed with 429. Rotating key and waiting {delay:.2f} seconds...")
                rotate_api_key()
                if progress_callback:
                    try:
                        progress_callback(is_waiting=True, est_time_remaining_add=delay)
                    except Exception as cb_err:
                        print(f"Error in progress callback: {cb_err}")
                time.sleep(delay)
                if progress_callback:
                    try:
                        progress_callback(is_waiting=False)
                    except Exception as cb_err:
                        print(f"Error in progress callback: {cb_err}")
                backoff = min(90.0, backoff * 2.0)
                attempt += 1
                continue
                
            if r.status_code != 200:
                print(f"[API ERROR DETAILS] Status: {r.status_code}, Response: {r.text}")
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
        except Exception as e:
            print(f"[API ERROR] Attempt {attempt+1}/{max_attempts} failed: {e}")
            delay = 2.0
            time.sleep(delay)
            attempt += 1
            
    return None

def extract_json(text):
    if not text:
        return None
    # Method 1: direct parse
    try:
        return json.loads(text)
    except:
        pass
    # Method 2: find outermost { }
    try:
        s = text.find('{')
        e = text.rfind('}') + 1
        if s != -1 and e > s:
            return json.loads(text[s:e])
    except:
        pass
    # Method 3: find outermost [ ]
    try:
        s = text.find('[')
        e = text.rfind(']') + 1
        if s != -1 and e > s:
            return json.loads(text[s:e])
    except:
        pass
    return None

# STAGE 1: INTAKE AGENT (PURE PYTHON)

def run_intake_agent(research_question):
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
    after_date = 0

    # --- Load Stream A ---
    sheet_a = "stream_a_scraped"
    if sheet_a not in xl.sheet_names:
        raise ValueError(f"Sheet '{sheet_a}' not found in Excel file.")
    df_a = pd.read_excel(xl, sheet_name=sheet_a)
    len_a = len(df_a)

    for idx, row in df_a.iterrows():
        if not row_matches_category(row, detected_category):
            continue
        after_cat += 1
        
        raw_type = row.get("Narrative Type", "")
        normalized_type = normalize_narrative_type(raw_type)
        if normalized_type not in ("VICTIM", "NEAR-MISS"):
            continue
        after_type += 1
        if normalized_type == "VICTIM":
            victim_count += 1
        else:
            near_miss_count += 1
            
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
            if not row_matches_category(row, detected_category):
                continue
            after_cat += 1
            
            raw_type = row.get("Narrative Type", "")
            normalized_type = normalize_narrative_type(raw_type)
            if normalized_type not in ("VICTIM", "NEAR-MISS"):
                continue
            after_type += 1
            if normalized_type == "VICTIM":
                victim_count += 1
            else:
                near_miss_count += 1
                
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
    def sample_evenly_by_date(records_list, max_count):
        if len(records_list) <= max_count:
            return records_list
        dated = [r for r in records_list if r['year'] is not None]
        undated = [r for r in records_list if r['year'] is None]
        dated.sort(key=lambda x: x['date'])
        step = max(1, len(dated) // max_count)
        sampled = dated[::step][:max_count]
        if len(sampled) < max_count:
            sampled += undated[:max_count - len(sampled)]
        return sampled

    victim_records = [r for r in records if r['narrative_type'] == 'VICTIM']
    near_miss_records = [r for r in records if r['narrative_type'] == 'NEAR-MISS']
    
    victim_sample = sample_evenly_by_date(victim_records, MAX_VICTIM)
    near_miss_sample = sample_evenly_by_date(near_miss_records, MAX_NEAR_MISS)
    
    final_records = victim_sample + near_miss_sample
    random.shuffle(final_records)
    
    web_count = sum(1 for r in final_records if r["source"] == "web_scraping")
    pq_count = sum(1 for r in final_records if r["source"] == "proquest")
    
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
    print(f"After date validation:  {after_date}")
    print(f"-------------------------------------")
    print(f"Final sample:           {len(final_records)}")
    print(f"  - VICTIM:             {len(victim_sample)}")
    print(f"  - NEAR-MISS:          {len(near_miss_sample)}")
    print(f"  - From web scraping:  {web_count}")
    print(f"  - From ProQuest:      {pq_count}")
    print(f"======================================\n")
    
    return final_records

# STAGE 2: EXTRACTION AGENT

def run_extraction_agent(chunks, research_question, detected_category, output_dir=None, progress_callback=None, concurrency_limit=1):
    print(f"[AGENT 2] Starting Extraction Agent. Screening {len(chunks)} chunks for relevance...")
    
    if concurrency_limit == 1:
        batch_size = 5
    else:
        batch_size = 1
        
    total_records = len(chunks)
    total_batches = (total_records + batch_size - 1) // batch_size
    
    if progress_callback:
        progress_callback(processed=0, batch_idx=0)
        
    relevant_records = []
    
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

    system_prompt_single = f"""You are a research assistant screening text excerpts for a qualitative Gioia methodology study on {detected_category} in India (2014-2025).

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

Respond with ONLY this JSON, nothing else:
{{"relevant": true, "reason": "one sentence"}}"""

    if concurrency_limit == 1:
        # Serial Batched Processing with recursive split-on-failure fallback
        def process_sub_batch(sub_chunks, attempt_depth=0):
            if not sub_chunks:
                return []
            
            batch_input = [{"id": r["id"], "text": r["text"]} for r in sub_chunks]
            user_message = json.dumps(batch_input, indent=2)
            
            res_text = call_groq(system_prompt_batched, user_message, MODEL_FAST, progress_callback=progress_callback)
            res_json = extract_json(res_text)
            
            # If batch failed (e.g. 413 token limit) and size > 1, split and recurse!
            if res_json is None and len(sub_chunks) > 1 and attempt_depth < 3:
                print(f"[BATCH FALLBACK] Batch of size {len(sub_chunks)} failed/too large. Splitting in half...")
                mid = len(sub_chunks) // 2
                left = process_sub_batch(sub_chunks[:mid], attempt_depth + 1)
                right = process_sub_batch(sub_chunks[mid:], attempt_depth + 1)
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
                
                if is_relevant:
                    r_copy = r.copy()
                    r_copy["relevance_reason"] = reason
                    results_list.append(r_copy)
            return results_list

        for b_idx in range(total_batches):
            start_idx = b_idx * batch_size
            end_idx = min(start_idx + batch_size, total_records)
            batch = chunks[start_idx:end_idx]
            
            batch_results = process_sub_batch(batch)
            relevant_records.extend(batch_results)
                    
            processed_count = end_idx
            if progress_callback:
                progress_callback(processed=processed_count, batch_idx=b_idx + 1)
                
            time.sleep(0.5)
            if (b_idx + 1) % 5 == 0 or b_idx + 1 == total_batches:
                print(f"[AGENT 2 PROGRESS] Processed batch {b_idx + 1}/{total_batches}. Relevant so far: {len(relevant_records)}")
    else:
        # Concurrent processing (Paid Tier)
        processed_lock = threading.Lock()
        state = {"processed": 0}
        
        def process_single(record):
            user_message = f"Record ID: {record['id']}\nText:\n{record['text']}"
            res_text = call_groq(system_prompt_single, user_message, MODEL_FAST)
            res_json = extract_json(res_text)
            
            is_relevant = False
            reason = ""
            if res_json and isinstance(res_json, dict):
                is_relevant = res_json.get("relevant", False)
                reason = res_json.get("reason", "")
                
            with processed_lock:
                state["processed"] += 1
                if progress_callback:
                    progress_callback(processed=state["processed"], batch_idx=state["processed"])
                    
            if is_relevant:
                r_copy = record.copy()
                r_copy["relevance_reason"] = reason
                return r_copy
            return None
            
        with ThreadPoolExecutor(max_workers=concurrency_limit) as executor:
            futures = [executor.submit(process_single, r) for r in chunks]
            for fut in as_completed(futures):
                res = fut.result()
                if res:
                    relevant_records.append(res)
                    
    print(f"[AGENT 2] Extraction complete. Kept {len(relevant_records)}/{len(chunks)} records.")
    return relevant_records

# STAGE 3: FIRST ORDER CODING AGENT

def run_first_order_coding_agent(relevant_records, research_question, detected_category, output_dir, progress_callback=None, concurrency_limit=1):
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
    
    if concurrency_limit == 1:
        batch_size = 5
    else:
        batch_size = 1
        
    total_records = len(relevant_records)
    
    processed_ids = set()
    first_order_codes = []
    
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
        
    total_batches = (total_unprocessed + batch_size - 1) // batch_size
    
    if progress_callback:
        progress_callback(processed=len(processed_ids), batch_idx=0)
        
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

    system_prompt_single = f"""You are conducting qualitative coding for a Gioia methodology study on {detected_category} in India.

Research Question: {research_question}

Generate 1-3 FIRST-ORDER CODES for this excerpt.
First-order codes must:
- Use language close to the actual text
- Be specific to {detected_category} when possible
- Capture WHO did WHAT (victim, fraudster, institution)
- Be 3-7 words each
- Reflect the informant's perspective

Also extract the single most powerful quote (1-2 sentences) from the text that best represents the experience.

Respond with ONLY this JSON, nothing else:
{{
  "codes": ["code1", "code2"],
  "key_quote": "exact quote from text"
}}"""

    if concurrency_limit == 1:
        # Serial Batched Processing with recursive split-on-failure fallback
        def process_sub_batch(sub_chunks, attempt_depth=0):
            if not sub_chunks:
                return []
            
            batch_input = [{"id": r["id"], "narrative_type": r["narrative_type"], "text": r["text"]} for r in sub_chunks]
            user_message = json.dumps(batch_input, indent=2)
            
            res_text = call_groq(system_prompt_batched, user_message, MODEL_FAST, progress_callback=progress_callback)
            res_json = extract_json(res_text)
            
            # If batch failed and size > 1, split and recurse!
            if (res_json is None or not isinstance(res_json, dict)) and len(sub_chunks) > 1 and attempt_depth < 3:
                print(f"[BATCH FALLBACK] Batch of size {len(sub_chunks)} failed/too large. Splitting in half...")
                mid = len(sub_chunks) // 2
                left = process_sub_batch(sub_chunks[:mid], attempt_depth + 1)
                right = process_sub_batch(sub_chunks[mid:], attempt_depth + 1)
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
                    if c.strip():
                        results_list.append({
                            "code": c.strip(),
                            "key_quote": key_quote,
                            "chunk_id": r["id"],
                            "date": r["date"],
                            "narrative_type": r["narrative_type"],
                            "source": r["source"],
                            "chunk_text": r["text"]
                        })
            return results_list

        for b_idx in range(total_batches):
            start_idx = b_idx * batch_size
            end_idx = min(start_idx + batch_size, total_unprocessed)
            batch = unprocessed_records[start_idx:end_idx]
            
            batch_results = process_sub_batch(batch)
            first_order_codes.extend(batch_results)
                        
            processed_count = len(processed_ids) + end_idx
            if progress_callback:
                progress_callback(processed=processed_count, batch_idx=b_idx + 1)
                
            # Save intermediate results
            with open(inter_path, "w", encoding="utf-8") as f:
                json.dump(first_order_codes, f, indent=2)
                
            time.sleep(0.5)
            if (b_idx + 1) % 5 == 0 or b_idx + 1 == total_batches:
                print(f"[AGENT 3 PROGRESS] Processed batch {b_idx + 1}/{total_batches}. Codes generated: {len(first_order_codes)}")
    else:
        # Concurrent processing (Paid Tier)
        processed_lock = threading.Lock()
        state = {"processed": len(processed_ids)}
        
        def process_single(record):
            user_message = f"Record ID: {record['id']}\nNarrative Type: {record['narrative_type']}\nText:\n{record['text']}"
            res_text = call_groq(system_prompt_single, user_message, MODEL_FAST)
            res_json = extract_json(res_text)
            
            codes = []
            key_quote = ""
            if res_json and isinstance(res_json, dict):
                codes = res_json.get("codes", [])
                key_quote = res_json.get("key_quote", "")
                
            if not codes:
                codes = ["uncategorized qualitative concept"]
                
            local_codes = []
            for c in codes:
                if c.strip():
                    local_codes.append({
                        "code": c.strip(),
                        "key_quote": key_quote,
                        "chunk_id": record["id"],
                        "date": record["date"],
                        "narrative_type": record["narrative_type"],
                        "source": record["source"],
                        "chunk_text": record["text"]
                    })
            
            with processed_lock:
                state["processed"] += 1
                if progress_callback:
                    progress_callback(processed=state["processed"], batch_idx=state["processed"])
                
                first_order_codes.extend(local_codes)
                
                with open(inter_path, "w", encoding="utf-8") as f:
                    json.dump(first_order_codes, f, indent=2)
            
            return True
            
        with ThreadPoolExecutor(max_workers=concurrency_limit) as executor:
            futures = [executor.submit(process_single, r) for r in unprocessed_records]
            for fut in as_completed(futures):
                fut.result()
                
    return first_order_codes

# STAGE 4: SECOND ORDER CODING AGENT

def run_second_order_coding_agent(first_order_codes, research_question, detected_category):
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
- Be more conceptual than first-order codes
- Each capture a meaningful pattern across codes
- Use researcher language (not just data language)
- Be specific to {detected_category} dynamics
- Total themes: minimum 5, maximum 8

For each theme provide:
- theme_name: 4-7 words, conceptual
- description: 2-3 sentences explaining the pattern and why it matters for understanding {detected_category}
- first_order_codes: list of code numbers belonging to this theme

IMPORTANT: Use Gioia methodology terminology.
NEVER use: open coding, axial coding, selective coding (those are Grounded Theory terms).
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
    
    res_text = call_groq(system_prompt, user_message, MODEL_SMART, max_tokens=4000)
    res_json = extract_json(res_text)
    
    if res_json is None:
        print("[JSON ERROR] Retry with stricter prompt for Agent 4...")
        retry_prompt = system_prompt + "\n\nYou must respond with valid JSON only. No markdown block, no backticks."
        res_text = call_groq(retry_prompt, user_message, MODEL_SMART, max_tokens=4000)
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

def run_dimension_agent(themes_list, research_question, detected_category):
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

Build 2-4 AGGREGATE DIMENSIONS.

Aggregate dimensions must:
- Represent the highest level of abstraction
- Be specific to {detected_category} in India
- Together answer the research question
- Have clear theoretical implications
- Be suitable for a top academic journal

For each dimension:
- dimension_name: formal academic name (must reference {detected_category} context)
- theoretical_concept: what theory this dimension contributes to
- themes_included: list of theme names
- theoretical_implication: what this means for theory and practice

Also provide:
- proposed_title: academic paper title
- theoretical_contribution: 3-sentence statement of what this study adds to knowledge
- theoretical_mechanism: how the dimensions relate to each other causally

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
    
    res_text = call_groq(system_prompt, user_message, MODEL_SMART, max_tokens=2000)
    res_json = extract_json(res_text)
    if res_json is None:
        print("[JSON ERROR] Retry with stricter prompt for Agent 5...")
        retry_prompt = system_prompt + "\n\nYou must respond with valid JSON only. No markdown block, no backticks."
        res_text = call_groq(retry_prompt, user_message, MODEL_SMART, max_tokens=2000)
        res_json = extract_json(res_text)
        if res_json is None:
            raise ValueError("Failed to parse valid JSON from Agent 5")
    return res_json

# STAGE 6: NARRATIVE AGENT

def run_narrative_agent(first_order_codes, themes_list, dimensions_data, research_question, detected_category, stats):
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
        quote = item.get("key_quote", "").strip()
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
    
    system_prompt = f"""You are writing the methods and findings sections of an academic paper on {detected_category} in India using Gioia methodology. Target: top IS or management journal.

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
Show minimum 15 rows, covering all dimensions.
Each row = one first-order code mapped up.

2. METHODS PARAGRAPH (200 words):
- State the qualitative Gioia methodology
- Mention both data sources
- Use EXACT statistics provided above
- Describe three-level coding procedure using correct Gioia terms only
- Mention ethical considerations briefly

3. FINDINGS SECTION (500 words):
- Organize by aggregate dimension
- For each dimension:
  * Introduce the dimension theoretically
  * Describe constituent themes
  * Include 1-2 direct quotes (cite as: Source, Year, Narrative Type)
  * Add temporal paragraph starting with 'Temporally,' showing how this dimension evolved across Phase 1/2/3
- Use formal academic prose
- No bullet points in narrative
- Connect dimensions at the end with theoretical mechanism

Respond with ONLY this JSON:
{{"data_structure_table": "markdown string",
  "methods_paragraph": "...",
  "findings_section": "..."}}"""

    user_message = f"Gioia Coding Structure:\n{json.dumps(structure_context, indent=2)}\n\nTemporal Quotes Map:\n{temporal_str}"
    
    res_text = call_groq(system_prompt, user_message, MODEL_SMART, max_tokens=4000)
    res_json = extract_json(res_text)
    if res_json is None:
        print("[JSON ERROR] Retry with stricter prompt for Agent 6...")
        retry_prompt = system_prompt + "\n\nYou must respond with valid JSON only. No markdown block, no backticks."
        res_text = call_groq(retry_prompt, user_message, MODEL_SMART, max_tokens=4000)
        res_json = extract_json(res_text)
        if res_json is None:
            raise ValueError("Failed to parse valid JSON from Agent 6")
    return res_json

# COMPATIBILITY CLASS FOR WEB APP (FastAPI)

class GioiaPipeline:
    def __init__(self, research_question, fraud_category=None, run_id=None):
        self.research_question = research_question
        self.fraud_category = fraud_category
        
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
                    return json.load(f)
            except:
                pass
        return {
            "run_id": self.run_id,
            "research_question": self.research_question,
            "fraud_category": self.fraud_category,
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
                print(f"[STAGE 1] Running Intake Agent for run {self.run_id}...")
                metadata["current_stage"] = 1
                self.save_metadata(metadata)
                
                chunks = run_intake_agent(self.research_question)
                self.save_stage_data(1, chunks)
                
                metadata["stats"]["chunks_count"] = len(chunks)
                self.save_metadata(metadata)
                print(f"[STAGE 1] Intake complete. {len(chunks)} chunks retrieved.")
                
            # Stage 2: Extraction
            if start_stage <= 2:
                print(f"[STAGE 2] Running Extraction Agent...")
                metadata["current_stage"] = 2
                self.save_metadata(metadata)
                
                chunks = self.load_stage_data(1)
                
                batch_size = 15 if CONCURRENCY_LIMIT == 1 else 1
                total_batches = (len(chunks) + batch_size - 1) // batch_size
                progress_cb = self.make_progress_callback(len(chunks), total_batches, time.time())
                
                excerpts = run_extraction_agent(
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
                print(f"[STAGE 3] Running First Order Coding Agent...")
                metadata["current_stage"] = 3
                self.save_metadata(metadata)
                
                excerpts = self.load_stage_data(2)
                
                batch_size = 15 if CONCURRENCY_LIMIT == 1 else 1
                total_batches = (len(excerpts) + batch_size - 1) // batch_size
                progress_cb = self.make_progress_callback(len(excerpts), total_batches, time.time())
                
                first_order = run_first_order_coding_agent(
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
                
            # Stage 4: Second Order Coding
            if start_stage <= 4:
                print(f"[STAGE 4] Running Second Order Coding Agent...")
                metadata["current_stage"] = 4
                self.save_metadata(metadata)
                
                first_order = self.load_stage_data(3)
                second_order = run_second_order_coding_agent(first_order, self.research_question, detected_category)
                self.save_stage_data(4, second_order)
                
                with open(os.path.join(self.output_dir, "second_order_themes.json"), "w", encoding="utf-8") as f:
                    json.dump(second_order, f, indent=2)
                    
                metadata["stats"]["themes_count"] = len(second_order)
                self.save_metadata(metadata)
                print(f"[STAGE 4] Second Order Coding complete. {len(second_order)} themes created.")
                
            # Stage 5: Dimension Agent
            if start_stage <= 5:
                print(f"[STAGE 5] Running Dimension Agent...")
                metadata["current_stage"] = 5
                self.save_metadata(metadata)
                
                second_order = self.load_stage_data(4)
                dimensions = run_dimension_agent(second_order, self.research_question, detected_category)
                
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
                
                narrative = run_narrative_agent(first_order, second_order, dimensions, self.research_question, detected_category, stats_for_narrative)
                
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
    args = parser.parse_args()
    
    pipeline = GioiaPipeline(
        research_question=args.question,
        run_id=args.run_id
    )
    pipeline.run()

if __name__ == "__main__":
    main()
