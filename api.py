from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import speech_recognition as sr
import re
from gtts import gTTS

import os
import tempfile
from langdetect import detect, DetectorFactory

from dotenv import load_dotenv
from langchain_groq import ChatGroq

import wave
import audioop
import subprocess

from status_extractor import check_pnr_combined, generate_pnr_summary

# Set seed for language detection
DetectorFactory.seed = 0


load_dotenv()
key = os.getenv("GROQ_API_KEY")
model = ChatGroq(model="llama-3.3-70b-versatile", api_key=key)


app = FastAPI()

# CORS 
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class TextInput(BaseModel):
    text: str

class PNRInput(BaseModel):
    pnr: str
    language: str = "english" 

class TTSRequest(BaseModel):
    text: str
    language: str




def convert_to_wav(input_file: str, output_file: str) -> tuple[bool, str]:
    """
    Convert any audio input to WAV PCM signed 16-bit, mono, 16000 Hz using ffmpeg
    Returns (success, stderr_text).
    """
    try:
        # Build ffmpeg command to produce PCM S16 LE wav, mono, 16000 Hz
        cmd = [
            "ffmpeg",
            "-y",                 # overwrite
            "-nostdin",
            "-loglevel", "error", # only show errors
            "-i", input_file,
            "-ac", "1",           # mono
            "-ar", "16000",       # sampling rate
            "-acodec", "pcm_s16le",
            output_file
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        if proc.returncode != 0:
            return False, proc.stderr or "ffmpeg failed with return code {}".format(proc.returncode)
        # quick sanity check: file exists and non-empty
        if not os.path.exists(output_file) or os.path.getsize(output_file) < 100:
            return False, "Converted file missing or too small"
        return True, ""
    except FileNotFoundError:
        return False, "ffmpeg not found; please install ffmpeg and make sure it's in PATH"
    except Exception as e:
        return False, str(e)



def convert_to_wav_basic(input_file, output_file):
    """Basic WAV conversion fallback"""
    try:
        # Read the input file as binary
        with open(input_file, 'rb') as f:
            audio_data = f.read()
        
        # Try to open as WAV and resave with correct parameters
        with wave.open(input_file, 'rb') as wav_in:
            params = wav_in.getparams()
            frames = wav_in.readframes(params.nframes)
            
            # Convert to mono if stereo
            if params.nchannels == 2:
                frames = audioop.tomono(frames, params.sampwidth, 1, 1)
                channels = 1
            else:
                channels = params.nchannels
            
            # Write new WAV file with correct format
            with wave.open(output_file, 'wb') as wav_out:
                wav_out.setnchannels(channels)
                wav_out.setsampwidth(params.sampwidth)
                wav_out.setframerate(params.framerate)
                wav_out.writeframes(frames)
        
        return True
    except Exception as e:
        print(f"Basic WAV conversion error: {e}")
        return False





def detect_language(text):
    try:
        lang_code = detect(text)
        lang_map = {'hi': 'hindi', 'en': 'english', 'ur': 'hindi'}
        return lang_map.get(lang_code, 'english')
    except:
        return 'english'


def extract_pnr_from_text(text):
    """Extract 10-digit PNR from text, handling pauses and natural speech"""
    # Remove common words and normalize
    text = text.lower()
    
    # Replace common speech patterns
    text = text.replace('pause', ' ')
    text = text.replace('wait', ' ')
    text = text.replace('uh', ' ')
    text = text.replace('um', ' ')
    
    # Extract all digit sequences
    digit_sequences = re.findall(r'\d+', text)
 
    # First try: Find any 10-digit sequence
    for seq in digit_sequences:
        if len(seq) == 10:
            return seq
    
    # Second try: Combine consecutive digit groups to form 10 digits 
    all_digits = ''.join(digit_sequences)
    if len(all_digits) >= 10:
        # Take first 10 digits
        return all_digits[:10]
    
    return None




@app.post("/speech_to_text")
async def speech_to_text(audio: UploadFile = File(...)):
    """Convert speech audio to text"""
    temp_audio_path = None
    converted_audio_path = None
    
    try:
        # derive extension from original filename if possible (fallback to .bin)
        orig_ext = os.path.splitext(getattr(audio, "filename", "") or "")[1].lower() or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=orig_ext) as temp_audio:
            content = await audio.read()
            if not content or len(content) < 10:
                return JSONResponse(status_code=400, content={"success": False, "error": "Uploaded audio is empty or too small"})
            temp_audio.write(content)
            temp_audio_path = temp_audio.name
        
        # set output WAV path
        converted_audio_path = temp_audio_path + ".wav"
        
        # Convert to WAV using ffmpeg (recommended)
        conversion_success, conv_err = convert_to_wav(temp_audio_path, converted_audio_path)
        
        if not conversion_success:
            # don't silently fallback to the original file – fail clearly so user/deploy knows to fix conversion
            return JSONResponse(status_code=400, content={
                "success": False,
                "error": "Conversion to WAV failed. Details: " + conv_err
            })
        
        # Initialize recognizer
        recognizer = sr.Recognizer()
        recognizer.energy_threshold = 300
        recognizer.dynamic_energy_threshold = True
        
        # Load audio file (now guaranteed to be a proper WAV)
        with sr.AudioFile(converted_audio_path) as source:
            recognizer.adjust_for_ambient_noise(source, duration=0.5)
            audio_data = recognizer.record(source)
        
        # Try to recognize speech
        text = None
        try:
            text = recognizer.recognize_google(audio_data, language='en-IN')
        except Exception:
            try:
                text = recognizer.recognize_google(audio_data, language='hi-IN')
            except Exception:
                try:
                    text = recognizer.recognize_google(audio_data)
                except Exception as e:
                    raise Exception(f"Could not understand audio: {str(e)}")
        
        if not text:
            raise Exception("No speech detected in audio")
        
        detected_language = detect_language(text)
        
        return {"success": True, "text": text, "language": detected_language}
        
    except Exception as e:
        return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
    finally:
        # Clean up temp files
        for p in (temp_audio_path, converted_audio_path):
            if p and os.path.exists(p):
                try:
                    os.unlink(p)
                except:
                    pass


