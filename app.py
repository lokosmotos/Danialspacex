from flask import Flask, render_template, request, redirect, send_file
import os
import re
import tempfile

app = Flask(__name__)

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

@app.route('/remove-cc', methods=['POST'])
def remove_cc():
    file = request.files['srtfile']
    if file.filename.endswith('.srt'):
        content = file.read().decode('utf-8')
        cleaned_lines = []

        cc_patterns = [r"\[.*?\]", r"\(.*?\)", r"<.*?>"]

        for line in content.splitlines():
            if any(re.search(pattern, line) for pattern in cc_patterns):
                continue
            cleaned_lines.append(line)

        cleaned_content = "\n".join(cleaned_lines)

        temp = tempfile.NamedTemporaryFile(delete=False, suffix=".srt", mode='w', encoding='utf-8')
        temp.write(cleaned_content)
        temp.close()

        return send_file(temp.name, as_attachment=True, download_name='cleaned_subtitles.srt')

    return redirect('/cc-remover')

import pandas as pd
from werkzeug.utils import secure_filename

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
        srt_output.append("")  # Empty line between entries

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

    blocks = content.strip().split("\n\n")
    data = []

    for block in blocks:
        lines = block.splitlines()
        if len(lines) >= 3:
            # Format:
            # 1
            # 00:00:01,000 --> 00:00:04,000
            # Subtitle Text
            start_end = lines[1].split(' --> ')
            start_time = start_end[0].strip()
            end_time = start_end[1].strip()
            subtitle_text = ' '.join(lines[2:])  # in case of multiple lines

            data.append({
                'Start Time': start_time,
                'End Time': end_time,
                'Subtitle Text': subtitle_text
            })

    df = pd.DataFrame(data)

    temp = tempfile.NamedTemporaryFile(delete=False, suffix=".xlsx")
    df.to_excel(temp.name, index=False)

    return send_file(temp.name, as_attachment=True, download_name='converted_from_srt.xlsx')


if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
