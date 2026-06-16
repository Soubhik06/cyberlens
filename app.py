import os
import csv
import json
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, jsonify

app = Flask(__name__)

# Constants
OUTPUT_FOLDER = "./gioia_output"
CSV_FILE = "submissions.csv"

def parse_markdown_table(filepath):
    """Parses markdown table in gioia_data_structure.md into rows of cells."""
    if not os.path.exists(filepath):
        return None
    try:
        rows = []
        with open(filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # Skip divider rows and empty lines
                if not line or line.startswith("| ---") or line.startswith("|---"):
                    continue
                parts = [p.strip() for p in line.split("|")]
                # Strip out the empty outer elements if present due to splitting on bounds
                if len(parts) >= 3:
                    if parts[0] == "":
                        parts = parts[1:]
                    if parts[-1] == "":
                        parts = parts[:-1]
                    # Skip header row
                    if parts[0].lower().startswith("first-order"):
                        continue
                    # Ensure exactly 3 elements to prevent IndexError in template
                    while len(parts) < 3:
                        parts.append("")
                    parts = parts[:3]
                    rows.append(parts)
        return rows
    except Exception as e:
        print(f"Error parsing markdown table: {e}")
        return None

@app.route('/')
def index():
    return redirect(url_for('submit_experience'))

@app.route('/submit', methods=['GET', 'POST'])
def submit_experience():
    success_message = None
    if request.method == 'POST':
        # Retrieve form data
        exp_type = request.form.get("experience_type", "")
        text_content = request.form.get("text", "")
        year_val = request.form.get("year", "")
        platform_val = request.form.get("platform", "")
        amount = request.form.get("amount_lost", "")
        how_realized = request.form.get("how_found_out", "")
        
        # Format timestamp
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Save to CSV file
        file_exists = os.path.exists(CSV_FILE)
        try:
            with open(CSV_FILE, mode="a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["timestamp", "experience_type", "text", "year", "platform", "amount_lost", "how_found_out"])
                writer.writerow([timestamp, exp_type, text_content, year_val, platform_val, amount, how_realized])
            
            success_message = "Thank you for sharing your experience. It contributes to cybercrime research in India."
        except Exception as e:
            success_message = f"Error saving submission: {e}"
            
    return render_template('submit.html', success_message=success_message)

@app.route('/gioia')
def gioia_analysis():
    # Verify if the pipeline output files all exist
    required_files = [
        os.path.join(OUTPUT_FOLDER, "first_order_codes.json"),
        os.path.join(OUTPUT_FOLDER, "second_order_themes.json"),
        os.path.join(OUTPUT_FOLDER, "aggregate_dimensions.json"),
        os.path.join(OUTPUT_FOLDER, "gioia_data_structure.md"),
        os.path.join(OUTPUT_FOLDER, "methods_paragraph.txt"),
        os.path.join(OUTPUT_FOLDER, "findings_section.txt"),
        os.path.join(OUTPUT_FOLDER, "full_pipeline_output.json")
    ]
    
    pipeline_run = all(os.path.exists(f) for f in required_files)
    
    if not pipeline_run:
        return render_template('gioia.html', pipeline_run=False)
        
    # Load and parse output files
    table_rows = parse_markdown_table(os.path.join(OUTPUT_FOLDER, "gioia_data_structure.md"))
    
    # Load dimensions JSON
    dimensions_data = None
    try:
        with open(os.path.join(OUTPUT_FOLDER, "aggregate_dimensions.json"), "r", encoding="utf-8") as f:
            dimensions_data = json.load(f)
    except Exception as e:
        print(f"Error loading aggregate_dimensions.json: {e}")
        
    # Load methods paragraph and findings section
    methods_text = ""
    try:
        with open(os.path.join(OUTPUT_FOLDER, "methods_paragraph.txt"), "r", encoding="utf-8") as f:
            methods_text = f.read().strip()
    except Exception as e:
        print(f"Error loading methods_paragraph.txt: {e}")
        
    findings_text = ""
    try:
        with open(os.path.join(OUTPUT_FOLDER, "findings_section.txt"), "r", encoding="utf-8") as f:
            findings_text = f.read().strip()
    except Exception as e:
        print(f"Error loading findings_section.txt: {e}")
        
    # Load pipeline stats
    stats = {}
    try:
        with open(os.path.join(OUTPUT_FOLDER, "full_pipeline_output.json"), "r", encoding="utf-8") as f:
            full_out = json.load(f)
            stats = full_out.get("stats", {})
    except Exception as e:
        print(f"Error loading full_pipeline_output.json stats: {e}")
        
    return render_template(
        'gioia.html',
        pipeline_run=True,
        table_rows=table_rows,
        dimensions_data=dimensions_data,
        methods_text=methods_text,
        findings_text=findings_text,
        stats=stats
    )

def retrieve_relevant_codes(question, first_order_codes):
    """
    Selects the most relevant first-order codes for the given question.
    Uses simple token matching / overlap as a fallback, and LLM classification for precision.
    """
    unique_codes = []
    seen = set()
    for item in first_order_codes:
        c = item["code"]
        if c not in seen:
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

def map_codes_to_framework(selected_codes, OUTPUT_FOLDER):
    themes_path = os.path.join(OUTPUT_FOLDER, "second_order_themes.json")
    themes_data = []
    if os.path.exists(themes_path):
        with open(themes_path, "r", encoding="utf-8") as f:
            themes_data = json.load(f)
            
    dims_path = os.path.join(OUTPUT_FOLDER, "aggregate_dimensions.json")
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
            "source": code_item.get("source", ""),
            "date": code_item.get("date", ""),
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

@app.route('/query-gioia', methods=['POST'])
def query_gioia():
    data = request.get_json() or {}
    question = data.get("question", "").strip()
    if not question:
        return jsonify({"success": False, "error": "No question provided"})
        
    required_files = {
        "first_order": os.path.join(OUTPUT_FOLDER, "first_order_codes.json"),
        "second_order": os.path.join(OUTPUT_FOLDER, "second_order_themes.json"),
        "aggregate": os.path.join(OUTPUT_FOLDER, "aggregate_dimensions.json")
    }
    
    if not all(os.path.exists(f) for f in required_files.values()):
        return jsonify({"success": False, "error": "Pipeline analysis results are not available. Please run the pipeline first."})
        
    try:
        with open(required_files["first_order"], "r", encoding="utf-8") as f:
            first_order_codes = json.load(f)
            
        if not first_order_codes:
            return jsonify({"success": False, "error": "No qualitative codes found. Please run the pipeline with relevant records."})
            
        selected_codes = retrieve_relevant_codes(question, first_order_codes)
        retrieved_codes, mapped_themes, mapped_dims = map_codes_to_framework(selected_codes, OUTPUT_FOLDER)
        answer = synthesize_gioia_answer(question, retrieved_codes, mapped_themes, mapped_dims)
        
        workflow = {
            "retrieved_codes": retrieved_codes,
            "mapped_themes": [{"name": name, "description": desc} for name, desc in mapped_themes],
            "mapped_dimensions": mapped_dims
        }
        
        return jsonify({"success": True, "answer": answer, "workflow": workflow})
    except Exception as e:
        print(f"Error querying Gioia agent: {e}")
        return jsonify({"success": False, "error": str(e)})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000, debug=True)
