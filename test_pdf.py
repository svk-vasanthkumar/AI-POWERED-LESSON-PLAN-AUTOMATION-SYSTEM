from xhtml2pdf import pisa
import sys

def convert_html_to_pdf(html_string, pdf_path):
    with open(pdf_path, "w+b") as result_file:
        pisa_status = pisa.CreatePDF(html_string, dest=result_file)
    return pisa_status.err

if __name__ == "__main__":
    html = """
    <html>
    <head>
    <style>
        @page {
            size: a4 portrait;
            @frame header_frame {
                -pdf-frame-content: header_content;
                left: 50pt; width: 512pt; top: 50pt; height: 40pt;
            }
            @frame content_frame {
                left: 50pt; width: 512pt; top: 90pt; height: 632pt;
            }
            @frame footer_frame {
                -pdf-frame-content: footer_content;
                left: 50pt; width: 512pt; top: 772pt; height: 20pt;
            }
        }
        body { font-family: "Times New Roman"; font-size: 12pt; text-align: justify; }
        h1 { font-size: 16pt; font-weight: bold; text-align: center; }
    </style>
    </head>
    <body>
        <div id="header_content">Header</div>
        <div id="footer_content">Page <pdf:pagenumber></div>
        <h1>Test Header</h1>
        <p>This is a test document.</p>
    </body>
    </html>
    """
    err = convert_html_to_pdf(html, "test_output.pdf")
    if err:
        print("Error")
    else:
        print("Success")
