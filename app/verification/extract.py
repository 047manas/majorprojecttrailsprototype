import os
import PyPDF2

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in {'pdf', 'png', 'jpg', 'jpeg'}

def extract_text(filepath):
    text = ""
    annotation_urls = set()
    
    try:
        if filepath.lower().endswith('.pdf'):
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    text += page.extract_text() or ""
                    if '/Annots' in page:
                         # Basic annotation extraction logic 
                         annots = page['/Annots']
                         if isinstance(annots, list):
                             for annot in annots:
                                obj = annot.get_object()
                                if '/A' in obj and '/URI' in obj['/A']:
                                    annotation_urls.add(obj['/A']['/URI'])
    except Exception as e:
        print(f"Error extracting content from {filepath}: {e}")
        
    return text, annotation_urls
