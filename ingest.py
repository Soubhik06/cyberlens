import os
import re
import pandas as pd
import numpy as np
from tqdm import tqdm
import chromadb
from chromadb.utils import embedding_functions

# Path configuration
xlsx_path = "data/txt/all_data.xlsx"
if not os.path.exists(xlsx_path):
    xlsx_path = "data/all_data.xlsx"
    
txt_dir = "data/txt"
if not os.path.exists(txt_dir):
    txt_dir = "data/txts"

print(f"Excel path identified at: {xlsx_path}")
print(f"Text folder identified at: {txt_dir}")

# Initialize ChromaDB client and collection using path from .env
chroma_path = os.getenv("CHROMA_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db"))
client = chromadb.PersistentClient(path=chroma_path)
emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
collection = client.get_or_create_collection(
    name="cybercrime_india",
    embedding_function=emb_fn
)

# Load HuggingFace tokenizer from sentence-transformers for exact token counts
from transformers import AutoTokenizer
try:
    tokenizer = AutoTokenizer.from_pretrained("sentence-transformers/all-MiniLM-L6-v2", local_files_only=True)
    print("Successfully loaded sentence-transformers tokenizer.")
except Exception as e:
    print(f"Warning: could not load tokenizer, using fallback word splitter. Error: {e}")
    tokenizer = None

def split_text_into_chunks(text, max_tokens=800, overlap=100):
    if tokenizer is not None:
        try:
            tokens = tokenizer.encode(text, add_special_tokens=False)
            if len(tokens) <= max_tokens:
                return [text]
            chunks = []
            start = 0
            while start < len(tokens):
                end = min(start + max_tokens, len(tokens))
                chunk_tokens = tokens[start:end]
                chunk_text = tokenizer.decode(chunk_tokens, skip_special_tokens=True)
                chunks.append(chunk_text)
                start += (max_tokens - overlap)
            return chunks
        except Exception as e:
            print(f"Chunking with tokenizer failed, falling back to word count: {e}")
    
    # Fallback word-based chunker
    words = text.split()
    max_words = int(max_tokens / 1.3)
    overlap_words = int(overlap / 1.3)
    if len(words) <= max_words:
        return [text]
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + max_words, len(words))
        chunks.append(" ".join(words[start:end]))
        start += (max_words - overlap_words)
    return chunks

def extract_year(date_val):
    if pd.isna(date_val):
        return 0
    if isinstance(date_val, (int, float)):
        return int(date_val)
    if hasattr(date_val, 'year'):
        return int(date_val.year)
    s = str(date_val).strip()
    match = re.search(r'\b(20\d{2}|19\d{2})\b', s)
    if match:
        return int(match.group(1))
    for part in re.split(r'[-/]', s):
        if len(part) == 4 and part.isdigit():
            return int(part)
    return 0

def clean_metadata(meta_dict):
    cleaned = {}
    for k, v in meta_dict.items():
        if pd.isna(v):
            if k == "original_year":
                cleaned[k] = 0
            else:
                cleaned[k] = ""
        elif isinstance(v, (int, float)):
            cleaned[k] = v
        else:
            cleaned[k] = str(v)
    return cleaned

