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

@app.route('/split-bilingual', methods=['GET', 'POST'])
def split_bilingual():
    if request.method == 'GET':
        return render_template('split_bilingual.html')

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
from flask import Flask, render_template, request, send_file, redirect
from langdetect import detect, LangDetectException
from io import BytesIO
import zipfile
import re
import os

app = Flask(__name__)

@app.route('/')
def home():
    return render_template('split_bilingual.html')

@app.route('/split-bilingual', methods=['GET', 'POST'])
def split_bilingual():
    if request.method == 'GET':
        return render_template('split_bilingual.html')

    file = request.files.get('srtfile')
    if not file or not file.filename.endswith('.srt'):
        return redirect('/split-bilingual')

    content = file.read().decode('utf-8', errors='ignore')
    lang_blocks = split_subtitles_by_language(content)

    # Renumber and compile each language file
    zip_buffer = BytesIO()
    with zipfile.ZipFile(zip_buffer, 'a', zipfile.ZIP_DEFLATED, False) as zip_file:
        for lang, blocks in lang_blocks.items():
            renumbered = renumber_subtitles('\n\n'.join(blocks))
            zip_file.writestr(f'{lang}.srt', renumbered.encode('utf-8'))

    zip_buffer.seek(0)
    return send_file(
        zip_buffer,
        mimetype='application/zip',
        as_attachment=True,
        download_name='separated_languages.zip'
    )

# ================================
# 📦 HELPER FUNCTIONS
# ================================

def is_cjk(text):
    return bool(re.search(r'[\u4E00-\u9FFF\u3040-\u30FF\u3400-\u4DBF]', text))

def split_subtitles_by_language(content):
    """Splits a bilingual SRT file into blocks by detected language"""
    blocks = content.strip().split('\n\n')
    lang_blocks = {}

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
        block_number = lines[0].strip()
        time_line = lines[1].strip()
        text_lines = lines[2:]

        text_by_lang = {}

        for line in text_lines:
            line = line.strip()
            if not line:
                continue

            try:
                lang = detect(line)
            except LangDetectException:
                if is_cjk(line):
                    lang = 'zh'
                else:
                    lang = 'unknown'

            if lang not in text_by_lang:
                text_by_lang[lang] = []
            text_by_lang[lang].append(line)

        for lang, lang_lines in text_by_lang.items():
            srt_block = f"{block_number}\n{time_line}\n" + "\n".join(lang_lines)
            if lang not in lang_blocks:
                lang_blocks[lang] = []
            lang_blocks[lang].append(srt_block)

    return lang_blocks

def renumber_subtitles(content):
    """Renumber subtitles sequentially from content string"""
    blocks = content.strip().split('\n\n')
    new_blocks = []
    count = 1
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 2:
            continue
        time_line = lines[1]
        text_lines = lines[2:]
        new_block = f"{count}\n{time_line}\n" + "\n".join(text_lines)
        new_blocks.append(new_block)
        count += 1
    return '\n\n'.join(new_blocks)


# === CC REMOVER ===
# === CC REMOVER ===
def remove_cc():
    file = request.files['srtfile']
    if file.filename.endswith('.srt'):
        content = file.read().decode('utf-8')
 
        blocks = content.strip().split('\n\n')
        cleaned_blocks = []
 
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) < 3:
                continue
 
            index = lines[0]
            timecode = lines[1]
            text_lines = lines[2:]
 
            cleaned_text = []
            for line in text_lines:
                original_line = line.strip()
 
                # Remove quoted phrases and musical notes
                line = re.sub(r'♪.*?♪', '', line)
                line = re.sub(r'"[^"]*"', '', line)
                line = re.sub(r'\[.*?\]', '', line)
                line = re.sub(r'\(.*?\)', '', line)
                line = re.sub(r'<.*?>', '', line)
 
                # Remove if line is now empty or whitespace
                if line.strip():
                    cleaned_text.append(line.strip())
 
            # Only include block if there's remaining text
            if cleaned_text:
                cleaned_block = f"{index}\n{timecode}\n" + "\n".join(cleaned_text)
                cleaned_blocks.append(cleaned_block)
 
        cleaned_content = "\n\n".join(cleaned_blocks)
 
        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
        temp.write(cleaned_content)
        temp.close()
 
        return send_file(temp.name, as_attachment=True, download_name='cleaned_subtitles.srt')
 
    return redirect('/cc-remover')


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
