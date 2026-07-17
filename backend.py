import os
import sys
import re
import json
import datetime
import pandas as pd
from typing import Optional, List
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from insights import excel_lock

app = FastAPI(title="CyberLens FastAPI Backend")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup validation check
@app.on_event("startup")
def startup_checks():
    print("="*60)
    print("[INFO] Starting CyberLens Backend Diagnostics...")
    
    # Check Excel readability
    xlsx_path = "data/txt/all_data.xlsx"
    if not os.path.exists(xlsx_path):
        xlsx_path = "data/all_data.xlsx"
        
    excel_ok = False
    try:
        xl = pd.ExcelFile(xlsx_path)
        df = pd.read_excel(xl, sheet_name="stream_a_scraped")
        excel_ok = True
        print(f"[OK] Excel Registry Path: {xlsx_path} (READ: OK, {len(df)} rows)")
    except Exception as e:
        print(f"[ERROR] Excel Registry Path: {xlsx_path} (ERROR: {e})")
        
    # Check ChromaDB connection
    chroma_ok = False
    try:
        from ingest import collection
        count = collection.count()
        chroma_ok = True
        print(f"[OK] ChromaDB Collection: {collection.name} ({count} Chunks Indexed) (CONN: OK)")
    except Exception as e:
        print(f"[ERROR] ChromaDB Collection Connection Error: {e}")
        
    if excel_ok and chroma_ok:
        print("[STATUS] HEALTH STATUS: Fully Operational")
    else:
        print("[STATUS] HEALTH STATUS: Degraded (Some components failed check)")
    print("="*60)

# Request / Response Schemas
class SubmissionRequest(BaseModel):
    name: Optional[str] = "Anonymous"
    incident_date: str  # YYYY-MM-DD or DD-MM-YYYY
    location: str
    fraud_category: str
    description: str
    amount_lost: Optional[float] = 0.0
    reported_to_authorities: str  # yes, no, partial
    additional_details: Optional[str] = ""

class ChatMessage(BaseModel):
    role: str  # user or assistant
    content: str

class ChatRequest(BaseModel):
    question: str
    history: Optional[List[ChatMessage]] = []

# --- API ENDPOINTS ---

