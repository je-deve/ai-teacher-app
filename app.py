import os
import uuid
import requests
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import warnings
import traceback

# إخفاء التحذيرات
warnings.filterwarnings("ignore")

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

# ================== Helper Functions ==================
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

def ar(text):
    if not text or not isinstance(text, str): return ""
    try: return get_display(arabic_reshaper.reshape(text))
    except: return text

# --- تنظيف النصوص الإنجليزية فقط ---
def clean_en(text):
    if not text: return ""
    return text.encode('latin-1', 'replace').decode('latin-1')

def get_wrapped_lines(pdf, text, max_width_mm, font_size=12, is_arabic=True):
    font_family = 'Amiri' if is_arabic else 'Arial'
    try: 
        pdf.set_font(font_family, '', font_size)
    except: 
        pass
    
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = current_line + [word]
        test_str = " ".join(test_line)
        if is_arabic: test_str = ar(test_str)
        
        if pdf.get_string_width(test_str) <= max_width_mm:
            current_line.append(word)
        else:
            if current_line:
                final_str = " ".join(current_line)
                lines.append(ar(final_str) if is_arabic else final_str)
            current_line = [word]
            
    if current_line:
        final_str = " ".join(current_line)
        lines.append(ar(final_str) if is_arabic else final_str)
        
    return lines

def get_english_wrapped_lines(pdf, text, max_width_mm, font_size=11):
    pdf.set_font("Arial", "", font_size)
    text = clean_en(text)
    words = text.split()
    lines = []; current_line = []
    
    for word in words:
        test_line = current_line + [word]
        test_str = " ".join(test_line)
        if pdf.get_string_width(test_str) <= max_width_mm:
            current_line.append(word)
        else:
            if current_line: lines.append(" ".join(current_line))
            current_line = [word]
    if current_line: lines.append(" ".join(current_line))
    return lines

# ================== Drawing Functions ==================
def draw_dynamic_row(pdf, title, content_points, lang='ar'):
    if not content_points: return
    
    is_ar = (lang == 'ar')
    col_title_w = 45; col_content_w = 145; padding = 5; line_h = 7
    
    clean_points = [p.strip().replace('-','').replace('*','') for p in content_points if p.strip()]
    final_content_lines = []
    
    for p in clean_points:
        bullet = "• " if is_ar else "- "
        if is_ar:
             wrapped = get_wrapped_lines(pdf, bullet + p, col_content_w - (padding*2), 11, True)
        else:
             wrapped = get_english_wrapped_lines(pdf, bullet + p, col_content_w - (padding*2), 11)
        final_content_lines.extend(wrapped)
    
    content_h = (len(final_content_lines) * line_h) + (padding * 2)
    row_h = max(content_h, 20)
    
    if pdf.get_y() + row_h > 270: pdf.add_page()
    start_y = pdf.get_y()
    
    if is_ar: x_title = 155; x_content = 10
    else: x_title = 10; x_content = 55

    pdf.set_fill_color(253, 245, 230); pdf.set_draw_color(184, 134, 11)
    pdf.rect(x_title, start_y, col_title_w, row_h, 'FD')
    pdf.set_fill_color(255, 255, 255)
    pdf.rect(x_content, start_y, col_content_w, row_h, 'FD')

    pdf.set_text_color(101, 67, 33)
    if is_ar:
        try: 
            pdf.set_font('AmiriB', '', 13)
        except: 
            try: 
                pdf.set_font('Amiri', '', 13)
            except: 
                pass
        title_text = ar(title)
    else:
        pdf.set_font('Arial', 'B', 12)
        title_text = title
        
    pdf.set_xy(x_title, start_y + (row_h/2) - 3)
    pdf.cell(col_title_w, 6, title_text, 0, 0, 'C')

    pdf.set_text_color(50, 50, 50)
    if is_ar:
        try: 
            pdf.set_font('Amiri', '', 11)
        except: 
            pass
        align = 'R'
    else:
        pdf.set_font('Arial', '', 11)
        align = 'L'
        
    curr_y = start_y + padding
    for line in final_content_lines:
        pdf.set_xy(x_content + padding, curr_y)
        pdf.cell(col_content_w - (padding*2), line_h, line, 0, 0, align)
        curr_y += line_h

    pdf.set_y(start_y + row_h); pdf.ln(3)

