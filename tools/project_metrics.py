"""统计文件物理行数和真实测试结果，不推算个人贡献或AI代码比例。"""
import json
import subprocess
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    paths = [ROOT / 'server.py', *sorted((ROOT / 'modules').glob('*.py')),
             *sorted((ROOT / 'static').glob('*')), *sorted((ROOT / 'tests').glob('*.py')),
             *sorted((ROOT / 'tools').glob('*.py')), *sorted((ROOT / 'tools').glob('*.cjs'))]
    files = {str(p.relative_to(ROOT)).replace('\\', '/'): len(p.read_text(encoding='utf-8').splitlines()) for p in paths if p.is_file()}
    count = subprocess.run(['git', 'rev-list', '--count', 'HEAD'], cwd=ROOT, capture_output=True, text=True)
    report = {'generated_at': datetime.now().astimezone().isoformat(timespec='seconds'),
              'method': '物理文本行数，含空行和注释；不代表工作量、作者或覆盖率',
              'files': files, 'physical_lines': sum(files.values()),
              'repository_commit_count': int(count.stdout.strip()) if count.returncode == 0 else None,
              'personal_commit_count': '无法从共享基线可靠归属，需本人提供证据',
              'ai_assisted_lines': '未逐行记录，不能可靠精确统计'}
    out = ROOT / 'output' / 'acceptance' / 'project-metrics.json'
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'统计已保存：{out}')


if __name__ == '__main__':
    main()
