import os

replacements = {
    'Ã¡': 'á', 'Ã©': 'é', 'Ã­': 'í', 'Ã³': 'ó', 'Ãº': 'ú',
    'Ã\xad': 'í',
    'Ã ': 'Á', 'Ã‰': 'É', 'Ã\x8d': 'Í', 'Ã“': 'Ó', 'Ãš': 'Ú',
    'Ã±': 'ñ', 'Ã‘': 'Ñ',
    'Ã¼': 'ü', 'Ãœ': 'Ü',
    'â†’': '->', 'â€¢': '•', 'â€”': '—', 'â€“': '–',
    'Â°': '°', 'Â«': '«', 'Â»': '»', 'Â¿': '¿', 'Â¡': '¡',
    'Ǹ': 'é', 'ǭ': 'á', 'ǧ': 'ú',
    'Gua': 'Guía', 'gua': 'guía',
    'Propsito': 'Propósito', 'propsito': 'propósito',
    'Visin': 'Visión', 'visin': 'visión',
    'sesin': 'sesión', 'Sesin': 'Sesión',
    'aade': 'añade', 'Aade': 'Añade',
    'arquitectnica': 'arquitectónica',
    'tcnica': 'técnica', 'Tcnica': 'Técnica', 'tcnicamente': 'técnicamente',
    'farmacutica': 'farmacéutica', 'farmacutico': 'farmacéutico',
    'Programacin': 'Programación', 'programacin': 'programación',
    'Disea': 'Diseña', 'disea': 'diseña',
    'Ingeniera': 'Ingeniería',
    'Informacin': 'Información', 'informacin': 'información',
    'polglota': 'políglota',
    'asncrona': 'asíncrona', 'asncrono': 'asíncrono', 'asncronos': 'asíncronos',
    'autenticacin': 'autenticación',
    'distribucin': 'distribución',
    'Sncrona': 'Síncrona', 'sncrona': 'síncrona',
    'configuracin': 'configuración',
    'gestin': 'gestión',
    'Rbrica': 'Rúbrica', 'rbrica': 'rúbrica',
    'Evaluacin': 'Evaluación', 'evaluacin': 'evaluación',
    'Construccin': 'Construcción', 'construccin': 'construcción',
    'operacin': 'operación', 'Operacin': 'Operación',
    'emisin': 'emisión', 'Emisin': 'Emisión',
    'validacin': 'validación', 'Validacin': 'Validación',
    'orden_detalles': 'orden_detalles',
    'bǧsqueda': 'búsqueda', 'Bǧsqueda': 'Búsqueda',
    'catǭlogo': 'catálogo', 'Catǭlogo': 'Catálogo',
    'mǸtricas': 'métricas', 'MǸtricas': 'Métricas',
    'dinǭmicamente': 'dinámicamente', 'dinǭmico': 'dinámico',
    'cdigo': 'código', 'Cdigo': 'Código',
    'rdenes': 'órdenes', 'rden': 'orden',
    'actǧa': 'actúa', 'Actǧa': 'Actúa',
    'ǧnica': 'única', 'ǧnico': 'único',
    'quǸ': 'qué', 'QuǸ': 'Qué',
    'Perǧ': 'Perú'
}

count = 0
for root, dirs, files in os.walk('/docs/docs'):
    for file in files:
        if file.endswith('.md'):
            filepath = os.path.join(root, file)
            with open(filepath, 'rb') as f:
                raw = f.read()
            text = raw.decode('utf-8', errors='replace')
            for k, v in replacements.items():
                text = text.replace(k, v)
            with open(filepath, 'wb') as f:
                f.write(text.encode('utf-8'))
            count += 1

print(f'Procesados {count} archivos markdown exitosamente en UTF-8 puro.')

