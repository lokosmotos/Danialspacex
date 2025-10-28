import os
import re
import tempfile
import json
import pandas as pd
import zipfile
from io import BytesIO
from flask import Flask, render_template, request, redirect, send_file, jsonify, send_from_directory
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
# PROFANITY CHECKER API ROUTES
# ======================

@app.route('/static/profanity_list.json')
def serve_profanity_list():
    """Serve the profanity list JSON file"""
    try:
        return send_from_directory('static', 'profanity_list.json')
    except FileNotFoundError:
        # Return a default list if file doesn't exist
        default_list = {
            "words": [
                {"word": "hell", "severity": "low"},
                {"word": "damn", "severity": "low"},
                {"word": "bitch", "severity": "medium"},
                {"word": "ass", "severity": "medium"},
                {"word": "fuck", "severity": "high"},
                {"word": "shit", "severity": "high"},
                {"word": "crap", "severity": "low"},
                {"word": "asshole", "severity": "medium"},
                {"word": "bastard", "severity": "medium"},
                {"word": "dick", "severity": "medium"},
                {"word": "piss", "severity": "medium"},
                {"word": "cunt", "severity": "high"},
                {"word": "dickhead", "severity": "medium"}
            ]
        }
        return jsonify(default_list)

@app.route('/api/check-profanity', methods=['POST'])
def api_check_profanity():
    """API endpoint for profanity checking"""
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['file']
    if not file or not allowed_file(file.filename, {'srt', 'txt'}):
        return jsonify({'error': 'Invalid file type. Please upload SRT or TXT files.'}), 400

    try:
        content = file.read().decode('utf-8')
        results = analyze_profanity_content(content)
        
        return jsonify({
            'success': True,
            'filename': file.filename,
            'results': results,
            'total_profanities': len(results),
            'severity_counts': count_severities(results)
        })
        
    except Exception as e:
        app.logger.error(f"Profanity Check Error: {str(e)}")
        return jsonify({'error': f'Processing failed: {str(e)}'}), 500

