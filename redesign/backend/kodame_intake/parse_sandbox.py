"""Bound parser CPU, memory, output and elapsed time in a disposable process."""
import json
import os
import signal
from pathlib import Path
import subprocess
import sys
import tempfile
from .parsers import ParseError


class ParseLimitExceeded(ParseError):
    pass


def parse_isolated(path, extension, *, full_text=True):
    if os.getenv('PARSER_ISOLATION', 'false').lower() != 'true':
        from .parsers import parse_document
        return parse_document(path, extension, full_text=full_text)
    with tempfile.TemporaryDirectory(prefix='kodame-parse-') as temp:
        result_path = Path(temp) / 'result.json'
        process = subprocess.Popen([sys.executable, '-m', 'kodame_intake.parse_sandbox', str(path), extension, str(result_path)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        try:
            process.communicate(timeout=int(os.getenv('PARSER_TIMEOUT_SECONDS','240')))
        except subprocess.TimeoutExpired as exc:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
            raise ParseLimitExceeded('문서 추출 시간 한도를 초과했습니다. 파일을 나누어 등록해 주세요.') from exc
        if process.returncode or not result_path.is_file():
            raise ParseLimitExceeded('문서 추출 자원 한도 또는 파서 오류입니다. 원본은 보존됩니다.')
        payload = json.loads(result_path.read_text(encoding='utf-8'))
        if payload.get('error'):
            raise ParseError(payload['error'])
        return payload['text'], payload['method']


def main():
    import resource
    memory = int(os.getenv('PARSER_MEMORY_MB','512')) * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (memory, memory))
    seconds = int(os.getenv('PARSER_TIMEOUT_SECONDS','240'))
    resource.setrlimit(resource.RLIMIT_CPU, (seconds, seconds))
    resource.setrlimit(resource.RLIMIT_FSIZE, (64*1024*1024,64*1024*1024))
    from .parsers import parse_document
    try:
        text, method = parse_document(Path(sys.argv[1]), sys.argv[2], full_text=True)
        if len(text) > int(os.getenv('PARSER_MAX_CHARS','8000000')):
            raise ParseError('추출 원문이 800만자를 초과했습니다. 파일을 나누어 주세요.')
        payload = {'text': text, 'method': method}
    except Exception as exc:
        payload = {'error': f'문서 추출 실패: {type(exc).__name__}'}
    Path(sys.argv[3]).write_text(json.dumps(payload,ensure_ascii=False), encoding='utf-8')


if __name__ == '__main__':
    main()
