import sys, re
sys.stdout.reconfigure(encoding='utf-8')

with open('Pertamina_GLD_Visual_End_to_End.md', 'r', encoding='utf-8-sig') as f:
    text = f.read()

# U+2510 (top-right corner: ┐) corrupts to: â + U+201D (") + U+0090
corrupted_trc = 'â”'   # â + right-double-quote + PAD control char
count = text.count(corrupted_trc)
print(f'Found {count}x corrupted for ┐')
text = text.replace(corrupted_trc, '┐')

with open('Pertamina_GLD_Visual_End_to_End.md', 'w', encoding='utf-8-sig') as f:
    f.write(text)

remaining = sorted(set(re.findall(r'â.{0,4}', text)))
if remaining:
    print(f'Still remaining: {remaining}')
    for pat in remaining[:3]:
        for m in re.finditer(re.escape(pat), text):
            line_start = text.rfind('\n', 0, m.start()) + 1
            line_end = text.find('\n', m.end())
            print(f'  > {text[line_start:line_end][:100]}')
            break
else:
    print('Clean — no more corrupted sequences.')
