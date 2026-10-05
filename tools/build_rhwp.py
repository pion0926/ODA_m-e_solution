"""Prepare/publish pinned rHWP Studio with auditable K-ODAME integration.

See docs/service/development-tooling.md for fetching the exact source and npm core.
No source download or production deployment is performed by this script.
"""
import argparse
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSION = '0.8.6'
COMMIT = 'f1f9c6ae58344ee9368996d3543f76b9345cf227'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError(f'Upstream contract changed: expected one {old[:70]!r}')
    return text.replace(old, new, 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('source', type=Path)
    parser.add_argument('--publish', action='store_true')
    args = parser.parse_args()
    revision = subprocess.check_output(['git', '-C', str(args.source), 'rev-parse', 'HEAD'], text=True).strip()
    if revision != COMMIT:
        raise ValueError('Unexpected rHWP source commit')
    studio = args.source / 'rhwp-studio'
    if json.loads((studio / 'package.json').read_text())['version'] != VERSION:
        raise ValueError('Unexpected Studio version')
    if json.loads((args.source / 'pkg/package.json').read_text())['version'] != VERSION:
        raise ValueError('Unexpected WASM package version')
    if not args.publish:
        main_file = studio / 'src/main.ts'
        source = main_file.read_text(encoding='utf-8')
        if 'K-ODAME compatibility methods' not in source:
            bridge = (ROOT / 'tools/rhwp-service-bridge.ts').read_text(encoding='utf-8')
            source = replace_once(source, 'installEmbedRuntime({', bridge + '\ninstallEmbedRuntime({')
        source = source.replace('  maybeShowSkinOnboarding();', '  // K-ODAME owns the viewer UX; do not show standalone skin onboarding.')
        main_file.write_text(source, encoding='utf-8')
        # This is an authenticated embedded viewer, not a standalone offline PWA.
        config = studio / 'vite.config.ts'
        text = config.read_text(encoding='utf-8')
        if 'disable: true' not in text:
            config.write_text(replace_once(text, 'VitePWA({', 'VitePWA({\n      disable: true,'), encoding='utf-8')
        return
    dist = studio / 'dist'
    html = (dist / 'index.html').read_text(encoding='utf-8')
    if '/assets/rhwp/assets/' not in html:
        raise ValueError('Build with --base=/assets/rhwp/')
    target = ROOT / 'assets/rhwp'
    html, count = re.subn(r'<script type="module" crossorigin src="(/assets/rhwp/assets/[^\"]+\.js)"></script>',
        r'<script type="module" data-studio-module="\1" src="/assets/rhwp/studio-loader.js"></script>', html)
    if count != 1:
        raise ValueError('Expected one Studio module entry')
    (target / 'core' / VERSION).mkdir(parents=True, exist_ok=True)
    for name in ('rhwp.js', 'rhwp_bg.wasm', 'LICENSE'):
        shutil.copy2(args.source / 'pkg' / name, target / 'core' / VERSION / name)
    # Keep service-owned guard/QA/preview code out of the generated minified bundle.
    html = html.replace('</head>', '<script src="/assets/rhwp/service-host.js"></script>\n'
                        '<script type="module" src="/assets/rhwp/report-qa.js"></script>\n'
                        '<script type="module" src="/assets/rhwp/section-preview-mode.js"></script>\n</head>')
    # Obsolete hashed assets may be retained for in-flight browser sessions.
    for item in dist.iterdir():
        if item.name not in {'assets', 'icons', 'images', 'favicon.ico', 'theme-init.js', 'print.html'}:
            continue
        if item.is_dir():
            shutil.copytree(item, target / item.name, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target / item.name)
    (target / 'index.html').write_text(html, encoding='utf-8')
    shutil.copy2(args.source / 'LICENSE', target / 'LICENSE')
    hashes = {p.relative_to(target).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
              for p in target.rglob('*') if p.is_file() and p.suffix in {'.js', '.css', '.wasm', '.html'}}
    (target / 'version.json').write_text(json.dumps({
        'version': VERSION, 'source_commit': COMMIT,
        'source': 'https://github.com/edwardkim/rhwp/tree/' + COMMIT,
        'core_package': '@rhwp/core@' + VERSION,
        'build': 'RHWP_WITHOUT_HWPCTRL=1 RHWP_DISABLE_EXTERNAL_WEBFONTS=1 npm run build -- --base=/assets/rhwp/',
        'sha256': hashes,
    }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    main()
