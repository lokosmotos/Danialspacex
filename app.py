from flask import Flask, render_template, request, redirect, send_file, jsonify
import os
import re
import tempfile
import json
import pandas as pd
import zipfile
from io import BytesIO
from werkzeug.utils import secure_filename
from opencc import OpenCC
from langdetect import detect, LangDetectException

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

@app.route('/bilingual-splitter')
def bilingual_splitter():
    return render_template('bilingual_splitter.html')

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

# === BILINGUAL SPLITTER ===
@app.route('/split-bilingual', methods=['GET', 'POST'])
def split_bilingual():
    if request.method == 'GET':
        return render_template('split_bilingual.html')

    file = request.files.get('srtfile')
    if not file or not file.filename.endswith('.srt'):
        return redirect('/split-bilingual')

    content = file.read().decode('utf-8', errors='ignore')
    
    eng_blocks, rus_blocks = split_bilingual_subtitles(content)

    # Generate the final content for each language
    eng_content = '\n\n'.join(eng_blocks)
    rus_content = '\n\n'.join(rus_blocks)

    # Renumber both files sequentially
    eng_content = renumber_subtitles(eng_content)
    rus_content = renumber_subtitles(rus_content)

    # Create zip file
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
        zip_file.writestr('english.srt', eng_content.encode('utf-8'))
        zip_file.writestr('russian.srt', rus_content.encode('utf-8'))

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='separated_languages.zip'
    )

# === HELPER FUNCTIONS ===
def is_russian(text):
    """Improved Russian detection using regex for Cyrillic characters"""
    return bool(re.search(r'[А-Яа-яЁё]', text))

def split_bilingual_subtitles(content):
    """Split bilingual subtitles into separate English and Russian blocks"""
    blocks = content.strip().split('\n\n')
    eng_blocks = []
    rus_blocks = []
    
    for block in blocks:
        if not block.strip():
            continue
            
        lines = block.split('\n')
        if len(lines) < 3:  # Not a valid subtitle block
            continue
            
        block_number = lines[0].strip()
        time_line = lines[1].strip()
        text_lines = [line.strip() for line in lines[2:] if line.strip()]
        
        # Separate into language groups
        eng_lines = []
        rus_lines = []
        
        for line in text_lines:
            try:
                # First try langdetect for more accurate detection
                lang = detect(line)
                if lang == 'ru':
                    rus_lines.append(line)
                else:
                    eng_lines.append(line)
            except LangDetectException:
                # Fallback to character detection if langdetect fails
                if is_russian(line):
                    rus_lines.append(line)
                else:
                    eng_lines.append(line)
        
        # Create separate blocks for each language
        if eng_lines:
            eng_block = f"{block_number}\n{time_line}\n" + "\n".join(eng_lines)
            eng_blocks.append(eng_block)
            
        if rus_lines:
            rus_block = f"{block_number}\n{time_line}\n" + "\n".join(rus_lines)
            rus_blocks.append(rus_block)
    
    return eng_blocks, rus_blocks

def renumber_subtitles(content):
    """Renumber subtitles sequentially from content string"""
    blocks = content.split('\n\n')
    new_blocks = []
    current_num = 1
    
    for block in blocks:
        if not block.strip():
            continue
            
        lines = block.split('\n')
        if len(lines) < 3:
            continue
            
        # Keep the time line and text lines, only change the number
        new_block = f"{current_num}\n{lines[1]}\n" + "\n".join(lines[2:])
        new_blocks.append(new_block)
        current_num += 1
    
    return '\n\n'.join(new_blocks)

# === CC REMOVER ===
@app.route('/remove-cc', methods=['POST'])
def remove_cc():
    file = request.files['srtfile']
    if not file.filename.endswith('.srt'):
        return redirect('/cc-remover')

    content = file.read().decode('utf-8')
    cleaned_blocks = []
    current_block = []
    block_has_content = False

    # Enhanced CC patterns (now handles multi-line quotes and various CC markers)
    CC_PATTERNS = [
        r'^[\[\(<【].*[\]\)>】]$',  # Any bracket style (western or asian)
        r'(^["«»].*)|(.*["«»]$)',  # Quotes at start or end (supports different quote styles)
        r'^♪.*$',                  # Music symbols
        r'^♫.*$',
        r'^[A-Z\s]+$',             # ALL CAPS text
        r'^[#@&].*$',             # Special character lines
        r'^\*.*\*$',              # *text*
        r'^_._$',                  # _text_
        r'^●.*$',                  # Bullet points
        r'^►.*$',                  # Arrows
        r'\bCC\b',                # CC markers
        r'\bSUBTITLES?\b',        # Subtitle markers
        r'^\d+%$',                # Percentage indicators
        r'^[=-]+$',               # Lines with just === or ---
    ]

    for line in content.splitlines():
        stripped = line.strip()
        
        # New block starts with a number
        if stripped.isdigit():
            if current_block and block_has_content:
                cleaned_blocks.append(current_block)
            current_block = [line]
            block_has_content = False
        # Timestamp line
        elif re.match(r"\d{2}:\d{2}:\d{2},\d{3} --> \d{2}:\d{2}:\d{2},\d{3}", stripped):
            current_block.append(line)
        # Text content line
        else:
            # Check if line should be kept (not a CC line)
            if stripped and not any(re.search(pattern, stripped, re.IGNORECASE) for pattern in CC_PATTERNS):
                current_block.append(line)
                block_has_content = True
            # Special case: if it's a blank line between text in same block, keep it
            elif not stripped and block_has_content:
                current_block.append(line)

    # Add the last block if it has content
    if current_block and block_has_content:
        cleaned_blocks.append(current_block)

    # Rebuild the SRT content with only non-empty blocks
    output_lines = []
    for i, block in enumerate(cleaned_blocks, 1):
        output_lines.append(str(i))  # Renumber blocks
        # Keep all lines except the block number (which we just renumbered)
        output_lines.extend(block[1:])  
        output_lines.append("")  # Blank line between blocks

    cleaned_content = "\n".join(output_lines).strip()

    # Create and return the cleaned SRT file
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
    temp.write(cleaned_content)
    temp.close()

    return send_file(
        temp.name,
        as_attachment=True,
        download_name='cleaned_subtitles.srt',
        mimetype='text/srt'
    )


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

# HTML-FORM-FRIENDLY ROUTE
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

# JSON API (for fetch/XHR/AJAX)
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
