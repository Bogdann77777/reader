"""
Deep analysis of marketing_lecture_FINAL.txt for hidden characters
"""
import sys
import re

# Read file as binary to catch all bytes
with open(r'E:\project\reader\marketing_lecture_FINAL.txt', 'rb') as f:
    raw_bytes = f.read()

print("="*80)
print("DEEP FILE ANALYSIS - marketing_lecture_FINAL.txt")
print("="*80)
print(f"File size: {len(raw_bytes)} bytes")
print()

# Decode to text
text = raw_bytes.decode('utf-8', errors='replace')
print(f"Text length: {len(text)} characters")
print()

# ============================================================================
# CHECK 1: Find ALL non-standard characters
# ============================================================================
print("="*80)
print("CHECK 1: NON-STANDARD CHARACTERS")
print("="*80)

unusual_chars = {}
for i, char in enumerate(text):
    code = ord(char)
    
    # Skip normal characters:
    # - ASCII printable (32-126)
    # - Common whitespace (9=tab, 10=newline, 13=return)
    # - Cyrillic (0x0400-0x04FF)
    # - Common punctuation (0x2000-0x206F)
    
    is_normal = (
        (32 <= code <= 126) or  # ASCII printable
        code in [9, 10, 13] or   # Tab, LF, CR
        (0x0400 <= code <= 0x04FF) or  # Cyrillic
        (0x2000 <= code <= 0x206F)  # General punctuation
    )
    
    if not is_normal:
        if code not in unusual_chars:
            unusual_chars[code] = {
                'char': char,
                'count': 0,
                'positions': []
            }
        unusual_chars[code]['count'] += 1
        if len(unusual_chars[code]['positions']) < 5:  # Save first 5 positions
            unusual_chars[code]['positions'].append(i)

if unusual_chars:
    print(f"Found {len(unusual_chars)} types of unusual characters:\n")
    for code in sorted(unusual_chars.keys()):
        info = unusual_chars[code]
        char_repr = repr(info['char'])
        print(f"  U+{code:04X} {char_repr}")
        print(f"    Count: {info['count']}")
        print(f"    First positions: {info['positions'][:3]}")
        
        # Show context
        if info['positions']:
            pos = info['positions'][0]
            context_start = max(0, pos - 20)
            context_end = min(len(text), pos + 20)
            context = text[context_start:context_end]
            print(f"    Context: {repr(context)}")
        print()
else:
    print("✓ No unusual characters found")

print()

# ============================================================================
# CHECK 2: Zero-width and invisible characters
# ============================================================================
print("="*80)
print("CHECK 2: ZERO-WIDTH / INVISIBLE CHARACTERS")
print("="*80)

zero_width_chars = {
    '\u200B': 'ZERO WIDTH SPACE',
    '\u200C': 'ZERO WIDTH NON-JOINER',
    '\u200D': 'ZERO WIDTH JOINER',
    '\uFEFF': 'ZERO WIDTH NO-BREAK SPACE (BOM)',
    '\u00AD': 'SOFT HYPHEN',
    '\u2060': 'WORD JOINER',
}

found_invisible = False
for char, name in zero_width_chars.items():
    count = text.count(char)
    if count > 0:
        print(f"⚠️  Found {count}x {name} (U+{ord(char):04X})")
        found_invisible = True
        
        # Find first occurrence
        pos = text.index(char)
        context = text[max(0, pos-30):min(len(text), pos+30)]
        print(f"    First at position {pos}")
        print(f"    Context: {repr(context)}")
        print()

if not found_invisible:
    print("✓ No invisible characters found")

print()

# ============================================================================
# CHECK 3: Problematic patterns that XTTS might vocalize
# ============================================================================
print("="*80)
print("CHECK 3: PATTERNS THAT XTTS MIGHT READ AS ARTIFACTS")
print("="*80)

patterns = {
    r'\.{2,}': 'Multiple dots (.. or ...)',
    r'\s+\.': 'Space before period',
    r'\.\s*\.': 'Separated dots',
    r'[.!?]\s*[,;:]': 'Punctuation after sentence end',
    r'[А-Яа-яёЁ]\.$': 'Single letter with period at line end',
    r'\s+[.!?,;:]': 'Whitespace before punctuation',
}

print("Checking for problematic patterns:\n")

first_1000 = text[:5000]  # Check first 5000 chars

for pattern, description in patterns.items():
    matches = list(re.finditer(pattern, first_1000, re.MULTILINE))
    if matches:
        print(f"⚠️  {description}: {len(matches)} matches")
        # Show first 3
        for i, match in enumerate(matches[:3]):
            pos = match.start()
            context_start = max(0, pos - 20)
            context_end = min(len(first_1000), pos + 40)
            context = first_1000[context_start:context_end]
            print(f"    Match {i+1} at pos {pos}: {repr(context)}")
        print()

print()

# ============================================================================
# CHECK 4: Specific character sequences that might cause "TE", "TTU", "T2"
# ============================================================================
print("="*80)
print("CHECK 4: SUSPICIOUS SEQUENCES (might cause TE/TTU/T2 artifacts)")
print("="*80)

# These might be interpreted by XTTS as phonetic sounds
suspicious = [
    'т.', 'Т.', 'т..', 'Т...',  # Russian T with period
    '.т', '.Т',
    '• ', '•\n',  # Bullet with space/newline
    '\n.', '.\n.',  # Period with newlines
]

print("Checking for sequences that might create artifacts:\n")

for seq in suspicious:
    count = text.count(seq)
    if count > 0:
        print(f"⚠️  Found {count}x sequence: {repr(seq)}")
        # Find first occurrence
        pos = text.index(seq)
        context = text[max(0, pos-30):min(len(text), pos+30)]
        print(f"    First at position {pos}")
        print(f"    Context: {repr(context)}")
        print()

print()

# ============================================================================
# SUMMARY
# ============================================================================
print("="*80)
print("ANALYSIS SUMMARY")
print("="*80)
print()

issues_found = []

if unusual_chars:
    issues_found.append(f"{len(unusual_chars)} types of unusual characters")
if found_invisible:
    issues_found.append("Invisible/zero-width characters")

if issues_found:
    print("⚠️  ISSUES FOUND:")
    for issue in issues_found:
        print(f"  - {issue}")
else:
    print("✓ No major issues found")

print()
print("="*80)
