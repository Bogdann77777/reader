"""
INTELLIGENT clean_text() v2.0
Analyzes text context to create natural pauses like a professor's lecture
"""

import sys
import re

sys.stdout.reconfigure(encoding='utf-8')

def clean_text_intelligent(text):
    """
    Clean text with INTELLIGENT context analysis for natural TTS speech
    Creates pauses like a real professor giving a lecture
    """

    # STEP 1: Remove artifact-causing characters
    text = re.sub(r'[═─│┌┐└┘├┤┬┴┼╔╗╚╝╠╣╦╩╬▸►▶▷▹◂◃◄◅━┏┓┗┛┣┫┳┻╋║×÷→←↑↓★☆⭐✓✅✗❌•◦∙●○■□▪▫¹º]', ' ', text)

    # STEP 1_cleanup: Remove leading spaces at start of lines
    text = re.sub(r'\n\s+', '\n', text)

    # STEP 1a: FIX NUMBERING
    text = re.sub(r'(\d+)\.(\d+)\.(\d+)', r'\1 \2 \3', text)  # 1.1.1 → 1 1 1
    text = re.sub(r'(\d+)\.(\d+)', r'\1 \2', text)  # 1.1 → 1 1
    text = re.sub(r'(?<=\s)(\d+)\.(?=\s)', r'\1', text)  # " 1. " → " 1 "
    text = re.sub(r'^(\d+)\.(?=\s)', r'\1', text, flags=re.MULTILINE)

    # STEP 2: Remove brackets and quotes
    text = re.sub(r'[\(\)\[\]\{\}«»""\'\'<>]', '', text)

    # STEP 3: Remove invisible characters
    text = re.sub(r'[\u200B\u200C\u200D\uFEFF\u00AD\u2060]', '', text)

    # STEP 4: Split ENGLISH abbreviations
    text = re.sub(r'(?<![а-яА-ЯёЁ])([ABCDEFGHIJKLMNOPQRSTUVWXYZ]{2,5})(?![а-яА-ЯёЁA-Za-z])',
                  lambda m: ' '.join(m.group(1)), text)

    # STEP 5: Remove special symbols
    text = re.sub(r'[#@$^&*_+=|\\~\/`§†‡°♠♣♥♦←→↑↓↔⇐⇒⇔∀∂∃∅∇∈∉∋∏∑−∓√∝∞∠∧∨∩∪∫∴∼≅≈≠≡≤≥⊂⊃⊄⊆⊇⊕⊗⊥⋅¢£¤¥€¦¨©ª¬®¯´µ¶¸¹º¼½¾¿×÷˂˃˄˅ˆˇˉˊˋ˘˙˚˛˜˝¡▀▄█▌▐░▒▓]', '', text)

    # ============================================================================
    # INTELLIGENT PAUSE INSERTION - CONTEXT ANALYSIS
    # ============================================================================

    # STEP 6a: DETECT HEADERS (ALL CAPS, short lines 2-50 chars)
    # Headers need LONG pause after them (professor takes breath before new section)
    # "ВВЕДЕНИЕ В МАРКЕТИНГ\n" → "ВВЕДЕНИЕ В МАРКЕТИНГ...... "
    lines = text.split('\n')
    processed_lines = []

    for i, line in enumerate(lines):
        line = line.strip()
        if not line:
            processed_lines.append('')
            continue

        # Is this a header? (ALL CAPS, 2-50 chars, mostly letters)
        letter_count = sum(1 for c in line if c.isalpha())
        is_header = (
            len(line) >= 2 and
            len(line) <= 50 and
            line.isupper() and
            letter_count > len(line) * 0.6  # At least 60% letters
        )

        if is_header:
            # Add LONG pause after header (6 dots = ~1.5 seconds)
            processed_lines.append(line + '......')
        else:
            processed_lines.append(line)

    text = '\n'.join(processed_lines)

    # STEP 6b: QUESTIONS need pause before answer
    # "Почему так?\nПотому что" → "Почему так?... Потому что"
    text = re.sub(r'\?\s*\n', '?... ', text)

    # STEP 6c: COLONS after headers/labels → medium pause
    # "МИФ #1:" → "МИФ #1..."
    # But preserve colons in middle of sentences (time "12:00" etc)
    text = re.sub(r':(?=\s*(?:[А-ЯЁA-Z]|$))', '...', text)

    # STEP 6d: LIST ITEMS without punctuation → add comma for breath
    text = re.sub(r'([^\.\!\?,\n])\s*\n', r'\1,\n', text)

    # STEP 6e: NUMBER SEQUENCES - add slight pause
    # "2, 3, 4" → "2... 3... 4" (professor enumerates with pauses)
    text = re.sub(r'(\d)\s*,\s*(?=\d)', r'\1... ', text)

    # STEP 7: SMART NEWLINE HANDLING
    # Paragraph breaks (double newline) → medium pause
    text = re.sub(r'\n\s*\n+', '... ', text)

    # Single newlines → join naturally
    text = re.sub(r'\n+', ' ', text)

    # STEP 8: ELLIPSIS normalization
    # Replace original ellipsis with consistent 3-dot version
    text = re.sub(r'\.{2,3}(?!\.)', '...', text)  # 2-3 dots → 3 dots
    # Keep longer ellipsis (4-6 dots) as is for long pauses

    # STEP 9: Clean up punctuation issues
    text = re.sub(r',\s*([.!?])', r'\1', text)  # ", ." → "."
    text = re.sub(r'(^|[.!?])\s*,', r'\1', text)  # Leading commas

    # STEP 10: Fix spacing
    text = re.sub(r'\s+([.,!?:;])', r'\1', text)  # "word ." → "word."
    text = re.sub(r'([.,!?:;])([^\s\d.])', r'\1 \2', text)  # "word.word" → "word. word"

    # STEP 11: Normalize whitespace (but preserve multiple dots)
    text = re.sub(r'(?<!\.)\s{2,}(?!\.)', ' ', text)  # Multiple spaces → single (except near dots)

    # STEP 12: Clean up edges
    text = text.strip()
    text = re.sub(r'^[.,;:\s]+', '', text)

    return text