@app.post("/api/submit")
def submit_experience(data: SubmissionRequest):
    try:
        # Check date format and convert if needed to DD-MM-YYYY
        parsed_date = data.incident_date
        try:
            dt = datetime.datetime.strptime(data.incident_date, "%Y-%m-%d")
            parsed_date = dt.strftime("%d-%m-%Y")
        except ValueError:
            # Already DD-MM-YYYY or in another format
            pass

        # Identify path
        xlsx_path = "data/txt/all_data.xlsx"
        if not os.path.exists(xlsx_path):
            xlsx_path = "data/all_data.xlsx"
            
        # 1. Assign Next ID
        with excel_lock:
            xl = pd.ExcelFile(xlsx_path)
            sheets_data = {s: pd.read_excel(xl, sheet_name=s) for s in xl.sheet_names}
            df_a_sheet = sheets_data["stream_a_scraped"]
            
            ids = df_a_sheet["Unique ID"].dropna().astype(str)
            numbers = []
            for x in ids:
                if x.startswith("NA-"):
                    parts = x.split("-")
                    if len(parts) > 1 and parts[1].isdigit():
                        numbers.append(int(parts[1]))
                        
            next_id_num = max(numbers) + 1 if numbers else 4501
            new_doc_id = f"NA-{next_id_num:04d}"
            
            # 2. Write structured TXT file
            txt_dir_path = "data/txt"
            if not os.path.exists(txt_dir_path):
                txt_dir_path = "data/txts"
            if not os.path.exists(txt_dir_path):
                os.makedirs(txt_dir_path)
                
            name_str = data.name.strip() if data.name and data.name.strip() else "Anonymous"
            location_str = data.location.strip() if data.location and data.location.strip() else "Not specified"
            amount_str = f"{data.amount_lost:.2f} INR" if data.amount_lost and data.amount_lost > 0 else "Not specified"
            reported_str = data.reported_to_authorities.strip() if data.reported_to_authorities else "no"
            details_str = data.additional_details.strip() if data.additional_details and data.additional_details.strip() else "None provided"
            
            txt_content = f"""SUBMISSION TYPE: User Submitted Experience
DOC ID: {new_doc_id}
SUBMITTED BY: {name_str}
DATE OF INCIDENT: {parsed_date}
LOCATION: {location_str}
FRAUD CATEGORY: {data.fraud_category}
AMOUNT LOST: {amount_str}
REPORTED TO AUTHORITIES: {reported_str}

--- EXPERIENCE ---

{data.description.strip()}

--- ADDITIONAL DETAILS ---

{details_str}"""
            
            new_file_path = os.path.join(txt_dir_path, f"{new_doc_id}.txt")
            with open(new_file_path, "w", encoding="utf-8") as f:
                f.write(txt_content)
                
            # 3. Add row to Excel
            today_str = datetime.date.today().strftime("%d-%m-%Y")
            new_row = {
                "Unique ID": new_doc_id,
                "Date of Collection": today_str,
                "Collector Name": "User Submission",
                "Source Platform": "User Submission",
                "Source Publication": None,
                "Original Date": parsed_date,
                "Title/Headline": f"User Submitted Experience - {new_doc_id}",
                "URL": None,
                "Search Query Used": None,
                "Fraud Category": data.fraud_category,
                "Fraud Subcategory": "Unknown",
                "Narrative Type": "VICTIM",
                "TXT File Name": f"{new_doc_id}.txt",
                "Notes": f"Submitted by: {name_str} | Loss: {amount_str} | Reported: {reported_str}",
                "ingestion_status": "Pending"
            }
            
            new_row_df = pd.DataFrame([new_row])
            df_a_sheet = pd.concat([df_a_sheet, new_row_df], ignore_index=True)
            sheets_data["stream_a_scraped"] = df_a_sheet
            
            with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                for s, df_sheet in sheets_data.items():
                    df_sheet.to_excel(writer, sheet_name=s, index=False)
                    
            # 4. Immediate ChromaDB Ingestion
            from ingest import split_text_into_chunks, clean_metadata, collection, extract_year
            chunks = split_text_into_chunks(txt_content)
            
            batch_ids = []
            batch_documents = []
            batch_metadatas = []
            
            for i, chunk in enumerate(chunks):
                raw_meta = {
                    "doc_id": new_doc_id,
                    "stream": "A",
                    "source_platform": "User Submission",
                    "original_date": parsed_date,
                    "original_year": extract_year(parsed_date),
                    "fraud_category": data.fraud_category,
                    "fraud_subcategory": "Unknown",
                    "narrative_type": "VICTIM",
                    "geographic_scope": "Unknown",
                    "title": f"User Submitted Experience - {new_doc_id}",
                    "chunk_index": i
                }
                batch_ids.append(f"{new_doc_id}_chunk_{i}")
                batch_documents.append(chunk)
                batch_metadatas.append(clean_metadata(raw_meta))
                
            if batch_ids:
                collection.add(
                    ids=batch_ids,
                    documents=batch_documents,
                    metadatas=batch_metadatas
                )
                
            # Update ingestion status in Excel to Ingested
            sheets_data["stream_a_scraped"].loc[sheets_data["stream_a_scraped"]["Unique ID"] == new_doc_id, "ingestion_status"] = "Ingested"
            with pd.ExcelWriter(xlsx_path, engine="openpyxl") as writer:
                for s, df_sheet in sheets_data.items():
                    df_sheet.to_excel(writer, sheet_name=s, index=False)
                    
            # Force streamlit cache reload if Streamlit is sharing cache in same process context
            # (Though they run in different processes, Excel writing is shared on disk)
            return {"status": "success", "doc_id": new_doc_id}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Submission failed: {e}")