def draw_level_badge(pdf, level_text, x, y, lang='ar'):
    try:
        # --- عدم تنظيف النص العربي ---
        if lang == 'ar':
            level = level_text.replace('%','').replace('|','').strip()
        else:
            level = clean_en(level_text).replace('%','').replace('|','').strip()
            
        if not level: level = "متوسط" if lang=='ar' else "Medium"

        # اختيار اللون
        if any(w in level.lower() for w in ['high', 'عالي', 'excellent', 'متميز', 'مبدع']):
            pdf.set_fill_color(218, 165, 32) 
        elif any(w in level.lower() for w in ['medium', 'متوسط', 'good', 'جيد']):
            pdf.set_fill_color(192, 192, 192)
        else:
            pdf.set_fill_color(205, 127, 50)

        # رسم الدائرة
        pdf.set_draw_color(101, 67, 33); pdf.set_line_width(0.5)
        pdf.circle(x, y, 16, 'FD')
        
        # العنوان
        pdf.set_text_color(101, 67, 33)
        if lang == 'ar':
            try: 
                pdf.set_font('AmiriB', '', 11)
            except: 
                try: 
                    pdf.set_font('Amiri', '', 11)
                except: 
                    pass
            title = ar("المستوى")
        else:
            try: 
                pdf.set_font('Arial', 'B', 10)
            except: 
                pass
            title = "Level"
            
        pdf.set_xy(x - 15, y - 25)
        pdf.cell(30, 6, title, 0, 0, 'C')

        # النص داخل الدائرة
        pdf.set_text_color(255, 255, 255)
        
        font_size = 14
        if len(level) > 7: font_size = 10
        elif len(level) > 5: font_size = 12
        
        if lang == 'ar':
            try: 
                pdf.set_font('AmiriB', '', font_size)
            except: 
                try: 
                    pdf.set_font('Amiri', '', font_size)
                except: 
                    pass
            level_disp = ar(level)
        else:
            try: 
                pdf.set_font('AmiriB', '', font_size)
            except: 
                pdf.set_font('Arial', 'B', font_size)
            level_disp = level

        pdf.set_xy(x - 15, y - 5)
        pdf.cell(30, 10, level_disp, 0, 0, 'C')
    except: pass

# ================== PDF Classes ==================
class BasePDF(FPDF):
    def draw_frame(self):
        self.set_draw_color(101,67,33); self.set_line_width(0.6)
        self.rect(5, 5, 200, 287)
    def draw_logo(self):
        if os.path.exists('static/logo.png'): self.image('static/logo.png', 170, 8, 25)

class ArabicPDF(BasePDF):
    def header(self):
        self.draw_frame(); self.draw_logo()
        try:
            self.add_font('Amiri', '', os.path.abspath('Amiri-Regular.ttf'))
            self.add_font('AmiriB', '', os.path.abspath('Amiri-Bold.ttf'))
            self.set_font('AmiriB', '', 18)
        except: self.set_font('Arial', 'B', 16)
        self.set_text_color(101,67,33)
        self.cell(0, 10, ar("مدارس قدرات الأجيال العالمية"), 0, 1, 'C')
        try: self.set_font('Amiri', '', 14)
        except: pass
        self.set_text_color(184,134,11)
        self.cell(0, 8, ar("نظام التقييم الصوتي الذكي"), 0, 1, 'C')
        self.ln(5)
    def footer(self):
        self.set_y(-15)
        try:
            self.set_font('Amiri','',10)
        except: pass
        self.set_text_color(128,128,128); self.cell(0,10,ar(f"صفحة {self.page_no()}"),0,0,'C')

