"""
TTS Reader - Flask Application
A local text reader with XTTS v2 voice synthesis
"""

import os
import sys
import re
import glob
import json
import traceback
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import torch
from TTS.api import TTS
import time

# Fix encoding for Windows console to support Cyrillic
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
CONFIG = {
    'SAMPLES_DIR': 'samples',
    'AUDIO_OUTPUT_DIR': 'audio_output',
    'MODEL_NAME': 'tts_models/multilingual/multi-dataset/xtts_v2',
    'DEVICE': 'cuda',  # GPU enabled: RTX 5060 Ti with SM 12.0 support via PyTorch nightly CUDA 12.8
    'LANGUAGE': 'ru',
    'MIN_SENTENCES': 10,  # Back to original - minimum sentences per chunk
    'MAX_SENTENCES': 15,  # Back to original - maximum sentences per chunk
    'MAX_CHARS': 600,     # Back to original - larger chunks
}

# Global variables
tts_model = None
current_chunks = []
synthesis_lock = threading.Lock()  # CRITICAL: Prevent parallel synthesis on GPU (XTTS not thread-safe)

print(f"[INFO] Using device: {CONFIG['DEVICE']}")


# ============================================
# Function: Load TTS Model
# ============================================
def load_tts_model():
    """
    Load XTTS v2 model on startup
    Returns: TTS model instance
    """
    global tts_model

    try:
        print("\n" + "="*60)
        print("[INFO] Loading XTTS v2 model...")
        print(f"[INFO] Model name: {CONFIG['MODEL_NAME']}")
        print(f"[INFO] Target device: {CONFIG['DEVICE']}")

        # Check CUDA availability
        if CONFIG['DEVICE'] == 'cuda':
            print(f"[INFO] CUDA available: {torch.cuda.is_available()}")
            if torch.cuda.is_available():
                print(f"[INFO] CUDA version: {torch.version.cuda}")
                print(f"[INFO] GPU count: {torch.cuda.device_count()}")
                for i in range(torch.cuda.device_count()):
                    print(f"[INFO] GPU {i}: {torch.cuda.get_device_name(i)}")
                    print(f"[INFO]   Compute capability: {torch.cuda.get_device_capability(i)}")
                    mem_total = torch.cuda.get_device_properties(i).total_memory / 1024**3
                    print(f"[INFO]   Total memory: {mem_total:.2f} GB")

        print("[INFO] Initializing TTS model...")
        start_time = time.time()

        tts_model = TTS(model_name=CONFIG['MODEL_NAME'])

        print(f"[INFO] Moving model to {CONFIG['DEVICE']}...")
        tts_model = tts_model.to(CONFIG['DEVICE'])

        load_time = time.time() - start_time
        print(f"[SUCCESS] Model loaded in {load_time:.2f} seconds")

        if CONFIG['DEVICE'] == 'cuda' and torch.cuda.is_available():
            allocated = torch.cuda.memory_allocated(0) / 1024**3
            print(f"[INFO] GPU memory allocated: {allocated:.2f} GB")

        print("="*60 + "\n")
        return tts_model

    except Exception as e:
        print("\n" + "="*60)
        print(f"[ERROR] Failed to load TTS model: {str(e)}")
        print("[ERROR] Full traceback:")
        traceback.print_exc()
        print("="*60 + "\n")
        return None


# ============================================
# Function: Scan Voice Samples
# ============================================
def scan_voices():
    """
    Scan samples directory for WAV files
    Returns: List of voice dictionaries with name and path
    """
    voices = []

    try:
        samples_path = Path(CONFIG['SAMPLES_DIR'])

        # Create samples directory if it doesn't exist
        if not samples_path.exists():
            samples_path.mkdir(parents=True)
            print(f"[INFO] Created samples directory: {samples_path}")

        # Scan for WAV files
        wav_files = glob.glob(os.path.join(CONFIG['SAMPLES_DIR'], '*.wav'))

        for wav_file in wav_files:
            filename = os.path.basename(wav_file)
            voice_name = os.path.splitext(filename)[0]

            voices.append({
                'name': voice_name,
                'path': wav_file
            })

        print(f"[INFO] Found {len(voices)} voice samples")

        return voices

    except Exception as e:
        print(f"[ERROR] Failed to scan voices: {str(e)}")
        return []


