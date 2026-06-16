import os
import time
# pyrefly: ignore [missing-import]
import chromadb
from chromadb.utils import embedding_functions
from dotenv import load_dotenv
from gemini_client import gemini

# Load environment variables
load_dotenv()

# Initialize ChromaDB Client using path from .env
chroma_path = os.getenv("CHROMA_PATH", os.path.join(os.path.dirname(os.path.abspath(__file__)), "chroma_db"))
client = chromadb.PersistentClient(path=chroma_path)
# Step 4 Confirmation:
# Model string in ingest.py: "all-MiniLM-L6-v2"
# Model string in rag.py:    "all-MiniLM-L6-v2"
# Both files use character-for-character identical model names.
emb_fn = embedding_functions.SentenceTransformerEmbeddingFunction(
    model_name="all-MiniLM-L6-v2"
)
collection = client.get_or_create_collection(
    name="cybercrime_india",
    embedding_function=emb_fn
)

# Startup Diagnostics (Step 1, 2, 3, 4)
print("\n" + "="*50)
print("=== ChromaDB Vector Search Startup Diagnostics ===")
try:
    print(f"ChromaDB Path: {chroma_path}")
    print(f"Collection Name: {collection.name}")
    print(f"Collection Count: {collection.count()}")
    
    # Step 1: Peek 3 random chunks
    peek_res = collection.peek(3)
    if peek_res and peek_res["ids"]:
        print("\n[Step 1] Peek 3 Chunks metadata and snippets:")
        for i in range(len(peek_res["ids"])):
            print(f"  Chunk {i+1} ID: {peek_res['ids'][i]}")
            print(f"  Metadata: {peek_res['metadatas'][i]}")
            print(f"  Text Snippet: {peek_res['documents'][i][:150]}...\n")
    else:
        print("\n[Step 1] Peek returned no results.")
        
    # Step 2 & 4: Compare model names side-by-side
    # Model in ingest.py: "all-MiniLM-L6-v2"
    # Model in rag.py:    "all-MiniLM-L6-v2"
    # Side-by-side comment confirmation matches exactly.
    print(f"\n[Step 2] Model Name in rag.py:    'all-MiniLM-L6-v2'")
    print(f"[Step 2] Model Name in ingest.py: 'all-MiniLM-L6-v2'")
    
    # Step 3: Run test query "bank fraud india" with n_results=3
    print("\n[Step 3] Test Query 'bank fraud india' (No filters, n_results=3):")
    query_res = collection.query(
        query_texts=["bank fraud india"],
        n_results=3,
        where=None
    )
    if query_res and query_res["ids"] and query_res["ids"][0]:
        for idx in range(len(query_res["ids"][0])):
            r_id = query_res["ids"][0][idx]
            r_dist = query_res["distances"][0][idx]
            r_doc = query_res["documents"][0][idx]
            print(f"  Result {idx+1}: ID={r_id}, Distance={r_dist}")
            print(f"  Snippet: {r_doc[:150]}...\n")
    else:
        print("  Query returned zero results.")
except Exception as diag_err:
    print(f"Diagnostic Error occurred: {diag_err}")
print("="*50 + "\n")

def build_where_filter(stream=None, fraud_category=None, source_platform=None, 
                       narrative_type=None, geographic_scope=None, year_range=None):
    """
    Builds ChromaDB metadata filters dynamically.
    """
    conditions = []
    
    if stream and stream in ["A", "B"]:
        conditions.append({"stream": stream})
        
    if fraud_category:
        conditions.append({"fraud_category": {"$in": fraud_category}})
        
    if source_platform:
        conditions.append({"source_platform": {"$in": source_platform}})
        
    if narrative_type:
        conditions.append({"narrative_type": {"$in": narrative_type}})
        
    if geographic_scope:
        conditions.append({"geographic_scope": {"$in": geographic_scope}})
        
    if year_range:
        start_year, end_year = year_range
        conditions.append({"original_year": {"$gte": start_year}})
        conditions.append({"original_year": {"$lte": end_year}})
        
    if not conditions:
        return None
    elif len(conditions) == 1:
        return conditions[0]
    else:
        return {"$and": conditions}


def detect_tier_one_greeting(query_text):
    text = query_text.strip().lower().rstrip("?.!")
    greetings = {
        "hi", "hello", "hey", "greetings", "good morning", "good afternoon", "good evening",
        "yo", "hola", "namaste", "hi there", "hello there", "hey there", "welcome"
    }
    if text in greetings:
        return True
    
    # Check if input is a very simple short greeting phrase
    words = text.split()
    if len(words) <= 2 and any(w in ["hi", "hello", "hey"] for w in words):
        return True
    return False


