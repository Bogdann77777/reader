"""
TTS Reader - Flask Application
A local text reader with XTTS v2 multilingual voice synthesis
"""

import os
import sys
import logging
from datetime import datetime

# CRITICAL FIX: PyTorch 2.9.0 environment variables
os.environ["TORCH_FORCE_NO_WEIGHTS_ONLY_LOAD"] = "1"  # Disable weights_only strict loading
os.environ["TORCHAUDIO_USE_BACKEND_DISPATCHER"] = "0"  # Force soundfile backend

# Setup file logging FIRST
log_file = f'server_log_{datetime.now().strftime("%Y%m%d_%H%M%S")}.txt'
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
logger.info(f"="*80)
logger.info(f"SERVER STARTED - Logging to {log_file}")
logger.info(f"="*80)

# CRITICAL FIX: Add ffmpeg to PATH before importing any libraries that might use it
# Whisper (transformers) needs ffmpeg to process audio files for transcription
venv_scripts = os.path.join(os.getcwd(), 'venv', 'Scripts')
if venv_scripts not in os.environ['PATH']:
    os.environ['PATH'] = venv_scripts + os.pathsep + os.environ['PATH']
    logger.info(f"Added ffmpeg to PATH: {venv_scripts}")

import re
import glob
import json
import traceback
import threading
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_file
from flask_cors import CORS
import torch
from ruaccent import RUAccent
import time
import numpy as np
import soundfile as sf

# CRITICAL FIX: PyTorch 2.9.0+ requires safe_globals for custom classes in checkpoints
# XTTS model uses multiple custom classes that need to be allowlisted
try:
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import XttsAudioConfig, XttsArgs
    from TTS.tts.layers.xtts.gpt import GPTConfig
    from TTS.tts.layers.xtts.hifigan_decoder import HifiganConfig

    torch.serialization.add_safe_globals([
        XttsConfig,
        XttsAudioConfig,
        XttsArgs,
        GPTConfig,
        HifiganConfig
    ])
except Exception as e:
    print(f"[WARNING] Could not add safe globals: {e}")
    pass  # Fallback for older PyTorch versions

from TTS.api import TTS

# Fix encoding for Windows console to support Cyrillic
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Force torchaudio to use soundfile backend for better compatibility
# CRITICAL: PyTorch 2.9.0+cu128 tries to use torchcodec which has DLL issues on Windows
os.environ['TORCHAUDIO_USE_BACKEND_DISPATCHER'] = '0'
os.environ['TORCHAUDIO_BACKEND'] = 'soundfile'
os.environ['TORCHAUDIO_INCLUDE_TORCHCODEC'] = '0'
print("[INFO] Using torchaudio with soundfile backend (torchcodec forcefully disabled)")

# Initialize Flask app
app = Flask(__name__)
CORS(app)

# Configuration
CONFIG = {
    'SAMPLES_DIR': 'samples',
    'AUDIO_OUTPUT_DIR': 'audio_output',
    'XTTS_MODEL': 'tts_models/multilingual/multi-dataset/xtts_v2',  # XTTS v2 multilingual model
    'DEVICE': 'cuda',  # Using CUDA with PyTorch 2.9.0+cu128 (supports RTX 5060 Ti SM 12.0)
    'LANGUAGE': 'ru',
    'MIN_SENTENCES': 3,   # minimum sentences per chunk
    'MAX_SENTENCES': 10,  # maximum sentences per chunk
    'MAX_CHARS': 800,     # max characters per chunk (XTTS can handle up to ~400 words)
}

# Global variables
accentizer = None  # RUAccent for stress marking (optional for XTTS)
tts_model = None   # XTTS model (loaded once at startup)
current_chunks = []
synthesis_lock = threading.Lock()  # CRITICAL: Prevent parallel synthesis on GPU

print(f"[INFO] Using device: {CONFIG['DEVICE']}")