# ============================================
# Function: Analyze Sentence Structure
# ============================================
def analyze_sentence_structure(text):
    """
    Intelligent sentence analysis for natural phrase-level intonation
    Analyzes sentence structure, not individual word stress
    Identifies complex sentences that need internal pauses for clarity
    """
    sentences = []

    # Split into sentences while preserving punctuation
    raw_sentences = re.split(r'([.!?]+\s*)', text)

    current_sentence = ""
    for i, part in enumerate(raw_sentences):
        if re.match(r'[.!?]+\s*', part):
            current_sentence += part.strip()
            if current_sentence:
                sentence_info = {
                    'text': current_sentence,
                    'length': len(current_sentence),
                    'type': 'question' if '?' in part else 'exclamation' if '!' in part else 'statement',
                    'needs_split': False,
                    'split_points': []
                }

                # Analyze if sentence is too long (>200 chars) and needs internal pauses
                if len(current_sentence) > 200:
                    sentence_info['needs_split'] = True

                    # Find natural split points at conjunctions and clause boundaries
                    # Russian conjunctions that indicate phrase boundaries
                    conjunctions = [
                        r',\s+(и|но|а|однако|поэтому|потому\s+что|так\s+как|если|когда|где|куда|откуда|чтобы|хотя|пока|как)\s+',
                        r',\s+который',
                        r',\s+что\s+',
                        r';\s+'
                    ]

                    for pattern in conjunctions:
                        for match in re.finditer(pattern, current_sentence, re.IGNORECASE):
                            sentence_info['split_points'].append(match.start() + 1)  # After comma

                # VERY long sentences (>400 chars) need additional splitting
                # Even if no conjunctions found, split at commas for better comprehension
                if len(current_sentence) > 400 and len(sentence_info['split_points']) < 2:
                    sentence_info['needs_split'] = True

                    # Find ALL commas in very long sentences for additional pause points
                    for match in re.finditer(r',\s+', current_sentence):
                        pos = match.start() + 1
                        if pos not in sentence_info['split_points']:
                            sentence_info['split_points'].append(pos)

                sentences.append(sentence_info)
                current_sentence = ""
        else:
            current_sentence += part

    # Handle remaining text without sentence-ending punctuation
    if current_sentence.strip():
        sentences.append({
            'text': current_sentence.strip(),
            'length': len(current_sentence.strip()),
            'type': 'statement',
            'needs_split': len(current_sentence.strip()) > 200,
            'split_points': []
        })

    return sentences


