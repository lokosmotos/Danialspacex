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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
