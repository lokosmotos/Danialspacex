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
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB limit
app.config['TEMPLATES_AUTO_RELOAD'] = True

# ============== MAIN ROUTES ==============
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

# ============== PROCESSING ROUTES ==============
@app.route('/process-cc-removal', methods=['POST'])
def process_cc_removal():
    if 'srtfile' not in request.files:
        return jsonify({'success': False, 'message': 'No file uploaded'}), 400
    
    file = request.files['srtfile']
    
    if not file or not file.filename.lower().endswith('.srt'):
        return jsonify({'success': False, 'message': 'Only .srt files are allowed'}), 400
    
    try:
        # Check file size
        file.seek(0, os.SEEK_END)
        file_length = file.tell()
        if file_length > app.config['MAX_CONTENT_LENGTH']:
            return jsonify({'success': False, 'message': 'File size exceeds 10MB limit'}), 400
        file.seek(0)

        content = file.read().decode('utf-8')
        cleaned_content = remove_cc(content)
        
        # Create temporary file
        temp_fd, temp_path = tempfile.mkstemp(suffix='.srt')
        try:
            with os.fdopen(temp_fd, 'w', encoding='utf-8') as temp_file:
                temp_file.write(cleaned_content)
            
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"cleaned_{secure_filename(file.filename)}",
                mimetype='text/plain'
            )
        finally:
            try:
                os.unlink(temp_path)
            except:
                pass
                
    except UnicodeDecodeError:
        return jsonify({'success': False, 'message': 'Invalid file encoding'}), 400
    except Exception as e:
        app.logger.error(f"Error processing file: {str(e)}")
        return jsonify({'success': False, 'message': 'Processing error'}), 500

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

@app.route('/process-bilingual-srt', methods=['POST'])
def process_bilingual_srt():
    if 'srtfile' not in request.files:
        return redirect('/bilingual-splitter')
    
    file = request.files['srtfile']
    if not file or not file.filename.lower().endswith('.srt'):
        return redirect('/bilingual-splitter')

    try:
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
    except Exception as e:
        app.logger.error(f"Error processing bilingual SRT: {str(e)}")
        return redirect('/bilingual-splitter')

# ============== HELPER FUNCTIONS ==============
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
            line = re.sub(r'''
                (?:♪[^♪]*♪)|          # Music symbols
                (?:"[^"]*")|          # Quoted text
                (?:\[[^\]]*\])|       # Bracketed text
                (?:\([^\)]*\))|       # Parentheses text
                (?:\{[^\}]*\})|       # Curly braces
                (?:<[^>]*>)|          # HTML tags
                (?:^\s*[-–]\s*)|      # Speaker dashes
                (?:^[A-Z]+\s*:\s*)    # Speaker labels
            ''', '', line, flags=re.VERBOSE)
            
            line = line.strip()
            if line:
                cleaned_text.append(line)

        if cleaned_text:
            cleaned_blocks.append(f"{index}\n{timecode}\n" + "\n".join(cleaned_text))

    return "\n\n".join(cleaned_blocks)

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

def is_cjk(text):
    return bool(re.search(r'[\u4E00-\u9FFF\u3040-\u30FF\u3400-\u4DBF]', text))

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
