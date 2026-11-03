"""执行真实集成测试并保存可审查结果。任何失败均以非零退出。"""
import json
import platform
import sys
import time
import unittest
from contextlib import redirect_stderr
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tests'))


class Result(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []

    def startTest(self, test):
        self.started = time.perf_counter()
        super().startTest(test)

    def record(self, test, status):
        self.records.append({'id': test.id(), 'status': status,
                             'seconds': round(time.perf_counter() - self.started, 4)})

    def addSuccess(self, test):
        super().addSuccess(test)
        self.record(test, 'passed')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.record(test, 'failed')

    def addError(self, test, err):
        super().addError(test, err)
        self.record(test, 'error')


def main():
    output = ROOT / 'output' / 'acceptance'
    output.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    with (output / 'tests.log').open('w', encoding='utf-8') as log, redirect_stderr(log):
        suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'))
        result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=Result).run(suite)
    report = {'executed_at': datetime.now().astimezone().isoformat(timespec='seconds'),
              'python': platform.python_version(), 'os': platform.platform(),
              'tests_run': result.testsRun, 'failures': len(result.failures),
              'errors': len(result.errors), 'successful': result.wasSuccessful(),
              'duration_seconds': round(time.perf_counter() - started, 3),
              'tests': result.records}
    (output / 'test-results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"{result.testsRun} tests; failures={len(result.failures)}, errors={len(result.errors)}")
    print(f'详细结果：{output}')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