# ============================================================================
# TEST WITH REAL LECTURE CONTENT
# ============================================================================

test_lecture = """
БЛОК 1: ФУНДАМЕНТ

1.1. ВВЕДЕНИЕ: РЕАЛЬНОСТЬ ЦИФРОВОГО РЫНКА 2025

Добро пожаловать на курс по маркетингу!

▸ ПОЧЕМУ 90% ЦИФРОВЫХ ПРОДУКТОВ НЕ ДОЖИВАЮТ ДО ГОДА

Жесткая статистика показывает:
• 90% стартапов закрываются в течение первого года
• 42% из них закрываются потому что нет рынка для продукта
• 29% - из-за нехватки денег

Что это значит на практике?

Представьте: вы запускаете приложение для чтения книг с AI-озвучкой.
Потратили 6 месяцев на разработку. Запустили. И... тишина.

Почему так происходит?

1. ПРОБЛЕМА: "Построим - придут" мышление
2. ПРОБЛЕМА: Нет понимания целевой аудитории
3. ПРОБЛЕМА: Запуск без валидации
"""

print("="*80)
print("ТЕСТ: ИНТЕЛЛЕКТУАЛЬНАЯ ОБРАБОТКА ТЕКСТА")
print("="*80)
print("\nОРИГИНАЛ:")
print("-"*80)
print(test_lecture[:500])
print("\n...")

cleaned = clean_text_intelligent(test_lecture)

print("\n" + "="*80)
print("РЕЗУЛЬТАТ (с контекстными паузами):")
print("="*80)
print(cleaned)

print("\n" + "="*80)
print("АНАЛИЗ ПАУ3:")
print("="*80)
print(f"Длинные паузы (......): {cleaned.count('......')} шт - после заголовков")
print(f"Средние паузы (...): {cleaned.count('...')} шт - между мыслями")
print(f"Короткие паузы (,): {cleaned.count(',')} шт - для дыхания")
print(f"\nОбщая длина: {len(cleaned)} символов")