# ============================================
# Function: Load Models (RUAccent + XTTS)
# ============================================
def load_models():
    """
    Load RUAccent (optional) and XTTS v2 model
    XTTS v2 is multilingual and does NOT require stress marks
    Returns: tuple (accentizer, tts_model)
    """
    global accentizer, tts_model

    try:
        logger.info("="*80)
        logger.info("Loading models...")
        logger.info(f"XTTS Model: {CONFIG['XTTS_MODEL']}")
        logger.info(f"Target device: {CONFIG['DEVICE']}")

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

        # Load RUAccent (OPTIONAL for XTTS - can improve quality)
        print("[INFO] Initializing RUAccent (optional for XTTS)...")
        start_time = time.time()
        try:
            accentizer = RUAccent()
            accentizer.load(omograph_model_size='turbo', use_dictionary=True)
            load_time = time.time() - start_time
            print(f"[SUCCESS] RUAccent loaded in {load_time:.2f} seconds")
        except Exception as e:
            print(f"[WARNING] RUAccent failed to load: {e}")
            print("[INFO] Continuing without RUAccent (XTTS works fine without it)")
            accentizer = None

        # Load XTTS v2 model
        print(f"[INFO] Loading XTTS v2 model: {CONFIG['XTTS_MODEL']}...")
        start_time = time.time()

        tts_model = TTS(
            model_name=CONFIG['XTTS_MODEL'],
            progress_bar=True,
            gpu=(CONFIG['DEVICE'] == 'cuda')
        )

        # Move model to device
        if CONFIG['DEVICE'] == 'cuda' and torch.cuda.is_available():
            tts_model.to(CONFIG['DEVICE'])

        load_time = time.time() - start_time
        logger.info(f"SUCCESS: XTTS model loaded in {load_time:.2f} seconds")
        logger.info("XTTS v2 is multilingual (supports Russian without stress marks)")

        return accentizer, tts_model

    except Exception as e:
        print("\n" + "="*60)
        print(f"[ERROR] Failed to load models: {str(e)}")
        print("[ERROR] Full traceback:")
        traceback.print_exc()
        print("="*60 + "\n")
        return None, None


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
# Function: Analyze Text Emotion
# ============================================
def analyze_text_emotion(text):
    """
    Analyze emotional tone and context of text
    Returns emotion parameters for TTS synthesis
    """
    emotion_data = {
        'overall_emotion': 'neutral',
        'intensity': 0.5,
        'speed_modifier': 1.0,
        'pause_modifier': 1.0,
        'sections': []
    }

    # Emotion keywords and patterns (Russian)
    emotion_patterns = {
        'excitement': {
            'keywords': ['восхитительно', 'удивительно', 'потрясающе', 'невероятно', 'фантастически'],
            'intensity': 0.8,
            'speed_modifier': 1.1,
            'pause_modifier': 0.9
        },
        'sadness': {
            'keywords': ['грустно', 'печально', 'тоскливо', 'уныло', 'скорбно', 'траурно'],
            'intensity': 0.6,
            'speed_modifier': 0.85,
            'pause_modifier': 1.2
        },
        'anger': {
            'keywords': ['возмутительно', 'недопустимо', 'ужасно', 'отвратительно', 'мерзко'],
            'intensity': 0.9,
            'speed_modifier': 1.15,
            'pause_modifier': 0.8
        },
        'fear': {
            'keywords': ['страшно', 'жутко', 'ужасающе', 'пугающе', 'тревожно', 'опасно'],
            'intensity': 0.7,
            'speed_modifier': 1.05,
            'pause_modifier': 1.1
        },
        'joy': {
            'keywords': ['радостно', 'весело', 'счастливо', 'празднично', 'ликующе', 'торжественно'],
            'intensity': 0.75,
            'speed_modifier': 1.05,
            'pause_modifier': 0.95
        },
        'contemplative': {
            'keywords': ['размышляя', 'думая', 'полагаю', 'возможно', 'вероятно', 'наверное'],
            'intensity': 0.4,
            'speed_modifier': 0.9,
            'pause_modifier': 1.15
        }
    }

    # Analyze text sections
    text_lower = text.lower()
    emotion_scores = {}

    # Count emotion indicators
    for emotion, data in emotion_patterns.items():
        score = 0
        for keyword in data['keywords']:
            score += text_lower.count(keyword)
        emotion_scores[emotion] = score

    # Determine dominant emotion
    if sum(emotion_scores.values()) > 0:
        dominant_emotion = max(emotion_scores, key=emotion_scores.get)
        emotion_data['overall_emotion'] = dominant_emotion
        emotion_data['intensity'] = emotion_patterns[dominant_emotion]['intensity']
        emotion_data['speed_modifier'] = emotion_patterns[dominant_emotion]['speed_modifier']
        emotion_data['pause_modifier'] = emotion_patterns[dominant_emotion]['pause_modifier']

    # Analyze punctuation for additional emotional cues
    exclamation_count = text.count('!')
    question_count = text.count('?')
    ellipsis_count = text.count('...')

    # Adjust parameters based on punctuation
    if exclamation_count > 3:
        emotion_data['intensity'] = min(1.0, emotion_data['intensity'] + 0.2)
        emotion_data['speed_modifier'] *= 1.05

    if question_count > 5:
        emotion_data['pause_modifier'] *= 1.1  # More pauses for rhetorical questions

    if ellipsis_count > 2:
        emotion_data['speed_modifier'] *= 0.95  # Slower for contemplative text
        emotion_data['pause_modifier'] *= 1.2

    # Detect dialogue markers
    if '"' in text or '«' in text or '—' in text:
        emotion_data['has_dialogue'] = True
    else:
        emotion_data['has_dialogue'] = False

    logger.info(f"Emotion analysis: {emotion_data['overall_emotion']} "
                f"(intensity: {emotion_data['intensity']:.2f}, "
                f"speed: {emotion_data['speed_modifier']:.2f})")

    return emotion_data