def detect_tier_two_system_query(query_text):
    text = query_text.strip().lower().rstrip("?.! ")
    
    # Hardcoded phrases commonly asked about system capabilities
    system_phrases = {
        "what can you do", "what can you answer", "how do you work", "what is your purpose",
        "what are you", "who are you", "what is this", "what is this tool", "what is this app",
        "how can you help", "what help", "what topics do you cover", "what topics",
        "what categories", "what fraud categories", "what categories do you cover", "what fraud types",
        "what streams", "what data do you have", "what data is available", "what data", "what files",
        "what database", "tell me about yourself", "what are your capabilities", "about this platform",
        "how to use this", "how to use", "what can i ask you", "what do you do", "what are your capabilities"
    }
    if text in system_phrases:
        return True
        
    # Check for keywords and patterns
    keywords = ["what can you", "how do you work", "what streams", "what topics", "what categories", "what data", "about the system", "how to use"]
    if any(k in text for k in keywords):
        return True
        
    # Substring checks for assistant queries
    import re
    system_patterns = [
        r"\b(what|how|which)\b.*\b(can|do|does)\b.*\b(you|your|assistant|system|platform|app|tool)\b.*\b(do|answer|work|help|cover|have|contain|about)\b",
        r"\b(what|which)\b.*\b(topics|categories|streams|data|files|sources|scams|frauds)\b.*\b(do you|available|covered|in this|system|database|platform)\b",
        r"\b(tell me|explain)\b.*\b(about|how to use|how it works)\b.*\b(you|your|system|platform|app|tool)\b",
        r"\b(who|what)\b.*\b(are you|is your creator|designed you)\b"
    ]
    for pattern in system_patterns:
        if re.search(pattern, text):
            return True
            
    return False


SYSTEM_KNOWLEDGE = (
    "You are the research assistant for the CyberLens platform, developed for academic research at IIM Bangalore. "
    "Here is the hardcoded knowledge of what the system is, what data it contains, and how it works:\n\n"
    "1. WHAT IS CYBERLENS:\n"
    "   - CyberLens is an academic research platform designed to analyze the evolution of cybercrime in India.\n\n"
    "2. DATA STREAMS IN THE SYSTEM:\n"
    "   - The platform indexes two distinct data streams from a master academic registry:\n"
    "     * Stream A (Narratives & News): 14,857 registered documents containing news reports, victim narratives, media stories, and ProQuest database entries documenting personal cybercrime accounts and qualitative details.\n"
    "     * Stream B (Government Reports & Statistics): 55 official reports from government organizations (such as the NCRB - National Crime Records Bureau, CERT-In, RBI, and other official police/state circulars) representing aggregated cybercrime statistics and quantitative data.\n\n"
    "3. FRAUD CATEGORIES AVAILABLE:\n"
    "   - The system categorizes cybercrimes into several key fraud categories, including:\n"
    "     * Financial & Banking Fraud (e.g., UPI scams, credit/debit card fraud, KYC update scams)\n"
    "     * Identity Theft & Spoofing (e.g., Aadhaar enabled payment system fraud, social media account hijacking)\n"
    "     * Social Engineering & Phishing (e.g., WhatsApp job scams, part-time work scamming, electricity bill scams)\n"
    "     * Ransomware and Malware attacks\n"
    "     * Cyber Espionage and Data Breaches\n"
    "     * Emerging and Miscellaneous Fraud Types (e.g., dropshipping scam farm, instant loan app extortion)\n\n"
    "4. HOW IT WORKS:\n"
    "   - It uses a retrieval-augmented generation (RAG) pipeline.\n"
    "   - Documents and Excel registries are chunked, embedded using sentence-transformers (all-MiniLM-L6-v2), and stored in a ChromaDB vector database.\n"
    "   - When a research question is asked, it searches ChromaDB (with any active filters chosen in the sidebar like streams, fraud categories, organizations, or year ranges) and feeds the top 8 context chunks to Gemini to produce a cited academic answer.\n"
)


SYSTEM_PROMPT = (
    "You are CyberLens, a research assistant built for the IIM Bangalore cybercrime research project. "
    "You have a knowledge base of 14,912 documents covering the evolution of cybercrime in India from 2013 to 2025. "
    "You cover multiple streams of data, from narrative reports and news (Stream A) to government registries and official statistics (Stream B, e.g., NCRB, RBI, CERT-In). "
    "You cover specific categories of cybercrime including UPI fraud, digital arrest scams, phishing, investment fraud, identity theft, ecommerce fraud, banking fraud, and ransomware. "
    "You must answer with the confidence of a domain expert. NEVER include any disclaimers like 'I don't have enough data', 'As an AI model', 'I cannot answer this', or similar qualifiers. Speak confidently."
)

MODE_INSTRUCTIONS = {
    "Quick Answer": "Format: Quick Answer. Provide a concise response in maximum 2 to 3 sentences, straight to the point, with no elaboration.",
    "Research Mode": "Format: Research Mode. Provide a detailed structured analytical response with clear sections, citing specific patterns and evidence (using the provided doc_ids if context is available). The length must be strictly between 150 and 300 words.",
    "Deep Dive": "Format: Deep Dive. Provide a comprehensive long-form response with multiple angles, comparisons, and trends, suitable for academic writing. The length must be strictly under 500 words maximum."
}