@app.route('/api/generate-cleaned-srt', methods=['POST'])
def generate_cleaned_srt():
    """Generate cleaned SRT file with replacements"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        original_content = data.get('original_content', '')
        replacements = data.get('replacements', {})
        filename = data.get('filename', 'cleaned_subtitles.srt')
        
        if not original_content:
            return jsonify({'error': 'No content provided'}), 400
            
        cleaned_content = apply_profanity_replacements(original_content, replacements)
        
        # Create temporary file for download
        fd, temp_path = tempfile.mkstemp(suffix='.srt')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as tmp:
                tmp.write(cleaned_content)
            
            return send_file(
                temp_path,
                as_attachment=True,
                download_name=f"cleaned_{secure_filename(filename)}",
                mimetype='text/plain'
            )
        finally:
            try:
                os.unlink(temp_path)
            except:
                pass
                
    except Exception as e:
        app.logger.error(f"Generate Cleaned SRT Error: {str(e)}")
        return jsonify({'error': f'Failed to generate cleaned file: {str(e)}'}), 500

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
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['excelfile']
    if not file or not allowed_file(file.filename, {'xls', 'xlsx'}):
        return jsonify({'error': 'Invalid file type. Please upload Excel files (.xls, .xlsx)'}), 400

    try:
        df = pd.read_excel(file)
        srt_content = excel_to_srt(df)
        return send_srt_as_download(srt_content, f"converted_{secure_filename(file.filename.replace('.xlsx', '').replace('.xls', ''))}.srt")
    except Exception as e:
        app.logger.error(f"Excel to SRT Error: {str(e)}")
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

@app.route('/convert-srt-to-excel', methods=['POST'])
def convert_srt_to_excel():
    if 'srtfile' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400
    
    file = request.files['srtfile']
    if not file or not allowed_file(file.filename, {'srt'}):
        return jsonify({'error': 'Invalid file type. Please upload SRT files'}), 400

    try:
        content = file.read().decode('utf-8')
        df = srt_to_excel(content)
        return send_excel_as_download(df, f"converted_{secure_filename(file.filename.replace('.srt', ''))}.xlsx")
    except Exception as e:
        app.logger.error(f"SRT to Excel Error: {str(e)}")
        return jsonify({'error': f'Conversion failed: {str(e)}'}), 500

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
# PROFANITY CHECKER (Legacy - for template rendering)
# ======================

@app.route('/check-profanity', methods=['POST'])
def check_profanity_route():
    """Legacy route for template-based profanity checker"""
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
    output = BytesIO()
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
    """Converts .srt subtitle text to a pandas DataFrame"""
    content = content.replace('\r\n', '\n').strip()
    blocks = re.split(r'\n\s*\n', content)
    data = []

    for block in blocks:
        lines = block.strip().split('\n')
        if len(lines) >= 3:
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
    
    return pd.DataFrame(data)

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
    """Legacy profanity checker for template rendering"""
    try:
        with open('static/profanity_list.json', 'r', encoding='utf-8') as f:
            profanity_data = json.load(f)
            profanity_list = profanity_data.get('words', [word['word'] for word in profanity_data] if isinstance(profanity_data, list) else [])
    except:
        profanity_list = ["bad", "word"]  # Fallback list
    
    profanities = []
    for line_num, line in enumerate(content.splitlines(), 1):
        for word in profanity_list:
            word_text = word if isinstance(word, str) else word.get('word', '')
            if word_text and re.search(r'\b' + re.escape(word_text) + r'\b', line, re.IGNORECASE):
                profanities.append({
                    'line_number': line_num,
                    'line_text': line,
                    'profanity': word_text
                })
    return profanities

def analyze_profanity_content(content):
    """Enhanced profanity analysis for API"""
    try:
        with open('static/profanity_list.json', 'r', encoding='utf-8') as f:
            profanity_data = json.load(f)
            # Handle both array and object formats
            if isinstance(profanity_data, list):
                profanity_words = [{'word': item['word'], 'severity': item.get('severity', 'high')} for item in profanity_data if 'word' in item]
            else:
                profanity_words = profanity_data.get('words', [])
    except Exception as e:
        app.logger.error(f"Error loading profanity list: {str(e)}")
        # Fallback list
        profanity_words = [
            {"word": "hell", "severity": "low"},
            {"word": "damn", "severity": "low"},
            {"word": "bitch", "severity": "medium"},
            {"word": "ass", "severity": "medium"},
            {"word": "fuck", "severity": "high"},
            {"word": "shit", "severity": "high"}
        ]
    
    blocks = parse_srt_blocks(content)
    results = []
    
    for block in blocks:
        profanities_in_block = []
        
        for profanity in profanity_words:
            word = profanity['word']
            severity = profanity.get('severity', 'high')
            regex = re.compile(r'\b' + re.escape(word) + r'\b', re.IGNORECASE)
            
            for match in regex.finditer(block['text']):
                profanities_in_block.append({
                    'word': match.group(),
                    'index': match.start(),
                    'length': len(match.group()),
                    'severity': severity,
                    'id': f"{block['number']}-{match.start()}-{word}"
                })
        
        if profanities_in_block:
            # Determine overall block severity
            severities = [p['severity'] for p in profanities_in_block]
            block_severity = 'high' if 'high' in severities else 'medium' if 'medium' in severities else 'low'
            
            results.append({
                'block_number': block['number'],
                'timecodes': block['timecodes'],
                'text': block['text'],
                'profanities': profanities_in_block,
                'severity': block_severity
            })
    
    return results

def parse_srt_blocks(content):
    """Parse SRT content into blocks"""
    blocks = []
    content = content.replace('\r\n', '\n').strip()
    block_texts = content.split('\n\n')
    
    for block_text in block_texts:
        lines = [line.strip() for line in block_text.split('\n') if line.strip()]
        if len(lines) < 3:
            continue
            
        try:
            number = int(lines[0])
            timecodes = lines[1]
            text = '\n'.join(lines[2:])
            
            blocks.append({
                'number': number,
                'timecodes': timecodes,
                'text': text
            })
        except (ValueError, IndexError):
            continue
    
    return blocks

def count_severities(results):
    """Count profanities by severity"""
    counts = {'high': 0, 'medium': 0, 'low': 0}
    for result in results:
        for profanity in result['profanities']:
            counts[profanity['severity']] += 1
    return counts

def apply_profanity_replacements(content, replacements):
    """Apply profanity replacements to content"""
    blocks = parse_srt_blocks(content)
    
    for block in blocks:
        block_number = block['number']
        if str(block_number) in replacements:
            block_text = block['text']
            # Apply replacements (this would need to be more sophisticated)
            for find_word, replace_word in replacements[str(block_number)].items():
                block_text = re.sub(r'\b' + re.escape(find_word) + r'\b', replace_word, block_text, flags=re.IGNORECASE)
            
            # Update the content
            old_block = f"{block_number}\n{block['timecodes']}\n{block['text']}"
            new_block = f"{block_number}\n{block['timecodes']}\n{block_text}"
            content = content.replace(old_block, new_block)
    
    return content

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
