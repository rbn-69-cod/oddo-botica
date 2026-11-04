#!/usr/bin/env python3
"""
One-shot module fixer: Scans ALL views and generates complete field/method list
"""

import re
from pathlib import Path
from lxml import etree
from collections import defaultdict

def scan_module(module_path):
    """Scan entire module and generate complete fix list"""
    
    module_path = Path(module_path)
    results = defaultdict(lambda: {'fields': set(), 'methods': set(), 'view_files': set()})
    
    # Scan all XML view files
    for xml_file in module_path.rglob('*.xml'):
        if 'views' not in str(xml_file):
            continue
            
        try:
            tree = etree.parse(str(xml_file))
            root = tree.getroot()
            
            for record in root.findall(".//record[@model='ir.ui.view']"):
                model_elem = record.find("./field[@name='model']")
                if model_elem is None or not model_elem.text:
                    continue
                
                model_name = model_elem.text
                arch = record.find("./field[@name='arch']")
                
                if arch is not None:
                    # Extract all field names
                    for field_elem in arch.iter('field'):
                        field_name = field_elem.get('name')
                        if field_name:
                            results[model_name]['fields'].add(field_name)
                            results[model_name]['view_files'].add(xml_file.name)
                    
                    # Extract all method names from buttons
                    for button_elem in arch.iter('button'):
                        if button_elem.get('type') == 'object':
                            method_name = button_elem.get('name')
                            if method_name:
                                results[model_name]['methods'].add(method_name)
                                results[model_name]['view_files'].add(xml_file.name)
        
        except Exception as e:
            print(f"⚠️  Error parsing {xml_file}: {e}")
    
    # Scan existing model files to see what's already defined
    existing_models = {}
    models_dir = module_path / 'models'
    
    if models_dir.exists():
        for py_file in models_dir.rglob('*.py'):
            if py_file.name == '__init__.py':
                continue
            
            try:
                content = py_file.read_text()
                
                # Find model name
                model_match = re.search(r"_name\s*=\s*['\"]([^'\"]+)['\"]", content)
                if model_match:
                    model_name = model_match.group(1)
                    
                    # Find existing fields
                    field_pattern = r"(\w+)\s*=\s*fields\.\w+\("
                    existing_fields = set(re.findall(field_pattern, content))
                    
                    # Find existing methods
                    method_pattern = r"def\s+([a-zA-Z_]\w*)\s*\("
                    existing_methods = set(re.findall(method_pattern, content))
                    
                    existing_models[model_name] = {
                        'file': py_file,
                        'fields': existing_fields,
                        'methods': existing_methods
                    }
            
            except Exception as e:
                print(f"⚠️  Error reading {py_file}: {e}")
    
    # Generate report
    print("="*80)
    print("COMPLETE MODULE AUDIT REPORT")
    print("="*80)
    
    for model_name in sorted(results.keys()):
        view_data = results[model_name]
        model_data = existing_models.get(model_name, {'fields': set(), 'methods': set(), 'file': None})
        
        # Calculate missing items
        special_fields = {'id', 'create_date', 'write_date', 'create_uid', 'write_uid', 
                         '__last_update', 'display_name', 'name', 'active'}
        
        missing_fields = view_data['fields'] - model_data['fields'] - special_fields
        missing_methods = view_data['methods'] - model_data['methods']
        
        if missing_fields or missing_methods:
            print(f"\n{'='*80}")
            print(f"MODEL: {model_name}")
            print(f"{'='*80}")
            print(f"File: {model_data.get('file', 'NOT FOUND - CREATE NEW FILE')}")
            print(f"Used in views: {', '.join(sorted(view_data['view_files']))}")
            
            if missing_fields:
                print(f"\n  MISSING FIELDS ({len(missing_fields)}):")
                for field in sorted(missing_fields):
                    print(f"    • {field}")
            
            if missing_methods:
                print(f"\n  MISSING METHODS ({len(missing_methods)}):")
                for method in sorted(missing_methods):
                    print(f"    • {method}")
    
    print("\n" + "="*80)
    return results, existing_models

if __name__ == '__main__':
    import sys
    module_path = sys.argv[1] if len(sys.argv) > 1 else '.'
    scan_module(module_path)