def ingest_data():
    if not os.path.exists(xlsx_path):
        print(f"Error: Excel file not found at {xlsx_path}")
        return

    # Delete existing collection to rebuild HNSW index from scratch
    print("Deleting old collection to rebuild HNSW index...")
    try:
        client.delete_collection("cybercrime_india")
        print("Successfully deleted old collection.")
    except Exception as e:
        print(f"No existing collection to delete: {e}")

    global collection
    collection = client.get_or_create_collection(
        name="cybercrime_india",
        embedding_function=emb_fn
    )

    # Read all sheets
    xl = pd.ExcelFile(xlsx_path)
    sheet_names = xl.sheet_names
    print(f"Found sheets in Excel: {sheet_names}")
    
    sheets_data = {}
    for s in sheet_names:
        sheets_data[s] = pd.read_excel(xl, sheet_name=s)
        # Clear ingestion_status in memory to force re-ingestion of all rows
        sheets_data[s]["ingestion_status"] = np.nan
            
    # Load all existing chunk IDs in ChromaDB for fast O(1) checks
    print("Loading existing indexed chunk IDs from ChromaDB...")
    try:
        existing_res = collection.get(include=[])
        existing_ids = set(existing_res["ids"])
        print(f"ChromaDB currently has {len(existing_ids)} chunk IDs.")
    except Exception as e:
        existing_ids = set()
        print(f"Could not load existing IDs (collection may be empty): {e}")

    # Accumulation buffers for batch inserts
    batch_ids = []
    batch_documents = []
    batch_metadatas = []
    batch_size = 500  # Insert 500 chunks at a time for optimal throughput
    
    total_embedded = 0
    total_skipped = 0
    total_failed = 0
    excel_updates = 0

    def flush_batch():
        nonlocal batch_ids, batch_documents, batch_metadatas
        if batch_ids:
            collection.add(
                ids=batch_ids,
                documents=batch_documents,
                metadatas=batch_metadatas
            )
            batch_ids.clear()
            batch_documents.clear()
            batch_metadatas.clear()

    # 1. Process Stream A: Scraped
    if "stream_a_scraped" in sheets_data:
        df = sheets_data["stream_a_scraped"]
        print("\nProcessing stream_a_scraped...")
        for idx, row in tqdm(df.iterrows(), total=len(df)):
            doc_id = row.get("Unique ID")
            if pd.isna(doc_id):
                continue
            doc_id = str(doc_id).strip()
            
            # Check if already indexed in database or Excel
            is_ingested_excel = str(row.get("ingestion_status")).strip().lower() == "ingested"
            is_indexed_db = f"{doc_id}_chunk_0" in existing_ids
            
            if is_ingested_excel or is_indexed_db:
                if is_indexed_db and not is_ingested_excel:
                    df.at[idx, "ingestion_status"] = "Ingested"
                    excel_updates += 1
                total_skipped += 1
                continue
                
            txt_filename = row.get("TXT File Name")
            if pd.isna(txt_filename):
                txt_filename = f"{doc_id}.txt"
            
            txt_path = os.path.join(txt_dir, str(txt_filename).strip())
            print(f"Looking for text file at: {txt_path}")
            
            if os.path.exists(txt_path):
                print(f"Found text file at: {txt_path}")
                with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                    text_content = f.read()
            else:
                print(f"Warning: Text file {txt_filename} not found for ID {doc_id}. Skipping.")
                total_failed += 1
                continue
                
            chunks = split_text_into_chunks(text_content)
            
            for i, chunk in enumerate(chunks):
                raw_meta = {
                    "doc_id": doc_id,
                    "stream": "A",
                    "source_platform": row.get("Source Platform"),
                    "original_date": row.get("Original Date"),
                    "original_year": extract_year(row.get("Original Date")),
                    "fraud_category": row.get("Fraud Category"),
                    "fraud_subcategory": row.get("Fraud Subcategory"),
                    "narrative_type": row.get("Narrative Type"),
                    "geographic_scope": "Unknown",
                    "title": row.get("Title/Headline"),
                    "chunk_index": i
                }
                batch_ids.append(f"{doc_id}_chunk_{i}")
                batch_documents.append(chunk)
                batch_metadatas.append(clean_metadata(raw_meta))
                
            df.at[idx, "ingestion_status"] = "Ingested"
            total_embedded += 1
            excel_updates += 1
            
            if len(batch_ids) >= batch_size:
                flush_batch()
                
    # 2. Process Stream A: ProQuest (if sheet exists)
    if "stream_a_proquest" in sheets_data:
        df = sheets_data["stream_a_proquest"]
        print("\nProcessing stream_a_proquest...")
        for idx, row in tqdm(df.iterrows(), total=len(df)):
            doc_id = row.get("Unique ID")
            if pd.isna(doc_id):
                continue
            doc_id = str(doc_id).strip()
            
            is_ingested_excel = str(row.get("ingestion_status")).strip().lower() == "ingested"
            is_indexed_db = f"{doc_id}_chunk_0" in existing_ids
            
            if is_ingested_excel or is_indexed_db:
                if is_indexed_db and not is_ingested_excel:
                    df.at[idx, "ingestion_status"] = "Ingested"
                    excel_updates += 1
                total_skipped += 1
                continue
                
            txt_filename = row.get("TXT File Name")
            if pd.isna(txt_filename):
                txt_filename = f"{doc_id}.txt"
                
            txt_path = os.path.join(txt_dir, str(txt_filename).strip())
            print(f"Looking for text file at: {txt_path}")
            
            if os.path.exists(txt_path):
                print(f"Found text file at: {txt_path}")
                with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                    text_content = f.read()
            else:
                print(f"Warning: Text file {txt_filename} not found for ID {doc_id}. Skipping.")
                total_failed += 1
                continue
                
            chunks = split_text_into_chunks(text_content)
            
            for i, chunk in enumerate(chunks):
                raw_meta = {
                    "doc_id": doc_id,
                    "stream": "A",
                    "source_platform": row.get("Source Platform"),
                    "original_date": row.get("Original Date"),
                    "original_year": extract_year(row.get("Original Date")),
                    "fraud_category": row.get("Fraud Category"),
                    "fraud_subcategory": row.get("Fraud Subcategory"),
                    "narrative_type": row.get("Narrative Type"),
                    "geographic_scope": "Unknown",
                    "title": row.get("Title/Headline"),
                    "chunk_index": i
                }
                batch_ids.append(f"{doc_id}_chunk_{i}")
                batch_documents.append(chunk)
                batch_metadatas.append(clean_metadata(raw_meta))
                
            df.at[idx, "ingestion_status"] = "Ingested"
            total_embedded += 1
            excel_updates += 1
            
            if len(batch_ids) >= batch_size:
                flush_batch()

    # 3. Process Stream B: Government reports
    if "stream_b_govt" in sheets_data:
        df = sheets_data["stream_b_govt"]
        print("\nProcessing stream_b_govt...")
        for idx, row in tqdm(df.iterrows(), total=len(df)):
            doc_id = f"NB-{idx+1:04d}"
            
            is_ingested_excel = str(row.get("ingestion_status")).strip().lower() == "ingested"
            is_indexed_db = f"{doc_id}_chunk_0" in existing_ids
            
            if is_ingested_excel or is_indexed_db:
                if is_indexed_db and not is_ingested_excel:
                    df.at[idx, "ingestion_status"] = "Ingested"
                    excel_updates += 1
                total_skipped += 1
                continue
                
            pdf_filename = row.get("Pdf File Name")
            txt_filename = None
            if pd.notna(pdf_filename):
                base = os.path.splitext(str(pdf_filename).strip())[0]
                txt_filename = base + ".txt"
            
            txt_path = os.path.join(txt_dir, txt_filename) if txt_filename else None
            
            if txt_path:
                print(f"Looking for text file at: {txt_path}")
                if os.path.exists(txt_path):
                    print(f"Found text file at: {txt_path}")
                    with open(txt_path, "r", encoding="utf-8", errors="ignore") as f:
                        text_content = f.read()
                else:
                    print(f"Text file NOT found at: {txt_path}. Constructing representation from Excel columns.")
                    parts = []
                    if pd.notna(row.get("Source Organisation")):
                        parts.append(f"Source Organisation: {row['Source Organisation']}")
                    if pd.notna(row.get("Report/Document Title")):
                        parts.append(f"Report/Document Title: {row['Report/Document Title']}")
                    if pd.notna(row.get("Report Year")):
                        parts.append(f"Report Year: {row['Report Year']}")
                    if pd.notna(row.get("Publication Date")):
                        parts.append(f"Publication Date: {row['Publication Date']}")
                    if pd.notna(row.get("Cybercrime Category")):
                        parts.append(f"Cybercrime Category: {row['Cybercrime Category']}")
                    if pd.notna(row.get("Geographic Scope")):
                        parts.append(f"Geographic Scope: {row['Geographic Scope']}")
                    if pd.notna(row.get("Key Data Points")):
                        parts.append(f"Key Data Points: {row['Key Data Points']}")
                    if pd.notna(row.get("Notes")):
                        parts.append(f"Notes: {row['Notes']}")
                    text_content = "\n".join(parts)
            else:
                print("No text file path specified for Stream B. Constructing representation from Excel columns.")
                parts = []
                if pd.notna(row.get("Source Organisation")):
                    parts.append(f"Source Organisation: {row['Source Organisation']}")
                if pd.notna(row.get("Report/Document Title")):
                    parts.append(f"Report/Document Title: {row['Report/Document Title']}")
                if pd.notna(row.get("Report Year")):
                    parts.append(f"Report Year: {row['Report Year']}")
                if pd.notna(row.get("Publication Date")):
                    parts.append(f"Publication Date: {row['Publication Date']}")
                if pd.notna(row.get("Cybercrime Category")):
                    parts.append(f"Cybercrime Category: {row['Cybercrime Category']}")
                if pd.notna(row.get("Geographic Scope")):
                    parts.append(f"Geographic Scope: {row['Geographic Scope']}")
                if pd.notna(row.get("Key Data Points")):
                    parts.append(f"Key Data Points: {row['Key Data Points']}")
                if pd.notna(row.get("Notes")):
                    parts.append(f"Notes: {row['Notes']}")
                text_content = "\n".join(parts)
                
            chunks = split_text_into_chunks(text_content)
            
            for i, chunk in enumerate(chunks):
                raw_meta = {
                    "doc_id": doc_id,
                    "stream": "B",
                    "source_platform": row.get("Source Organisation"),
                    "original_date": str(row.get("Publication Date")) if pd.notna(row.get("Publication Date")) else str(row.get("Report Year")),
                    "original_year": extract_year(row.get("Report Year")),
                    "fraud_category": row.get("Cybercrime Category"),
                    "fraud_subcategory": "",
                    "narrative_type": row.get("Data Type"),
                    "geographic_scope": row.get("Geographic Scope"),
                    "title": row.get("Report/Document Title"),
                    "chunk_index": i
                }
                batch_ids.append(f"{doc_id}_chunk_{i}")
                batch_documents.append(chunk)
                batch_metadatas.append(clean_metadata(raw_meta))
                
            df.at[idx, "ingestion_status"] = "Ingested"
            total_embedded += 1
            excel_updates += 1
            
            if len(batch_ids) >= batch_size:
                flush_batch()

    # Flush any remaining chunks in buffer
    flush_batch()

    # Save Excel sheets back to file if updates were made
    if excel_updates > 0:
        print("\nSaving ingestion status updates back to Excel...")
        with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
            for s, df_sheet in sheets_data.items():
                df_sheet.to_excel(writer, sheet_name=s, index=False)
            
    print("\n=== INGESTION SUMMARY ===")
    print(f"Total documents newly embedded: {total_embedded}")
    print(f"Total documents skipped (already indexed): {total_skipped}")
    print(f"Total documents failed (file not found): {total_failed}")
    try:
        col_count = collection.count()
        print(f"ChromaDB collection count: {col_count} chunks")
    except Exception as e:
        print(f"Could not retrieve ChromaDB collection count: {e}")
    print("Ingestion pipeline finished successfully!")

if __name__ == "__main__":
    ingest_data()
