# TTS Reader - Text to Speech with XTTS v2

A local text reader application with voice synthesis using XTTS v2 zero-shot voice cloning.

## Features

- Web-based interface for easy text upload
- XTTS v2 voice cloning from sample files
- Drag & drop file upload
- Start/Stop playback controls
- Position saving and resuming
- Automatic audio cleanup
- GPU acceleration support

## Project Structure

```
reader/
├── app.py                  # Flask backend server
├── requirements.txt        # Python dependencies
├── samples/               # Voice sample files (WAV)
├── audio_output/          # Temporary audio files
├── templates/
│   └── index.html         # Main web interface
└── static/
    ├── css/
    │   └── style.css      # Application styles
    └── js/
        └── app.js         # Frontend logic
```

## Installation

### Prerequisites

- Python 3.10 or higher
- NVIDIA GPU with CUDA support (recommended)
- 8GB+ RAM
- 5GB+ free disk space

### Steps

1. **Install Python dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Add voice samples:**
   - Create WAV files (6-10 seconds of clear speech)
   - Format: 22050Hz, mono recommended
   - Place in `samples/` directory
   - Files will appear in voice dropdown by name

3. **Run the application:**
   ```bash
   python app.py
   ```

4. **Open in browser:**
   ```
   http://localhost:5000
   ```

## Usage

### 1. Select a Voice
Choose a voice from the dropdown menu loaded from your `samples/` directory.

### 2. Upload Text
- Drag and drop a `.txt` file onto the upload area
- Or click to browse and select a file
- Text will be displayed in the text area

### 3. Start Reading
- Click **START** to begin reading from the beginning
- Or click in the text area to set a custom start position
- The application will read through all text chunks

### 4. Control Playback
- **STOP**: Pause reading and save current position
- **CLEANUP**: Remove all temporary audio files

## Voice Sample Preparation

For best results with voice cloning:

1. **Recording guidelines:**
   - 6-10 seconds of clean, clear speech
   - No background noise
   - Natural speaking pace
   - Good quality microphone

2. **File format:**
   - WAV format
   - 22050Hz sample rate (or 16kHz)
   - Mono or stereo
   - Name the file descriptively (e.g., `male_deep.wav`)

3. **Adding voices:**
   - Place WAV files in the `samples/` directory
   - Restart the application to load new voices
   - Voice name in dropdown = filename without extension

## API Endpoints

- `GET /` - Main application page
- `GET /api/voices` - List available voices
- `POST /api/process_text` - Process uploaded text
- `POST /api/synthesize` - Generate audio for text chunk
- `GET /api/audio/<filename>` - Serve audio file
- `POST /api/cleanup` - Delete temporary audio files
- `POST /api/save_position` - Save reading position

## Technical Details

### Text Processing

- **Cleaning**: Removes special characters, keeps punctuation
- **Chunking**: Splits text into 300-500 character segments
- **Smart splitting**: Breaks at sentence boundaries

### TTS Parameters

- **Speed**: 1.0 (natural)
- **Temperature**: 0.75 (natural variation)
- **Repetition Penalty**: 5.0 (avoid monotony)
- **Language**: Russian (configurable)

### Performance

- **GPU**: ~0.5-1 second per second of audio
- **CPU**: ~2-5 seconds per second of audio
- **Model size**: ~2GB (downloads on first run)
- **Memory usage**: 4-8GB RAM

## Troubleshooting

### Model not loading
- Check CUDA installation if using GPU
- Verify sufficient disk space (5GB+)
- Check internet connection (first run downloads model)

### No voices available
- Add WAV files to `samples/` directory
- Restart the application
- Check file format (must be .wav)

### Audio playback issues
- Check browser audio permissions
- Try different browser (Chrome/Firefox recommended)
- Verify audio files are being generated in `audio_output/`

### Slow synthesis
- Enable GPU acceleration (requires CUDA)
- Reduce text chunk size
- Check system resources

## System Requirements

### Minimum
- CPU: 4 cores
- RAM: 8GB
- GPU: NVIDIA GPU with 4GB VRAM (or CPU fallback)
- Storage: 5GB free space

### Recommended
- CPU: 8+ cores
- RAM: 16GB
- GPU: NVIDIA RTX 3060+ with 8GB+ VRAM
- Storage: 10GB SSD

## License

This project is for educational and personal use.

## Credits

- **XTTS v2**: Coqui TTS
- **Framework**: Flask
- **UI**: Vanilla JavaScript
