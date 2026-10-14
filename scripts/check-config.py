#!/usr/bin/env python3
"""Parse tracked JSON/YAML and reject duplicate mapping keys."""
import json
from pathlib import Path
import subprocess

import yaml


def unique_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError(f'Duplicate key: {key!r}')
        result[key] = value
    return result


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node):
    return unique_pairs((loader.construct_object(key), loader.construct_object(value))
                        for key, value in node.value)


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)
repo = Path(__file__).resolve().parent.parent
tracked = subprocess.check_output(['git', 'ls-files', '-z'], cwd=repo, text=True).split('\0')
for name in tracked:
    path = repo / name
    if not path.is_file():
        continue
    if path.suffix == '.json':
        json.loads(path.read_text(), object_pairs_hook=unique_pairs)
        print(f'Valid JSON: {name}')
    elif path.suffix in {'.yml', '.yaml'}:
        list(yaml.load_all(path.read_text(), Loader=UniqueLoader))
        print(f'Valid YAML: {name}')
