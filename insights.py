import os
import re
import threading
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as px_go
from dotenv import load_dotenv
from gemini_client import gemini

# Load environment variables
load_dotenv()

xlsx_path = "data/txt/all_data.xlsx"
if not os.path.exists(xlsx_path):
    xlsx_path = "data/all_data.xlsx"

excel_lock = threading.Lock()

def load_data():
    with excel_lock:
        xl = pd.ExcelFile(xlsx_path)
        df_a = pd.read_excel(xl, sheet_name="stream_a_scraped")
        df_b = pd.read_excel(xl, sheet_name="stream_b_govt")
    
    # Filter empty ID rows for Stream A
    df_a = df_a.dropna(subset=["Unique ID"])
    
    # Clean column names (strip whitespace)
    df_b.columns = [c.strip() for c in df_b.columns]
    
    # Parse years
    def extract_year(date_val):
        if pd.isna(date_val):
            return np.nan
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
        return np.nan

    df_a["parsed_year"] = df_a["Original Date"].apply(extract_year)
    df_b["parsed_year"] = df_b["Report Year"].apply(extract_year)
    
    return df_a, df_b

def get_llm_response(prompt):
    try:
        return gemini.generate(prompt)
    except Exception as e:
        return f"Error generating LLM analysis: {e}"

# --- PANEL A: TEMPORAL TRENDS ---
def get_temporal_trends_data():
    df_a, df_b = load_data()
    
    # Group Stream A and B by year
    years_a = df_a["parsed_year"].dropna().astype(int).value_counts().reset_index()
    years_a.columns = ["Year", "Count"]
    years_a["Stream"] = "Stream A (Narratives)"
    
    years_b = df_b["parsed_year"].dropna().astype(int).value_counts().reset_index()
    years_b.columns = ["Year", "Count"]
    years_b["Stream"] = "Stream B (Government)"
    
    df_comb = pd.concat([years_a, years_b]).sort_values("Year")
    
    # Stream B cases by year
    # Handle Total cases column
    cases_col = "Total cases" if "Total cases" in df_b.columns else "Total cases "
    cases_df = df_b.dropna(subset=[cases_col, "parsed_year"]).copy()
    cases_df[cases_col] = pd.to_numeric(cases_df[cases_col], errors="coerce")
    cases_by_year = cases_df.groupby("parsed_year")[cases_col].sum().reset_index()
    cases_by_year.columns = ["Year", "Total Cases"]
    cases_by_year = cases_by_year.sort_values("Year")
    
    return df_comb, cases_by_year

def generate_panel_a_narrative(year_range):
    df_comb, cases_by_year = get_temporal_trends_data()
    
    # Format data for LLM
    data_summary = "Stream A & B Document Counts:\n" + df_comb.to_string(index=False)
    data_summary += "\n\nStream B Official Cases:\n" + cases_by_year.to_string(index=False)
    
    prompt = (
        "You are an expert cybercrime researcher. Based on the following dataset details spanning "
        f"{year_range[0]} to {year_range[1]}, analyze the major temporal trends in Indian cybercrime. "
        "Cite specific years, counts, and cases from the data, and discuss patterns such as spikes or structural shifts.\n\n"
        f"Data:\n{data_summary}\n\n"
        "Your Academic Analysis:"
    )
    return get_llm_response(prompt)

# --- PANEL B: FRAUD CATEGORY LANDSCAPE ---
def get_fraud_landscape_data():
    df_a, df_b = load_data()
    
    cat_a = df_a["Fraud Category"].value_counts().reset_index()
    cat_a.columns = ["Category", "Count"]
    cat_a["Stream"] = "Stream A (Narratives)"
    
    cat_b = df_b["Cybercrime Category"].value_counts().reset_index()
    cat_b.columns = ["Category", "Count"]
    cat_b["Stream"] = "Stream B (Government)"
    
    df_comb = pd.concat([cat_a, cat_b])
    return df_comb

def generate_panel_b_narrative():
    df_comb = get_fraud_landscape_data()
    data_summary = df_comb.to_string(index=False)
    
    prompt = (
        "You are a senior cybercrime researcher analyzing Indian cybercrime trends.\n"
        "Based on this category frequency landscape:\n"
        f"{data_summary}\n\n"
        "Identify the top 3 most documented fraud types in this dataset, explain what the data reveals about each, "
        "and note any category naming or coverage differences between Stream A and Stream B. Keep the analysis academic and rigorous.\n\n"
        "Your Academic Analysis:"
    )
    return get_llm_response(prompt)

