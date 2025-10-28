import os
import re
import tempfile
import json
import pandas as pd
import zipfile
from io import BytesIO
from flask import Flask, render_template, request, redirect, send_file, jsonify
from werkzeug.utils import secure_filename
from opencc import OpenCC
from langdetect import detect, LangDetectException

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key')

# ======================
# MAIN ROUTES
# ======================

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/tools')
def tools():
    return render_template('tools.html')

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

@app.route('/bilingual-splitter')
def bilingual_splitter():
    return render_template('split_bilingual.html')

# ======================
# FILE PROCESSING ROUTES
# ======================

@app.route('/process-cc-removal', methods=['POST'])
def process_cc_removal():
    if 'srtfile' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['srtfile']
    if not file or not allowed_file(file.filename, {'srt'}):
        return jsonify({'error': 'Invalid file type'}), 400

    try:
        content = file.read().decode('utf-8')
        cleaned = remove_cc(content)
        return send_srt_as_download(cleaned, f"cleaned_{secure_filename(file.filename)}")
    except Exception as e:
        app.logger.error(f"CC Removal Error: {str(e)}")
        return jsonify({'error': 'Processing failed'}), 500

@app.route('/convert-excel-to-srt', methods=['POST'])
def convert_excel_to_srt():
    if 'excelfile' not in request.files:
        return redirect('/converter')
    
    file = request.files['excelfile']
    if not file or not allowed_file(file.filename, {'xls', 'xlsx'}):
        return redirect('/converter')

    try:
        df = pd.read_excel(file)
        srt_content = excel_to_srt(df)
        return send_srt_as_download(srt_content, "converted.srt")
    except Exception as e:
        app.logger.error(f"Excel to SRT Error: {str(e)}")
        return redirect('/converter')

@app.route('/convert-srt-to-excel', methods=['POST'])
def convert_srt_to_excel():
    if 'srtfile' not in request.files:
        return redirect('/converter')
    
    file = request.files['srtfile']
    if not file or not allowed_file(file.filename, {'srt'}):
        return redirect('/converter')

    try:
        content = file.read().decode('utf-8')
        df = srt_to_excel(content)
        return send_excel_as_download(df, "converted.xlsx")
    except Exception as e:
        app.logger.error(f"SRT to Excel Error: {str(e)}")
        return redirect('/converter')

# ======================
# CHINESE CONVERSION
# ======================

@app.route('/convert-chinese', methods=['POST'])
def convert_chinese_form():
    text = request.form.get('chinese_text', '')
    direction = request.form.get('direction', 's2t')
    
    if not text.strip():
        return redirect('/chinese-converter')

    converted_text, diffs = convert_chinese_variant(text, direction)
    return render_template('chinese_converter_result.html',
                         original_text=text,
                         converted_text=converted_text,
                         diffs=diffs,
                         direction=direction)

@app.route('/upload-chinese-srt', methods=['POST'])
def upload_chinese_srt():
    if 'srtfile' not in request.files:
        return redirect('/chinese-converter')
    
    file = request.files['srtfile']
    if not file or not allowed_file(file.filename, {'srt'}):
        return redirect('/chinese-converter')

    try:
        content = file.read().decode('utf-8')
        variant = detect_chinese_variant(content)
        direction = 's2t' if variant == 'zhs' else 't2s'
        converted, diffs = convert_chinese_variant(content, direction)
        
        highlighted_diffs = [{
            'original': orig,
            'highlighted': highlight_differences(orig, conv)
        } for orig, conv in diffs]

        return render_template('converted_chinese_result.html',
                            original=content,
                            converted=converted,
                            highlighted_diffs=highlighted_diffs,
                            direction=direction,
                            detected_variant=variant)
    except Exception as e:
        app.logger.error(f"Chinese Conversion Error: {str(e)}")
        return redirect('/chinese-converter')

# ======================
# PROFANITY CHECKER
# ======================

