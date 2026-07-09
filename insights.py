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
    years_a = pd.to_numeric(df_a["parsed_year"], errors="coerce").dropna().astype(int).value_counts().reset_index()
    years_a.columns = ["Year", "Count"]
    years_a["Stream"] = "Stream A (Narratives)"
    
    years_b = pd.to_numeric(df_b["parsed_year"], errors="coerce").dropna().astype(int).value_counts().reset_index()
    years_b.columns = ["Year", "Count"]
    years_b["Stream"] = "Stream B (Government)"
    
    df_comb = pd.concat([years_a, years_b]).sort_values("Year")
    
    # Stream B cases by year
    # Handle Total cases column
    cases_col = "Total cases" if "Total cases" in df_b.columns else "Total cases "
    cases_df = df_b.dropna(subset=[cases_col, "parsed_year"]).copy()
    cases_df[cases_col] = pd.to_numeric(cases_df[cases_col], errors="coerce")
    cases_df["parsed_year"] = pd.to_numeric(cases_df["parsed_year"], errors="coerce")
    cases_by_year = cases_df.dropna(subset=["parsed_year"]).groupby("parsed_year")[cases_col].sum().reset_index()
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


# ─────────────────────────────────────────────────────────────────────────────
# INSIGHT CHATBOT: Answer natural language questions with data + Plotly charts
# ─────────────────────────────────────────────────────────────────────────────

def _apply_dark_theme(fig, title: str = ""):
    """Apply consistent dark theme to any Plotly figure."""
    fig.update_layout(
        paper_bgcolor="#0b0f17",
        plot_bgcolor="rgba(22,27,34,0.9)",
        font=dict(color="#c9d1d9", family="Inter, sans-serif", size=11),
        title=dict(
            text=title,
            font=dict(color="#58a6ff", size=13, family="Inter, sans-serif"),
            x=0.01
        ),
        xaxis=dict(
            gridcolor="#21262d",
            linecolor="#30363d",
            tickfont=dict(color="#8b949e", size=10),
            title_font=dict(color="#8b949e")
        ),
        yaxis=dict(
            gridcolor="#21262d",
            linecolor="#30363d",
            tickfont=dict(color="#8b949e", size=10),
            title_font=dict(color="#8b949e")
        ),
        legend=dict(
            bgcolor="rgba(11,15,23,0.6)",
            bordercolor="#21262d",
            borderwidth=1,
            font=dict(size=10, color="#c9d1d9")
        ),
        margin=dict(l=50, r=20, t=55, b=60),
        height=360,
        colorway=["#58a6ff", "#bc8cff", "#7ee787", "#ff7b72", "#d2a8ff", "#ffa657", "#39d353"]
    )
    return fig


