"""Offline region recognition using a locally installed Tesseract executable."""
import io
import os
from pathlib import Path
import re
import shutil
import subprocess

DEFAULT_OCR = {'languages': 'eng+kor', 'executable': ''}


def validate_options(options):
    if not isinstance(options, dict):
        raise ValueError('Invalid OCR settings.')
    languages = options.get('languages', 'eng+kor')
    executable = options.get('executable', '')
    if not isinstance(languages, str) or not re.fullmatch(r'[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*', languages):
        raise ValueError('Use language codes separated by +, for example eng+kor or eng+jpn.')
    if not isinstance(executable, str):
        raise ValueError('Choose a valid Tesseract executable path.')
    return {'languages': languages, 'executable': executable.strip()}


def find_executable(configured=''):
    if configured:
        if Path(configured).is_file():
            return configured
        raise RuntimeError('Tesseract executable not found. Update the path in OCR settings.')
    found = shutil.which('tesseract')
    if found:
        return found
    for root in (os.environ.get('ProgramFiles', ''), os.environ.get('LOCALAPPDATA', '')):
        for suffix in ('Tesseract-OCR/tesseract.exe', 'Programs/Tesseract-OCR/tesseract.exe'):
            candidate = Path(root) / suffix
            if root and candidate.is_file():
                return str(candidate)
    raise RuntimeError('Install Tesseract OCR with English and Korean language data, then choose '
                       'tesseract.exe in OCR settings (or add it to PATH). See README for setup.')


def run(arguments, data=None):
    try:
        result = subprocess.run(arguments, input=data, capture_output=True, timeout=60,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('OCR timed out. Try a smaller selection.') from error
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip() or 'Tesseract failed.')
    return result.stdout.decode('utf-8', errors='replace')


def recognize(image, options):
    options = validate_options(options)
    executable = find_executable(options['executable'])
    installed = set(run([executable, '--list-langs']).splitlines())
    missing = set(options['languages'].split('+')) - installed
    if missing:
        raise RuntimeError('Missing Tesseract language data: ' + ', '.join(sorted(missing)) +
                           '. Install these .traineddata files in Tesseract\'s tessdata folder, '
                           'or change OCR settings.')
    stream = io.BytesIO()
    image.convert('RGB').save(stream, 'PNG')
    return run([executable, 'stdin', 'stdout', '-l', options['languages'], '--psm', '6'],
               stream.getvalue()).strip()
