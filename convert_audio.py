# -*- coding: utf-8 -*-
"""
Convert MP3 files to WAV format for TTS Reader
Converts all MP3 files in samples/ to WAV format (22050Hz, mono)
"""

import os
import sys
import librosa
import soundfile as sf
from pathlib import Path

# Set UTF-8 encoding for console output
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

def convert_mp3_to_wav(mp3_path, output_dir="samples"):
    """
    Convert MP3 file to WAV format using librosa
    Args:
        mp3_path: Path to MP3 file
        output_dir: Output directory for WAV file
    """
    try:
        filename = Path(mp3_path).stem
        print(f"\n[INFO] Converting: {filename}")

        # Load MP3 with librosa (automatically converts to mono if specified)
        audio, sr = librosa.load(mp3_path, sr=22050, mono=True)

        # Get filename without extension
        output_path = os.path.join(output_dir, f"{filename}.wav")

        # Export as WAV using soundfile
        sf.write(output_path, audio, 22050, subtype='PCM_16')

        duration = len(audio) / 22050.0  # Duration in seconds
        print(f"[SUCCESS] Saved: {filename}.wav")
        print(f"[INFO] Duration: {duration:.2f} seconds")
        print(f"[INFO] Sample rate: 22050Hz, Channels: mono")

        return output_path

    except Exception as e:
        print(f"[ERROR] Failed to convert {Path(mp3_path).name}: {str(e)}")
        return None


def main():
    """Convert all MP3 files in samples directory"""
    samples_dir = "samples"

    # Find all MP3 files
    mp3_files = []
    for file in os.listdir(samples_dir):
        if file.endswith('.mp3'):
            mp3_files.append(os.path.join(samples_dir, file))

    if not mp3_files:
        print("[WARNING] No MP3 files found in samples/ directory")
        return

    print(f"\n{'='*50}")
    print(f"Found {len(mp3_files)} MP3 files to convert")
    print(f"{'='*50}")

    # Convert each MP3
    converted = 0
    for mp3_file in mp3_files:
        result = convert_mp3_to_wav(mp3_file, samples_dir)
        if result:
            converted += 1

    print(f"\n{'='*50}")
    print(f"Conversion complete: {converted}/{len(mp3_files)} files converted")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    main()
