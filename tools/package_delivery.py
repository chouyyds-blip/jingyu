"""打包明确列出的源码、课程参考材料和虚构验收库；不收集原业务库或Git目录。"""
import json
import sqlite3
import uuid
import zipfile
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    output = ROOT / 'output' / 'package'
    output.mkdir(parents=True, exist_ok=True)
    files = [ROOT / name for name in ('README.md', 'server.py', 'start.bat', 'start-acceptance.bat', '.gitignore', '.gitattributes')]
    for folder, patterns in [('modules', ('*.py',)), ('static', ('*.html', '*.js', '*.css')),
                             ('tests', ('*.py',)), ('tools', ('*.py', '*.cjs')), ('docs', ('*.md',)),
                             ('output/pdf', ('*.pdf',)), ('output/acceptance', ('*.json', 'tests.log', '*.png'))]:
        for pattern in patterns:
            files.extend(p for p in (ROOT / folder).glob(pattern) if p.name != 'browser-failure.png')
    files.append(ROOT / 'output' / '课程大作业工程参考稿.md')
    missing = [str(p) for p in files if not p.is_file()]
    if missing:
        raise RuntimeError(f'交付文件缺失：{missing}')
    target = output / '课程项目验收交付包.zip'
    temporary = ROOT / 'tmp' / ('delivery-' + uuid.uuid4().hex + '.db')
    source = ROOT / 'data' / 'acceptance.db'
    if not source.is_file():
        raise RuntimeError('先用prepare_demo.py生成独立验收库')
    (ROOT / 'tmp').mkdir(exist_ok=True)
    try:
        with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
            with closing(sqlite3.connect(temporary)) as dst:
                src.backup(dst)
                if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('验收库备份完整性失败')
        with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as package:
            for file in sorted(set(files)):
                package.write(file, str(file.relative_to(ROOT)).replace('\\', '/'))
            package.write(temporary, 'data/acceptance.db')
            manifest = {'created_at': datetime.now().astimezone().isoformat(timespec='seconds'),
                        'database': '仅含生成的虚构验收数据，不包含data/app.db',
                        'start': '解压后双击start-acceptance.bat',
                        'report_status': 'AI辅助工程参考稿，个人过程材料待本人补齐'}
            package.writestr('交付说明.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        with zipfile.ZipFile(target) as package:
            if package.testzip() is not None:
                raise RuntimeError('ZIP校验失败')
            if 'data/app.db' in package.namelist():
                raise RuntimeError('不应包含原业务库')
        print(f'交付包：{target}（{target.stat().st_size}字节）')
    finally:
        temporary.unlink(missing_ok=True)


if __name__ == '__main__':
    main()