class EnglishPDF(BasePDF):
    def header(self):
        self.draw_frame(); self.draw_logo()
        try:
            self.add_font('Amiri', '', os.path.abspath('Amiri-Regular.ttf'))
            self.add_font('AmiriB', '', os.path.abspath('Amiri-Bold.ttf'))
            self.set_font('AmiriB', '', 18) 
        except: self.set_font('Arial', 'B', 16)
        self.set_text_color(101,67,33)
        self.cell(0, 10, "Generations Abilities Schools", 0, 1, 'C')
        try: self.set_font('Amiri', '', 14)
        except: self.set_font('Arial', '', 12)
        self.set_text_color(184,134,11)
        self.cell(0, 8, "Smart Reading Assessment System", 0, 1, 'C')
        self.ln(8)
    def footer(self):
        self.set_y(-15)
        try:
            self.set_font('Amiri','',10)
        except:
            self.set_font('Arial','',10)
        self.set_text_color(128,128,128); self.cell(0,10,f"Page {self.page_no()}",0,0,'C')

# ================== AI Logic ==================
def gemini_analyze_audio(path, ref_text, lang="ar"):
    try:
        myfile = genai.upload_file(path)
        model = genai.GenerativeModel("gemini-2.5-flash")
        
        if lang == "ar":
            # البرومبت العربي
            prompt = f"""
            أنت خبير تربوي. النص المرجعي: "{ref_text}"
            
            1. قيّم القراءة بدقة.
            2. حدد "التقييم العام" باختيار كلمة واحدة فقط من القائمة التالية: (عالي، متوسط، ضعيف).

            التنسيق (التزم به):
            الوعي الصوتي|__/25
            قراءة المقاطع|__/24
            الكلمات الشائعة|__/20
            الطلاقة القرائية|__ كلمة/دقيقة
            التقييم العام|(الكلمة المختارة)

            [تحليل الأخطاء]
            - (نقطة)
            [مؤشرات الأداء]
            - (نقطة)
            [التوصيات]
            - (نقطة)
            """
        else:
            # English Prompt
            prompt = f"""
            Professional English teacher. Ref: "{ref_text}"
            
            Task: 
            1. Score the reading.
            2. Set "Overall Level" to one of: (High, Medium, Low).
            
            IMPORTANT: Use simple text only. No IPA symbols.

            Strict Format:
            SCORES_START
            Pronunciation|__/25
            Word Recognition|__/20
            Fluency|__ wpm
            Intonation|__/15
            Overall Level|(The chosen word)
            SCORES_END

            NOTES_START
            # Error Analysis
            - (Point 1)
            # Performance Overview
            - (Point 1)
            # Recommendations
            - (Point 1)
            NOTES_END
            """
        res = model.generate_content([myfile, prompt])
        return res.text.strip()
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
        
        if "GEMINI_ERROR" in ai_text: return f"Error: {ai_text}", 500

        table_data = []
        overall_level = "متوسط"
        sections = {"تحليل الأخطاء":[],"مؤشرات الأداء":[],"التوصيات":[]}
        curr_sec = None
        
        for line in ai_text.split('\n'):
            clean = line.strip().replace('*','').replace('#','').replace('[','').replace(']','')
            if not clean: continue
            
            if '|' in clean:
                parts = clean.split('|')
                if len(parts) >= 2:
                    k, v = parts[0].strip(), parts[1].strip()
                    if "التقييم العام" in k:
                        overall_level = v
                    elif any(x in k for x in ["الوعي", "المقاطع", "الكلمات", "الطلاقة"]):
                        table_data.append((k,v))
            
            elif "تحليل الأخطاء" in clean: curr_sec = "تحليل الأخطاء"
            elif "مؤشرات الأداء" in clean: curr_sec = "مؤشرات الأداء"
            elif "التوصيات" in clean: curr_sec = "التوصيات"
            elif curr_sec: sections[curr_sec].append(clean)

        pdf = ArabicPDF()
        pdf.add_page()
        
        try:
            pdf.add_font('Amiri', '', os.path.abspath('Amiri-Regular.ttf'))
            pdf.add_font('AmiriB', '', os.path.abspath('Amiri-Bold.ttf'))
        except: pass

        draw_level_badge(pdf, overall_level, x=35, y=pdf.get_y()+8, lang='ar')

        try: pdf.set_font('Amiri', '', 14)
        except: pass
        pdf.set_fill_color(240,240,240); pdf.set_text_color(101,67,33)
        pdf.set_xy(65, pdf.get_y())
        pdf.cell(80,10,ar("تاريخ التقييم"),1,0,'C',1)
        pdf.cell(60,10,ar("اسم الطالب"),1,1,'C',1)
        pdf.set_xy(65, pdf.get_y()+10)
        pdf.set_fill_color(255,255,255)
        pdf.cell(80,10,date.today().strftime("%Y/%m/%d"),1,0,'C',1)
        pdf.cell(60,10,ar(name),1,1,'C',1)
        pdf.ln(15)

        if ref_text:
            try: pdf.set_font('AmiriB','',14)
            except: pass
            pdf.set_text_color(101,67,33)
            pdf.cell(0,10,ar("النص المقروء:"),0,1,'R')
            try: pdf.set_font('Amiri','',12)
            except: pass
            pdf.set_text_color(80,80,80)
            for l in get_wrapped_lines(pdf, ref_text, 190, 12):
                pdf.cell(0,7,l,0,1,'R')
            pdf.ln(5)

        if table_data:
            try: pdf.set_font('AmiriB','',16)
            except: pass
            pdf.set_text_color(101,67,33)
            pdf.cell(0,10,ar("نتائج التقييم:"),0,1,'R')
            pdf.ln(2)
            pdf.set_fill_color(184,134,11); pdf.set_text_color(255,255,255)
            # FIX: SPLIT TRY/EXCEPT
            try: 
                pdf.set_font('AmiriB','',14)
            except: 
                pass
            pdf.cell(60,10,ar("الدرجة"),1,0,'C',1)
            pdf.cell(130,10,ar("المعيار"),1,1,'C',1)
            
            pdf.set_text_color(0,0,0)
            # FIX: SPLIT TRY/EXCEPT
            try: 
                pdf.set_font('Amiri','',13)
            except: 
                pass
            fill=False
            for k,v in table_data:
                if fill: pdf.set_fill_color(245,245,245)
                else: pdf.set_fill_color(255,255,255)
                pdf.cell(60,10,ar(v),1,0,'C',fill)
                pdf.cell(130,10,ar(k),1,1,'R',fill)
                fill=not fill
            pdf.ln(10)

        if any(sections.values()):
            try: pdf.set_font('AmiriB','',16)
            except: pass
            pdf.set_text_color(101,67,33)
            pdf.cell(0,10,ar("الملاحظات:"),0,1,'R')
            draw_dynamic_row(pdf, "تحليل الأخطاء", sections["تحليل الأخطاء"])
            draw_dynamic_row(pdf, "مؤشرات الأداء", sections["مؤشرات الأداء"])
            draw_dynamic_row(pdf, "التوصيات", sections["التوصيات"])

        out_name = f"Rep_{uuid.uuid4().hex[:6]}.pdf"
        pdf.output(out_name)
        return send_file(out_name, as_attachment=True, download_name=out_name)

    except Exception as e:
        return f"Err: {e}",500
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

        scores_data = []
        overall_level = "Medium"
        notes = {"Error Analysis":[],"Performance Overview":[],"Recommendations":[]}
        curr_note = None
        in_scores = False; in_notes = False

        for line in ai_text.split('\n'):
            clean = line.strip().replace('*','')
            if not clean: continue
            if "SCORES_START" in clean: in_scores=True; continue
            if "SCORES_END" in clean: in_scores=False; continue
            if "NOTES_START" in clean: in_notes=True; continue
            if "NOTES_END" in clean: in_notes=False; continue

            if in_scores and '|' in clean:
                parts = clean.split('|')
                if len(parts) >= 2:
                    k = parts[0].strip()
                    v = parts[1].strip()
                    if "Overall Level" in k:
                        overall_level = v
                    else:
                        scores_data.append((k, v))

            if in_notes:
                clean_note = clean.replace('#', '').strip()
                if "Error Analysis" in clean_note: curr_note = "Error Analysis"
                elif "Performance Overview" in clean_note: curr_note = "Performance Overview"
                elif "Recommendations" in clean_note: curr_note = "Recommendations"
                elif curr_note: notes[curr_note].append(clean_note)

        pdf = EnglishPDF()
        pdf.add_page()
        try: pdf.set_font("Amiri", "", 12)
        except: pass

        # Info
        pdf.set_fill_color(240,240,240); pdf.set_draw_color(184,134,11); pdf.set_text_color(101,67,33)
        pdf.cell(80,10,"Date",1,0,'C',1)
        pdf.cell(70,10,"Student Name",1,1,'C',1)
        
        pdf.set_xy(10, pdf.get_y()+10)
        pdf.set_fill_color(255,255,255)
        pdf.cell(80,10,date.today().strftime("%Y/%m/%d"),1,0,'C',1)
        safe_name = clean_en(name)
        pdf.cell(70,10,safe_name,1,1,'C',1)
        
        # BADGE
        draw_level_badge(pdf, overall_level, x=185, y=pdf.get_y()-5, lang='en')
        pdf.ln(18)

        if ref_text:
            # FIX: SPLIT TRY/EXCEPT
            try: 
                pdf.set_font("AmiriB","",12)
            except: 
                pass
            pdf.set_text_color(101,67,33)
            pdf.cell(0,8,"Reference Text:",0,1,'L')
            # FIX: SPLIT TRY/EXCEPT
            try: 
                pdf.set_font("Amiri","",11)
            except: 
                pass
            pdf.set_text_color(60,60,60)
            lines = get_english_wrapped_lines(pdf, ref_text, 190, 11)
            for l in lines: pdf.cell(0,6,l,0,1,'L')
            pdf.ln(8)

        if scores_data:
            # FIX: SPLIT TRY/EXCEPT
            try: 
                pdf.set_font("AmiriB","",14)
            except: 
                pass
            pdf.set_text_color(101,67,33)
            pdf.cell(0,10,"Assessment Scores:",0,1,'L')
            pdf.ln(2)
            pdf.set_fill_color(184,134,11); pdf.set_text_color(255,255,255)
            # FIX: SPLIT TRY/EXCEPT
            try: 
                pdf.set_font("AmiriB","",12)
            except: 
                pass
            pdf.cell(130,10,"Criteria",1,0,'L',1)
            pdf.cell(60,10,"Score",1,1,'C',1)
            pdf.set_text_color(0,0,0)
            # FIX: SPLIT TRY/EXCEPT
            try: 
                pdf.set_font("Amiri","",12)
            except: 
                pass
            fill=False
            for c,s in scores_data:
                if fill: pdf.set_fill_color(245,245,245)
                else: pdf.set_fill_color(255,255,255)
                safe_c = clean_en(c)
                safe_s = clean_en(s)
                pdf.cell(130,10,"  "+safe_c,1,0,'L',fill)
                pdf.cell(60,10,safe_s,1,1,'C',fill)
                fill=not fill
            pdf.ln(12)

        if any(notes.values()):
            # FIX: SPLIT TRY/EXCEPT
            try: 
                pdf.set_font("AmiriB","",14)
            except: 
                pass
            pdf.set_text_color(101,67,33)
            pdf.cell(0,10,"Detailed Feedback:",0,1,'L')
            draw_dynamic_row(pdf, "Error Analysis", notes["Error Analysis"], 'en')
            draw_dynamic_row(pdf, "Performance Overview", notes["Performance Overview"], 'en')
            draw_dynamic_row(pdf, "Recommendations", notes["Recommendations"], 'en')

        out_name = f"Rep_EN_{uuid.uuid4().hex[:6]}.pdf"
        pdf.output(out_name)
        return send_file(out_name, as_attachment=True, download_name=out_name)

    except Exception as e:
        return f"Error: {e}", 500
    finally:
        if os.path.exists(fname): os.remove(fname)

if __name__ == '__main__':
    app.run(debug=True, port=5001, threaded=True)