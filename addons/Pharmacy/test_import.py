
import sys
import os

# Add Odoo and local path
sys.path.append('/home/nick/odoo')
sys.path.append('/home/nick')

try:
    import odoo
    from odoo.modules.module import get_module_path, get_manifest
    
    module_name = 'Pharmacy'
    path = get_module_path(module_name)
    print(f"Module path: {path}")
    
    manifest = get_manifest(module_name)
    print(f"Manifest keys: {list(manifest.keys()) if manifest else 'None'}")
    
    print("\nAttempting to import Pharmacy...")
    import Pharmacy
    print("Pharmacy imported successfully!")
    
except ImportError as e:
    print(f"ImportError: {e}")
    import traceback
    traceback.print_exc()
except Exception as e:
    print(f"An error occurred: {e}")
    import traceback
    traceback.print_exc()
