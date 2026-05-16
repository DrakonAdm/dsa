import PyPDF2
import sys

def extract_text_from_pdf(pdf_path):
    text = ""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            for page in reader.pages:
                text += page.extract_text() + "\n\n"
        return text
    except Exception as e:
        return f"Error: {e}"

if __name__ == "__main__":
    pdf_file = sys.argv[1] if len(sys.argv) > 1 else '/Users/larisa/Documents/frontend_generation/TZ.pdf'
    text = extract_text_from_pdf(pdf_file)
    print(text)