# ============================================
# Function: Clean Text
# ============================================
def clean_text(text):
    """
    INTELLIGENT text cleaning for natural TTS speech flow
    Analyzes context to create pauses like a professor giving a lecture
    Creates monolithic, natural-sounding speech with proper intonation
    """
    # STEP 1: Remove ALL artifact-causing characters (analysis: 663x •, 2037x ═, 4679x ─)
    # These cause "TE", "TTU", "T2" sounds when XTTS tries to vocalize them
    text = re.sub(r'[═─│┌┐└┘├┤┬┴┼╔╗╚╝╠╣╦╩╬▸►▶▷▹◂◃◄◅━┏┓┗┛┣┫┳┻╋║×÷→←↑↓★☆⭐✓✅✗❌•◦∙●○■□▪▫¹º]', ' ', text)

    # STEP 1_cleanup: Remove leading spaces at start of lines (from removed bullets/symbols)
    text = re.sub(r'\n\s+', '\n', text)

    # ============================================================================
    # INTELLIGENT CONTEXT ANALYSIS FOR NATURAL PAUSES - EARLY DETECTION
    # Detect headers and key structures BEFORE symbol removal
    # ============================================================================

    # STEP 1a: DETECT HEADERS (ALL CAPS lines) - DO THIS EARLY!
    # Headers need LONG pause after them - professor takes breath before new section
    lines = text.split('\n')
    processed_lines = []

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            processed_lines.append('')
            continue

        # Check if line is a header: ALL CAPS, short-to-medium length, mostly letters
        # Remove parenthetical content for length check: "TITLE (notes)" → check "TITLE"
        line_without_parens = re.sub(r'\([^)]*\)', '', line_stripped).strip()
        letter_count = sum(1 for c in line_without_parens if c.isalpha())

        is_header = (
            len(line_without_parens) >= 2 and
            len(line_without_parens) <= 80 and
            line_stripped.isupper() and
            letter_count > len(line_without_parens) * 0.4  # At least 40% letters
        )

        if is_header:
            # Add comma after header for natural pause (XTTS interprets headers with natural emphasis)
            # NO ELLIPSIS - causes speed issues and artifacts
            processed_lines.append(line_stripped + ',')
        else:
            processed_lines.append(line_stripped)

    text = '\n'.join(processed_lines)

    # STEP 2: FIX NUMBERING - Replace numbered list markers to avoid reading dots
    # Must process 3-part numbers BEFORE 2-part to avoid conflicts
    text = re.sub(r'(\d+)\.(\d+)\.(\d+)', r'\1 \2 \3', text)  # 1.1.1 → 1 1 1
    text = re.sub(r'(\d+)\.(\d+)', r'\1 \2', text)  # 1.1 → 1 1
    text = re.sub(r'(?<=\s)(\d+)\.(?=\s)', r'\1', text)  # " 1. " → " 1 "
    text = re.sub(r'^(\d+)\.(?=\s)', r'\1', text, flags=re.MULTILINE)  # Start of line: "1. " → "1 "

    # STEP 3: Remove brackets and quote marks
    text = re.sub(r'[\(\)\[\]\{\}«»""\'\'<>]', '', text)

    # STEP 4: Remove invisible/zero-width characters
    text = re.sub(r'[\u200B\u200C\u200D\uFEFF\u00AD\u2060]', '', text)

    # STEP 5: Split ENGLISH ONLY abbreviations (2-5 capital LATIN letters) for letter-by-letter reading
    text = re.sub(r'(?<![а-яА-ЯёЁ])([ABCDEFGHIJKLMNOPQRSTUVWXYZ]{2,5})(?![а-яА-ЯёЁA-Za-z])',
                  lambda m: ' '.join(m.group(1)), text)

    # STEP 6: Remove all other special symbols except % and - (hyphen for dates/ranges)
    text = re.sub(r'[#@$^&*_+=|\\~\/`§†‡°♠♣♥♦←→↑↓↔⇐⇒⇔∀∂∃∅∇∈∉∋∏∑−∓√∝∞∠∧∨∩∪∫∴∼≅≈≠≡≤≥⊂⊃⊄⊆⊇⊕⊗⊥⋅¢£¤¥€¦¨©ª¬®¯´µ¶¸¹º¼½¾¿×÷˂˃˄˅ˆˇˉˊˋ˘˙˚˛˜˝¡▀▄█▌▐░▒▓]', '', text)

    # ============================================================================
    # CONTEXT-AWARE PAUSE INSERTION
    # ============================================================================

    # STEP 6b: QUESTIONS need pause before answer
    # "Почему так?\nПотому что" → "Почему так? Потому что" (no ellipsis - XTTS handles ? naturally)
    text = re.sub(r'\?\s*\n', '? ', text)

    # STEP 6c: COLONS after headers/labels → remove them (XTTS reads colons as sounds)
    # "МИФ #1:" → "МИФ #1" (let natural sentence pause handle it)
    # But preserve colons in time "12:00" and ratios
    text = re.sub(r':(?=\s+[А-ЯЁA-Z])', '', text)  # Before uppercase word
    text = re.sub(r':(?=\s*$)', '', text)  # At end of line

    # STEP 6d: LIST ITEMS without punctuation → add comma for breath pause
    # BUT only if line looks like list item (short, starts with number/bullet after cleanup)
    # Don't add comma if it's middle of sentence that wrapped to next line
    def add_list_comma(match):
        line_before = match.group(1)
        # Only add comma if line is relatively short (likely a list item, not sentence wrap)
        if len(line_before) < 80:
            return line_before + ',\n'
        return line_before + '\n'

    text = re.sub(r'([^\.\!\?,\n]{1,200})\s*\n', add_list_comma, text)

    # STEP 6e: NUMBER/PERCENTAGE SEQUENCES - keep commas as is
    # XTTS handles "2, 3, 4" naturally with commas - NO ELLIPSIS needed
    # Just ensure proper spacing
    text = re.sub(r'(\d+%?)\s*,\s*(?=\d)', r'\1, ', text)

    # STEP 6f: INTELLIGENT SENTENCE STRUCTURE ANALYSIS
    # Analyze long complex sentences and add natural phrase-level pauses
    # This improves intonation for complex sentences without affecting short ones
    try:
        sentence_analysis = analyze_sentence_structure(text)

        for sent_info in sentence_analysis:
            if sent_info['needs_split'] and sent_info['split_points']:
                original = sent_info['text']
                modified = original

                # Add extra commas at conjunction points in long sentences
                # Work backwards to maintain position indices
                for pos in sorted(sent_info['split_points'], reverse=True):
                    # Only add comma if there isn't already strong punctuation
                    if pos < len(modified):
                        before = modified[:pos].rstrip()
                        after = modified[pos:].lstrip()

                        # Check if there's already a comma at this position
                        if not before.endswith(',') and not before.endswith('.') and not before.endswith('!') and not before.endswith('?'):
                            # CRITICAL FIX: Add space after comma to prevent XTTS from reading "слово,и" as one word
                            # This was causing "ите", "уте" artifacts at word boundaries
                            modified = before + ', ' + after

                # Replace in text only if modification actually occurred
                # Use safer replacement: only if original text appears exactly once
                # or if we can find exact match position
                if modified != original:
                    count = text.count(original)
                    if count == 1:
                        # Safe to replace - only one occurrence
                        text = text.replace(original, modified, 1)
                    elif count > 1:
                        # Multiple occurrences - skip to avoid wrong replacement
                        # Let the later STEP 10 (normalize whitespace) handle cleanup
                        print(f"[DEBUG] Skipping sentence replacement (found {count} duplicates): {original[:50]}...")
                        pass

    except Exception as e:
        # If analysis fails, continue with original text (fail-safe)
        print(f"[WARNING] Sentence analysis failed: {e}")
        pass

    # STEP 6g: POST-ANALYSIS CLEANUP
    # Normalize spacing and punctuation after intelligent sentence analysis
    # This ensures no artifacts from comma insertion (must run BEFORE newline removal)

    # Remove multiple spaces around commas: "слово  ,  и" → "слово, и"
    text = re.sub(r'\s*,\s*', ', ', text)

    # Remove double/triple commas that might appear: "слово,, и" → "слово, и"
    text = re.sub(r',{2,}', ',', text)

    # Remove space before punctuation (safety net): "слово ," → "слово,"
    text = re.sub(r'\s+,', ',', text)

    # Ensure single space after comma: "слово,и" → "слово, и" (critical for XTTS)
    text = re.sub(r',([^\s\d])', r', \1', text)

    # STEP 7: SMART NEWLINE HANDLING
    # Paragraph breaks (double newline) → single space (XTTS will pause naturally at sentence end)
    text = re.sub(r'\n\s*\n+', ' ', text)

    # Single newlines → join naturally with space
    text = re.sub(r'\n+', ' ', text)

    # STEP 8: CLEAN UP PUNCTUATION ISSUES
    # Remove comma before sentence-ending punctuation
    text = re.sub(r',\s*([.!?])', r'\1', text)

    # Remove leading commas after strong punctuation
    text = re.sub(r'([.!?])\s*,', r'\1', text)

    # CRITICAL: Remove trailing commas at end of text (causes XTTS to duplicate/add artifacts)
    text = re.sub(r',\s*$', '', text)

    # Remove multiple consecutive commas
    text = re.sub(r',{2,}', ',', text)

    # STEP 9: FIX SPACING AROUND PUNCTUATION
    # Remove spaces before punctuation
    text = re.sub(r'\s+([.,!?;])', r'\1', text)

    # Ensure single space after punctuation
    text = re.sub(r'([.,!?;])([^\s\d])', r'\1 \2', text)

    # STEP 10: NORMALIZE WHITESPACE
    # Collapse multiple spaces
    text = re.sub(r'\s{2,}', ' ', text)

    # STEP 11: CLEAN UP EDGES
    text = text.strip()
    # Remove leading punctuation
    text = re.sub(r'^[.,;:\s]+', '', text)
    # Remove trailing punctuation except period/exclamation/question
    text = re.sub(r'[,;:\s]+$', '', text)

    return text