# ============================================
# Function: Calculate Dynamic Speed
# ============================================
def calculate_dynamic_speed(text, base_speed=1.0, emotion_data=None):
    """
    Calculate dynamic reading speed based on text complexity and emotion
    Adjusts speed for difficult words, numbers, abbreviations
    """
    speed_data = {
        'base_speed': base_speed,
        'segments': []
    }

    # Complexity patterns that require slower reading
    complexity_patterns = {
        'technical_terms': {
            'pattern': r'\b[A-Z]{2,}(?:[a-z]+)?(?:\d+)?\b',  # API, XMLHttpRequest, HTML5
            'speed_modifier': 0.85,
            'description': 'technical abbreviations'
        },
        'numbers': {
            'pattern': r'\d+(?:[.,]\d+)?(?:%|₽|\$|€)?',  # Numbers with units
            'speed_modifier': 0.9,
            'description': 'numbers and percentages'
        },
        'scientific': {
            'pattern': r'\b(?:квант|молекул|атом|ген|нейро|био|хим|физ|матем)\w+\b',
            'speed_modifier': 0.88,
            'description': 'scientific terminology'
        },
        'foreign_words': {
            'pattern': r'\b[A-Za-z]+(?:-[A-Za-z]+)*\b',  # English words in Russian text
            'speed_modifier': 0.87,
            'description': 'foreign language words'
        },
        'complex_words': {
            'pattern': r'\b\w{15,}\b',  # Very long words (15+ chars)
            'speed_modifier': 0.85,
            'description': 'complex long words'
        }
    }

    # Split text into sentences for segment analysis
    import re
    sentences = re.split(r'([.!?]+)', text)

    current_position = 0
    for i in range(0, len(sentences), 2):
        if i >= len(sentences):
            break

        sentence = sentences[i]
        if not sentence.strip():
            continue

        # Base speed for this segment
        segment_speed = base_speed

        # Apply emotion modifier if available
        if emotion_data:
            segment_speed *= emotion_data.get('speed_modifier', 1.0)

        # Analyze complexity
        complexity_score = 0
        complexity_factors = []

        for pattern_name, pattern_data in complexity_patterns.items():
            matches = re.findall(pattern_data['pattern'], sentence, re.IGNORECASE)
            if matches:
                complexity_score += len(matches)
                complexity_factors.append(f"{pattern_data['description']}: {len(matches)}")
                # Apply strongest modifier
                segment_speed = min(segment_speed, base_speed * pattern_data['speed_modifier'])

        # Check sentence length (longer sentences read slightly slower)
        word_count = len(sentence.split())
        if word_count > 20:
            segment_speed *= 0.95
            complexity_factors.append(f"long sentence: {word_count} words")

        # Check for lists or enumerations (read slightly slower for clarity)
        if re.search(r'(?:во-первых|во-вторых|первое|второе|\d+\)|\d+\.)', sentence):
            segment_speed *= 0.92
            complexity_factors.append("enumeration detected")

        # Important text markers (emphasis, slower)
        if any(marker in sentence.upper() for marker in ['ВАЖНО', 'ВНИМАНИЕ', 'КРИТИЧНО', 'КЛЮЧЕВОЙ']):
            segment_speed *= 0.88
            complexity_factors.append("important text marker")

        # Dialogue adjustments (more natural pacing)
        if '"' in sentence or '«' in sentence or '—' in sentence:
            segment_speed *= 1.02  # Slightly faster for natural dialogue
            complexity_factors.append("dialogue")

        # Store segment data
        segment_data = {
            'start': current_position,
            'end': current_position + len(sentence),
            'text': sentence[:50] + '...' if len(sentence) > 50 else sentence,
            'speed': round(segment_speed, 2),
            'complexity_score': complexity_score,
            'factors': complexity_factors
        }
        speed_data['segments'].append(segment_data)

        current_position += len(sentence)
        if i + 1 < len(sentences):
            current_position += len(sentences[i + 1])  # Add punctuation length

    # Calculate average speed
    if speed_data['segments']:
        avg_speed = sum(s['speed'] for s in speed_data['segments']) / len(speed_data['segments'])
        speed_data['average_speed'] = round(avg_speed, 2)
    else:
        speed_data['average_speed'] = base_speed

    logger.info(f"Dynamic speed calculated: avg={speed_data['average_speed']}, "
                f"segments={len(speed_data['segments'])}")

    return speed_data