# --- PANEL C: NARRATIVE VS OFFICIAL DIVERGENCE ---
def analyze_divergence():
    df_a, df_b = load_data()
    
    # Calculate percentages for comparison
    counts_a = df_a["Fraud Category"].value_counts(normalize=True).reset_index()
    counts_a.columns = ["Category", "Pct_A"]
    
    counts_b = df_b["Cybercrime Category"].value_counts(normalize=True).reset_index()
    counts_b.columns = ["Category", "Pct_B"]
    
    # Merge on Category (handle slight string discrepancies if needed, but outer join is safest)
    df_div = pd.merge(counts_a, counts_b, on="Category", how="outer").fillna(0)
    
    # Calculate divergence metric
    df_div["Difference"] = df_div["Pct_A"] - df_div["Pct_B"]
    df_div["Ratio"] = df_div.apply(lambda r: r["Pct_A"] / (r["Pct_B"] + 0.001), axis=1)
    
    # Identify underreported categories
    # Flag criteria: High in Stream A (> 5%) and low in Stream B (< 2%)
    df_div["Underreported"] = (df_div["Pct_A"] > 0.05) & (df_div["Pct_B"] < 0.02)
    
    return df_div

def generate_panel_c_narrative():
    df_div = analyze_divergence()
    data_summary = df_div.to_string(index=False)
    
    prompt = (
        "You are a senior cybercrime researcher at IIM Bangalore. You are analyzing the narrative vs. official statistics divergence in cybercrime reporting.\n"
        "The following table compares the proportions of fraud categories in victim narratives (Stream A) versus government statistics (Stream B):\n"
        f"{data_summary}\n\n"
        "Analyze this divergence in detail. Address the following questions:\n"
        "1. Which fraud types are heavily reported by victims but severely underrepresented in official data (underreported)? Why does this happen?\n"
        "2. What are the policy and policing implications of this reporting gap?\n"
        "3. How can law enforcement bridge the gap between official metrics and victim realities?\n\n"
        "Your Academic Analysis:"
    )
    return get_llm_response(prompt)

# --- PANEL D: GEOGRAPHIC PATTERNS ---
def get_geographic_data():
    _, df_b = load_data()
    geo_counts = df_b["Geographic Scope"].value_counts().reset_index()
    geo_counts.columns = ["Scope", "Count"]
    return geo_counts

def generate_panel_d_narrative():
    geo_counts = get_geographic_data()
    data_summary = geo_counts.to_string(index=False)
    
    prompt = (
        "You are a senior cybercrime researcher analyzing the regional/geographic distribution of cybercrime in India.\n"
        "Based on the distribution of geographic scope in the government dataset:\n"
        f"{data_summary}\n\n"
        "Analyze the geographic concentration patterns. What regions are highlighted? Why do certain regions appear "
        "as hot-spots in official statistics? How does geographic scope impact cybercrime investigation?\n\n"
        "Your Academic Analysis:"
    )
    return get_llm_response(prompt)

# --- PANEL E: EVOLUTION ANALYSIS ---
def generate_panel_e_narrative():
    df_a, df_b = load_data()
    
    # Sample documents from early years (e.g. <= 2018) vs later years (e.g. >= 2024)
    early_docs = df_a[df_a["parsed_year"] <= 2018][["Unique ID", "Title/Headline", "parsed_year", "Fraud Category"]].head(5)
    late_docs = df_a[df_a["parsed_year"] >= 2024][["Unique ID", "Title/Headline", "parsed_year", "Fraud Category"]].head(5)
    
    context_str = "Representative Early Documents (<= 2018):\n"
    for _, r in early_docs.iterrows():
        context_str += f"- [{r['Unique ID']}] ({int(r['parsed_year'])}): {r['Title/Headline']} [{r['Fraud Category']}]\n"
        
    context_str += "\nRepresentative Recent Documents (>= 2024):\n"
    for _, r in late_docs.iterrows():
        context_str += f"- [{r['Unique ID']}] ({int(r['parsed_year'])}): {r['Title/Headline']} [{r['Fraud Category']}]\n"
        
    prompt = (
        "You are a senior cybercrime researcher at IIM Bangalore studying the long-term evolution of cybercrime in India.\n"
        "Below is a sample of document metadata from early and recent periods in our dataset:\n"
        f"{context_str}\n\n"
        "Write an evolutionary analysis of cybercrime in India. Specifically:\n"
        "1. What new fraud types have emerged in recent years (e.g., dropshipping scam farms, instant loan app frauds, UPI QR scams)?\n"
        "2. What traditional fraud types (e.g., card cloning, phishing, website spoofing) have persisted or declined?\n"
        "3. How has the operational sophistication and geographic reach of criminal syndicates evolved over time?\n\n"
        "Your Academic Analysis:"
    )
    return get_llm_response(prompt)
