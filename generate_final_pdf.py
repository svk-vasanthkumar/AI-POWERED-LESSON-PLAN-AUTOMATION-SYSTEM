import markdown
from xhtml2pdf import pisa
import fitz
import re

def generate_pdf():
    # 1. Read Markdown
    with open(r'e:\projects\Lesson planner frontend\AI-POWERED-LESSON-PLAN-AUTOMATION-SYSTEM\docs\documentation.md', 'r', encoding='utf-8') as f:
        md_text = f.read()

    # Strip everything before # ABSTRACT
    idx = md_text.find('# ABSTRACT')
    if idx != -1:
        md_text = md_text[idx:]

    # Insert Magic Marker for Chapter 1
    # Use regex to match exactly # CHAPTER 1 and not # CHAPTER 10
    md_text = re.sub(r'(?m)^# CHAPTER 1$', '<div style="color: white; font-size: 1px;">MAGIC_CHAPTER_1_START</div>\n# CHAPTER 1', md_text)

    # 2. Convert to HTML
    html_body = markdown.markdown(md_text, extensions=['tables'])

    # 3. Add CSS for tables
    def remove_border(match):
        table_html = match.group(0)
        if 'CHAPTER NO.' in table_html or 'TABLE NAME' in table_html or 'FIGURE NAME' in table_html or 'ARTIFICIAL INTELLIGENCE' in table_html:
            return table_html.replace('<table>', '<table class="no-border">')
        else:
            return table_html.replace('<table>', '<table class="bordered">')

    html_body = re.sub(r'<table>.*?</table>', remove_border, html_body, flags=re.DOTALL)

    # Replace <div style="page-break-after: always;"></div> with CSS equivalent
    html_body = html_body.replace('<div style="page-break-after: always;"></div>', '<pdf:nextpage />')

    html_content = f"""
    <html>
    <head>
    <style>
        @page {{
            size: a4 portrait;
            margin: 1in;
            @frame footer {{
                -pdf-frame-content: footer_content;
                bottom: 30pt; margin-left: 1in; margin-right: 1in; height: 20pt; text-align: center;
            }}
        }}
        body {{
            font-family: "Times New Roman", serif;
            font-size: 12pt;
            line-height: 1.5;
            text-align: justify;
        }}
        h1 {{
            font-size: 16pt;
            font-weight: bold;
            text-align: center;
            text-transform: uppercase;
            margin-top: 20px;
            margin-bottom: 20px;
            page-break-before: always;
        }}
        h2 {{
            font-size: 14pt;
            font-weight: bold;
            text-align: center;
            text-transform: uppercase;
        }}
        h3, h4 {{
            font-size: 12pt;
            font-weight: bold;
            text-align: left;
            text-transform: uppercase;
        }}
        p {{
            text-indent: 0.5in;
            margin-bottom: 10px;
        }}
        /* Do not indent paragraphs inside tables */
        td p, th p {{
            text-indent: 0;
            margin-bottom: 0;
        }}
        /* Do not indent headings */
        h1, h2, h3, h4 {{
            text-indent: 0;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 20px;
        }}
        table.bordered th, table.bordered td {{
            border: 1px solid black;
            padding: 8px;
            text-align: left;
        }}
        table.bordered th {{
            text-align: center;
        }}
        table.no-border th, table.no-border td {{
            border: none;
            padding: 8px;
            text-align: left;
        }}
        table.no-border th {{
            text-align: center;
        }}
    </style>
    </head>
    <body>
        <div id="footer_content"></div>
        {html_body}
    </body>
    </html>
    """

    # H1 page-break-before: always will ensure that every # Heading starts on a new page.
    # Actually wait, in markdown, abstract, TOC etc are all # Heading. So they will start on new pages automatically!
    # I should remove the <pdf:nextpage /> that were generated if it causes double blanks.
    html_content = html_content.replace('<pdf:nextpage />', '')

    temp_pdf = "temp_report.pdf"
    with open(temp_pdf, "wb") as result_file:
        pisa.CreatePDF(html_content, dest=result_file)

    # 4. Add Page Numbers
    doc = fitz.open(temp_pdf)
    chapter_1_page_idx = -1
    for i in range(len(doc)):
        page = doc[i]
        text = page.get_text("text")
        if "MAGIC_CHAPTER_1_START" in text:
            chapter_1_page_idx = i
            break
            
    if chapter_1_page_idx == -1:
        chapter_1_page_idx = 5 # fallback
        
    roman_numerals = ['iv', 'v', 'vi', 'vii', 'viii', 'ix', 'x', 'xi', 'xii', 'xiii', 'xiv', 'xv', 'xvi', 'xvii', 'xviii']
    
    for i in range(len(doc)):
        page = doc[i]
        rect = page.rect
        
        if i < chapter_1_page_idx:
            page_str = roman_numerals[i]
        else:
            page_str = str(i - chapter_1_page_idx + 1)
            
        # Draw text at center bottom
        tw = fitz.get_text_length(page_str, fontname="times-roman", fontsize=12)
        x = (rect.width - tw) / 2.0
        y = rect.height - 50 # 50 points from bottom
        
        page.insert_text(fitz.Point(x, y), page_str, fontname="times-roman", fontsize=12)
        
    final_pdf_path = r"e:\projects\Lesson planner frontend\AI-POWERED-LESSON-PLAN-AUTOMATION-SYSTEM\AI-POWERED-LESSON-PLAN-AUTOMATION-SYSTEM.pdf"
    doc.save(final_pdf_path)
    doc.close()
    print(f"Generated successfully: {final_pdf_path}")
    print(f"Total Pages: {len(doc)}")
    print(f"Chapter 1 started at page index: {chapter_1_page_idx}")

if __name__ == '__main__':
    generate_pdf()
