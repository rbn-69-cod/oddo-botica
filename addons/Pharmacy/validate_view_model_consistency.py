#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
View-Model Consistency Validation Script for Odoo Pharmacy Management Module
Validates that all methods called from views exist in their respective models
"""

import os
import re
import xml.etree.ElementTree as ET
from pathlib import Path
import importlib.util

class ViewModelValidator:
    def __init__(self, module_path):
        self.module_path = Path(module_path)
        self.models = {}
        self.views = []
        self.issues = []
        
    def load_models(self):
        """Load all Python models and extract method names"""
        models_dir = self.module_path / 'models'
        if not models_dir.exists():
            return
            
        for py_file in models_dir.glob('*.py'):
            if py_file.name == '__init__.py':
                continue
                
            try:
                with open(py_file, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                # Extract class name and _name
                class_match = re.search(r'class\s+(\w+)\s*\([^)]*models\.Model[^)]*\)', content)
                if not class_match:
                    continue
                    
                class_name = class_match.group(1)
                
                # Extract _name attribute
                name_match = re.search(r'_name\s*=\s*[\'"]([^\'\"]+)[\'"]', content)
                if not name_match:
                    continue
                    
                model_name = name_match.group(1)
                
                # Extract all method definitions
                methods = re.findall(r'def\s+(\w+)\s*\(', content)
                
                self.models[model_name] = {
                    'class_name': class_name,
                    'file': py_file,
                    'methods': set(methods)
                }
                
            except Exception as e:
                self.issues.append({
                    'type': 'model_load_error',
                    'file': str(py_file),
                    'message': f"Error loading model: {str(e)}"
                })
    
    def load_views(self):
        """Load all XML views and extract method calls"""
        views_dir = self.module_path / 'views'
        if not views_dir.exists():
            return
            
        for xml_file in views_dir.glob('*.xml'):
            try:
                tree = ET.parse(xml_file)
                root = tree.getroot()
                
                for record in root.findall('.//record'):
                    if record.get('model') == 'ir.ui.view':
                        view_id = record.get('id')
                        model_name = None
                        method_calls = []
                        
                        # Find the model this view is for
                        for field in record.findall('field'):
                            if field.get('name') == 'model':
                                model_name = field.text
                                break
                        
                        # Extract method calls from buttons
                        for button in record.findall('.//button'):
                            if button.get('type') == 'object':
                                method_name = button.get('name')
                                if method_name:
                                    method_calls.append({
                                        'method': method_name,
                                        'line': self._get_line_number(xml_file, button),
                                        'type': 'button'
                                    })
                        
                        # Extract method calls from onchange attributes
                        for field in record.findall('.//field'):
                            onchange = field.get('onchange')
                            if onchange:
                                # Extract method names from onchange expressions
                                onchange_methods = re.findall(r'(\w+)\s*\(', onchange)
                                for method in onchange_methods:
                                    method_calls.append({
                                        'method': method,
                                        'line': self._get_line_number(xml_file, field),
                                        'type': 'onchange'
                                    })
                        
                        if model_name and method_calls:
                            self.views.append({
                                'view_id': view_id,
                                'model': model_name,
                                'file': xml_file,
                                'methods': method_calls
                            })
                            
            except Exception as e:
                self.issues.append({
                    'type': 'view_load_error',
                    'file': str(xml_file),
                    'message': f"Error loading view: {str(e)}"
                })
    
    def _get_line_number(self, xml_file, element):
        """Get approximate line number for an XML element"""
        try:
            with open(xml_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # This is a simplified approach - in practice, you'd need more sophisticated XML line tracking
            element_text = ET.tostring(element, encoding='unicode')
            for i, line in enumerate(lines, 1):
                if element.get('name') and element.get('name') in line:
                    return i
            return 0
        except:
            return 0
    
    def validate_consistency(self):
        """Check that all methods called from views exist in models"""
        for view in self.views:
            model_name = view['model']
            
            if model_name not in self.models:
                self.issues.append({
                    'type': 'missing_model',
                    'view_id': view['view_id'],
                    'model': model_name,
                    'file': str(view['file']),
                    'message': f"Model '{model_name}' not found"
                })
                continue
            
            model_methods = self.models[model_name]['methods']
            
            for method_call in view['methods']:
                method_name = method_call['method']
                
                if method_name not in model_methods:
                    self.issues.append({
                        'type': 'missing_method',
                        'view_id': view['view_id'],
                        'model': model_name,
                        'method': method_name,
                        'file': str(view['file']),
                        'line': method_call['line'],
                        'call_type': method_call['type'],
                        'message': f"Method '{method_name}' not found in model '{model_name}'"
                    })
    
    def check_field_references(self):
        """Check that all field references in views exist in models"""
        # This is a simplified version - a full implementation would parse model field definitions
        pass
    
    def generate_report(self):
        """Generate a comprehensive validation report"""
        print("🔍 PHARMACY MANAGEMENT MODULE - VIEW-MODEL CONSISTENCY REPORT")
        print("=" * 70)
        
        print(f"\n📊 SUMMARY:")
        print(f"  Models Found: {len(self.models)}")
        print(f"  Views Found: {len(self.views)}")
        print(f"  Issues Found: {len(self.issues)}")
        
        if not self.issues:
            print("\n🎉 EXCELLENT! No view-model consistency issues found!")
            return True
        
        print(f"\n❌ ISSUES DETECTED:")
        print("-" * 50)
        
        # Group issues by type
        issues_by_type = {}
        for issue in self.issues:
            issue_type = issue['type']
            if issue_type not in issues_by_type:
                issues_by_type[issue_type] = []
            issues_by_type[issue_type].append(issue)
        
        for issue_type, issues in issues_by_type.items():
            print(f"\n🔸 {issue_type.upper().replace('_', ' ')} ({len(issues)} issues):")
            
            for issue in issues:
                if issue_type == 'missing_method':
                    print(f"  • {issue['file']}:{issue['line']} - {issue['message']}")
                    print(f"    View: {issue['view_id']} | Method: {issue['method']} ({issue['call_type']})")
                else:
                    print(f"  • {issue['file']} - {issue['message']}")
        
        # Provide suggested fixes
        print(f"\n🔧 SUGGESTED FIXES:")
        print("-" * 50)
        
        missing_methods = [i for i in self.issues if i['type'] == 'missing_method']
        if missing_methods:
            print("\nFor missing methods, add these to your models:")
            for issue in missing_methods[:5]:  # Show first 5
                print(f"\n  # In {issue['model']} model:")
                print(f"  def {issue['method']}(self):")
                print(f"      \"\"\"{issue['method']} method implementation\"\"\"")
                print(f"      pass")
            
            if len(missing_methods) > 5:
                print(f"\n  ... and {len(missing_methods) - 5} more methods")
        
        return False
    
    def save_report(self, filename):
        """Save the detailed report to a file"""
        with open(filename, 'w', encoding='utf-8') as f:
            f.write("PHARMACY MANAGEMENT MODULE - VIEW-MODEL CONSISTENCY REPORT\n")
            f.write("=" * 70 + "\n\n")
            
            for issue in self.issues:
                f.write(f"{issue['type']}: {issue['message']}\n")
                f.write(f"  File: {issue['file']}\n")
                if 'line' in issue:
                    f.write(f"  Line: {issue['line']}\n")
                if 'method' in issue:
                    f.write(f"  Method: {issue['method']}\n")
                f.write("\n")

def main():
    """Main validation function"""
    module_path = Path(__file__).parent
    
    validator = ViewModelValidator(module_path)
    
    print("🔄 Loading models...")
    validator.load_models()
    
    print("🔄 Loading views...")
    validator.load_views()
    
    print("🔄 Validating consistency...")
    validator.validate_consistency()
    
    print("🔄 Generating report...")
    is_valid = validator.generate_report()
    
    # Save detailed report
    validator.save_report('view_model_consistency_report.txt')
    print(f"\n📄 Detailed report saved to: view_model_consistency_report.txt")
    
    return 0 if is_valid else 1

if __name__ == "__main__":
    exit(main())