# ============================================
# Function: Split Text into Chunks
# ============================================
def split_into_chunks(text, min_sentences=10, max_sentences=20, max_chars=1000):
    """
    Split text into chunks by sentences count, not character size
    Args:
        text: Cleaned text to split
        min_sentences: Minimum sentences per chunk (default 10 for lectures)
        max_sentences: Maximum sentences per chunk (default 20)
        max_chars: Safety limit for character count (default 1000 for XTTS)
    Returns: List of text chunks
    """
    chunks = []

    # Split by sentence-ending punctuation
    sentences = re.split(r'([.!?]+)', text)

    # Combine sentences with their punctuation
    full_sentences = []
    for i in range(0, len(sentences), 2):
        sentence = sentences[i].strip()
        if not sentence:
            continue
        punctuation = sentences[i + 1] if i + 1 < len(sentences) else ""
        full_sentences.append(sentence + punctuation)

    # Group sentences into chunks
    current_chunk = []
    current_char_count = 0

    for sentence in full_sentences:
        sentence_len = len(sentence)

        # If single sentence exceeds max_chars, force split by words
        if sentence_len > max_chars:
            # Save current chunk if it has content
            if current_chunk:
                chunks.append(" ".join(current_chunk))
                current_chunk = []
                current_char_count = 0

            # Split long sentence by words
            words = sentence.split()
            temp_chunk = ""
            for word in words:
                if len(temp_chunk) + len(word) + 1 <= max_chars:
                    temp_chunk += (" " if temp_chunk else "") + word
                else:
                    if temp_chunk:
                        chunks.append(temp_chunk)
                    temp_chunk = word
            if temp_chunk:
                chunks.append(temp_chunk)
            continue

        # Check if adding this sentence exceeds limits
        will_exceed_chars = current_char_count + sentence_len > max_chars
        will_exceed_sentences = len(current_chunk) >= max_sentences

        # CRITICAL FIX: If exceeding char limit, ALWAYS save current chunk (even if < min_sentences)
        # This prevents chunks from growing way past max_chars limit
        if (will_exceed_chars or will_exceed_sentences) and current_chunk:
            chunks.append(" ".join(current_chunk))
            current_chunk = []
            current_char_count = 0

        # Add sentence to current chunk
        current_chunk.append(sentence)
        current_char_count += sentence_len

    # Add remaining chunk (even if less than min_sentences at the end)
    if current_chunk:
        chunks.append(" ".join(current_chunk))

    # Filter out empty or whitespace-only chunks AND too short chunks (< 10 chars)
    chunks = [chunk.strip() for chunk in chunks if chunk.strip() and len(chunk.strip()) >= 10]

    return chunks


