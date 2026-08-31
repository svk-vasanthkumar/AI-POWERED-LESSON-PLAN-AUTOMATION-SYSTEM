from xhtml2pdf import pisa

def test():
    html = """
    <html>
    <head>
    <style>
        @page {
            size: a4 portrait;
            @frame footer {
                -pdf-frame-content: footer_content;
                bottom: 2cm; height: 1cm; text-align: center;
            }
        }
    </style>
    </head>
    <body>
        <div id="footer_content"><pdf:pagenumber></div>
        <h1>Page 1</h1>
        <pdf:nextpage />
        <h1>Page 2</h1>
    </body>
    </html>
    """
    with open("test2.pdf", "wb") as f:
        pisa.CreatePDF(html, dest=f)

if __name__ == '__main__':
    test()
