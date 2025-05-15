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

# === MAIN ROUTES ===
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tools')
def tools():
    return render_template('index.html')  # Could be the same as index.html

@app.route('/features')
def features():
    return render_template('features.html')

@app.route('/my-list')
def my_list():
    return render_template('my_list.html')

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

@app.route('/convert-chinese', methods=['POST'])
def convert_chinese_form():
    text = request.form.get('chinese_text')
    direction = request.form.get('direction', 's2t')
    
    if not text:
        return redirect('/chinese-converter')

    converted_text, diffs = convert_chinese_variant(text, direction)

    return render_template('chinese_converter_result.html',
                         original_text=text,
                         converted_text=converted_text,
                         diffs=diffs,
                         direction=direction)

@app.route('/bilingual-splitter')
def bilingual_splitter():
    return render_template('split_bilingual.html')

# === FILE PROCESSING ROUTES ===
@app.route('/upload-chinese-srt', methods=['POST'])
def upload_chinese_srt():
    file = request.files.get('srtfile')
    if not file or not file.filename.endswith('.srt'):
        return redirect('/chinese-converter')

    content = file.read().decode('utf-8', errors='ignore')
    variant = detect_chinese_variant(content)
    direction = 's2t' if variant == 'zhs' else 't2s'
    converted_text, diffs = convert_chinese_variant(content, direction)

    return render_template('converted_chinese_result.html',
                         original=content,
                         converted=converted_text,
                         diffs=diffs,
                         direction=direction,
                         detected_variant=variant)

@app.route('/process-bilingual-srt', methods=['POST'])
def process_bilingual_srt():
    file = request.files.get('srtfile')
    if not file or not file.filename.endswith('.srt'):
        return redirect('/bilingual-splitter')

    content = file.read().decode('utf-8', errors='ignore')
    lang_blocks = split_subtitles_by_language(content)

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

@app.route('/process-cc-removal', methods=['POST'])
def process_cc_removal():
    file = request.files.get('srtfile')
    if not file or not file.filename.endswith('.srt'):
        return redirect('/cc-remover')

    content = file.read().decode('utf-8', errors='ignore')
    cleaned_content = remove_cc(content)

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
    temp.write(cleaned_content)
    temp.close()

    return send_file(temp.name, as_attachment=True, download_name='cleaned_subtitles.srt')

# === CONVERTER ROUTES ===
@app.route('/convert-excel-to-srt', methods=['POST'])
def convert_excel_to_srt():
    file = request.files.get('excelfile')
    if not file or not file.filename.endswith(('.xls', '.xlsx')):
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
    file = request.files.get('srtfile')
    if not file or not file.filename.endswith('.srt'):
        return redirect('/converter')

    content = file.read().decode('utf-8')
    pattern = re.compile(r"(\d+)\s*\n?(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})\s*\n?([^\d]+)", re.MULTILINE)
    matches = pattern.findall(content)

    data = []
    for match in matches:
        _, start, end, text = match
        data.append({
            'Start Time': start,
            'End Time': end,
            'Subtitle Text': ' '.join(text.strip().splitlines()).strip()
        })

    df = pd.DataFrame(data)
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    with pd.ExcelWriter(temp.name, engine='openpyxl') as writer:
        df.to_excel(writer, index=False)
    return send_file(temp.name, as_attachment=True, download_name='converted_from_srt.xlsx')

# === PROFANITY CHECKER ROUTES ===
@app.route('/check-profanity', methods=['POST'])
def check_profanity_route():
    file = request.files.get('file')
    if not file or not (file.filename.endswith('.srt') or file.filename.endswith('.xlsx')):
        return redirect('/profanity-checker')

    content = file.read().decode('utf-8', errors='ignore')
    profanities = check_profanity(content)

    if profanities:
        return render_template('edit_profanities.html',
                             content=content,
                             profanities=profanities,
                             original_filename=file.filename)
    return "No profanities detected"