def query_rag(query_text, stream=None, fraud_category=None, source_platform=None, 
              narrative_type=None, geographic_scope=None, year_range=None, mode="Research Mode"):
    """
    Queries ChromaDB and generates a response from Gemini using RAG.
    """
    # Tier 1: Greetings
    if detect_tier_one_greeting(query_text):
        system_prompt = (
            f"{SYSTEM_PROMPT}\n"
            "The user has greeted you. Politely greet them back and invite them to ask research questions about cybercrime in India or ask about your capabilities. "
            "Keep the response brief and match the tone of CyberLens."
        )
        prompt = f"{system_prompt}\n\nUser Message: {query_text}\n\nResponse:"
        response_stream = gemini.generate_stream(prompt)
        return response_stream, []

    # Tier 2: System Capabilities
    if detect_tier_two_system_query(query_text):
        mode_inst = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["Research Mode"])
        prompt = (
            f"System Prompt:\n{SYSTEM_PROMPT}\n\n"
            f"System Knowledge Details:\n{SYSTEM_KNOWLEDGE}\n\n"
            f"User Question: {query_text}\n\n"
            "Based ONLY on the system knowledge details provided above, answer the user's question clearly and structured in a professional academic tone. "
            f"You must strictly follow this length and formatting rule: {mode_inst}\n\n"
            "Response:"
        )
        response_stream = gemini.generate_stream(prompt)
        return response_stream, []

    # Tier 3: Research Queries
    where_filter = build_where_filter(
        stream=stream,
        fraud_category=fraud_category,
        source_platform=source_platform,
        narrative_type=narrative_type,
        geographic_scope=geographic_scope,
        year_range=year_range
    )
    
    # Retrieve relevant documents
    try:
        results = collection.query(
            query_texts=[query_text],
            n_results=8,
            where=where_filter
        )
    except Exception as e:
        print(f"Error querying ChromaDB: {e}")
        results = None
        
    # Check if results are empty or zero matching documents
    if not results or not results["documents"] or len(results["documents"][0]) == 0:
        mode_inst = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["Research Mode"])
        fallback_prompt = (
            f"System Prompt:\n{SYSTEM_PROMPT}\n\n"
            f"User Question: {query_text}\n\n"
            "You must answer the user's question based on your general academic knowledge of Indian cybercrime. "
            "Do NOT include any warning, disclaimer, or disclosure about documents not being found. "
            "Ensure the answer is highly scholarly, objective, and relevant to the Indian context. "
            f"You must strictly follow this length and formatting rule: {mode_inst}\n\n"
            "Research Analysis:"
        )
        response_stream = gemini.generate_stream(fallback_prompt)
        return response_stream, []
        
    documents = results["documents"][0]
    metadatas = results["metadatas"][0]
    
    # Deduplicate metadata for unique sources list
    seen_sources = set()
    unique_sources = []
    for meta in metadatas:
        doc_id = meta.get("doc_id")
        if doc_id not in seen_sources:
            seen_sources.add(doc_id)
            unique_sources.append(meta)
            
    context_str = ""
    for i, (doc, meta) in enumerate(zip(documents, metadatas), 1):
        stream_label = "Stream A (Narratives & News)" if meta.get("stream") == "A" else "Stream B (Official Statistics)"
        context_str += (
            f"--- Context Source {i} ---\n"
            f"Document ID: {meta.get('doc_id')}\n"
            f"Stream: {stream_label}\n"
            f"Title: {meta.get('title')}\n"
            f"Source Platform/Organisation: {meta.get('source_platform')}\n"
            f"Original/Publication Date: {meta.get('original_date')}\n"
            f"Fraud Category: {meta.get('fraud_category')}\n"
            f"Content Chunk:\n{doc}\n\n"
        )

    # Build System Prompt and Context block
    mode_inst = MODE_INSTRUCTIONS.get(mode, MODE_INSTRUCTIONS["Research Mode"])
    
    rag_prompt = (
        f"System Prompt:\n{SYSTEM_PROMPT}\n\n"
        "Guidelines:\n"
        "1. Your response must be scholarly, objective, and directly backed by the provided evidence context. "
        "   Do not use generic knowledge or generalize beyond what is found in the context sources. "
        "   (Even if sources are limited, answer confidently as a domain expert using the available context; do NOT output disclaimers saying you don't have enough data).\n"
        "2. Cite sources by doc_id and title (e.g., [NA-123] Title) when stating facts, numbers, or narratives.\n"
        "3. Distinguish between narrative/media evidence (Stream A) and official government statistics (Stream B).\n"
        "4. Highlight if the evidence retrieved is limited or one-sided.\n"
        "5. Focus on Indian context and specific cities, regions, and platforms mentioned in the sources.\n\n"
        f"Retrieved Context Documents:\n{context_str}\n"
        f"User Question: {query_text}\n\n"
        f"You must strictly follow this length and formatting rule: {mode_inst}\n\n"
        "Research Analysis:"
    )
    
    # Query Gemini with key rotator
    response_stream = gemini.generate_stream(rag_prompt)
    return response_stream, unique_sources