@app.post("/extract_pnr")
async def extract_pnr(data: TextInput):
    """Extract PNR number from text"""
    try:
        pnr = extract_pnr_from_text(data.text)
        
        if pnr:
            return {
                "success": True,
                "pnr": pnr
            }
        else:
            return {
                "success": False,
                "error": "No valid PNR found in the text"
            }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/get_pnr_status")
async def get_pnr_status(data: PNRInput):
    """Get PNR status and generate AI summary - merged endpoint"""
    try:
        pnr_data = check_pnr_combined(data.pnr)
        
        if not pnr_data:
            return {
                "success": False,
                "error": "Unable to fetch PNR status. Please verify the PNR number."
            }
        
        summary = generate_pnr_summary(pnr_data)
        
        return {
            "success": True,
            "pnr_data": pnr_data,
            "summary": summary,
            "language": data.language
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/text_to_speech")
async def text_to_speech(data: TTSRequest):
    """Convert text to speech using gTTS"""
    temp_audio_path = None
    
    try:
        lang_map = {
            'hindi': 'hi',
            'english': 'en'
        }
        
        lang_code = lang_map.get(data.language, 'en')
        
        # Generate speech
        tts = gTTS(text=data.text, lang=lang_code, slow=False)
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
            tts.save(temp_audio.name)
            temp_audio_path = temp_audio.name
        
        # Return audio file
        return FileResponse(
            temp_audio_path,
            media_type="audio/mpeg",
            filename="response.mp3",
            background=None
        )
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.get("/")
async def root():
    """Root endpoint"""
    return {"message": "PNR voice to voice agent running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 