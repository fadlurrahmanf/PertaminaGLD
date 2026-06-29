import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('Pertamina_GLD_Visual_End_to_End.md', 'r', encoding='utf-8-sig') as f:
    text = f.read()

def fix_double_encoding(text, original_char):
    utf8_bytes = original_char.encode('utf-8')
    try:
        corrupted_str = utf8_bytes.decode('cp1252')
        if corrupted_str != original_char and corrupted_str in text:
            count = text.count(corrupted_str)
            text = text.replace(corrupted_str, original_char)
            print(f'  Fixed {count}x: {repr(original_char)}  ({original_char})')
    except Exception:
        pass
    return text

chars_to_fix = [
    # arrows & math
    '→', '←', '↔', '↑', '↓',
    '≥', '≤', '≠', '×', '°', 'µ', 'Ω', '−', '±',
    # dashes & quotes
    '—', '–', ''', ''', '"', '"', '…', '•',
    # box drawing (common in ASCII tables)
    '─', '│', '┌', '┐', '└', '┘', '├', '┤', '┬', '┴', '┼',
    '╔', '╗', '╚', '╝', '╠', '╣', '╦', '╩', '╬', '═', '║',
    # checkmarks & symbols
    '✅', '✓', '✗', '✘', '⚠', '❌', '⚡', '🔴', '🟡', '🟢',
    # misc
    '®', '©', '™', '·', '¶', '§',
]

print('Fixing corrupted Unicode...')
for ch in chars_to_fix:
    text = fix_double_encoding(text, ch)

with open('Pertamina_GLD_Visual_End_to_End.md', 'w', encoding='utf-8-sig') as f:
    f.write(text)

# Check remaining â sequences
import re
remaining = sorted(set(re.findall(r'â.{0,4}', text)))
if remaining:
    print(f'\nRemaining â-sequences: {remaining}')
    # Show context for each
    for pat in remaining[:5]:
        for m in re.finditer(re.escape(pat), text):
            line_start = text.rfind('\n', 0, m.start()) + 1
            line_end = text.find('\n', m.end())
            print(f'  Line: {text[line_start:line_end][:80]}')
            break
else:
    print('\nNo more corrupted sequences.')
print('Done.')
