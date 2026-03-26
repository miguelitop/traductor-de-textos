import ollama
import striprtf.striprtf as rtf_parser
import sys
from pathlib import Path

def traducir_rtf(archivo_entrada):
    # Leer y extraer texto del RTF
    contenido_rtf = Path(archivo_entrada).read_text(encoding="utf-8", errors="ignore")
    texto = rtf_parser.rtf_to_text(contenido_rtf)

    prompt = f"""You are a professional English (en) to Spanish (es) translator. Your goal is to accurately translate the original English text while adhering to Spanish grammar, vocabulary, and cultural sensitivities. Produce only the Spanish translation, without any additional explanations or commentary. Please translate the following English text into Spanish:


{texto}"""

    print("Traduciendo... (esto puede tardar unos segundos)")
    
    response = ollama.chat(
        model="translategemma:27b",
        messages=[{"role": "user", "content": prompt}]
    )
    
    traduccion = response["message"]["content"]
    
    # Guardar resultado
    archivo_salida = Path(archivo_entrada).stem + "_es.txt"
    Path(archivo_salida).write_text(traduccion, encoding="utf-8")
    print(f"✓ Traducción guardada en: {archivo_salida}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python traducir.py archivo.rtf")
        sys.exit(1)
    traducir_rtf(sys.argv[1])