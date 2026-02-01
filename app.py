import os
import uuid
import requests
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import warnings
import traceback

# إخفاء التحذيرات
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=DeprecationWarning)

from dotenv import load_dotenv
import google.generativeai as genai
from flask import Flask, render_template, request, send_file

from fpdf import FPDF
from fpdf.enums import XPos, YPos
import arabic_reshaper
from bidi.algorithm import get_display

# ================== Config ==================
load_dotenv()
API_KEY = os.getenv("GEMINI_API_KEY") 
genai.configure(api_key=API_KEY)

app = Flask(__name__)
GEMINI_TIMEOUT_SECONDS = 90

# ================== Auto-Download Fonts Helper ==================
def check_and_download_fonts():
    fonts = {
        "Amiri-Regular.ttf": "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Regular.ttf",
        "Amiri-Bold.ttf": "https://github.com/google/fonts/raw/main/ofl/amiri/Amiri-Bold.ttf"
    }
    for font_name, url in fonts.items():
        if not os.path.exists(font_name):
            try:
                response = requests.get(url)
                if response.status_code == 200:
                    with open(font_name, 'wb') as f:
                        f.write(response.content)
            except:
                pass

check_and_download_fonts()

# ================== Arabic Text Helper ==================
def ar(text):
    if not text or not isinstance(text, str):
        return ""
    try:
        reshaped = arabic_reshaper.reshape(text)
        return get_display(reshaped)
    except:
        return text

# ================== Safe Wrapping Helper (Arabic) ==================
def get_wrapped_lines(pdf, text, max_width_mm, font_size=12):
    try:
        pdf.set_font('Amiri', '', font_size)
    except:
        return [text]

    words = text.split()
    lines = []
    current_line = []
    effective_width = max_width_mm 

    for word in words:
        test_line_words = current_line + [word]
        test_string = " ".join(test_line_words)
        reshaped_test = ar(test_string)
        
        if pdf.get_string_width(reshaped_test) <= effective_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(ar(" ".join(current_line)))
            current_line = [word]
            if pdf.get_string_width(ar(word)) > effective_width:
                lines.append(ar(word))
                current_line = []

    if current_line:
        lines.append(ar(" ".join(current_line)))
    return lines

# ================== English Wrapping Helper ==================
def get_english_wrapped_lines(pdf, text, max_width_mm, font_size=11):
    pdf.set_font("Arial", "", font_size)
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        if pdf.get_string_width(test_line) <= max_width_mm:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines

# ================== Pro Table Drawers ==================
def draw_smart_table_row(pdf, title, content_points):
    if not content_points: return

    col_title_width = 45
    col_content_width = 145 
    padding_top = 4
    line_height = 8
    padding_x = 3

    final_lines_to_print = []
    for point in content_points:
        clean = point.strip().replace('-', '').replace('•', '').replace('*', '').strip()
        if len(clean) > 0 and clean[0].isdigit():
             clean = clean.lstrip('0123456789.- ').strip()
        if not clean: continue
        wrapped = get_wrapped_lines(pdf, "• " + clean, col_content_width - (padding_x*2), 12)
        final_lines_to_print.extend(wrapped)

    total_row_height = (len(final_lines_to_print) * line_height) + (padding_top * 2)
    if total_row_height < 20: total_row_height = 20
    if pdf.get_y() + total_row_height > 275: pdf.add_page()

    start_y = pdf.get_y()
    x_title = 155
    x_content = 10 

    pdf.set_fill_color(253, 245, 230)
    pdf.set_draw_color(184, 134, 11)
    pdf.set_line_width(0.3)
    pdf.rect(x_title, start_y, col_title_width, total_row_height, 'FD')
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(x_content, start_y, col_content_width, total_row_height, 'FD')

    try: pdf.set_font('AmiriB', '', 13)
    except: 
        try: pdf.set_font('Amiri', '', 13)
        except: pass
            
    pdf.set_text_color(101, 67, 33)
    pdf.set_xy(x_title, start_y + (total_row_height/2) - 3)
    pdf.cell(col_title_width, 6, ar(title), 0, 0, 'C')

    try: pdf.set_font('Amiri', '', 12)
    except: pass
    pdf.set_text_color(40, 40, 40)
    
    cur_y = start_y + padding_top
    for line in final_lines_to_print:
        pdf.set_xy(x_content + padding_x, cur_y)
        pdf.cell(col_content_width - (padding_x*2), line_height, line, 0, 0, 'R')
        cur_y += line_height

    pdf.set_y(start_y + total_row_height)
    pdf.ln(3)

