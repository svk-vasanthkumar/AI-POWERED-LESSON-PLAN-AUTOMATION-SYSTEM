import fitz  # PyMuPDF
from docx import Document


def extract_text(filepath: str):
    if filepath.endswith(".pdf"):
        return extract_pdf(filepath)

    elif filepath.endswith(".docx"):
        return extract_docx(filepath)

    else:
        raise ValueError("Unsupported file format")


def extract_pdf(filepath: str):
    document = fitz.open(filepath)

    text = ""

    for page in document:
        text += page.get_text()

    document.close()

    return text


def extract_docx(filepath: str):
    document = Document(filepath)

    text = ""

    for paragraph in document.paragraphs:
        text += paragraph.text + "\n"

    return text