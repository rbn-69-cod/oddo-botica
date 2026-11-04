#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XML Escaping Fix Script for Pharmacy Management System
Automatically fixes unescaped characters in XML view files
"""

import os
import re
import shutil
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path


def backup_file(file_path):
    """Create a backup of the original file"""
    backup_path = f"{file_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    shutil.copy2(file_path, backup_path)
    print(f"  📁 Backup created: {os.path.basename(backup_path)}")
    return backup_path


def fix_domain_escaping(content):
    """Fix unescaped characters in domain attributes"""
    fixes_applied = 0

    # Pattern to match domain attributes
    domain_pattern = r'domain="([^"]*[<>=][^"]*)"'

    def escape_domain(match):
        nonlocal fixes_applied
        domain_content = match.group(1)
        original_content = domain_content

        # Only escape if not already escaped and not in CDATA
        if "<![CDATA[" not in domain_content:
            # Escape comparison operators
            domain_content = domain_content.replace("&", "&amp;")  # Must be first
            domain_content = domain_content.replace("<", "&lt;")
            domain_content = domain_content.replace(">", "&gt;")
            domain_content = domain_content.replace('"', "&quot;")

            if domain_content != original_content:
                fixes_applied += 1

        return f'domain="{domain_content}"'

    fixed_content = re.sub(domain_pattern, escape_domain, content)
    return fixed_content, fixes_applied


def fix_context_escaping(content):
    """Fix unescaped characters in context attributes"""
    fixes_applied = 0

    # Pattern to match context attributes
    context_pattern = r'context="([^"]*[{}\'"][^"]*)"'

    def escape_context(match):
        nonlocal fixes_applied
        context_content = match.group(1)
        original_content = context_content

        # Only escape if not already escaped and not in CDATA
        if "<![CDATA[" not in context_content:
            # Escape special characters
            context_content = context_content.replace("&", "&amp;")  # Must be first
            context_content = context_content.replace("<", "&lt;")
            context_content = context_content.replace(">", "&gt;")
            context_content = context_content.replace('"', "&quot;")

            if context_content != original_content:
                fixes_applied += 1

        return f'context="{context_content}"'

    fixed_content = re.sub(context_pattern, escape_context, content)
    return fixed_content, fixes_applied


def fix_other_attributes(content):
    """Fix other common XML escaping issues"""
    fixes_applied = 0

    # Fix style attributes with percentage signs
    style_pattern = r'style="([^"]*%[^"]*)"'

    def escape_style(match):
        nonlocal fixes_applied
        style_content = match.group(1)
        original_content = style_content

        # Replace %% with % if double-escaped
        if "%%" in style_content:
            style_content = style_content.replace("%%", "%")
            fixes_applied += 1

        return f'style="{style_content}"'

    fixed_content = re.sub(style_pattern, escape_style, content)
    return fixed_content, fixes_applied


def validate_xml_syntax(file_path):
    """Validate that the XML file is syntactically correct"""
    try:
        ET.parse(file_path)
        return True, None
    except ET.ParseError as e:
        return False, str(e)


def fix_xml_file(file_path):
    """Fix XML escaping issues in a single file"""
    relative_path = os.path.relpath(file_path, start=Path(__file__).parent)
    print(f"\n🔧 Processing: {relative_path}")

    # Read original content
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            original_content = f.read()
    except Exception as e:
        print(f"  ❌ Error reading file: {e}")
        return False

    # Apply fixes
    content = original_content
    total_fixes = 0

    # Fix domain attributes
    content, domain_fixes = fix_domain_escaping(content)
    total_fixes += domain_fixes
    if domain_fixes > 0:
        print(f"  ✅ Fixed {domain_fixes} domain escaping issues")

    # Fix context attributes
    content, context_fixes = fix_context_escaping(content)
    total_fixes += context_fixes
    if context_fixes > 0:
        print(f"  ✅ Fixed {context_fixes} context escaping issues")

    # Fix other attributes
    content, other_fixes = fix_other_attributes(content)
    total_fixes += other_fixes
    if other_fixes > 0:
        print(f"  ✅ Fixed {other_fixes} other escaping issues")

    # Only write if changes were made
    if content != original_content:
        # Create backup
        backup_path = backup_file(file_path)

        # Write fixed content
        try:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)

            # Validate the fixed XML
            is_valid, error = validate_xml_syntax(file_path)
            if is_valid:
                print(f"  ✅ File fixed and validated ({total_fixes} fixes applied)")
                return True
            else:
                print(f"  ❌ Fixed file has syntax errors: {error}")
                # Restore backup
                shutil.copy2(backup_path, file_path)
                print(f"  📁 Restored from backup")
                return False

        except Exception as e:
            print(f"  ❌ Error writing fixed file: {e}")
            return False
    else:
        print(f"  ✅ No fixes needed")
        return True


def fix_all_xml_files(module_path):
    """Fix all XML files in the module"""
    view_files = [
        "views/pharmacy_branch_views.xml",
        "views/pharmacy_patient_views.xml",
        "views/pharmacy_coverage_rule_views.xml",
        "views/pharmacy_controlled_substance_register_views.xml",
        "views/pharmacy_dosage_form_views.xml",
        "views/pharmacy_discount_rule_views.xml",
        "views/pharmacy_accounting_views.xml",
        "views/pharmacy_pricing_views.xml",
        "views/pharmacy_stock_lot_views.xml",
        "views/pharmacy_insurer_views.xml",
        "views/pharmacy_claim_views.xml",
        "views/pharmacy_prescription_views.xml",
    ]

    print("🏥 Pharmacy Management System - XML Escaping Fix")
    print("=" * 60)
    print(f"📍 Module path: {module_path}")
    print(f"📋 Processing {len(view_files)} view files...")

    success_count = 0
    total_count = 0

    for view_file in view_files:
        file_path = os.path.join(module_path, view_file)

        if os.path.exists(file_path):
            total_count += 1
            if fix_xml_file(file_path):
                success_count += 1
        else:
            print(f"\n⚠️  File not found: {view_file}")

    print("\n" + "=" * 60)
    print(f"📊 SUMMARY:")
    print(f"  Files processed: {total_count}")
    print(f"  Successfully fixed: {success_count}")
    print(f"  Failed: {total_count - success_count}")

    if success_count == total_count:
        print("🎉 All files processed successfully!")
    else:
        print("⚠️  Some files had issues. Check the output above.")

    return success_count == total_count


def main():
    """Main function"""
    module_path = Path(__file__).parent

    print("🔧 Starting XML escaping fixes...")
    print("📝 This script will:")
    print("   1. Create backups of all modified files")
    print("   2. Fix unescaped characters in domain and context attributes")
    print("   3. Validate XML syntax after fixes")
    print("   4. Restore from backup if validation fails")
    print("")

    # Auto-proceed without confirmation
    print("Proceeding with automatic fixes...")

    success = fix_all_xml_files(module_path)

    if success:
        print("\n🎯 NEXT STEPS:")
        print("1. Review the changes in the modified files")
        print("2. Test the module installation: python odoo-bin -u Pharmacy")
        print("3. Check that all views load correctly")
        print("4. Run the XML validation script to confirm fixes")
        print("\n💡 TIP: Keep the backup files until you've tested the system")
        return 0
    else:
        print("\n🚨 Some files could not be fixed automatically.")
        print("Please review the errors above and fix them manually.")
        return 1


if __name__ == "__main__":
    exit(main())