def draw_styled_english_row(pdf, title, content_points):
    if not content_points: return

    col_title_width = 45  
    col_content_width = 145 
    padding_top = 4
    line_height = 7
    padding_x = 3

    final_lines_to_print = []
    for point in content_points:
        clean = point.strip().replace('-', '').replace('•', '').replace('*', '').strip()
        if not clean: continue
        bullet_text = "- " + clean
        wrapped = get_english_wrapped_lines(pdf, bullet_text, max_width_mm=col_content_width - (padding_x*2), font_size=11)
        final_lines_to_print.extend(wrapped)

    total_row_height = (len(final_lines_to_print) * line_height) + (padding_top * 2)
    if total_row_height < 20: total_row_height = 20
    if pdf.get_y() + total_row_height > 275: pdf.add_page()

    start_y = pdf.get_y()
    x_title = 10
    x_content = 55 

    pdf.set_fill_color(253, 245, 230)
    pdf.set_draw_color(184, 134, 11)
    pdf.set_line_width(0.3)
    pdf.rect(x_title, start_y, col_title_width, total_row_height, 'FD')
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(x_content, start_y, col_content_width, total_row_height, 'FD')

    pdf.set_font("Arial", "B", 12)
    pdf.set_text_color(101, 67, 33)
    
    title_words = title.split()
    if len(title) > 15 and len(title_words) > 1:
        pdf.set_xy(x_title, start_y + (total_row_height/2) - 4)
        pdf.multi_cell(col_title_width, 5, title, align='C')
    else:
        pdf.set_xy(x_title, start_y + (total_row_height/2) - 2.5)
        pdf.cell(col_title_width, 5, title, 0, 0, 'C')

    pdf.set_font("Arial", "", 11)
    pdf.set_text_color(50, 50, 50)
    cur_y = start_y + padding_top
    for line in final_lines_to_print:
        pdf.set_xy(x_content + padding_x, cur_y)
        pdf.cell(col_content_width - (padding_x*2), line_height, line, 0, 0, 'L')
        cur_y += line_height

    pdf.set_y(start_y + total_row_height)
    pdf.ln(3)

def draw_overall_badge(pdf, level_text, x, y, lang='ar'):
    # Clean Text
    level = level_text.replace('%', '').strip()
    
    # Dynamic Color based on Level
    # Gold for High/Creative
    if any(w in level for w in ['High', 'مبدع', 'متميز', 'Excellent']):
        pdf.set_fill_color(184, 134, 11) 
    # Silver for Medium/Advanced
    elif any(w in level for w in ['Medium', 'متقدم', 'Good', 'جيد']):
        pdf.set_fill_color(192, 192, 192) 
    # Bronze/Orange for Low/Needs Help
    else:
        pdf.set_fill_color(205, 127, 50) 

    pdf.set_draw_color(101, 67, 33)
    pdf.set_line_width(0.5)
    pdf.circle(x, y, 15, 'FD')
    
    # Title
    pdf.set_text_color(101, 67, 33)
    if lang == 'ar':
        try: pdf.set_font('AmiriB', '', 11)
        except: pdf.set_font('Arial', 'B', 10)
        title = ar("المستوى العام")
    else:
        pdf.set_font('Arial', 'B', 9)
        title = "Overall Level"
        
    pdf.set_xy(x - 15, y - 24)
    pdf.cell(30, 6, title, 0, 0, 'C')

    # Level Text inside circle
    pdf.set_text_color(255, 255, 255)
    
    # Dynamic Font Size for Text
    font_size = 14
    if len(level) > 6: font_size = 10
    elif len(level) > 4: font_size = 12
    
    if lang == 'ar':
        try: pdf.set_font('AmiriB', '', font_size)
        except: pass
        level_display = ar(level)
    else:
        pdf.set_font('Arial', 'B', font_size)
        level_display = level

    pdf.set_xy(x - 15, y - 5)
    pdf.cell(30, 10, level_display, 0, 0, 'C')

