from flask import Flask, render_template, request, redirect, send_file, jsonify
import os
import re
import tempfile
import json
import pandas as pd
from werkzeug.utils import secure_filename
from opencc import OpenCC

app = Flask(__name__)

# === ROUTES ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/cc-remover')
def cc_remover():
    return render_template('cc_remover.html')

@app.route('/converter')
def converter():
    return render_template('converter.html')

@app.route('/profanity-checker')
def profanity_checker():
    return render_template('profanity_checker.html')

@app.route('/zht-zhs-converter')
def zht_zhs_converter():
    return render_template('zht_zhs_converter.html')

@app.route('/chinese-converter')
def chinese_converter():
    return render_template('chinese_converter.html')
@app.route('/upload-chinese-srt', methods=['POST'])
def upload_chinese_srt():
    file = request.files.get('srtfile')
    if not file or not file.filename.endswith('.srt'):
        return redirect('/chinese-converter')

    content = file.read().decode('utf-8', errors='ignore')

    # Detect language
    variant = detect_chinese_variant(content)
    direction = 's2t' if variant == 'zhs' else 't2s'

    # Convert and diff
    converted_text, diffs = convert_chinese_variant(content, direction)

    return render_template('converted_chinese_result.html', 
                           original=content, 
                           converted=converted_text, 
                           diffs=diffs,
                           direction=direction,
                           detected_variant=variant)

# === CC REMOVER ===
@app.route('/remove-cc', methods=['POST'])
def remove_cc():
    file = request.files['srtfile']
    if file.filename.endswith('.srt'):
        content = file.read().decode('utf-8')
        cleaned_lines = []
        
        # Common CC patterns
        patterns = [
            r"\[.*?\]",    # [text]
            r"\(.*?\)",    # (text)
            r"<.*?>",      # <text>
            r'^".*"$',     # Entire line in quotes
            r"^♪.*$",      # Music symbols
            r"^♫.*$",      # Music symbols
            r"^[A-Z\s]+$", # ALL CAPS LINES (common for CC)
            r"^[#@].*$",   # Lines starting with # or @
            r"^\*.*\*$",   # *text*
            r"^_._$",      # _text_
            r"^●.*$",      # ● bullet points
            r"^►.*$",     # ► arrows
            r"^[0-9]+$",   # Standalone numbers (could be mistaken for subtitle numbers)
        ]
        
        # Keep track of subtitle numbering
        current_number = 0
        prev_line_was_number = False
        
        for line in content.splitlines():
            line = line.strip()
            
            # Skip empty lines
            if not line:
                cleaned_lines.append(line)
                prev_line_was_number = False
                continue
                
            # Handle subtitle numbering
            if line.isdigit():
                current_number = int(line)
                cleaned_lines.append(line)
                prev_line_was_number = True
                continue
                
            # Skip timing lines (we want to keep these)
            if re.match(r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}", line):
                cleaned_lines.append(line)
                prev_line_was_number = False
                continue
                
            # Check for CC patterns
            is_cc = any(re.search(pattern, line) for pattern in patterns)
            
            # Special case: don't remove lines that are part of the actual dialogue
            if not is_cc or (prev_line_was_number and not any(re.fullmatch(pattern, line) for pattern in patterns)):
                cleaned_lines.append(line)
                
            prev_line_was_number = False
            
        cleaned_content = "\n".join(cleaned_lines)
        
        # Fix numbering in case we removed some entries
        cleaned_content = renumber_subtitles(cleaned_content)
        
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
        temp.write(cleaned_content)
        temp.close()
        
        return send_file(temp.name, as_attachment=True, download_name='cleaned_subtitles.srt')
    
    return redirect('/cc-remover')

def renumber_subtitles(content):
    """Renumber subtitles sequentially after some were removed"""
    lines = content.splitlines()
    new_lines = []
    current_num = 1
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if line.isdigit():
            # Replace with new number
            new_lines.append(str(current_num))
            current_num += 1
            i += 1
            
            # Keep timing line
            if i < len(lines):
                new_lines.append(lines[i])
                i += 1
                
            # Keep text lines until empty line
            while i < len(lines) and lines[i].strip():
                new_lines.append(lines[i])
                i += 1
                
            # Add empty line if exists
            if i < len(lines) and not lines[i].strip():
                new_lines.append(lines[i])
                i += 1
        else:
            new_lines.append(lines[i])
            i += 1
            
    return "\n".join(new_lines)

# === EXCEL ⇄ SRT CONVERTER ===
@app.route('/convert-excel-to-srt', methods=['POST'])
def convert_excel_to_srt():
    file = request.files['excelfile']
    if not file.filename.endswith(('.xls', '.xlsx')):
        return redirect('/converter')

    df = pd.read_excel(file)

    srt_output = []
    for i, row in df.iterrows():
        srt_output.append(f"{i+1}")
        srt_output.append(f"{row['Start Time']} --> {row['End Time']}")
        srt_output.append(f"{row['Subtitle Text']}")
        srt_output.append("")

    srt_content = "\n".join(srt_output)

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
    temp.write(srt_content)
    temp.close()

    return send_file(temp.name, as_attachment=True, download_name='converted_from_excel.srt')

