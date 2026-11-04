#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML Validation Script for Odoo Pharmacy Management Module
Validates all XML files for syntax errors and common Odoo XML pitfalls
"""

import os
import xml.etree.ElementTree as ET
import re
from pathlib import Path

def validate_xml_file(file_path):
    """Validate a single XML file for syntax errors and common issues"""
    issues = []
    
    try:
        # Parse XML for syntax errors
        tree = ET.parse(file_path)
        root = tree.getroot()
        
        # Read file content for additional checks
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Check for unescaped characters in attributes
        lines = content.split('\n')
        for line_num, line in enumerate(lines, 1):
            # Find attribute values with unescaped < or >
            attr_pattern = r'(\w+)\s*=\s*["\'][^"\']*<[^"\']*["\']'
            matches = re.finditer(attr_pattern, line)
            for match in matches:
                attr_name = match.group(1)
                issues.append({
                    'line': line_num,
                    'type': 'unescaped_character',
                    'message': f"Unescaped '<' character in attribute '{attr_name}'",
                    'content': line.strip()
                })
            
            # Check for domain attributes with unescaped operators
            if 'domain=' in line and ('<' in line or '>' in line):
                if '&lt;' not in line and '&gt;' not in line and '<![CDATA[' not in line:
                    issues.append({
                        'line': line_num,
                        'type': 'unescaped_domain',
                        'message': "Unescaped comparison operators in domain attribute",
                        'content': line.strip()
                    })
            
            # Check for context attributes with unescaped operators
            if 'context=' in line and ('<' in line or '>' in line):
                if '&lt;' not in line and '&gt;' not in line and '<![CDATA[' not in line:
                    issues.append({
                        'line': line_num,
                        'type': 'unescaped_context',
                        'message': "Unescaped characters in context attribute",
                        'content': line.strip()
                    })
        
        return issues
        
    except ET.ParseError as e:
        return [{
            'line': e.lineno or 0,
            'type': 'syntax_error',
            'message': f"XML Syntax Error: {str(e)}",
            'content': ''
        }]
    except Exception as e:
        return [{
            'line': 0,
            'type': 'file_error',
            'message': f"Error reading file: {str(e)}",
            'content': ''
        }]

def validate_all_xml_files(module_path):
    """Validate all XML files in the Odoo module"""
    xml_files = list(Path(module_path).rglob("*.xml"))
    
    print(f"🔍 Validating {len(xml_files)} XML files...")
    print("=" * 60)
    
    total_issues = 0
    files_with_issues = 0
    
    for xml_file in xml_files:
        relative_path = xml_file.relative_to(module_path)
        issues = validate_xml_file(xml_file)
        
        if issues:
            files_with_issues += 1
            total_issues += len(issues)
            print(f"\n❌ {relative_path}")
            print("-" * 40)
            
            for issue in issues:
                print(f"  Line {issue['line']}: {issue['message']}")
                if issue['content']:
                    print(f"  Content: {issue['content']}")
                print()
        else:
            print(f"✅ {relative_path}")
    
    print("=" * 60)
    print(f"📊 SUMMARY:")
    print(f"  Total files: {len(xml_files)}")
    print(f"  Files with issues: {files_with_issues}")
    print(f"  Total issues: {total_issues}")
    
    if total_issues == 0:
        print("🎉 All XML files are valid!")
    else:
        print(f"⚠️  Found {total_issues} issues that need to be fixed")
    
    return total_issues == 0

def main():
    """Main validation function"""
    module_path = Path(__file__).parent
    
    print("🏥 Pharmacy Management Module - XML Validation")
    print("=" * 60)
    
    is_valid = validate_all_xml_files(module_path)
    
    if not is_valid:
        print("\n🔧 QUICK FIX GUIDE:")
        print("1. Replace '<' with '&lt;' in attribute values")
        print("2. Replace '>' with '&gt;' in attribute values")
        print("3. Or use CDATA sections: <![CDATA[...]]>")
        print("4. Common locations: domain, context, modifiers attributes")
    
    return 0 if is_valid else 1

if __name__ == "__main__":
    exit(main())
