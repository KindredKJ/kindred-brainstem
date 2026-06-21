from pathlib import Path
import zipfile, hashlib, base64
NAME='kindred_brainstem'; VERSION='0.1.0'; DIST=f'{NAME}-{VERSION}.dist-info'
def _metadata(base):
    d=Path(base)/DIST; d.mkdir(parents=True, exist_ok=True)
    (d/'METADATA').write_text('Metadata-Version: 2.1\nName: kindred-brainstem\nVersion: 0.1.0\nRequires-Python: >=3.12\nRequires-Dist: typer>=0.12.0\nRequires-Dist: pyyaml>=6.0.1\nRequires-Dist: pydantic>=2.7.0\n', encoding='utf-8')
    (d/'WHEEL').write_text('Wheel-Version: 1.0\nGenerator: brainstem-build-backend\nRoot-Is-Purelib: true\nTag: py3-none-any\n', encoding='utf-8')
    (d/'entry_points.txt').write_text('[console_scripts]\nbrainstem = brainstem.cli.app:app\n', encoding='utf-8')
    (d/'RECORD').write_text('', encoding='utf-8')
    return DIST
def prepare_metadata_for_build_editable(metadata_directory, config_settings=None): return _metadata(metadata_directory)
def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None): return _metadata(metadata_directory)
def get_requires_for_build_editable(config_settings=None): return []
def get_requires_for_build_wheel(config_settings=None): return []
def build_editable(wheel_directory, config_settings=None, metadata_directory=None): return build_wheel(wheel_directory, config_settings, metadata_directory, editable=True)
def build_wheel(wheel_directory, config_settings=None, metadata_directory=None, editable=False):
    wheel=Path(wheel_directory)/f'{NAME}-{VERSION}-py3-none-any.whl'
    files=[]
    with zipfile.ZipFile(wheel,'w',zipfile.ZIP_DEFLATED) as z:
        if editable:
            content=str(Path.cwd())+'\n'; z.writestr('kindred_brainstem_editable.pth', content); files.append(('kindred_brainstem_editable.pth', content.encode()))
        else:
            for p in Path('brainstem').rglob('*.py'):
                data=p.read_bytes(); z.writestr(str(p),data); files.append((str(p),data))
        meta_dir=Path(metadata_directory)/DIST if metadata_directory else None
        meta_files=[]
        if meta_dir and meta_dir.exists():
            for p in meta_dir.iterdir(): meta_files.append((f'{DIST}/{p.name}', p.read_bytes()))
        else:
            import tempfile
            with tempfile.TemporaryDirectory() as td:
                _metadata(td)
                for p in (Path(td)/DIST).iterdir(): meta_files.append((f'{DIST}/{p.name}', p.read_bytes()))
        record_lines=[]
        for arc,data in files+[(a,d) for a,d in meta_files if not a.endswith('/RECORD')]:
            z.writestr(arc,data); h=base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b'=').decode(); record_lines.append(f'{arc},sha256={h},{len(data)}')
        record_lines.append(f'{DIST}/RECORD,,')
        z.writestr(f'{DIST}/RECORD','\n'.join(record_lines))
    return wheel.name