@app.route('/check-profanity', methods=['POST'])
def check_profanity_route():
    if 'file' not in request.files:
        return redirect('/profanity-checker')
    
    file = request.files['file']
    if not file or not allowed_file(file.filename, {'srt', 'txt'}):
        return redirect('/profanity-checker')

    try:
        content = file.read().decode('utf-8')
        profanities = check_profanity(content)
        
        if profanities:
            return render_template('edit_profanities.html',
                                content=content,
                                profanities=profanities,
                                original_filename=file.filename)
        return render_template('profanity_checker.html', message="No profanities found!")
    except Exception as e:
        app.logger.error(f"Profanity Check Error: {str(e)}")
        return redirect('/profanity-checker')

# ======================
# HELPER FUNCTIONS
# ======================

def allowed_file(filename, allowed_extensions):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in allowed_extensions

def send_srt_as_download(content, filename):
    fd, path = tempfile.mkstemp(suffix='.srt')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as tmp:
            tmp.write(content)
        return send_file(path, as_attachment=True, download_name=filename)
    finally:
        try:
            os.unlink(path)
        except:
            pass

def send_excel_as_download(df, filename):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Subtitles')
    output.seek(0)
    return send_file(
        output,
        as_attachment=True,
        download_name=filename,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )

def remove_cc(content):
    blocks = content.strip().split('\n\n')
    cleaned_blocks = []
    
    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) < 3:
            continue
            
        index = lines[0]
        timecode = lines[1]
        text_lines = [re.sub(r'\(.*?\)|\[.*?\]|\{.*?\}|<.*?>|♪.*?♪|^[A-Z]+:\s*', '', line).strip() 
                     for line in lines[2:]]
        text_lines = [line for line in text_lines if line]
        
        if text_lines:
            cleaned_blocks.append(f"{index}\n{timecode}\n" + "\n".join(text_lines))
    
    return "\n\n".join(cleaned_blocks)

def excel_to_srt(df):
    srt_lines = []
    for i, row in df.iterrows():
        srt_lines.extend([
            str(i+1),
            f"{row['Start Time']} --> {row['End Time']}",
            str(row['Subtitle Text']),
            ""
        ])
    return "\n".join(srt_lines)

def srt_to_excel(content):
    """
    Converts .srt subtitle text to a pandas DataFrame
    """
    # Normalize line endings
    content = content.replace('\r\n', '\n').strip()
    blocks = re.split(r'\n\s*\n', content)
    data = []

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
            # Expecting structure like:
            # 1
            # 00:00:01,000 --> 00:00:04,000
            # Hello world
            time_line = lines[1]
            if '-->' not in time_line:
                continue
            start, end = [t.strip() for t in time_line.split('-->')]
            text = " ".join(lines[2:])
            data.append({
                'Start Time': start,
                'End Time': end,
                'Subtitle Text': text
            })
    
    df = pd.DataFrame(data)
    return df

def detect_chinese_variant(text):
    simplified = "爱边陈当发干国红黄鸡开来马内齐时体为习"
    traditional = "愛邊陳當發幹國紅黃雞開來馬內齊時體為習"
    simp_count = sum(1 for char in text if char in simplified)
    trad_count = sum(1 for char in text if char in traditional)
    return 'zhs' if simp_count > trad_count else 'zht'

def convert_chinese_variant(text, direction='s2t'):
    cc = OpenCC(direction)
    converted = cc.convert(text)
    diffs = [(orig, conv) for orig, conv in zip(text.splitlines(), converted.splitlines()) if orig != conv]
    return converted, diffs

def highlight_differences(orig, conv):
    result = []
    for o, c in zip(orig, conv):
        if o == c:
            result.append(c)
        else:
            result.append(f'<span class="text-red-500">{c}</span>')
    return ''.join(result)

def check_profanity(content):
    try:
        with open('static/profanity_list.json', 'r', encoding='utf-8') as f:
            profanity_list = json.load(f)
    except:
        profanity_list = ["bad", "word"]  # Fallback list
    
    profanities = []
    for line_num, line in enumerate(content.splitlines(), 1):
        for word in profanity_list:
            if re.search(r'\b' + re.escape(word) + r'\b', line, re.IGNORECASE):
                profanities.append({
                    'line_number': line_num,
                    'line_text': line,
                    'profanity': word
                })
    return profanities

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