# ================== PDF Classes ==================
class BasePDF(FPDF):
    def draw_frame(self):
        self.set_draw_color(101, 67, 33)
        self.set_line_width(0.6)
        self.rect(5, 5, 200, 287)
    def draw_logo(self):
        if os.path.exists('static/logo.png'):
            self.image('static/logo.png', 170, 8, 25)

class ArabicPDF(BasePDF):
    def header(self):
        self.draw_frame(); self.draw_logo()
        try:
            self.add_font('Amiri', '', os.path.abspath('Amiri-Regular.ttf'))
            self.add_font('AmiriB', '', os.path.abspath('Amiri-Bold.ttf'))
        except: pass
        try: self.set_font('AmiriB', '', 18)
        except: self.set_font('Arial', 'B', 16)
        
        self.set_text_color(101, 67, 33)
        self.cell(0, 10, ar("مدارس قدرات الأجيال العالمية"), 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        try: self.set_font('Amiri', '', 14)
        except: pass
        self.set_text_color(184, 134, 11)
        self.cell(0, 8, ar("نظام التقييم الصوتي الذكي"), 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        try: self.set_font('Amiri', '', 10)
        except: self.set_font('Arial', '', 10)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, ar(f"صفحة {self.page_no()}"), 0, align='C')

class EnglishPDF(BasePDF):
    def header(self):
        self.draw_frame(); self.draw_logo()
        self.set_font('Arial', 'B', 16)
        self.set_text_color(101, 67, 33)
        self.cell(0, 10, "Generations Abilities Schools", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.set_font('Arial', '', 12)
        self.set_text_color(184, 134, 11)
        self.cell(0, 8, "Smart Reading Assessment System", 0, new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
        self.ln(10)
    
    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', '', 10)
        self.set_text_color(128, 128, 128)
        self.cell(0, 10, f"Page {self.page_no()}", 0, align='C')

# ================== Gemini ==================
def gemini_analyze_audio(path, ref_text, lang="ar"):
    try:
        myfile = genai.upload_file(path)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        if lang == "ar":
            prompt = f"""
            أنت معلم أطفال داعم ومشجع جداً. النص المرجعي: "{ref_text}"
            
            المهمة: قيّم قراءة الطفل بلطف. ركز على الجوانب الإيجابية.
            
            تعليمات الدرجات:
            - "التقييم العام": اختر واحدة فقط من هذه المستويات بناءً على الأداء: (مبدع، متميز، متقدم، يحتاج للمساعدة).
            
            المطلوب (التزم بهذا التنسيق):
            الوعي الصوتي|__/25
            قراءة المقاطع|__/24
            الكلمات الشائعة|__/20
            الطلاقة القرائية|__ كلمة/دقيقة
            التقييم العام|__

            [تحليل الأخطاء]
            - (اذكر الأخطاء بأسلوب لطيف وبناء)
            
            [مؤشرات الأداء]
            - (اذكر نقاط القوة وما أتقنه الطالب)
            
            [التوصيات]
            - (نصائح بسيطة ومشجعة للتحسن)
            """
        else:
            prompt = f"""
            You are a very encouraging and kind teacher for kids. Reference: "{ref_text}"
            
            Task: Evaluate the child's reading gently. Focus on positives.
            
            Scoring Instructions:
            - "Overall Level": Choose exactly one: (High, Medium, Low).
            
            Strict Format:
            SCORES_START
            Pronunciation|__/25
            Word Recognition|__/20
            Fluency|__ wpm
            Intonation|__/15
            Overall Level|__
            SCORES_END

            NOTES_START
            # Error Analysis
            - (Mention errors gently)
            # Performance Overview
            - (Highlight strengths)
            # Recommendations
            - (Simple, encouraging tips)
            NOTES_END
            """
        res = model.generate_content([myfile, prompt])
        return res.text.strip() if hasattr(res, 'text') else ""
    except Exception as e:
        return f"GEMINI_ERROR: {str(e)}"

# ================== Routes ==================
@app.route('/')
def home(): return render_template('home.html')
@app.route('/arabic')
def arabic_page(): return render_template('index.html')
@app.route('/english')
def english_page(): return render_template('english.html')

@app.route('/analyze', methods=['POST'])
def analyze_ar():
    name = (request.form.get('name') or 'طالب').strip()
    ref_text = (request.form.get('ref_text') or '').strip()
    f = request.files.get('audio_upload') or request.files.get('audio_record')
    if not f: return "No audio", 400
    
    fname = f"temp_ar_{uuid.uuid4().hex[:12]}.wav"
    try:
        f.save(fname)
        with ThreadPoolExecutor(1) as ex:
            ai_text = ex.submit(gemini_analyze_audio, fname, ref_text, "ar").result(GEMINI_TIMEOUT_SECONDS)
        
        if "GEMINI_ERROR" in ai_text:
            return f"<h1>Error</h1><p>{ai_text}</p>", 500

        # === Parsing Arabic ===
        table_data = []
        overall_score = "---"
        sections = {"تحليل الأخطاء":[],"مؤشرات الأداء":[],"التوصيات":[]}
        curr_sec = None
        
        for line in ai_text.split('\n'):
            clean = line.strip().replace('**','').replace('#','').replace('[', '').replace(']', '').strip()
            if not clean: continue
            
            if '|' in clean and len(clean.split('|'))==2:
                k, v = clean.split('|')
                if "التقييم العام" in k:
                    overall_score = v.strip()
                else:
                    table_data.append((k,v))
            
            elif "تحليل الأخطاء" in clean: curr_sec = "تحليل الأخطاء"
            elif "مؤشرات الأداء" in clean: curr_sec = "مؤشرات الأداء"
            elif "التوصيات" in clean: curr_sec = "التوصيات"
            elif curr_sec and len(clean) > 2: sections[curr_sec].append(clean)

        pdf = ArabicPDF()
        pdf.add_page()
        
        # Student Info + Badge
        try: pdf.set_font('Amiri', '', 14)
        except: pass
        pdf.set_fill_color(240,240,240)
        pdf.set_draw_color(184,134,11)
        pdf.set_text_color(101,67,33)
        
        start_x = 60
        pdf.set_x(start_x)
        pdf.cell(80,10,ar("تاريخ التقييم"),1,0,'C',1)
        pdf.cell(60,10,ar("اسم الطالب"),1,1,'C',1)
        
        pdf.set_x(start_x)
        pdf.set_fill_color(255,255,255)
        pdf.cell(80,10,date.today().strftime("%Y/%m/%d"),1,0,'C',1)
        pdf.cell(60,10,ar(name),1,1,'C',1)
        
        # Badge on Left
        draw_overall_badge(pdf, overall_score, x=35, y=pdf.get_y()-10, lang='ar')
        pdf.ln(12)

        # Ref Text
        if ref_text:
            try: pdf.set_font('AmiriB','',14)
            except: pdf.set_font('Amiri','',14)
            pdf.set_text_color(101,67,33)
            pdf.cell(0,10,ar("النص المقروء:"),0,1,'R')
            try: pdf.set_font('Amiri','',12)
            except: pass
            pdf.set_text_color(80,80,80)
            for l in get_wrapped_lines(pdf, ref_text, 190, 12):
                pdf.cell(0,7,l,0,1,'R')
            pdf.ln(5)

        # Scores
        if table_data:
            try: pdf.set_font('AmiriB','',16)
            except: pdf.set_font('Amiri','',16)
            pdf.set_text_color(101,67,33)
            pdf.cell(0,10,ar("نتائج التقييم:"),0,1,'R')
            pdf.ln(2)
            
            pdf.set_fill_color(184,134,11)
            pdf.set_text_color(255,255,255)
            try: pdf.set_font('AmiriB','',14)
            except: pdf.set_font('Amiri','',14)
            
            pdf.cell(60,10,ar("الدرجة"),1,0,'C',1)
            pdf.cell(130,10,ar("المعيار"),1,1,'C',1)
            
            pdf.set_text_color(0,0,0)
            try: pdf.set_font('Amiri','',13)
            except: pass
            
            fill=False
            for k,v in table_data:
                if "الفهم القرائي" in k: continue
                if fill: pdf.set_fill_color(245,245,245)
                else: pdf.set_fill_color(255,255,255)
                pdf.cell(60,10,ar(v.strip()),1,0,'C',fill)
                pdf.cell(130,10,ar(k.strip()),1,1,'R',fill)
                fill=not fill
            pdf.ln(10)

        # Feedback
        if any(sections.values()):
            try: pdf.set_font('AmiriB','',16)
            except: pass
            pdf.set_text_color(101,67,33)
            pdf.cell(0,10,ar("الملاحظات:"),0,1,'R')
            pdf.ln(2)
            draw_smart_table_row(pdf, "تحليل الأخطاء", sections["تحليل الأخطاء"])
            draw_smart_table_row(pdf, "مؤشرات الأداء", sections["مؤشرات الأداء"])
            draw_smart_table_row(pdf, "التوصيات", sections["التوصيات"])

        out_name = f"Rep_{uuid.uuid4().hex[:6]}.pdf"
        pdf.output(out_name)
        return send_file(out_name, as_attachment=True, download_name=out_name)
    except Exception as e:
        return f"""
        <div style="background:#f8d7da; padding:20px;">
            <h2>Error Details</h2>
            <pre>{traceback.format_exc()}</pre>
        </div>
        """, 500
    finally:
        if os.path.exists(fname): os.remove(fname)

@app.route('/analyze_english', methods=['POST'])
def analyze_en():
    name = (request.form.get('name') or 'Student').strip()
    ref_text = (request.form.get('ref_text') or '').strip()
    f = request.files.get('audio_upload') or request.files.get('audio_record')
    if not f: return "No audio", 400

    fname = f"temp_en_{uuid.uuid4().hex[:12]}.wav"
    try:
        f.save(fname)
        with ThreadPoolExecutor(1) as ex:
            ai_text = ex.submit(gemini_analyze_audio, fname, ref_text, "en").result(GEMINI_TIMEOUT_SECONDS)

        if "GEMINI_ERROR" in ai_text: return f"Gemini Error: {ai_text}", 500

        # Parsing English
        scores_data = []
        overall_score = "---"
        notes_sections = {"Error Analysis": [], "Performance Overview": [], "Recommendations": []}
        current_section = None
        in_scores = False
        in_notes = False

        for line in ai_text.split('\n'):
            clean = line.strip()
            if not clean: continue
            if "SCORES_START" in clean: in_scores = True; continue
            if "SCORES_END" in clean: in_scores = False; continue
            if "NOTES_START" in clean: in_notes = True; continue
            if "NOTES_END" in clean: in_notes = False; continue

            if in_scores and '|' in clean:
                 parts = clean.split('|')
                 if len(parts) == 2:
                     k, v = parts[0].strip(), parts[1].strip()
                     if "Overall Level" in k:
                         overall_score = v
                     else:
                         scores_data.append((k, v))

            if in_notes:
                clean_note = clean.replace('#', '').strip()
                if "Error Analysis" in clean_note: current_section = "Error Analysis"
                elif "Performance Overview" in clean_note: current_section = "Performance Overview"
                elif "Recommendations" in clean_note: current_section = "Recommendations"
                elif current_section and len(clean_note) > 2:
                     notes_sections[current_section].append(clean_note)

        pdf = EnglishPDF()
        pdf.add_page()
        pdf.set_font("Arial", "", 12)

        # Info + Badge
        pdf.set_fill_color(240, 240, 240)
        pdf.set_draw_color(184, 134, 11)
        pdf.set_text_color(101, 67, 33)
        pdf.cell(80, 10, "Date", 1, 0, 'C', 1)
        pdf.cell(70, 10, "Student Name", 1, 1, 'C', 1)
        
        pdf.set_fill_color(255, 255, 255)
        pdf.cell(80, 10, date.today().strftime("%Y/%m/%d"), 1, 0, 'C', 1)
        pdf.cell(70, 10, name, 1, 1, 'C', 1)

        # Badge on Right
        draw_overall_badge(pdf, overall_score, x=180, y=pdf.get_y()-10, lang='en')
        pdf.ln(15)

        # Ref
        if ref_text:
            pdf.set_font("Arial", "B", 12)
            pdf.set_text_color(101, 67, 33)
            pdf.cell(0, 8, "Reference Text:", 0, 1, 'L')
            pdf.set_font("Arial", "", 11)
            pdf.set_text_color(60, 60, 60)
            pdf.set_x(10)
            pdf.multi_cell(190, 6, ref_text)
            pdf.ln(10)

        # Scores
        if scores_data:
            pdf.set_font("Arial", "B", 14)
            pdf.set_text_color(101, 67, 33)
            pdf.cell(0, 10, "Assessment Scores:", 0, 1, 'L')
            pdf.ln(2)

            pdf.set_fill_color(184, 134, 11)
            pdf.set_text_color(255, 255, 255)
            pdf.set_font("Arial", "B", 12)
            pdf.cell(130, 10, "Criteria", 1, 0, 'L', 1)
            pdf.cell(60, 10, "Score", 1, 1, 'C', 1)

            pdf.set_text_color(0, 0, 0)
            pdf.set_font("Arial", "", 12)
            fill = False
            for c, s in scores_data:
                if fill: pdf.set_fill_color(245, 245, 245)
                else: pdf.set_fill_color(255, 255, 255)
                pdf.cell(130, 10, "  " + c, 1, 0, 'L', fill)
                pdf.cell(60, 10, s, 1, 1, 'C', fill)
                fill = not fill
            pdf.ln(12)

        # Notes
        if any(notes_sections.values()):
             pdf.set_font("Arial", "B", 14)
             pdf.set_text_color(101, 67, 33)
             pdf.cell(0, 10, "Detailed Feedback & Notes:", 0, 1, 'L')
             pdf.ln(5)
             draw_styled_english_row(pdf, "Error Analysis", notes_sections["Error Analysis"])
             draw_styled_english_row(pdf, "Performance Overview", notes_sections["Performance Overview"])
             draw_styled_english_row(pdf, "Recommendations", notes_sections["Recommendations"])

        out_name = f"Rep_EN_{uuid.uuid4().hex[:6]}.pdf"
        pdf.output(out_name)
        return send_file(out_name, as_attachment=True, download_name=out_name)

    except Exception as e:
        return f"<pre>{traceback.format_exc()}</pre>", 500
    finally:
        if os.path.exists(fname): os.remove(fname)

if __name__ == '__main__':
    app.run(debug=True, port=5001, threaded=True)