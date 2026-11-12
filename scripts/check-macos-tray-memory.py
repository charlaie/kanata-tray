"""Stress a built macOS tray with simulated Kanata events, without grabbing keys.

Usage: python3 scripts/check-macos-tray-memory.py dist/kanata-tray-macos
Creates a temporary menu-bar icon and leaves logs/results in a temp directory.
"""

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time

def wait_for(predicate, timeout=40):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(0.025)
    raise TimeoutError('Timed out waiting for tray processing')

def fake_kanata():
    root = Path(os.environ['TRAY_TEST_DIR'])
    port = int(sys.argv[sys.argv.index('--port') + 1])
    with socket.socket() as server:
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('127.0.0.1', port))
        server.listen(1)
        conn, _ = server.accept()
        with conn:
            conn.recv(4096)
            conn.sendall(b'{"LayerNames":{"names":["normal","nav","template"]}}\n')
            last = None
            while True:
                phase = root / 'phase.json'
                if phase.exists():
                    try:
                        job = json.loads(phase.read_text())
                    except json.JSONDecodeError:
                        continue
                    if job['id'] != last:
                        last = job['id']
                        messages = []
                        for i in range(job['count']):
                            if job['mode'] == 'reload':
                                messages.append({'ConfigFileReload': {'new': 'test'}})
                            else:
                                layer = job['layers'][i % len(job['layers'])]
                                messages.append({'LayerChange': {'new': layer}})
                        messages.append({'LayerChange': {'new': 'BARRIER_' + str(last)}})
                        conn.sendall(b''.join(json.dumps(m).encode() + b'\n' for m in messages))
                time.sleep(0.02)

def footprint(pid):
    text = subprocess.check_output(['/usr/bin/footprint', '-p', str(pid)], text=True, stderr=subprocess.STDOUT)
    match = re.search(r'phys_footprint:\s+([\d.]+)\s+(KB|MB|GB)', text)
    if not match:
        raise RuntimeError(text)
    return float(match[1]) * {'KB': 1 / 1024, 'MB': 1, 'GB': 1024}[match[2]]

def controller(binary):
    if sys.platform != 'darwin':
        raise RuntimeError('This check requires a macOS graphical login session')
    if not binary.is_file():
        raise FileNotFoundError(binary)
    repo = Path(__file__).resolve().parents[1]
    root = Path(tempfile.mkdtemp(prefix='kanata-tray-memory-'))
    (root / 'icons').mkdir()
    for name, original in [('normalTemplate.ico', 'default.ico'), ('navTemplate.ico', 'pause.ico'), ('samePlain.ico', 'default.ico')]:
        shutil.copy(repo / 'status_icons' / original, root / 'icons' / name)
    fake = root / 'fake-kanata'
    fake.write_text('#!/bin/sh\nexec ' + shlex.quote(sys.executable) + ' ' + shlex.quote(str(Path(__file__).resolve())) + ' --fake "$@"\n')
    fake.chmod(0o755)
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1', 0))
        port = reservation.getsockname()[1]
    (root / 'kanata-tray.toml').write_text(f'''
[defaults]
tcp_port = {port}
[defaults.layer_icons]
normal = 'normalTemplate.ico'
nav = 'navTemplate.ico'
template = 'samePlain.ico'
[presets.test]
kanata_executable = '{fake}'
kanata_config = '{root}/unused.kbd'
autorun = true
''')
    env = dict(os.environ, KANATA_TRAY_CONFIG_DIR=str(root), KANATA_TRAY_LOG_DIR=str(root), TRAY_TEST_DIR=str(root))
    with (root / 'console.log').open('w') as console:
        proc = subprocess.Popen([str(binary), '--log-level=1'], env=env, stdout=console, stderr=console)
        def log():
            path = root / 'kanata_tray_lastrun.log'
            return path.read_text() if path.exists() else ''
        try:
            wait_for(lambda: 'RequestLayerNames' in log())
            time.sleep(0.2)
            results = []
            for i, (name, mode, layers, count) in enumerate([
                ('same_1000', 'layers', ['normal'], 1000),
                ('same_5000', 'layers', ['normal'], 5000),
                ('alternating_5000', 'layers', ['normal', 'nav'], 5000),
                ('alternating_10000', 'layers', ['normal', 'nav'], 5000),
                ('template_5000', 'layers', ['normal', 'template'], 5000),
                ('reload_10', 'reload', [], 10),
            ]):
                before = log().count('Updating tray icon')
                (root / 'phase.json').write_text(json.dumps(dict(id=i, mode=mode, layers=layers, count=count)))
                wait_for(lambda: 'BARRIER_' + str(i) in log())
                time.sleep(0.2)
                updates = log().count('Updating tray icon') - before
                expected = {'same_1000': 1, 'same_5000': 0, 'alternating_5000': 5000,
                            'alternating_10000': 5000, 'template_5000': 5000, 'reload_10': 20}[name]
                if updates != expected:
                    raise AssertionError(f'{name}: {updates} updates, expected {expected}')
                result = dict(phase=name, updates=updates, footprint_MB=footprint(proc.pid))
                results.append(result)
                print(json.dumps(result), flush=True)
            (root / 'results.json').write_text(json.dumps(results, indent=2))
            # Allow allocator/cache variation, but reject sustained growth of
            # the size seen in the old native icon-loading path.
            if results[4]['footprint_MB'] - results[2]['footprint_MB'] > 10:
                raise AssertionError('Memory grew by over 10 MB after icon warmup')
            print('logs=' + str(root), flush=True)
        finally:
            proc.terminate()
            proc.wait(timeout=10)
            print('tray_exit=' + str(proc.returncode), flush=True)

if __name__ == '__main__':
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    if sys.argv[1] == '--fake':
        fake_kanata()
    else:
        controller(Path(sys.argv[1]).resolve())