@app.get("/api/stats")
def get_stats():
    try:
        from insights import load_data
        df_a, df_b = load_data()
        
        total_docs = len(df_a) + len(df_b)
        
        stream_breakdown = {
            "Stream A": len(df_a),
            "Stream B": len(df_b)
        }
        
        # Combine fraud categories and get top 5
        combined_cats = pd.concat([df_a["Fraud Category"], df_b["Cybercrime Category"]]).value_counts().head(5).to_dict()
        
        # Date range of dataset
        val_min_a = pd.to_numeric(df_a["parsed_year"], errors="coerce").min()
        val_min_b = pd.to_numeric(df_b["parsed_year"], errors="coerce").min()
        val_max_a = pd.to_numeric(df_a["parsed_year"], errors="coerce").max()
        val_max_b = pd.to_numeric(df_b["parsed_year"], errors="coerce").max()
        
        min_year = int(min(val_min_a, val_min_b)) if pd.notna(val_min_a) and pd.notna(val_min_b) else 2013
        max_year = int(max(val_max_a, val_max_b)) if pd.notna(val_max_a) and pd.notna(val_max_b) else 2026
        
        return {
            "total_document_count": total_docs,
            "stream_breakdown": stream_breakdown,
            "top_5_fraud_categories": combined_cats,
            "date_range": {
                "start_year": min_year,
                "end_year": max_year
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/search")
def run_search(q: str = Query(..., description="Semantic search query string")):
    try:
        from ingest import collection
        results = collection.query(
            query_texts=[q],
            n_results=5
        )
        
        formatted_results = []
        if results and results["ids"] and results["ids"][0]:
            for idx in range(len(results["ids"][0])):
                formatted_results.append({
                    "doc_id": results["metadatas"][0][idx].get("doc_id"),
                    "title": results["metadatas"][0][idx].get("title"),
                    "stream": results["metadatas"][0][idx].get("stream"),
                    "source_platform": results["metadatas"][0][idx].get("source_platform"),
                    "original_date": results["metadatas"][0][idx].get("original_date"),
                    "fraud_category": results["metadatas"][0][idx].get("fraud_category"),
                    "snippet": results["documents"][0][idx],
                    "distance": results["distances"][0][idx] if "distances" in results else None
                })
        return {"query": q, "results": formatted_results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/documents")
def get_documents(
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=50000, description="Documents per page"),
    stream: Optional[str] = Query(None, description="Filter by stream ('A' or 'B')"),
    fraud_category: Optional[str] = Query(None, description="Filter by fraud category"),
    narrative_type: Optional[str] = Query(None, description="Filter by narrative or data type")
):
    try:
        from insights import load_data
        df_a, df_b = load_data()
        
        df_all_docs = []
        for _, r in df_a.iterrows():
            df_all_docs.append({
                "doc_id": r.get("Unique ID"),
                "title": r.get("Title/Headline"),
                "source_platform": r.get("Source Platform"),
                "original_date": r.get("Original Date"),
                "fraud_category": r.get("Fraud Category"),
                "narrative_type": r.get("Narrative Type"),
                "stream": "A",
                "file_name": r.get("TXT File Name")
            })
        for idx, r in df_b.iterrows():
            df_all_docs.append({
                "doc_id": f"NB-{idx+1:04d}",
                "title": r.get("Report/Document Title"),
                "source_platform": r.get("Source Organisation"),
                "original_date": str(r.get("Publication Date")) if pd.notna(r.get("Publication Date")) else str(r.get("Report Year")),
                "fraud_category": r.get("Cybercrime Category"),
                "narrative_type": r.get("Data Type"),
                "stream": "B",
                "file_name": r.get("Pdf File Name")
            })
            
        df_explorer = pd.DataFrame(df_all_docs)
        
        # Apply filters
        if stream:
            df_explorer = df_explorer[df_explorer["stream"].astype(str).str.upper() == stream.upper()]
        if fraud_category:
            df_explorer = df_explorer[df_explorer["fraud_category"].astype(str).str.lower() == fraud_category.lower()]
        if narrative_type:
            df_explorer = df_explorer[df_explorer["narrative_type"].astype(str).str.lower() == narrative_type.lower()]
            
        total_items = len(df_explorer)
        total_pages = (total_items + page_size - 1) // page_size
        
        # Slice
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        sliced_df = df_explorer.iloc[start_idx:end_idx].fillna("")
        
        return {
            "total_items": total_items,
            "total_pages": total_pages,
            "page": page,
            "page_size": page_size,
            "documents": sliced_df.to_dict(orient="records")
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def query_excel_stats(question: str):
    import re
    from insights import load_data
    
    try:
        df_a, df_b = load_data()
    except Exception as e:
        print(f"Error loading Excel data in query_excel_stats: {e}")
        return "", []
        
    context_lines = []
    unique_sources = []
    seen_docs = set()
    
    # Extract years (2013-2026)
    years = [int(y) for y in re.findall(r'\b(20\d{2})\b', question)]
    
    # Extract keywords
    words = [w.lower() for w in re.findall(r'\b[a-zA-Z]{3,}\b', question)]
    stopwords = {"what", "were", "was", "the", "and", "for", "how", "many", "much", "lost", "loss", "total", "count", "number", "scam", "scams", "fraud", "frauds", "involving", "cases", "year", "scammed"}
    keywords = [w for w in words if w not in stopwords]
    
    # Search Stream B (Government)
    df_b_matches = []
    cases_col = "Total cases" if "Total cases" in df_b.columns else "Total cases "
    
    for idx, row in df_b.iterrows():
        score = 0
        row_year_val = row.get("parsed_year")
        try:
            row_year = int(row_year_val) if pd.notna(row_year_val) else None
        except:
            row_year = None
            
        row_org = str(row.get("Source Organisation", "")).lower()
        row_title = str(row.get("Report/Document Title", "")).lower()
        row_cat = str(row.get("Cybercrime Category", "")).lower()
        row_points = str(row.get("Key Data Points", "")).lower()
        row_notes = str(row.get("Notes", "")).lower()
        
        row_text = f"{row_org} {row_title} {row_cat} {row_points} {row_notes}"
        
        if row_year and row_year in years:
            score += 10
        elif any(str(y) in row_text for y in years):
            score += 5
            
        for kw in keywords:
            if kw in row_text:
                score += 2
                
        # If the question contains matching source org like "ncrb", "cert", "rbi"
        for org_name in ["ncrb", "cert", "rbi"]:
            if org_name in question.lower() and org_name in row_org:
                score += 5
                
        if score > 0:
            df_b_matches.append((score, row))
            
    df_b_matches.sort(key=lambda x: x[0], reverse=True)
    if df_b_matches:
        context_lines.append("=== Stream B (Government Statistics & Reports) Matches ===")
        for score, row in df_b_matches[:10]:
            doc_id = f"NB-{row.name+1:04d}" if hasattr(row, "name") else f"NB-{idx+1:04d}"
            context_lines.append(
                f"Document ID: {doc_id} | Source: {row.get('Source Organisation')} | Title: {row.get('Report/Document Title')} | "
                f"Year: {row.get('Report Year')} | Category: {row.get('Cybercrime Category')} | "
                f"Cases Count: {row.get(cases_col)} | Data Points: {row.get('Key Data Points')} | Notes: {row.get('Notes')}"
            )
            if doc_id not in seen_docs:
                seen_docs.add(doc_id)
                unique_sources.append({
                    "doc_id": doc_id,
                    "stream": "B",
                    "title": row.get("Report/Document Title") or f"Government Report - {doc_id}",
                    "source_platform": row.get("Source Organisation") or "Unknown",
                    "original_date": str(row.get("Publication Date")) if pd.notna(row.get("Publication Date")) else str(row.get("Report Year")),
                    "fraud_category": row.get("Cybercrime Category") or "Unknown"
                })
                
    # Search Stream A (Victim Narratives)
    df_a_matches = []
    for idx, row in df_a.iterrows():
        score = 0
        row_id = str(row.get("Unique ID", ""))
        row_title = str(row.get("Title/Headline", "")).lower()
        row_cat = str(row.get("Fraud Category", "")).lower()
        row_sub = str(row.get("Fraud Subcategory", "")).lower()
        row_notes = str(row.get("Notes", "")).lower()
        
        row_text = f"{row_id} {row_title} {row_cat} {row_sub} {row_notes}"
        
        row_year = row.get("parsed_year")
        try:
            row_year_int = int(row_year) if pd.notna(row_year) else None
        except (ValueError, TypeError):
            row_year_int = None
        if row_year_int and row_year_int in years:
            score += 5
            
        for kw in keywords:
            if kw in row_text:
                score += 2
                
        has_loss_in_q = any(w in question.lower() for w in ["lost", "loss", "amount", "rupees", "inr"])
        if has_loss_in_q and "loss:" in row_notes:
            score += 4
            
        if score > 2:
            df_a_matches.append((score, row))
            
    df_a_matches.sort(key=lambda x: x[0], reverse=True)
    if df_a_matches:
        if context_lines:
            context_lines.append("")
        context_lines.append("=== Stream A (Victim Narratives) Matches ===")
        for score, row in df_a_matches[:15]:
            doc_id = row.get("Unique ID")
            context_lines.append(
                f"Document ID: {doc_id} | Date: {row.get('Original Date')} | "
                f"Category: {row.get('Fraud Category')} | Subcategory: {row.get('Fraud Subcategory')} | "
                f"Title: {row.get('Title/Headline')} | Notes: {row.get('Notes')}"
            )
            if doc_id not in seen_docs:
                seen_docs.add(doc_id)
                unique_sources.append({
                    "doc_id": doc_id,
                    "stream": "A",
                    "title": row.get("Title/Headline") or f"Victim Narrative - {doc_id}",
                    "source_platform": row.get("Source Platform") or "Unknown",
                    "original_date": row.get("Original Date") or "Unknown",
                    "fraud_category": row.get("Fraud Category") or "Unknown"
                })
                
    return "\n".join(context_lines), unique_sources

@app.post("/api/chat")
def get_chat_response(data: ChatRequest):
    try:
        from ingest import collection
        from gemini_client import gemini
        
        # Check if query is statistical/numerical
        is_num = any(w in data.question.lower() for w in [
            "lost", "loss", "amount", "rupees", "inr", "cases", "arrests", 
            "total", "count", "number", "statistics", "statistical", 
            "figure", "figures", "metric", "metrics", "data points", 
            "ncrb", "cert-in", "cert", "rbi", "report year"
        ])
        
        context_str = ""
        unique_sources = []
        
        if is_num:
            context_str, unique_sources = query_excel_stats(data.question)
            
        # Fallback to ChromaDB RAG if context is empty
        if not context_str:
            results = collection.query(
                query_texts=[data.question],
                n_results=8
            )
            seen_docs = set()
            if results and results["documents"] and results["documents"][0]:
                documents = results["documents"][0]
                metadatas = results["metadatas"][0]
                for doc, meta in zip(documents, metadatas):
                    doc_id = meta.get("doc_id")
                    if doc_id not in seen_docs:
                        seen_docs.add(doc_id)
                        unique_sources.append(meta)
                    
                    stream_label = "Stream A" if meta.get("stream") == "A" else "Stream B"
                    context_str += f"--- Context Source ---\nDocument ID: {doc_id}\nStream: {stream_label}\nTitle: {meta.get('title')}\nContent Chunk:\n{doc}\n\n"
                
        # Build chat history string
        history_str = ""
        if data.history:
            for msg in data.history:
                role_label = "Researcher" if msg.role == "user" else "Assistant Researcher"
                history_str += f"{role_label}: {msg.content}\n"
                
        from rag import SYSTEM_PROMPT
        
        prompt = f"""
        System Prompt:
        {SYSTEM_PROMPT}
        
        Strict Grounding Rule:
        - You must strictly answer the question using ONLY the provided Retrieved Context Documents.
        - If the answer is not in the provided context (Excel matches or ChromaDB snippets), respond exactly with: "I cannot find this in the CyberLens dataset."
        - Do not use any external knowledge or make assumptions.
        
        Guidelines:
        1. Answer the current question objectively using the provided evidence context.
        2. Speak confidently. Avoid disclaimers.
        3. Cite sources by doc_id when stating facts.
        
        Conversation History:
        {history_str}
        
        Retrieved Context Documents:
        {context_str if context_str.strip() else "No matching documents found in the dataset."}
        
        Current Question: {data.question}
        
        Response:
        """
        
        response_text = gemini.generate(prompt)
        
        # Clean unique_sources NaNs for JSON serialization
        cleaned_sources = []
        for src in unique_sources:
            clean_src = {}
            for k, v in src.items():
                if pd.isna(v):
                    clean_src[k] = ""
                else:
                    clean_src[k] = v
            cleaned_sources.append(clean_src)
            
        return {
            "answer": response_text.strip(),
            "sources": cleaned_sources
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- INSIGHTS CHATBOT ENDPOINT ---

class InsightChatRequest(BaseModel):
    question: str

@app.post("/api/insights/chat")
def insights_chat(data: InsightChatRequest):
    """
    Natural-language Q&A about the cybercrime dataset.
    Returns { answer: str, chart: dict (Plotly JSON), chart_title: str }.
    """
    try:
        from insights import answer_insight_question
        result = answer_insight_question(data.question)
        return {
            "answer": result.get("answer", ""),
            "chart": result.get("chart"),
            "chart_title": result.get("chart_title", "")
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --- GIOIA METHODS & ENDPOINTS ---

import threading
from gioia_pipeline import GioiaPipeline, generate_run_id

class GioiaRunRequest(BaseModel):
    research_question: str
    fraud_category: Optional[str] = None
    max_records: Optional[int] = 400

active_runs = {}

@app.post("/api/gioia/run")
def run_gioia_pipeline(data: GioiaRunRequest):
    try:
        run_id = generate_run_id(data.research_question)
        pipeline = GioiaPipeline(
            research_question=data.research_question,
            fraud_category=data.fraud_category,
            run_id=run_id,
            max_records=data.max_records or 400
        )
        
        # Save initial metadata
        initial_meta = pipeline.load_metadata()
        pipeline.save_metadata(initial_meta)
        
        def thread_target():
            try:
                pipeline.run(start_stage=1)
            except Exception as e:
                print(f"Background thread failed for run {run_id}: {e}")
            finally:
                active_runs.pop(run_id, None)
                
        thread = threading.Thread(target=thread_target)
        active_runs[run_id] = thread
        thread.start()
        
        return {"status": "success", "run_id": run_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Pipeline initialization failed: {e}")

@app.get("/api/gioia/status/{run_id}")
def get_gioia_status(run_id: str):
    output_dir = os.path.join("gioia_outputs", run_id)
    metadata_path = os.path.join(output_dir, "metadata.json")
    
    if not os.path.exists(metadata_path):
        raise HTTPException(status_code=404, detail="Run not found.")
        
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {e}")
        
    # Sync status if thread died due to server restart
    if metadata.get("status") == "running" and run_id not in active_runs:
        metadata["status"] = "failed"
        metadata["error"] = "Pipeline execution was interrupted (e.g. server restart)."
        metadata["updated_at"] = datetime.datetime.now().isoformat()
        try:
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception:
            pass
            
    stage_names = {
        1: "Intake Agent — collecting chunks",
        2: "Extraction Agent — finding relevant passages",
        3: "First Order Coding — labelling excerpts",
        4: "Second Order Coding — grouping into themes",
        5: "Dimension Agent — building theory",
        6: "Narrative Agent — writing findings"
    }
    
    stage_num = metadata.get("current_stage", 1)
    stage_name = stage_names.get(stage_num, "Unknown Stage")
    
    return {
        "run_id": run_id,
        "current_stage": stage_num,
        "stage_name": stage_name,
        "status": metadata.get("status", "running"),
        "error": metadata.get("error"),
        "stats": metadata.get("stats", {}),
        "updated_at": metadata.get("updated_at")
    }

@app.get("/api/gioia/results/{run_id}")
def get_gioia_results(run_id: str):
    output_dir = os.path.join("gioia_outputs", run_id)
    metadata_path = os.path.join(output_dir, "metadata.json")
    
    if not os.path.exists(metadata_path):
        raise HTTPException(status_code=404, detail="Run not found.")
        
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {e}")
        
    if metadata.get("status") == "running" and run_id not in active_runs:
        metadata["status"] = "failed"
        metadata["error"] = "Pipeline execution was interrupted (e.g. server restart)."
        metadata["updated_at"] = datetime.datetime.now().isoformat()
        try:
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception:
            pass
            
    if metadata.get("status") == "running":
        raise HTTPException(status_code=400, detail="Pipeline is still running.")
        
    pipeline = GioiaPipeline(
        research_question=metadata.get("research_question", ""),
        fraud_category=metadata.get("fraud_category"),
        run_id=run_id
    )
    
    return pipeline.get_all_results()

@app.get("/api/gioia/checkpoints")
def get_gioia_checkpoints():
    gioia_dir = "gioia_outputs"
    if not os.path.exists(gioia_dir):
        return []
        
    runs = []
    try:
        for run_id in os.listdir(gioia_dir):
            run_path = os.path.join(gioia_dir, run_id)
            if not os.path.isdir(run_path):
                continue
                
            metadata_path = os.path.join(run_path, "metadata.json")
            if os.path.exists(metadata_path):
                try:
                    with open(metadata_path, "r", encoding="utf-8") as f:
                        meta = json.load(f)
                        
                    if meta.get("status") == "running" and run_id not in active_runs:
                        meta["status"] = "failed"
                        meta["error"] = "Pipeline execution was interrupted (e.g. server restart)."
                        meta["updated_at"] = datetime.datetime.now().isoformat()
                        with open(metadata_path, "w", encoding="utf-8") as f_out:
                            json.dump(meta, f_out, indent=2)
                            
                    runs.append({
                        "run_id": run_id,
                        "research_question": meta.get("research_question"),
                        "fraud_category": meta.get("fraud_category"),
                        "status": meta.get("status"),
                        "current_stage": meta.get("current_stage"),
                        "updated_at": meta.get("updated_at"),
                        "stats": meta.get("stats", {})
                    })
                except Exception:
                    pass
        runs.sort(key=lambda r: r.get("run_id", ""), reverse=True)
        return runs
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/gioia/resume/{run_id}/{stage_number}")
def resume_gioia_pipeline(run_id: str, stage_number: int):
    output_dir = os.path.join("gioia_outputs", run_id)
    metadata_path = os.path.join(output_dir, "metadata.json")
    
    if not os.path.exists(metadata_path):
        raise HTTPException(status_code=404, detail="Run not found.")
        
    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            metadata = json.load(f)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to read metadata: {e}")
        
    if stage_number < 1 or stage_number > 6:
        raise HTTPException(status_code=400, detail="Invalid stage number. Must be between 1 and 6.")
        
    if stage_number > 1:
        prev_filename = f"stage{stage_number-1}_data.json"
        prev_filepath = os.path.join(output_dir, prev_filename)
        if stage_number == 4:
            alt_filepath = os.path.join(output_dir, "first_order_codes.json")
            if not os.path.exists(prev_filepath) and not os.path.exists(alt_filepath):
                raise HTTPException(status_code=400, detail=f"Missing checkpoint data for previous stage: {prev_filename} or first_order_codes.json")
        else:
            if not os.path.exists(prev_filepath):
                raise HTTPException(status_code=400, detail=f"Missing checkpoint data for previous stage: {prev_filename}")
            
    if run_id in active_runs:
        raise HTTPException(status_code=400, detail="Pipeline run is already active.")
        
    # Clear any previous cancellation flag on resume
    cancelled_file = os.path.join(output_dir, "cancelled")
    if os.path.exists(cancelled_file):
        try:
            os.remove(cancelled_file)
        except Exception:
            pass
            
    pipeline = GioiaPipeline(
        research_question=metadata.get("research_question", ""),
        fraud_category=metadata.get("fraud_category"),
        run_id=run_id,
        max_records=int(metadata.get("max_records", 400))
    )
    
    metadata["status"] = "running"
    metadata["error"] = None
    metadata["current_stage"] = stage_number
    metadata["updated_at"] = datetime.datetime.now().isoformat()
    pipeline.save_metadata(metadata)
    
    def thread_target():
        try:
            pipeline.run(start_stage=stage_number)
        except Exception as e:
            print(f"Background resume thread failed for run {run_id}: {e}")
        finally:
            active_runs.pop(run_id, None)
            
    thread = threading.Thread(target=thread_target)
    active_runs[run_id] = thread
    thread.start()
    
    return {"status": "success", "run_id": run_id}

@app.post("/api/gioia/stop/{run_id}")
def stop_gioia_pipeline(run_id: str):
    output_dir = os.path.join("gioia_outputs", run_id)
    if not os.path.exists(output_dir):
        raise HTTPException(status_code=404, detail="Run directory not found.")
        
    # Write cancellation flag file
    cancelled_file = os.path.join(output_dir, "cancelled")
    try:
        with open(cancelled_file, "w", encoding="utf-8") as f:
            f.write("cancelled")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to create cancellation flag: {e}")
        
    # Update run metadata immediately to show failed status
    metadata_path = os.path.join(output_dir, "metadata.json")
    if os.path.exists(metadata_path):
        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            metadata["status"] = "failed"
            metadata["error"] = "Pipeline stopped by user"
            metadata["updated_at"] = datetime.datetime.now().isoformat()
            with open(metadata_path, "w", encoding="utf-8") as f:
                json.dump(metadata, f, indent=2)
        except Exception:
            pass
            
    # Clean up from active runs list
    active_runs.pop(run_id, None)
    
    return {"status": "success", "detail": "Stop signal sent to pipeline."}

@app.get("/api/gioia/chunks/{run_id}")
def get_gioia_chunks(run_id: str):
    output_dir = os.path.join("gioia_outputs", run_id)
    stage1_file = os.path.join(output_dir, "stage1_data.json")
    if not os.path.exists(stage1_file):
        raise HTTPException(status_code=404, detail="Intake chunks not found. Stage 1 must complete first.")
    try:
        with open(stage1_file, "r", encoding="utf-8") as f:
            chunks = json.load(f)
        return chunks
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# --- GIOIA QUERY AGENT Q&A ENDPOINT ---

class GioiaQueryRequest(BaseModel):
    run_id: str
    question: str

def retrieve_relevant_codes(question, first_order_codes):
    """
    Selects the most relevant first-order codes for the given question.
    Uses simple token matching / overlap as a fallback, and LLM classification for precision.
    """
    unique_codes = []
    seen = set()
    for item in first_order_codes:
        c = item.get("code")
        if c and c not in seen:
            seen.add(c)
            unique_codes.append(item)
            
    if len(unique_codes) <= 5:
        return unique_codes
        
    # Prepare list for LLM selection
    codes_str = "\n".join([f"{idx}: {item['code']}" for idx, item in enumerate(unique_codes)])
    
    prompt = (
        "You are a qualitative research assistant. A researcher has asked this question:\n"
        f"\"{question}\"\n\n"
        "Here is a list of first-order codes generated during qualitative analysis of UPI fraud:\n"
        f"{codes_str}\n\n"
        "Identify the top 5 codes that are most relevant to answering the researcher's question. "
        "Respond with ONLY a JSON list of the indices of the selected codes, like this: [2, 5, 8, 12, 14]. "
        "No other text, no markdown block."
    )
    
    try:
        from gemini_client import gemini
        res_text = gemini.generate(prompt)
        import re
        import json
        match = re.search(r'\[[\d,\s]*\]', res_text)
        if match:
            indices = json.loads(match.group(0))
            selected = []
            for idx in indices:
                if 0 <= idx < len(unique_codes):
                    selected.append(unique_codes[idx])
            return selected[:5]
    except Exception as e:
        print(f"Error selecting codes via LLM: {e}")
        
    question_tokens = set(question.lower().split())
    scored = []
    for item in unique_codes:
        code_tokens = set(item["code"].lower().split())
        overlap = len(question_tokens.intersection(code_tokens))
        scored.append((overlap, item))
    scored.sort(key=lambda x: x[0], reverse=True)
    return [item for _, item in scored[:5]]

def map_codes_to_framework(selected_codes, output_dir):
    themes_path = os.path.join(output_dir, "second_order_themes.json")
    themes_data = []
    if os.path.exists(themes_path):
        with open(themes_path, "r", encoding="utf-8") as f:
            themes_data = json.load(f)
            
    dims_path = os.path.join(output_dir, "aggregate_dimensions.json")
    dims_data = {}
    if os.path.exists(dims_path):
        with open(dims_path, "r", encoding="utf-8") as f:
            dims_data = json.load(f)
            
    code_to_theme = {}
    for theme in themes_data:
        theme_name = theme.get("theme_name", "")
        theme_desc = theme.get("description", "")
        for c_item in theme.get("codes", []):
            code_str = c_item.get("code", "")
            code_to_theme[code_str] = {
                "theme_name": theme_name,
                "description": theme_desc
            }
            
    theme_to_dim = {}
    for dim in dims_data.get("aggregate_dimensions", []):
        dim_name = dim.get("dimension_name", "")
        concept = dim.get("theoretical_concept", "")
        implication = dim.get("theoretical_implication", "")
        for t_name in dim.get("themes_included", []):
            theme_to_dim[t_name] = {
                "dimension_name": dim_name,
                "theoretical_concept": concept,
                "theoretical_implication": implication
            }
            
    retrieved_codes = []
    mapped_themes = {}
    mapped_dims = {}
    
    for code_item in selected_codes:
        code_str = code_item["code"]
        theme_info = code_to_theme.get(code_str, {"theme_name": "Uncategorized", "description": "Miscellaneous qualitative codes."})
        theme_name = theme_info["theme_name"]
        
        dim_info = theme_to_dim.get(theme_name, {"dimension_name": "Uncategorized", "theoretical_concept": "General qualitative category", "theoretical_implication": "N/A"})
        dim_name = dim_info["dimension_name"]
        
        retrieved_codes.append({
            "code": code_str,
            "quote": code_item.get("key_quote", ""),
            "source": code_item.get("chunk_id", code_item.get("source", "Unknown")),
            "date": code_item.get("date", "Unknown"),
            "theme": theme_name,
            "dimension": dim_name
        })
        
        if theme_name != "Uncategorized" and theme_name not in mapped_themes:
            mapped_themes[theme_name] = theme_info["description"]
            
        if dim_name != "Uncategorized" and dim_name not in mapped_dims:
            mapped_dims[dim_name] = dim_info
            
    return retrieved_codes, list(mapped_themes.items()), list(mapped_dims.values())

def synthesize_gioia_answer(question, retrieved_codes, mapped_themes, mapped_dims):
    codes_ctx = ""
    for idx, c in enumerate(retrieved_codes, 1):
        codes_ctx += f"{idx}. Code: \"{c['code']}\"\n   Illustrative Quote: \"{c['quote']}\" (Source: {c['source']}, Date: {c['date']})\n"
        
    themes_ctx = ""
    for t_name, t_desc in mapped_themes:
        themes_ctx += f"- Theme: {t_name}\n  Description: {t_desc}\n"
        
    dims_ctx = ""
    for d in mapped_dims:
        dims_ctx += f"- Dimension: {d['dimension_name']}\n  Theoretical Concept: {d['theoretical_concept']}\n  Implication: {d['theoretical_implication']}\n"
        
    prompt = (
        "You are the Gioia Qualitative Research Agent specializing in UPI fraud in India. "
        "You have conducted an academic qualitative study and developed a Gioia methodology framework. "
        "A researcher has asked this question:\n"
        f"\"{question}\"\n\n"
        "Here are the specific qualitative codes, themes, and dimensions that were retrieved from your analysis as relevant to this question:\n\n"
        "=== RELEVANT FIRST-ORDER CODES & INFORMANT QUOTES ===\n"
        f"{codes_ctx}\n"
        "=== RELEVANT SECOND-ORDER THEMES ===\n"
        f"{themes_ctx}\n"
        "=== RELEVANT AGGREGATE DIMENSIONS ===\n"
        f"{dims_ctx}\n"
        "Synthesize a clear, scholarly response to the researcher's question based strictly on this qualitative coding structure. "
        "Integrate the retrieved themes and dimensions into your analysis, and explicitly cite the informant quotes (e.g., using the source and date provided) to support your points. "
        "Do not invent details outside the provided qualitative context. Write in a rigorous, academic tone suitable for a top-tier information systems journal.\n\n"
        "Agent Answer:"
    )
    
    from gemini_client import gemini
    return gemini.generate(prompt)

@app.post("/api/gioia/query")
def query_gioia_endpoint(data: GioiaQueryRequest):
    run_id = data.run_id
    question = data.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="No question provided")
        
    output_dir = os.path.join("gioia_outputs", run_id)
    required_files = {
        "first_order": os.path.join(output_dir, "first_order_codes.json"),
        "second_order": os.path.join(output_dir, "second_order_themes.json"),
        "aggregate": os.path.join(output_dir, "aggregate_dimensions.json")
    }
    
    if not all(os.path.exists(f) for f in required_files.values()):
        raise HTTPException(status_code=400, detail="Pipeline analysis results are not available for this run. Please run or finish the pipeline first.")
        
    try:
        with open(required_files["first_order"], "r", encoding="utf-8") as f:
            first_order_codes = json.load(f)
            
        if not first_order_codes:
            raise HTTPException(status_code=400, detail="No qualitative codes found in this run.")
            
        selected_codes = retrieve_relevant_codes(question, first_order_codes)
        retrieved_codes, mapped_themes, mapped_dims = map_codes_to_framework(selected_codes, output_dir)
        answer = synthesize_gioia_answer(question, retrieved_codes, mapped_themes, mapped_dims)
        
        workflow = {
            "retrieved_codes": retrieved_codes,
            "mapped_themes": [{"name": name, "description": desc} for name, desc in mapped_themes],
            "mapped_dimensions": mapped_dims
        }
        
        return {"success": True, "answer": answer, "workflow": workflow}
    except Exception as e:
        import traceback
        print(f"Error querying Gioia agent: {e}")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# --- SERVE REACT FRONTEND STATIC FILES ---
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse

frontend_dist = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frontend", "dist")
assets_path = os.path.join(frontend_dist, "assets")

if os.path.exists(assets_path):
    app.mount("/assets", StaticFiles(directory=assets_path), name="assets")

# Serve text files dynamically for the React frontend document explorer
txt_dir_path = "data/txt"
if not os.path.exists(txt_dir_path):
    txt_dir_path = "data/txts"

if os.path.exists(txt_dir_path):
    app.mount("/txt", StaticFiles(directory=txt_dir_path), name="txt")

@app.get("/{catchall:path}", response_class=HTMLResponse)
def serve_react_app(catchall: str):
    if catchall.startswith("api/"):
        raise HTTPException(status_code=404, detail="API route not found")
        
    index_file = os.path.join(frontend_dist, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(
        content="<h3>Vite+React Frontend build not found!</h3><p>Please run <code>npm run build</code> inside the <code>frontend/</code> directory first.</p>",
        status_code=404
    )

if __name__ == "__main__":
    import uvicorn
    # Read the dynamic port assigned by Railway, default to 8000 if not found
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("backend:app", host="0.0.0.0", port=port)

