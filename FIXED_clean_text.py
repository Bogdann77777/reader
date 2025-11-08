# ИСПРАВЛЕННАЯ ФУНКЦИЯ clean_text()
# 
# Замени функцию clean_text() в app.py (примерно строка 143-210)
# на эту версию для устранения артефактов "TE", "TTU", "T2"

def clean_text(text):
    """
    Clean text for natural TTS speech flow - AGGRESSIVE artifact removal
    Removes ALL characters that XTTS might try to vocalize as "TE", "TTU", "T2"
    
    Based on deep analysis of marketing_lecture_FINAL.txt:
    - 663x bullets (•) causing artifacts
    - 2037x box chars (═) 
    - 4679x lines (─)
    - Multiple arrows, stars, checkmarks
    """
    # STEP 1: AGGRESSIVE removal of ALL decorative characters found in analysis
    # This removes characters at Unicode positions that XTTS tries to vocalize
    text = re.sub(r'[═─│┌┐└┘├┤┬┴┼╔╗╚╝╠╣╦╩╬▸►▶▷▹◂◃◄◅━┏┓┗┛┣┫┳┻╋║×÷→←↑↓★☆⭐✓✅✗❌•◦∙●○■□▪▫¹º]', ' ', text)
    
    # STEP 2: Replace ellipsis BEFORE other processing
    # "И... тишина" → "И, тишина"
    text = re.sub(r'\.{3,}', ',', text)
    
    # STEP 3: Remove brackets and quotes
    text = re.sub(r'[\(\)\[\]\{\}«»""\'\'<>]', '', text)
    
    # STEP 4: Remove invisible/zero-width characters
    text = re.sub(r'[\u200B\u200C\u200D\uFEFF\u00AD\u2060]', '', text)
    
    # STEP 5: Split ONLY English abbreviations (AI → A I)
    # CRITICAL: Must NOT split Cyrillic words
    text = re.sub(r'(?<![а-яА-ЯёЁ])([ABCDEFGHIJKLMNOPQRSTUVWXYZ]{2,5})(?![а-яА-ЯёЁA-Za-z])',
                  lambda m: ' '.join(m.group(1)), text)
    
    # STEP 6: Remove remaining special symbols (keep % and -)
    text = re.sub(r'[#@$^&*_+=|\\~\/`§†‡°♠♣♥♦⇐⇒⇔∀∂∃∅∇∈∉∋∏∑∓√∝∞∠∧∨∩∪∫∴∼≅≈≠≡≤≥⊂⊃⊄⊆⊇⊕⊗⊥⋅¢£¤¥€¦¨©ª¬®¯´µ¶¸¹º¼½¾¿˂˃˄˅ˆˇˉˊˋ˘˙˚˛˜˝¡▀▄█▌▐░▒▓]', '', text)
    
    # STEP 7: Smart newline handling
    # Mark real paragraphs
    text = re.sub(r'([.!?:])\s*\n+\s*', r'\1 ¶PARA¶ ', text)
    text = re.sub(r'\n\s*\n+', ' ¶PARA¶ ', text)
    
    # Join line continuations
    text = re.sub(r'\n+', ' ', text)
    
    # Remove paragraph markers
    text = re.sub(r'¶PARA¶', '', text)
    
    # STEP 8: Clean up punctuation issues
    text = re.sub(r',\s*([.!?])', r'\1', text)  # ", ." → "."
    text = re.sub(r'(^|[.!?:])\s*,\s*', r'\1 ', text)  # Leading commas
    
    # STEP 9: Fix multiple punctuation
    text = re.sub(r'\.{2,}', '.', text)
    text = re.sub(r',{2,}', ',', text)
    
    # STEP 10: Fix spacing around punctuation
    text = re.sub(r'\s+([.,!?:;])', r'\1', text)
    text = re.sub(r'([.,!?:;])([^\s\d])', r'\1 \2', text)
    
    # STEP 11: Normalize whitespace
    text = re.sub(r' +', ' ', text)
    
    # STEP 12: Clean edges
    text = text.strip()
    text = re.sub(r'^[.,;:\s]+', '', text)
    
    return text
