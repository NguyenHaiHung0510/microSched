"""Owner192 project doctor; source-only never implies native runtime acceptance."""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import subprocess

SOURCE = Path('C:/Users/os/.codex/worktrees/mimi-owner144-approved-batch/microsched').resolve()


def validate_binding(binding):
    if binding.get('lane') != 'mimi' or Path(binding['source']).resolve() != SOURCE:
        raise ValueError('exact_mimi_lane_and_approved_checkout_required')
    head = subprocess.check_output(['git', '-C', str(SOURCE), 'rev-parse', 'HEAD'], text=True).strip()
    if head != binding.get('head'):
        raise ValueError('candidate_head_changed')
    files = binding.get('files')
    if not isinstance(files, dict) or not files:
        raise ValueError('nonempty_supplied_file_mapping_required')
    for relative, wanted in files.items():
        parts = PurePosixPath(relative).parts
        if (not parts or '\\' in relative or ':' in relative or '..' in parts
                or PurePosixPath(relative).is_absolute()
                or any(p.startswith('.env') and p != '.env.example' for p in parts)):
            raise ValueError('unsafe_binding_path')
        file = SOURCE.joinpath(*parts)
        if not file.resolve().is_relative_to(SOURCE) or file.is_symlink() or file.is_junction():
            raise ValueError('binding_file_escape_or_link')
        if not file.is_file() or hashlib.sha256(file.read_bytes()).hexdigest() != wanted:
            raise ValueError('candidate_file_changed:' + relative)
    return {'source': str(SOURCE), 'head': head, 'files_checked': len(files),
            'source_status': 'SUPPLIED_FILES_MATCH', 'source_closure': 'NOT_ESTABLISHED_BY_DOCTOR', 'runtime_status': 'NOT_CHECKED',
            'native_live_browser_device_acceptance': 'NOT_RUN', 'paid_calls': 0}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['doctor'])
    parser.add_argument('--binding', required=True)
    args = parser.parse_args()
    try:
        result = validate_binding(json.loads(Path(args.binding).read_text(encoding='utf-8-sig')))
    except (ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        print(json.dumps({'status': 'BLOCKED', 'reason': str(error), 'paid_calls': 0}))
        return 2
    print(json.dumps(result))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
