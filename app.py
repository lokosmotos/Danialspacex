from flask import Flask, render_template, request, redirect, send_file, jsonify
import os
import re
import tempfile
import json
import pandas as pd
from werkzeug.utils import secure_filename
from opencc import OpenCC
import difflib

app = Flask(__name__)

# ==================== Chinese Conversion Support ====================
SIMPLIFIED_CHARS = set("的一是在不了有和人这中大为上个国我以要他时来用们生到作地于出就分对成会可主发年动同工也能下过子说产种面而方后多定行学法所民得经十三之进着等部度家电力里如水化高自二理起小物现实加量都两体制机当使点从业本去把性好应开它合还因由其些然前外天政四日那社义事平形相全表间样与关各重新线内数正心反你明看原又么利比或但质气第向道命此变条只没结解问意建月公无系军很情者最立代想已通并提直题党程展五果料象员革位入常文总次品式活设及管特件长求老头基资边流路级少图山统接知较将组见计别她手角期根论运农指几九区强放决西被干做必战先回则任取据处队南给色光门即保治北造百规热领七海口东导器压志世金增争济阶油思术极交受联什认六共权收证改清己美再采转更单风切打白教速花带安场身车例真务具万每目至达走积示议声报斗完类八离华名确才科张信马节话米整空元况今集温传土许步群广石记需段研界拉林律叫且究观越织装影算低持音众书布复容儿须际商非验连断深难近矿千周委素技备半办青省列习响约支般史感劳便团往酸历市克何除消构府太准精值号率族维划选标写存候毛亲快效斯院查江型眼王按格养易置派层片始却专状育厂京识适属圆包火住调满县局照参红细引听该铁价严龙飞")
TRADITIONAL_CHARS = set("的一是在不了有和人這中大為上個國我以要他時來用們生到作地於出就分對成會可主發年動同工也能下過子說產種面而方後多定行學法所民得經十三之進著等部度家電力裡如水化高自二理起小物現實加量都兩體制機當使點從業本去把性好應開它合還因由其些然前外天政四日那社義事平形相全表間樣與關各重新線內數正心反你明看原又麼利比或但質氣第向道命此變條只沒結解問意建月公無系軍很情者最立代想已通並提直題黨程展五果料象員革位入常文總次品式活設及管特件長求老頭基資邊流路級少圖山統接知較將組見計別她手角期根論運農指幾九區強放決西被幹做必戰先回則任取據處隊南給色光門即保治北造百規熱領七海口東導器壓誌世金增爭濟階油思術極交受聯什認六共權收證改清己美再採轉更單風切打白教速花帶安場身車例真務具萬每目至達走積示議聲報鬥完類八離華名確才科張信馬節話米整空元況今集溫傳土許步群廣石記需段研界拉林律叫且究觀越織裝影算低持音眾書布復容兒須際商非驗連斷深難近礦千週委素技備半辦青省列習響約支般史感勞便團往酸歷市克何除消構府太準精值號率族維劃選標寫存候毛親快效斯院查江型眼王按格養易置派層片始卻專狀育廠京識適屬圓包火住調滿縣局照參紅細引聽該鐵價嚴龍飛")

def detect_chinese_variant(text):
    """Detect if text is Simplified (zhs) or Traditional (zht) Chinese"""
    simp_count = sum(1 for char in text if char in SIMPLIFIED_CHARS)
    trad_count = sum(1 for char in text if char in TRADITIONAL_CHARS)
    
    total = simp_count + trad_count
    if total == 0:
        return 'unknown'
    
    ratio = simp_count / total
    if ratio > 0.7:
        return 'zhs'
    elif ratio < 0.3:
        return 'zht'
    else:
        return 'mixed'

def convert_chinese(text, direction):
    """Convert between Simplified and Traditional Chinese"""
    converter = OpenCC('s2t.json') if direction == 's2t' else OpenCC('t2s.json')
    return converter.convert(text)

# ==================== Routes ====================
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/chinese-converter')
def chinese_converter():
    return render_template('chinese_converter.html')

@app.route('/convert-chinese', methods=['POST'])
def handle_chinese_conversion():
    if 'file' not in request.files:
        return redirect('/chinese-converter')
    
    file = request.files['file']
    if not file.filename.lower().endswith('.srt'):
        return redirect('/chinese-converter')
    
    content = file.read().decode('utf-8')
    variant = detect_chinese_variant(content)
    target = request.form.get('target')
    
    # If automatic detection is uncertain
    if variant in ['unknown', 'mixed'] and not target:
        return render_template('chinese_confirm.html', 
                             content_sample=content[:500],
                             filename=file.filename)
    
    # Determine conversion direction
    if not target:
        target = 't2s' if variant == 'zht' else 's2t'
    
    # Perform conversion
    converted = convert_chinese(content, target)
    
    # Save to temp file
    with tempfile.NamedTemporaryFile(delete=False, mode='w', encoding='utf-8', suffix='.srt') as temp:
        temp.write(converted)
        temp_path = temp.name
    
    return send_file(temp_path, as_attachment=True, download_name=f'converted_{file.filename}')

# [Keep all your existing routes (cc-remover, converter, profanity-checker) exactly as they are]

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