def answer_insight_question(question: str) -> dict:
    """
    Parse a natural language question about the cybercrime dataset,
    return { answer: str, chart: dict (Plotly JSON) or None, chart_title: str }.
    """
    df_a, df_b = load_data()
    q = question.lower()

    # ── Year extraction: detect specific year(s) in the question ─────────────
    # Matches: "in 2024", "for 2024", "during 2020-2023", "between 2018 and 2022"
    year_range_match = re.search(r'(20[1-2]\d)[\s\-–to]+(?:and\s+)?(20[1-2]\d)', q)
    year_single_match = re.search(r'\b(20[1-2]\d)\b', q)

    filter_year_start = None
    filter_year_end   = None
    year_label        = ""  # e.g. " (2024)" or " (2020–2023)"

    if year_range_match:
        filter_year_start = int(year_range_match.group(1))
        filter_year_end   = int(year_range_match.group(2))
        year_label = f" ({filter_year_start}–{filter_year_end})"
    elif year_single_match:
        filter_year_start = filter_year_end = int(year_single_match.group(1))
        year_label = f" ({filter_year_start})"

    # Apply year filter to both streams when a specific year is found
    if filter_year_start is not None:
        df_a = df_a[
            pd.to_numeric(df_a["parsed_year"], errors="coerce")
            .between(filter_year_start, filter_year_end)
        ].copy()
        df_b = df_b[
            pd.to_numeric(df_b["parsed_year"], errors="coerce")
            .between(filter_year_start, filter_year_end)
        ].copy()

    # ── Intent flags ──────────────────────────────────────────────────────────
    UPI_KW     = ["upi", "phonePe", "google pay", "gpay", "paytm", "bhim", "qr code",
                  "digital payment", "unified payment", "collect request", "upi fraud"]
    LOAN_KW    = ["loan", "lending", "nbfc", "instant loan", "loan app"]
    PHISH_KW   = ["phishing", "otp", "vishing", "sms fraud", "bank impersonation"]
    INVEST_KW  = ["investment", "trading", "crypto", "bitcoin", "ponzi", "stock fraud"]
    COMPARE_KW = ["compare", "stream", "official", "government", "vs ", "versus",
                  "narrative vs", "victim vs", "stream a", "stream b"]
    # TIME_KW: only trigger timeline mode when no specific year (otherwise show filtered breakdown)
    TIME_KW    = ["trend", "over time", "timeline", "annual", "growth",
                  "increase", "decrease", "each year", "per year", "evolution", "since",
                  "history", "progression"]
    # "year" alone without a specific year number triggers timeline
    if filter_year_start is None:
        TIME_KW.append("year")
    CAT_KW     = ["category", "categories", "type", "types", "breakdown", "distribution",
                  "most common", "top fraud", "which fraud"]

    is_upi     = any(k in q for k in [k.lower() for k in UPI_KW])
    is_loan    = any(k in q for k in LOAN_KW)
    is_phish   = any(k in q for k in PHISH_KW)
    is_invest  = any(k in q for k in INVEST_KW)
    is_compare = any(k in q for k in COMPARE_KW)
    is_time    = any(k in q for k in TIME_KW)
    is_cat     = any(k in q for k in CAT_KW)

    CHART_COLORS = ["#58a6ff", "#bc8cff", "#7ee787", "#ff7b72", "#ffa657", "#d2a8ff", "#39d353"]

    fig = None
    chart_title = ""
    context_data_str = ""

    # ── HELPER: get yearly counts for a filtered df ───────────────────────────
    def yearly_counts(df, stream_label="Cases"):
        yr = pd.to_numeric(df["parsed_year"], errors="coerce").dropna().astype(int)
        yr = yr.value_counts().sort_index().reset_index()
        yr.columns = ["Year", "Count"]
        yr = yr[yr["Year"].between(2013, 2026)]
        return yr

    # ── 1. UPI / Digital Payment ──────────────────────────────────────────────
    if is_upi:
        pattern = r"UPI|Digital Payment|PhonePe|Paytm|BHIM|Google Pay|QR|Unified Payment|Collect Request"
        mask_a = df_a["Fraud Category"].str.contains(pattern, case=False, na=False, regex=True)
        df_upi = df_a[mask_a]

        if is_time:
            yr = yearly_counts(df_upi)
            fig = px_go.Figure()
            fig.add_trace(px_go.Scatter(
                x=yr["Year"], y=yr["Count"],
                mode="lines+markers",
                name="UPI Fraud Records",
                line=dict(color="#58a6ff", width=2.5),
                marker=dict(size=7, color="#58a6ff", line=dict(color="#0b0f17", width=1)),
                fill="tozeroy",
                fillcolor="rgba(88,166,255,0.08)"
            ))
            chart_title = f"UPI & Digital Payment Fraud Records — Year-on-Year{year_label}"
            context_data_str = f"UPI Fraud by year (Stream A){year_label}:\n{yr.to_string(index=False)}\nTotal UPI records: {len(df_upi)}"
        else:
            # Category breakdown within UPI
            cat = df_upi["Fraud Category"].value_counts().head(8).reset_index()
            cat.columns = ["Category", "Count"]
            fig = px_go.Figure(px_go.Bar(
                x=cat["Count"], y=cat["Category"],
                orientation="h",
                marker=dict(
                    color=CHART_COLORS[:len(cat)],
                    line=dict(color="#0b0f17", width=1)
                )
            ))
            chart_title = f"UPI & Digital Payment Fraud — Category Breakdown{year_label}"
            context_data_str = f"UPI-related fraud categories{year_label}:\n{cat.to_string(index=False)}"

    # ── 2. Loan App Fraud ─────────────────────────────────────────────────────
    elif is_loan:
        mask = df_a["Fraud Category"].str.contains(r"loan|lending|credit|nbfc", case=False, na=False, regex=True)
        df_loan = df_a[mask]
        yr = yearly_counts(df_loan)

        if not yr.empty and filter_year_start is None:
            # No specific year: show timeline
            fig = px_go.Figure()
            fig.add_trace(px_go.Bar(
                x=yr["Year"], y=yr["Count"],
                name="Loan App Fraud Cases",
                marker=dict(color="#ffa657", line=dict(color="#0b0f17", width=0.8))
            ))
            chart_title = f"Loan App & NBFC Fraud Records by Year{year_label}"
            context_data_str = f"Loan fraud by year:\n{yr.to_string(index=False)}\nTotal: {len(df_loan)}"
        else:
            # Year specified or no timeline data — show category breakdown
            cat_loan = df_loan["Fraud Category"].value_counts().head(10).reset_index()
            cat_loan.columns = ["Category", "Count"]
            cat_all = df_a["Fraud Category"].value_counts().head(10).reset_index()
            cat_all.columns = ["Category", "Count"]
            use_cat = cat_loan if not cat_loan.empty else cat_all
            fig = px_go.Figure(px_go.Bar(
                x=use_cat["Count"], y=use_cat["Category"], orientation="h",
                marker=dict(color="#ffa657", line=dict(color="#0b0f17", width=0.8))
            ))
            chart_title = f"Loan App & NBFC Fraud Categories{year_label}" if not cat_loan.empty else f"All Fraud Categories{year_label}"
            context_data_str = f"Loan fraud categories{year_label}:\n{use_cat.to_string(index=False)}\nTotal records: {len(df_loan)}"

    # ── 3. Phishing / OTP ────────────────────────────────────────────────────
    elif is_phish:
        mask = df_a["Fraud Category"].str.contains(r"phish|otp|vishing|sms|impersonat", case=False, na=False, regex=True)
        df_ph = df_a[mask]
        yr = yearly_counts(df_ph)
        if filter_year_start is not None or yr.empty:
            # Year specified: show category bar instead of timeline
            cat_ph = df_ph["Fraud Category"].value_counts().head(8).reset_index()
            cat_ph.columns = ["Category", "Count"]
            cat_all = df_a["Fraud Category"].value_counts().head(8).reset_index()
            cat_all.columns = ["Category", "Count"]
            use_cat = cat_ph if not cat_ph.empty else cat_all
            fig = px_go.Figure(px_go.Bar(
                x=use_cat["Count"], y=use_cat["Category"], orientation="h",
                marker=dict(color="#ff7b72", line=dict(color="#0b0f17", width=0.8))
            ))
            chart_title = f"Phishing & OTP Fraud Categories{year_label}"
            context_data_str = f"Phishing/OTP fraud categories{year_label}:\n{use_cat.to_string(index=False)}\nTotal: {len(df_ph)}"
        else:
            fig = px_go.Figure()
            fig.add_trace(px_go.Scatter(
                x=yr["Year"], y=yr["Count"],
                mode="lines+markers",
                line=dict(color="#ff7b72", width=2.5),
                marker=dict(size=7, color="#ff7b72"),
                fill="tozeroy",
                fillcolor="rgba(255,123,114,0.08)"
            ))
            chart_title = f"Phishing & OTP Fraud Records by Year{year_label}"
            context_data_str = f"Phishing/OTP fraud by year:\n{yr.to_string(index=False)}\nTotal: {len(df_ph)}"

    # ── 4. Investment / Crypto ────────────────────────────────────────────────
    elif is_invest:
        mask = df_a["Fraud Category"].str.contains(r"invest|trading|crypto|bitcoin|ponzi|stock", case=False, na=False, regex=True)
        df_inv = df_a[mask]
        yr = yearly_counts(df_inv)
        if filter_year_start is not None or yr.empty:
            # Year specified: show category breakdown
            cat_inv = df_inv["Fraud Category"].value_counts().head(8).reset_index()
            cat_inv.columns = ["Category", "Count"]
            cat_all = df_a["Fraud Category"].value_counts().head(8).reset_index()
            cat_all.columns = ["Category", "Count"]
            use_cat = cat_inv if not cat_inv.empty else cat_all
            fig = px_go.Figure(px_go.Bar(
                x=use_cat["Count"], y=use_cat["Category"], orientation="h",
                marker=dict(color="#7ee787", line=dict(color="#0b0f17", width=0.8))
            ))
            chart_title = f"Investment & Crypto Fraud Categories{year_label}"
            context_data_str = f"Investment fraud categories{year_label}:\n{use_cat.to_string(index=False)}\nTotal: {len(df_inv)}"
        else:
            fig = px_go.Figure()
            fig.add_trace(px_go.Bar(
                x=yr["Year"], y=yr["Count"],
                marker=dict(color="#7ee787", line=dict(color="#0b0f17", width=0.8))
            ))
            chart_title = f"Investment & Crypto Fraud Records by Year{year_label}"
            context_data_str = f"Investment fraud by year:\n{yr.to_string(index=False)}\nTotal: {len(df_inv)}"

    # ── 5. Stream A vs Stream B comparison ───────────────────────────────────
    elif is_compare:
        cnt_a = df_a["Fraud Category"].value_counts().head(8).reset_index()
        cnt_a.columns = ["Category", "StreamA"]
        cnt_b = df_b["Cybercrime Category"].value_counts().head(8).reset_index()
        cnt_b.columns = ["Category", "StreamB"]
        merged = pd.merge(cnt_a, cnt_b, on="Category", how="outer").fillna(0).sort_values("StreamA", ascending=False).head(10)

        fig = px_go.Figure()
        fig.add_trace(px_go.Bar(
            x=merged["Category"], y=merged["StreamA"],
            name="Victim Narratives (Stream A)",
            marker=dict(color="#bc8cff", line=dict(color="#0b0f17", width=0.8))
        ))
        fig.add_trace(px_go.Bar(
            x=merged["Category"], y=merged["StreamB"],
            name="Official Stats (Stream B)",
            marker=dict(color="#ff7b72", line=dict(color="#0b0f17", width=0.8))
        ))
        fig.update_layout(barmode="group")
        chart_title = f"Victim Narratives vs. Government Statistics — By Category{year_label}"
        context_data_str = f"Stream comparison{year_label}:\n{merged.to_string(index=False)}"

    # ── 6. Category breakdown ─────────────────────────────────────────────────
    elif is_cat:
        cat = df_a["Fraud Category"].value_counts().head(12).reset_index()
        cat.columns = ["Category", "Count"]
        colors = CHART_COLORS * 2
        fig = px_go.Figure(px_go.Bar(
            x=cat["Count"], y=cat["Category"],
            orientation="h",
            marker=dict(color=colors[:len(cat)], line=dict(color="#0b0f17", width=0.8))
        ))
        chart_title = f"Top Fraud Categories — Stream A (Victim Narratives){year_label}"
        context_data_str = f"Category distribution{year_label}:\n{cat.to_string(index=False)}"

    # ── 7. Overall / temporal trend ──────────────────────────────────────────
    elif is_time or "overall" in q or "all crime" in q or "total" in q:
        top_cats = df_a["Fraud Category"].value_counts().head(5).index.tolist()
        fig = px_go.Figure()
        all_yr_data = []

        for i, cat in enumerate(top_cats):
            df_cat = df_a[df_a["Fraud Category"] == cat]
            yr = yearly_counts(df_cat)
            if not yr.empty:
                fig.add_trace(px_go.Scatter(
                    x=yr["Year"], y=yr["Count"],
                    mode="lines+markers",
                    name=cat[:35] + ("…" if len(cat) > 35 else ""),
                    line=dict(color=CHART_COLORS[i % len(CHART_COLORS)], width=2),
                    marker=dict(size=5)
                ))
                all_yr_data.append(f"{cat}: {yr.to_string(index=False)}")

        # Also add a total line
        total_yr = yearly_counts(df_a)
        fig.add_trace(px_go.Scatter(
            x=total_yr["Year"], y=total_yr["Count"],
            mode="lines",
            name="ALL CATEGORIES",
            line=dict(color="#ffffff", width=1.5, dash="dot"),
            opacity=0.5
        ))

        chart_title = "Cybercrime Trends — Top Categories Over Time (2013–2026)"
        context_data_str = (
            f"Total records by year:\n{total_yr.to_string(index=False)}\n\n"
            f"Top 5 categories: {', '.join(top_cats)}"
        )

    # ── 8. Default: horizontal bar of all categories ──────────────────────────
    else:
        cat = df_a["Fraud Category"].value_counts().head(12).reset_index()
        cat.columns = ["Category", "Count"]
        colors = CHART_COLORS * 2
        fig = px_go.Figure(px_go.Bar(
            x=cat["Count"], y=cat["Category"],
            orientation="h",
            marker=dict(color=colors[:len(cat)], line=dict(color="#0b0f17", width=0.8))
        ))
        chart_title = f"Top Fraud Categories — Indian Cybercrime Registry{year_label}"
        context_data_str = (
            f"Fraud category distribution{year_label} (Stream A — {len(df_a)} records):\n{cat.to_string(index=False)}\n\n"
            f"Stream B (Government) total: {len(df_b)} records"
        )

    # Apply theme
    if fig is not None:
        _apply_dark_theme(fig, chart_title)

    # ── LLM text answer ───────────────────────────────────────────────────────
    prompt = (
        "You are a cybercrime data analyst specialising in Indian digital fraud. "
        f"Based on this data from the CyberLens Indian Cybercrime Registry:\n\n"
        f"{context_data_str}\n\n"
        f"Answer this question concisely in 2-4 sentences: {question}\n"
        "Be specific — cite numbers, years, and percentages from the data. Keep it professional and grounded."
    )
    answer_text = get_llm_response(prompt)

    # Serialise chart safely (convert numpy types → Python natives)
    chart_dict = None
    if fig is not None:
        import json
        import numpy as np

        def _np_safe(obj):
            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
            if isinstance(obj, (np.bool_,)):
                return bool(obj)
            return str(obj)

        raw = fig.to_dict()
        chart_dict = json.loads(json.dumps(raw, default=_np_safe))


    return {
        "answer": answer_text,
        "chart": chart_dict,
        "chart_title": chart_title
    }