# ============================================
# Function: Select Voice for Context
# ============================================
def select_voice_for_context(text, available_voices, emotion_data=None):
    """
    Select appropriate voice based on text context
    Supports multiple voices for dialogues, narration, quotes
    """
    voice_selection = {
        'primary_voice': None,
        'voice_map': {},  # Maps text segments to specific voices
        'dialogue_voices': [],
        'narrator_voice': None
    }

    # Analyze text for different voice contexts
    context_patterns = {
        'dialogue': {
            'pattern': r'[«"]([^»"]+)[»"]',  # Quoted speech
            'voice_type': 'character'
        },
        'thoughts': {
            'pattern': r'[\(«]([^)»]+)[\)»]',  # Thoughts or internal monologue
            'voice_type': 'internal'
        },
        'emphasis': {
            'pattern': r'[A-ZА-Я]{3,}(?:\s+[A-ZА-Я]{3,})*',  # ALL CAPS emphasis
            'voice_type': 'emphatic'
        },
        'narrator': {
            'pattern': r'^[^«"—]+',  # Non-dialogue text
            'voice_type': 'narrator'
        }
    }

    # If we don't have multiple voices, return the first available
    if len(available_voices) <= 1:
        voice_selection['primary_voice'] = available_voices[0] if available_voices else None
        logger.info("Single voice mode - using primary voice for all text")
        return voice_selection

    # Assign voices based on context
    # Strategy: Different voices for dialogue speakers
    voice_selection['narrator_voice'] = available_voices[0]  # First voice for narration
    voice_selection['primary_voice'] = available_voices[0]

    # Detect dialogue and assign alternating voices
    dialogue_matches = re.findall(context_patterns['dialogue']['pattern'], text)
    if dialogue_matches:
        # Use different voices for different speakers (simple alternation)
        speaker_voices = {}
        voice_index = 1  # Start from second voice for dialogue

        # Try to detect different speakers by analyzing text before quotes
        speaker_pattern = r'(\w+)\s+(?:сказал|говорит|спросил|ответил|произнес|воскликнул)[:\s]*[«"]'
        speakers = re.findall(speaker_pattern, text, re.IGNORECASE)

        for i, speaker in enumerate(speakers):
            if speaker not in speaker_voices:
                if voice_index < len(available_voices):
                    speaker_voices[speaker] = available_voices[voice_index]
                    voice_index = (voice_index + 1) % len(available_voices)
                    if voice_index == 0:
                        voice_index = 1  # Skip narrator voice
                else:
                    speaker_voices[speaker] = available_voices[1] if len(available_voices) > 1 else available_voices[0]

        voice_selection['dialogue_voices'] = list(speaker_voices.values())

        # Create voice map for text segments
        current_pos = 0
        for match in re.finditer(context_patterns['dialogue']['pattern'], text):
            start, end = match.span()

            # Add narrator segment before dialogue
            if current_pos < start:
                voice_selection['voice_map'][f"{current_pos}-{start}"] = {
                    'voice': voice_selection['narrator_voice'],
                    'type': 'narrator',
                    'text': text[current_pos:start][:50]
                }

            # Add dialogue segment
            dialogue_text = match.group(1)
            # Try to identify speaker for this dialogue
            speaker_voice = available_voices[1] if len(available_voices) > 1 else available_voices[0]

            # Check if we can identify the speaker
            pre_text = text[max(0, start-100):start]
            for speaker, voice in speaker_voices.items():
                if speaker in pre_text:
                    speaker_voice = voice
                    break

            voice_selection['voice_map'][f"{start}-{end}"] = {
                'voice': speaker_voice,
                'type': 'dialogue',
                'text': dialogue_text[:50]
            }

            current_pos = end

        # Add final narrator segment
        if current_pos < len(text):
            voice_selection['voice_map'][f"{current_pos}-{len(text)}"] = {
                'voice': voice_selection['narrator_voice'],
                'type': 'narrator',
                'text': text[current_pos:][:50]
            }

    # Apply emotion-based voice selection hints
    if emotion_data:
        emotion = emotion_data.get('overall_emotion', 'neutral')

        # For strong emotions, prefer voices with matching characteristics
        # This is a placeholder for voice characteristic matching
        if emotion in ['excitement', 'joy'] and len(available_voices) > 2:
            voice_selection['primary_voice'] = available_voices[2]  # Assume third voice is more energetic
        elif emotion in ['sadness', 'contemplative'] and len(available_voices) > 1:
            voice_selection['primary_voice'] = available_voices[1]  # Assume second voice is calmer

    logger.info(f"Voice selection: {len(voice_selection['voice_map'])} segments mapped, "
                f"{len(voice_selection['dialogue_voices'])} dialogue voices")

    return voice_selection


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

        # Analyze emotion and context
        emotion_data = analyze_text_emotion(text_stripped)
        speed_data = calculate_dynamic_speed(text_stripped, speed, emotion_data)

        # Get all available voices for context selection
        available_voice_paths = [v['path'] for v in scan_voices()]
        voice_selection = select_voice_for_context(text_stripped, available_voice_paths, emotion_data)

        # Use selected voice if different from requested
        if voice_selection.get('primary_voice') and voice_selection['primary_voice'] != voice_path:
            logger.info(f"Context suggests using voice: {voice_selection['primary_voice']}")
            # For now, we'll use the requested voice but log the suggestion
            # In future, we can switch voices dynamically

        # DEBUG: Show EXACT text sent to XTTS (all characters visible)
        print(f"\n{'='*60}")
        print(f"[DEBUG] CHUNK {chunk_index} - EXACT TEXT TO XTTS:")
        print(f"[DEBUG] Length: {len(text_stripped)} chars")
        print(f"[DEBUG] Text repr (shows hidden chars): {repr(text_stripped)}")
        print(f"[DEBUG] First 100 chars: {text_stripped[:100]}")
        print(f"{'='*60}\n")

        # Check if XTTS model is loaded
        if tts_model is None:
            return jsonify({
                'success': False,
                'error': 'XTTS model not loaded'
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

            # Clean chunk text
            text_for_tts = text_stripped.rstrip(',;: \t')
            if text_for_tts and text_for_tts[-1] not in '.!?':
                text_for_tts += '.'

            # XTTS v2 does NOT need stress marks! Model trained on clean text
            # RUAccent stress marks (БАРЬ+ЕР) break XTTS synthesis completely!
            # Keeping text clean for XTTS
            logger.info(f"Using clean text for XTTS (NO stress marks needed)")

            print(f"[INFO] Starting XTTS synthesis...")
            print(f"[DEBUG] Text to synthesize: {text_for_tts[:100]}...")

            # Retry mechanism with exponential backoff
            max_retries = 3
            retry_delay = 1.0  # Start with 1 second

            for attempt in range(max_retries):
                try:
                    # Use dynamic speed from analysis
                    synthesis_speed = speed_data.get('average_speed', 1.0)
                    logger.info(f"Using dynamic speed: {synthesis_speed:.2f} (base: {speed})")

                    if attempt > 0:
                        logger.info(f"Retry attempt {attempt + 1}/{max_retries} for chunk {chunk_index}")

                    # Call XTTS tts_to_file method
                    # XTTS only needs speaker_wav (reference audio), NO reference text needed
                    tts_model.tts_to_file(
                        text=text_for_tts,
                        file_path=str(output_path),
                        speaker_wav=voice_path_abs,
                        language=language,
                        speed=synthesis_speed,
                        # XTTS-specific PRODUCTION quality parameters
                        # Based on official Coqui TTS recommendations and community best practices
                        temperature=0.65,  # Lower = more stable, less artifacts (0.65-0.7 recommended)
                        length_penalty=1.0,  # Controls output length
                        repetition_penalty=10.0,  # CRITICAL: Default 10.0 prevents repetition/artifacts
                        top_k=50,  # Top-k sampling diversity
                        top_p=0.85,  # Nucleus sampling
                        gpt_cond_len=6,  # Use 6 seconds of reference audio for better cloning
                        enable_text_splitting=True,  # Better handling of long texts
                    )

                    print(f"[DEBUG] Synthesis complete")

                    # Success - break the retry loop
                    break

                except Exception as e:
                    print(f"[ERROR] XTTS synthesis failed (attempt {attempt + 1}): {str(e)}")

                    if attempt < max_retries - 1:
                        # Wait before retry with exponential backoff
                        print(f"[INFO] Waiting {retry_delay:.1f}s before retry...")
                        time.sleep(retry_delay)
                        retry_delay *= 2  # Exponential backoff

                        # Clear GPU cache before retry
                        if CONFIG['DEVICE'] == 'cuda' and torch.cuda.is_available():
                            torch.cuda.empty_cache()
                    else:
                        # Final attempt failed
                        print(f"[ERROR] All {max_retries} attempts failed for chunk {chunk_index}")
                        traceback.print_exc()
                        raise Exception(f"XTTS synthesis failed after {max_retries} attempts: {str(e)}")

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
        if 'index out of range' in error_msg or 'tokenizer' in error_msg.lower():
            error_msg = f"Text processing error in chunk {chunk_index}. The chunk may be too complex or contain unsupported characters."
        elif 'out of memory' in error_msg.lower():
            error_msg = f"GPU out of memory in chunk {chunk_index}. Try reducing chunk size or switching to CPU."
        elif 'CUDA' in error_msg.upper() or 'GPU' in error_msg.upper():
            error_msg = f"GPU error in chunk {chunk_index}: {error_msg}"
        elif 'speaker_wav' in error_msg.lower():
            error_msg = f"Voice sample error in chunk {chunk_index}. Check that the voice file is valid."

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
    print("TTS Reader - Starting Application (XTTS v2)")
    print("="*50 + "\n")

    # Load models (RUAccent + XTTS)
    load_models()

    # Check if XTTS model loaded successfully
    if tts_model is None:
        print("[ERROR] Failed to load XTTS model. Exiting.")
        sys.exit(1)

    # Scan for voices
    voices = scan_voices()
    if len(voices) == 0:
        print("[WARNING] No voice samples found in 'samples/' directory")
        print("[INFO] Add WAV files to 'samples/' directory for voice cloning")

    print("\n" + "="*50)
    print("Server starting at http://localhost:9000")
    print("="*50 + "\n")

    # Run Flask app
    app.run(
        host='0.0.0.0',
        port=9000,
        debug=True,
        use_reloader=False,  # Prevent double model loading
        threaded=True  # CRITICAL: Enable multi-threading for parallel prefetch requests
    )