@app.route('/convert-srt-to-excel', methods=['POST'])
def convert_srt_to_excel():
    file = request.files['srtfile']
    if not file.filename.endswith('.srt'):
        return redirect('/converter')

    content = file.read().decode('utf-8')

    pattern = re.compile(r"(\d+)\s*\n?(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\s*\n?([^\d]+)", re.MULTILINE)
    matches = pattern.findall(content)

    data = []
    for match in matches:
        _, start, end, text = match
        cleaned_text = ' '.join(text.strip().splitlines()).strip()
        data.append({
            'Start Time': start,
            'End Time': end,
            'Subtitle Text': cleaned_text
        })

    df = pd.DataFrame(data)

    with tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx") as temp:
        with pd.ExcelWriter(temp.name, engine='openpyxl') as writer:
            df.to_excel(writer, index=False)
        temp.flush()
        return send_file(temp.name, as_attachment=True, download_name='converted_from_srt.xlsx')

# === PROFANITY CHECKER ===
def load_profanity_list():
    with open('static/profanity_list.json', 'r') as file:
        profanity_list = json.load(file)
    return profanity_list

def check_profanity(content):
    profanity_list = load_profanity_list()
    patterns = [re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE) for word in profanity_list]

    detected_profanities = []

    for line_num, line in enumerate(content.splitlines(), start=1):
        for pattern, word in zip(patterns, profanity_list):
            if pattern.search(line):
                detected_profanities.append({
                    'line_number': line_num,
                    'line_text': line.strip(),
                    'profanity': word
                })

    return detected_profanities

@app.route('/check-profanity', methods=['POST'])
def check_profanity_route():
    file = request.files['file']
    if file and (file.filename.endswith('.srt') or file.filename.endswith('.xlsx')):
        content = file.read().decode('utf-8', errors='ignore')
        profanities = check_profanity(content)

        if profanities:
            return render_template('edit_profanities.html',
                                   content=content,
                                   profanities=profanities,
                                   original_filename=file.filename)
        else:
            return "No profanities detected"

    return redirect('/profanity-checker')

@app.route('/final-qc', methods=['POST'])
def final_qc():
    content = request.form['edited_content']
    original_filename = request.form['original_filename']
    profanities = check_profanity(content)

    if profanities:
        return render_template('edit_profanities.html',
                               content=content,
                               profanities=profanities,
                               original_filename=original_filename,
                               message="Still contains profanity!")
    else:
        suffix = '.srt' if original_filename.endswith('.srt') else '.txt'
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode='w', encoding='utf-8') as temp:
            temp.write(content)
        return send_file(temp.name, as_attachment=True, download_name='cleaned_' + original_filename)

# === ZHT ⇄ ZHS CONVERTER ===
def detect_chinese_variant(text):
    simplified_chars = "爱边陈当发干国红黄鸡开来马内齐时体为习"
    traditional_chars = "愛邊陳當發幹國紅黃雞開來馬內齊時體為習"
    simp_score = sum(char in simplified_chars for char in text)
    trad_score = sum(char in traditional_chars for char in text)
    if simp_score > trad_score:
        return "zhs"
    elif trad_score > simp_score:
        return "zht"
    return "unknown"

def convert_chinese_variant(text, direction='s2t'):
    cc = OpenCC(direction)
    converted_lines = []
    diffs = []
    for line in text.splitlines():
        converted = cc.convert(line)
        converted_lines.append(converted)
        if line != converted:
            diffs.append((line, converted))
    return "\n".join(converted_lines), diffs

# 🟢 NEW HTML-FORM-FRIENDLY ROUTE
@app.route('/convert-chinese', methods=['POST'])
def convert_chinese_form():
    text = request.form.get('chinese_text')
    direction = request.form.get('direction', 's2t')

    if not text:
        return "No text provided", 400

    converted_text, diffs = convert_chinese_variant(text, direction)

    return render_template('chinese_converter_result.html',
                           original_text=text,
                           converted_text=converted_text,
                           diffs=diffs)

# 🟢 JSON API (for fetch/XHR/AJAX)
@app.route('/api/convert-chinese', methods=['POST'])
def convert_chinese_api():
    data = request.get_json()
    text = data.get('text')
    direction = data.get('direction', 's2t')

    converted_text, diffs = convert_chinese_variant(text, direction)

    return jsonify({
        'converted': converted_text,
        'diffs': diffs
    })

@app.route('/download-converted', methods=['POST'])
def download_converted():
    converted = request.form['converted']
    with tempfile.NamedTemporaryFile(delete=False, suffix='.srt', mode='w', encoding='utf-8') as temp:
        temp.write(converted)
    return send_file(temp.name, as_attachment=True, download_name='converted_chinese.srt')


# === RUN ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
