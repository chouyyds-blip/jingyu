"""用 SQLite backup API 一致性备份，拒绝覆盖已有文件。"""
import argparse
import sqlite3
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'app.db')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    source = args.db.resolve()
    target = (args.out or ROOT / 'output' / 'backups' / f'{source.stem}-{datetime.now():%Y%m%d-%H%M%S-%f}.db').resolve()
    if not source.is_file():
        parser.exit(1, f'源数据库不存在：{source}\n')
    if target.exists():
        parser.exit(1, f'目标已存在，未覆盖：{target}\n')
    target.parent.mkdir(parents=True, exist_ok=True)
    # URI read-only 防止写错路径时静默生成空源库。
    with closing(sqlite3.connect(source.as_uri() + '?mode=ro', uri=True)) as src:
        with closing(sqlite3.connect(target)) as dst:
            src.backup(dst)
            if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                raise RuntimeError('备份完整性校验失败')
    print(f'备份通过完整性校验：{target}')
    print('恢复时先停止服务；建议使用 python server.py --db "备份文件路径" 验证备份。')


if __name__ == '__main__':
    main()
