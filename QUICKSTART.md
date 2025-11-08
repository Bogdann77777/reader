# Quick Start Guide - TTS Reader

## Step 1: Install Dependencies

```bash
pip install -r requirements.txt
```

**Note**: First run will download the XTTS v2 model (~2GB). This may take a few minutes.

## Step 2: Add Voice Samples

1. Create or obtain WAV audio files (6-10 seconds of clear speech)
2. Place them in the `samples/` directory
3. Example: `samples/my_voice.wav`

**If you don't have voice samples:**
- You can record your own voice using any audio recorder
- Or download free voice samples online
- Format: WAV, 22050Hz or 16000Hz, mono recommended

## Step 3: Run the Application

```bash
python app.py
```

Wait for:
- Model to load (first time: ~30-60 seconds)
- Server to start
- Message: "Server starting at http://localhost:5000"

## Step 4: Use the Application

1. **Open browser**: Go to `http://localhost:5000`

2. **Select voice**: Choose from dropdown (your WAV filename without extension)

3. **Upload text**:
   - Drag & drop `sample_text.txt` onto the upload area
   - Or click to browse and select any `.txt` file

4. **Start reading**: Click the **START** button

5. **Stop if needed**: Click **STOP** to pause (position is saved)

6. **Cleanup**: Click **CLEANUP** to remove temporary audio files

## Troubleshooting

### "No voices available"
- Add WAV files to `samples/` directory
- Restart the application

### Model loading fails
- Check internet connection (first run only)
- Ensure 5GB+ free disk space
- For GPU: Install CUDA Toolkit

### Slow synthesis
- GPU recommended for faster generation
- CPU mode works but is slower (2-5x)

## Testing

Use the included `sample_text.txt` file to test the application with Russian text.

## Next Steps

- Add more voice samples for variety
- Upload longer texts to read
- Experiment with different voices
- Share your own voice samples

## Need Help?

Check the full `README.md` for detailed documentation and troubleshooting.