# ============================================
# Function: Process Text
# ============================================
def process_text(text, start_position=0):
    """
    Clean text and split into chunks
    Args:
        text: Raw text input
        start_position: Character position to start from
    Returns: Dictionary with chunks and metadata
    """
    try:
        # Clean the text
        cleaned_text = clean_text(text)

        # Apply start position
        if start_position > 0:
            cleaned_text = cleaned_text[start_position:]

        # Split into chunks (sentence-based for better lecture listening)
        chunks = split_into_chunks(
            cleaned_text,
            CONFIG['MIN_SENTENCES'],
            CONFIG['MAX_SENTENCES'],
            CONFIG['MAX_CHARS']
        )

        print(f"[INFO] Processed text: {len(chunks)} chunks generated")

        return {
            'success': True,
            'chunks': chunks,
            'total_chunks': len(chunks),
            'total_characters': len(cleaned_text)
        }

    except Exception as e:
        print(f"[ERROR] Text processing failed: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


# ============================================
# API Endpoints
# ============================================

# Route: Main page
@app.route('/')
def index():
    """Render the main page"""
    return render_template('index.html')


# Route: Get available voices
@app.route('/api/voices', methods=['GET'])
def get_voices():
    """Return list of available voice samples"""
    voices = scan_voices()
    return jsonify(voices)


# Route: Process uploaded text
@app.route('/api/process_text', methods=['POST'])
def api_process_text():
    """
    Process uploaded text: clean and split into chunks
    Expected JSON: {"text": "...", "start_position": 0}
    """
    try:
        data = request.get_json()
        text = data.get('text', '')
        start_position = data.get('start_position', 0)

        if not text:
            return jsonify({'success': False, 'error': 'No text provided'}), 400

        result = process_text(text, start_position)

        # Store chunks globally for synthesis
        global current_chunks
        current_chunks = result.get('chunks', [])

        return jsonify(result)

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Route: Synthesize audio for a chunk
@app.route('/api/synthesize', methods=['POST'])
def api_synthesize():
    """
    Generate audio for a text chunk using XTTS v2
    Expected JSON: {
        "text": "...",
        "voice_path": "samples/voice.wav",
        "chunk_index": 0,
        "language": "ru",
        "speed": 1.0
    }
    """
    try:
        data = request.get_json()
        text = data.get('text', '')
        voice_path = data.get('voice_path', '')
        chunk_index = data.get('chunk_index', 0)
        language = data.get('language', CONFIG['LANGUAGE'])
        speed = data.get('speed', 1.0)

        # Validate text and voice_path
        if not text or not voice_path:
            return jsonify({
                'success': False,
                'error': 'Missing text or voice_path'
            }), 400

        # Validate voice file exists and convert to absolute path
        voice_file_path = Path(voice_path)
        if not voice_file_path.exists():
            print(f"[ERROR] Voice file not found: {voice_path}")
            available_voices = [v['path'] for v in scan_voices()]
            print(f"[ERROR] Available voices: {available_voices}")
            return jsonify({
                'success': False,
                'error': f'Voice file not found: {voice_path}'
            }), 400

        # Convert to absolute path and string for TTS library
        voice_path_abs = str(voice_file_path.absolute())

        # Validate text is not empty after stripping
        text_stripped = text.strip()
        if not text_stripped:
            print(f"[WARNING] Chunk {chunk_index} is empty after stripping, skipping")
            return jsonify({
                'success': False,
                'error': 'Empty text chunk'
            }), 400

        # DEBUG: Show EXACT text sent to XTTS (all characters visible)
        print(f"\n{'='*60}")
        print(f"[DEBUG] CHUNK {chunk_index} - EXACT TEXT TO XTTS:")
        print(f"[DEBUG] Length: {len(text_stripped)} chars")
        print(f"[DEBUG] Text repr (shows hidden chars): {repr(text_stripped)}")
        print(f"[DEBUG] First 100 chars: {text_stripped[:100]}")
        print(f"{'='*60}\n")

        # Check if model is loaded
        if tts_model is None:
            return jsonify({
                'success': False,
                'error': 'TTS model not loaded'
            }), 500

        # CRITICAL: Acquire lock to prevent parallel synthesis (XTTS not thread-safe on GPU)
        with synthesis_lock:
            # Ensure audio output directory exists
            output_dir = Path(CONFIG['AUDIO_OUTPUT_DIR'])
            output_dir.mkdir(exist_ok=True)

            # Generate audio file path
            output_filename = f"chunk_{chunk_index}.wav"
            output_path = output_dir / output_filename

            print(f"\n[INFO] ⚙️ Synthesizing chunk {chunk_index} [LOCK ACQUIRED]")
            print(f"[INFO]   Text length: {len(text_stripped)} chars")
            print(f"[INFO]   Voice: {voice_path_abs}")
            print(f"[INFO]   Speed: {speed}x")
            print(f"[INFO]   Language: {language}")
            print(f"[DEBUG]   Text preview: {text_stripped[:100]}...")

            # GPU memory management
            if CONFIG['DEVICE'] == 'cuda' and torch.cuda.is_available():
                # Clear CUDA cache to prevent memory issues
                torch.cuda.empty_cache()
                before_mem = torch.cuda.memory_allocated(0) / 1024**3
                print(f"[DEBUG]   GPU memory before: {before_mem:.2f} GB")
            elif CONFIG['DEVICE'] == 'cuda' and not torch.cuda.is_available():
                print("[WARNING] CUDA device requested but not available, synthesis may fail")

            start_time = time.time()

            # CRITICAL: Clean chunk text to prevent artifacts
            # Remove trailing commas/spaces that cause duplication
            text_for_tts = text_stripped.rstrip(',;: \t')

            # CRITICAL FIX: Ensure ends with period + add continuation text
            # This prevents XTTS from "slowing down" at chunk end
            if text_for_tts and text_for_tts[-1] not in '.!?':
                text_for_tts += '.'

            # Synthesize using XTTS v2
            print(f"[INFO] Starting TTS synthesis...")
            print(f"[DEBUG] Final text for XTTS: {repr(text_for_tts[:100])}...")

            tts_model.tts_to_file(
                text=text_for_tts,
                speaker_wav=voice_path_abs,
                language=language,
                file_path=str(output_path),
                speed=speed,  # User-controlled reading speed
                temperature=0.75,  # Natural variability - per scope specification
                length_penalty=1.0,  # Uniform speed control - prevents random acceleration/deceleration
                repetition_penalty=5.0,  # High penalty to avoid monotony - per scope specification
                enable_text_splitting=False  # CRITICAL: Don't let XTTS split text internally
            )

            synthesis_time = time.time() - start_time

            if CONFIG['DEVICE'] == 'cuda' and torch.cuda.is_available():
                after_mem = torch.cuda.memory_allocated(0) / 1024**3
                print(f"[DEBUG]   GPU memory after: {after_mem:.2f} GB")

            # Check file was created
            if not output_path.exists():
                raise Exception(f"Output file not created: {output_path}")

            file_size = output_path.stat().st_size / 1024
            print(f"[SUCCESS] ✓ Chunk {chunk_index} synthesized in {synthesis_time:.2f}s")
            print(f"[SUCCESS]   Output: {output_filename} ({file_size:.1f} KB)")
            print(f"[INFO] Lock released for chunk {chunk_index}\n")

            return jsonify({
                'success': True,
                'audio_url': f'/api/audio/{output_filename}',
                'chunk_index': chunk_index
            })

    except Exception as e:
        error_msg = str(e)
        print("\n" + "="*60)
        print(f"[ERROR] ❌ Synthesis failed for chunk {chunk_index}")
        print(f"[ERROR] Error message: {error_msg}")
        print(f"[ERROR] Text that caused error: {text[:200] if 'text' in locals() else 'N/A'}...")
        print(f"[ERROR] Voice path: {voice_path if 'voice_path' in locals() else 'N/A'}")
        print(f"[ERROR] Device: {CONFIG['DEVICE']}")

        if CONFIG['DEVICE'] == 'cuda' and torch.cuda.is_available():
            try:
                mem = torch.cuda.memory_allocated(0) / 1024**3
                print(f"[ERROR] GPU memory at error: {mem:.2f} GB")
            except:
                pass

        print("[ERROR] Full traceback:")
        traceback.print_exc()
        print("="*60 + "\n")

        # Provide user-friendly error message
        if 'index out of range' in error_msg:
            error_msg = f"Text processing error in chunk {chunk_index}. The chunk may be too complex or contain unsupported characters."
        elif 'out of memory' in error_msg.lower():
            error_msg = f"GPU out of memory in chunk {chunk_index}. Try reducing chunk size or switching to CPU."
        elif 'CUDA' in error_msg.upper() or 'GPU' in error_msg.upper():
            error_msg = f"GPU error in chunk {chunk_index}: {error_msg}"

        return jsonify({
            'success': False,
            'error': error_msg,
            'chunk_index': chunk_index
        }), 500


# Route: Serve audio files
@app.route('/api/audio/<filename>', methods=['GET'])
def serve_audio(filename):
    """Serve generated audio files"""
    try:
        audio_path = os.path.join(CONFIG['AUDIO_OUTPUT_DIR'], filename)

        if not os.path.exists(audio_path):
            return jsonify({'error': 'Audio file not found'}), 404

        return send_file(audio_path, mimetype='audio/wav')

    except Exception as e:
        return jsonify({'error': str(e)}), 500


# Route: Cleanup audio files
@app.route('/api/cleanup', methods=['POST'])
def cleanup_audio():
    """Delete all temporary audio files"""
    try:
        output_dir = Path(CONFIG['AUDIO_OUTPUT_DIR'])

        if not output_dir.exists():
            return jsonify({'success': True, 'deleted': 0})

        # Delete all WAV files
        deleted = 0
        for audio_file in output_dir.glob('*.wav'):
            try:
                audio_file.unlink()
                deleted += 1
            except Exception as e:
                print(f"[WARNING] Could not delete {audio_file}: {str(e)}")

        print(f"[INFO] Cleaned up {deleted} audio files")

        return jsonify({'success': True, 'deleted': deleted})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Route: Cleanup old chunks (keep last 2-3 for buffer)
@app.route('/api/cleanup_old_chunks', methods=['POST'])
def cleanup_old_chunks():
    """Delete old audio chunks, keeping last 2-3 for playback buffer"""
    try:
        data = request.get_json()
        current_chunk_index = data.get('current_chunk_index', 0)
        keep_count = data.get('keep_count', 3)  # Keep last 3 chunks by default

        output_dir = Path(CONFIG['AUDIO_OUTPUT_DIR'])

        if not output_dir.exists():
            return jsonify({'success': True, 'deleted': 0})

        # Calculate which chunks to delete (older than current - keep_count)
        delete_before_index = max(0, current_chunk_index - keep_count)

        deleted = 0
        for chunk_index in range(delete_before_index):
            chunk_file = output_dir / f"chunk_{chunk_index}.wav"
            if chunk_file.exists():
                try:
                    chunk_file.unlink()
                    deleted += 1
                    print(f"[INFO] Deleted old chunk: chunk_{chunk_index}.wav")
                except Exception as e:
                    print(f"[WARNING] Could not delete chunk_{chunk_index}.wav: {str(e)}")

        if deleted > 0:
            print(f"[INFO] Auto-cleanup: deleted {deleted} old chunks")

        return jsonify({'success': True, 'deleted': deleted})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# Route: Save reading position (optional - mainly handled by localStorage)
@app.route('/api/save_position', methods=['POST'])
def save_position():
    """Save current reading position"""
    try:
        data = request.get_json()
        position = data.get('position', 0)

        # This could be extended to save to a database
        # For now, just acknowledge the request
        print(f"[INFO] Position saved: {position}")

        return jsonify({'success': True, 'position': position})

    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Application Startup
# ============================================
if __name__ == '__main__':
    print("\n" + "="*50)
    print("TTS Reader - Starting Application")
    print("="*50 + "\n")

    # Load TTS model
    load_tts_model()

    # Scan for voices
    voices = scan_voices()
    if len(voices) == 0:
        print("[WARNING] No voice samples found in 'samples/' directory")
        print("[INFO] Add WAV files to 'samples/' directory for voice cloning")

    print("\n" + "="*50)
    print("Server starting at http://localhost:5000")
    print("="*50 + "\n")

    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=5000,
        debug=True,
        use_reloader=False,  # Prevent double model loading
        threaded=True  # CRITICAL: Enable multi-threading for parallel prefetch requests
    )
