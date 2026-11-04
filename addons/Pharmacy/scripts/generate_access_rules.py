"""Generate suggested `ir.model.access.csv` entries for models missing access rules.

Run inside a Python environment with the module path, or from the repo root. It writes
a CSV to `security/suggested_ir_model_access.csv` containing read-only access for
`base.group_user` for discovered models that appear to be missing rules.

This is a helper — please review before installing into `security/ir.model.access.csv`.
"""
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODELS_DIR = ROOT / 'models'
OUT = ROOT / 'security' / 'suggested_ir_model_access.csv'

MODEL_RE = re.compile(r"class\s+([A-Za-z0-9_]+)\(models\.Model\):")
NAME_RE = re.compile(r"_name\s*=\s*\"([a-z0-9_.]+)\"")

def find_models():
    models = {}
    for py in MODELS_DIR.glob('*.py'):
        text = py.read_text(encoding='utf-8')
        # try _name first
        mname = None
        m = NAME_RE.search(text)
        if m:
            mname = m.group(1)
        else:
            # fallback: sniff class names and guess
            m2 = MODEL_RE.findall(text)
            if m2:
                for c in m2:
                    # convert CamelCase to snake.case guess (best-effort)
                    snake = ''.join(['_'+i.lower() if i.isupper() else i for i in c]).lstrip('_')
                    models.setdefault(snake, []).append(py.name)
        if mname:
            models[mname] = [py.name]
    return models

def generate_csv(models):
    lines = [
        'id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink'
    ]
    for i, model in enumerate(sorted(models.keys()), start=1):
        key = f'Pharmacy.access_{model.replace(".", "_")}'
        name = f'access_{model.replace(".", "_")}'
        model_ref = f'Pharmacy.model_{model.replace(".", "_")}'
        lines.append(f'{key},{name},{model_ref},base.group_user,1,0,0,0')
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text('\n'.join(lines), encoding='utf-8')
    print('Wrote', OUT)

if __name__ == '__main__':
    models = find_models()
    # Filter out common Odoo / transient models that shouldn't get rules here
    ignore = {'ir.logging', 'mail.activity', 'mail.message'}
    models = {k: v for k, v in models.items() if k not in ignore}
    generate_csv(models)
