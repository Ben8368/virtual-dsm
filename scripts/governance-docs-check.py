#!/usr/bin/env python3
"""Check forced-load budgets, routes, links and ADR headers."""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ERRORS: list[str] = []

BUDGETS = [
    ('AGENTS.md', 85, 5200),
    ('CONTEXT.md', 45, 3000),
    ('LESSONS.md', 20, 1800),
    ('CLAUDE.md', 12, 800),
    ('.cursorrules', 12, 800),
]

REQUIRED_SECTIONS = {
    'AGENTS.md': ['## 开局与按需读取', '## 不可跨越的边界', '## 治理文档自治理', 'docs/GOVERNANCE.md'],
    'CONTEXT.md': ['## 当前决策', '## 近期优先级', '## 最近验证', '## 按需入口'],
    'LESSONS.md': [
        'docs/lessons/governance.md',
        'docs/lessons/qemu.md',
        'docs/lessons/arm64.md',
        'docs/lessons/windows.md',
    ],
}

ROUTED_TARGETS = [
    'docs/GOVERNANCE.md',
    'docs/AI_RULES.md',
    'docs/PRODUCT.md',
    'docs/QUALITY.md',
    'docs/RISK_REGISTER.md',
    'docs/TECH_DEBT.md',
    'docs/MAINTAINERS.md',
    'docs/ADR/README.md',
    'docs/platforms.md',
    'docs/ci.md',
    'docs/arm64-development.md',
]


def read(path: Path) -> str:
    return path.read_text(encoding='utf-8')


def ignored_paths() -> set[str]:
    result = subprocess.run(
        ['git', 'ls-files', '--others', '--ignored', '--exclude-standard', '--directory', '-z'],
        cwd=ROOT, capture_output=True, check=False)
    return {item.replace('\\', '/') for item in result.stdout.decode().split('\0') if item}


def is_ignored(path: Path, ignored: set[str]) -> bool:
    rel = path.resolve().relative_to(ROOT).as_posix()
    for item in ignored:
        if item.endswith('/'):
            directory = item[:-1]
            if rel == directory or rel.startswith(item):
                return True
        elif rel == item:
            return True
    return False


def main() -> int:
    contents: dict[str, str] = {}
    for file, max_lines, max_chars in BUDGETS:
        path = ROOT / file
        if not path.is_file():
            ERRORS.append(f'缺少强制加载文件：{file}')
            continue
        text = read(path)
        contents[file] = text
        lines = len(text.rstrip('\n').splitlines())
        characters = len(text)
        if lines > max_lines or characters > max_chars:
            ERRORS.append(f'{file}: {lines}/{max_lines} 行，{characters}/{max_chars} 字符')

    context = contents.get('CONTEXT.md', '')
    phase = re.search(r'\*\*阶段：\*\*\s*Phase\s+(\d+)', context)
    phase_n = phase.group(1) if phase else None
    for file in ('readme.md', 'SECURITY.md'):
        path = ROOT / file
        if not path.is_file():
            continue
        text = read(path)
        for claim in re.finditer(r'(?:当前处于|仍处于|项目处于)\s*\*{0,2}Phase\s+(\d+)', text):
            if phase_n and claim.group(1) != phase_n:
                ERRORS.append(f'{file}: 当前阶段与 CONTEXT.md 不一致，请改为引用唯一事实源')

    priority = re.search(r'## 近期优先级\s+([\s\S]*?)(?=\n## |$)', context)
    priorities = len(re.findall(r'^\d+\. ', priority.group(1) if priority else '', re.M))
    if priorities > 3:
        ERRORS.append(f'CONTEXT.md: 近期优先级不得超过 3 项，当前为 {priorities} 项')

    verification = re.search(r'## 最近验证\s+([\s\S]*?)(?=\n## |$)', context)
    for item in (verification.group(1) if verification else '').splitlines():
        if item.startswith('- ') and not re.search(r'\[[^\]]+\]\([^)]+\)', item):
            ERRORS.append('CONTEXT.md: 每条最近验证必须包含指向证据的 Markdown 链接')

    for forbidden in ('当前分支', '## 常用命令', '## 常用文档', '完整变更历史'):
        if forbidden in context:
            ERRORS.append(f'CONTEXT.md: 不应包含“{forbidden}”')

    for file, sections in REQUIRED_SECTIONS.items():
        content = contents.get(file, '')
        for section in sections:
            if section not in content:
                ERRORS.append(f'{file}: 缺少必需路由或章节“{section}”')

    for target in ROUTED_TARGETS:
        if not (ROOT / target).is_file():
            ERRORS.append(f'缺少路由目标：{target}')

    ignored = ignored_paths()
    for path in ROOT.rglob('*.md'):
        if is_ignored(path, ignored) or '.git' in path.parts:
            continue
        text = read(path)
        for match in re.finditer(r'\[[^\]]*\]\(([^)]+)\)', text):
            link = match.group(1).strip().strip('<>')
            if re.match(r'^(https?:|mailto:|#)', link, re.I):
                continue
            target = link.split('#', 1)[0]
            if not target:
                continue
            resolved = (path.parent / Path(target)).resolve()
            try:
                resolved.relative_to(ROOT)
            except ValueError:
                continue
            if is_ignored(resolved, ignored):
                ERRORS.append(f'{path.relative_to(ROOT).as_posix()}: 相对链接指向 Git 忽略路径 {match.group(1)}')
            elif not resolved.exists():
                ERRORS.append(f'{path.relative_to(ROOT).as_posix()}: 失效相对链接 {match.group(1)}')

    adr_dir = ROOT / 'docs' / 'ADR'
    if adr_dir.is_dir():
        for entry in adr_dir.iterdir():
            if not entry.is_file() or not re.match(r'^\d{4}-.+\.md$', entry.name):
                continue
            content = read(entry)
            if not re.search(r'^- 状态：(提议|已接受|已替代|已拒绝)$', content, re.M):
                ERRORS.append(f'docs/ADR/{entry.name}: 缺少合法状态')
            if not re.search(r'^- 日期：\d{4}-\d{2}-\d{2}$', content, re.M):
                ERRORS.append(f'docs/ADR/{entry.name}: 缺少 ISO 日期')

    if ERRORS:
        print('治理文档检查失败：', file=sys.stderr)
        for error in ERRORS:
            print(f'- {error}', file=sys.stderr)
        return 1
    print('治理文档检查通过。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