@app.route('/final-qc', methods=['POST'])
def final_qc():
    content = request.form.get('edited_content')
    original_filename = request.form.get('original_filename')
    profanities = check_profanity(content)

    if profanities:
        return render_template('edit_profanities.html',
                             content=content,
                             profanities=profanities,
                             original_filename=original_filename,
                             message="Still contains profanity!")
    
    suffix = '.srt' if original_filename.endswith('.srt') else '.txt'
    temp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode='w', encoding='utf-8')
    temp.write(content)
    temp.close()
    return send_file(temp.name, as_attachment=True, download_name='cleaned_' + original_filename)

# === API ROUTES ===
@app.route('/api/convert-chinese', methods=['POST'])
def convert_chinese_api():
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': 'Invalid request'}), 400

    text = data.get('text')
    direction = data.get('direction', 's2t')
    converted_text, diffs = convert_chinese_variant(text, direction)

    return jsonify({
        'converted': converted_text,
        'diffs': diffs
    })

@app.route('/download-converted', methods=['POST'])
def download_converted():
    converted = request.form.get('converted')
    if not converted:
        return redirect('/chinese-converter')

    temp = tempfile.NamedTemporaryFile(delete=False, suffix='.srt', mode='w', encoding='utf-8')
    temp.write(converted)
    temp.close()
    return send_file(temp.name, as_attachment=True, download_name='converted_chinese.srt')

# === HELPER FUNCTIONS ===
def is_cjk(text):
    return bool(re.search(r'[\u4E00-\u9FFF\u3040-\u30FF\u3400-\u4DBF]', text))

def split_subtitles_by_language(content):
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
                lang = 'zh' if is_cjk(line) else 'unknown'

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

def remove_cc(content):
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
            line = re.sub(r'♪.*?♪', '', line)
            line = re.sub(r'"[^"]*"', '', line)
            line = re.sub(r'\[.*?\]', '', line)
            line = re.sub(r'\(.*?\)', '', line)
            line = re.sub(r'<.*?>', '', line)

            if line.strip():
                cleaned_text.append(line.strip())

        if cleaned_text:
            cleaned_blocks.append(f"{index}\n{timecode}\n" + "\n".join(cleaned_text))

    return "\n\n".join(cleaned_blocks)

def detect_chinese_variant(text):
    simplified_chars = "爱边陈当发干国红黄鸡开来马内齐时体为习"
    traditional_chars = "愛邊陳當發幹國紅黃雞開來馬內齊時體為習"
    simp_score = sum(char in simplified_chars for char in text)
    trad_score = sum(char in traditional_chars for char in text)
    return "zhs" if simp_score > trad_score else "zht" if trad_score > simp_score else "unknown"

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

def load_profanity_list():
    with open('static/profanity_list.json', 'r', encoding='utf-8') as file:
        return json.load(file)

def check_profanity(content):
    profanity_list = load_profanity_list()
    patterns = [re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE) for word in profanity_list]
    detected = []

    for line_num, line in enumerate(content.splitlines(), start=1):
        for pattern, word in zip(patterns, profanity_list):
            if pattern.search(line):
                detected.append({
                    'line_number': line_num,
                    'line_text': line.strip(),
                    'profanity': word
                })
    return detected

def highlight_differences(orig, conv):
    result = ""
    for o, c in zip(orig, conv):
        if o == c:
            result += c
        else:
            result += f'<span class="text-red-500">{c}</span>'
    # Add any extra characters in converted if longer
    if len(conv) > len(orig):
        result += ''.join(f'<span class="text-red-500">{c}</span>' for c in conv[len(orig):])
    return result

def upload_chinese_srt():
    # ... your existing code to get original, converted, diffs ...

    # Example: diffs = [(original_line, converted_line), ...]
    highlighted_diffs = []
    for original_line, converted_line in diffs:
        highlighted_line = highlight_differences(original_line, converted_line)
        highlighted_diffs.append({
            "original": original_line,
            "highlighted": highlighted_line
        })

    return render_template('converted_chinese_result.html',
                           detected_variant=detected_variant,
                           direction=direction,
                           original=original,
                           converted=converted,
                           highlighted_diffs=highlighted_diffs)


# === RUN APPLICATION ===
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=True)
