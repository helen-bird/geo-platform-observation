#!/usr/bin/env python3
"""Recount Lab #07 from the included coding snapshot. No platform calls."""
import json
from collections import Counter
from pathlib import Path

data = json.loads(Path(__file__).with_name('creator-coding.json').read_text())
answers = data['answers']
assert len({r['answer_id'] for r in answers}) == len(answers) == 60
for env in ('chatgpt-web','grok-web'):
    for prompt in data['prompts']:
        rows = [r for r in answers if r['environment']==env and r['prompt_id']==prompt]
        assert len(rows) == 10
        print(env,prompt, 'recommendations / mentions (each out of 10)')
        for name in ('Aleyda Solis','Kevin Indig','Artur Ferreira','Helen Bird'):
            print(' ',name, sum(name in r['recommendations'] for r in rows),
                  '/',sum(name in r['mentioned'] for r in rows))
n = sum(len(r['recommendations']) for r in answers)
assert n == 294
for tag,k in Counter(t for r in answers for ts in r['recommendations'].values() for t in ts).most_common():
    print(tag, f'{k}/{n}', 'in',sum(any(tag in ts for ts in r['recommendations'].values()) for r in answers),'answers')
