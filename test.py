# new api
from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import re
from gtts import gTTS # TTS
import os
import tempfile
from langdetect import detect, DetectorFactory

from dotenv import load_dotenv
from langchain_groq import ChatGroq

import wave
import audioop
import subprocess

import os
import tempfile
import whisper
from fastapi import UploadFile, File
from fastapi.responses import JSONResponse


whisper_model = whisper.load_model("medium") # recognizer (openai whisper model)

from status_extractor import check_pnr_combined, generate_pnr_summary

# langdetect is non-deterministic by default — meaning the same text can return different languages on different runs. Setting the seed forces deterministic output.
DetectorFactory.seed = 0 


load_dotenv()
key = os.getenv("GROQ_API_KEY")
model = ChatGroq(model="llama-3.3-70b-versatile", api_key=key) #llm


app = FastAPI()

# CORS middleware
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
    language: str = "english"  # Optional language for response

class TTSRequest(BaseModel):
    text: str
    language: str




#  digit mapping for major Indian languages
DIGIT_MAPPINGS = {
    # Hindi/Urdu
    'शून्य': '0', 'shuny': '0', 'shunya': '0',
    'एक': '1', 'ek': '1',
    'दो': '2', 'do': '2',
    'तीन': '3', 'teen': '3', 'tin': '3',
    'चार': '4', 'char': '4', 'chaar': '4',
    'पांच': '5', 'paanch': '5', 'panch': '5', 'punch': '5',
    'छह': '6', 'chhah': '6', 'chha': '6', 'chhe': '6',
    'सात': '7', 'saat': '7', 'sat': '7',
    'आठ': '8', 'aath': '8', 'ath': '8',
    'नौ': '9', 'nau': '9', 'no': '9',
   
    # English
    'zero': '0',
    'one': '1',
    'two': '2',
    'three': '3',
    'four': '4',
    'five': '5',
    'six': '6',
    'seven': '7',
    'eight': '8',
    'nine': '9',
   
    # Bengali
    'শূন্য': '0', 'shunno': '0',
    'এক': '1', 'æk': '1',
    'দুই': '2', 'dui': '2',
    'তিন': '3', 'tin': '3',
    'চার': '4', 'char': '4',
    'পাঁচ': '5', 'pãch': '5',
    'ছয়': '6', 'choy': '6',
    'সাত': '7', 'sat': '7',
    'আট': '8', 'at': '8', 'aat': '8',
    'নয়': '9', 'noy': '9',
   
    # Tamil
    'பூஜ்ஜியம்': '0', 'poojiyam': '0',
    'ஒன்று': '1', 'onru': '1', 'ondru': '1',
    'இரண்டு': '2', 'irandu': '2',
    'மூன்று': '3', 'moondru': '3', 'munru': '3',
    'நான்கு': '4', 'naangu': '4', 'nanku': '4',
    'ஐந்து': '5', 'ainthu': '5',
    'ஆறு': '6', 'aaru': '6',
    'ஏழு': '7', 'ezhu': '7',
    'எட்டு': '8', 'ettu': '8',
    'ஒன்பது': '9', 'onbathu': '9',
   
    # Telugu
    'సున్న': '0', 'sunna': '0',
    'ఒకటి': '1', 'okati': '1',
    'రెండు': '2', 'rendu': '2',
    'మూడు': '3', 'moodu': '3',
    'నాలుగు': '4', 'naalugu': '4',
    'ఐదు': '5', 'aidu': '5',
    'ఆరు': '6', 'aaru': '6',
    'ఏడు': '7', 'edu': '7', 'yedu': '7',
    'ఎనిమిది': '8', 'enimidi': '8',
    'తొమ్మిది': '9', 'tommidi': '9',
   
    # Marathi
    'शून्य': '0',
    'एक': '1',
    'दोन': '2', 'don': '2',
    'तीन': '3',
    'चार': '4',
    'पाच': '5', 'paach': '5',
    'सहा': '6', 'saha': '6',
    'सात': '7',
    'आठ': '8',
    'नऊ': '9', 'nau': '9',
   
    # Gujarati
    'શૂન્ય': '0',
    'એક': '1',
    'બે': '2', 'be': '2',
    'ત્રણ': '3', 'tran': '3',
    'ચાર': '4',
    'પાંચ': '5',
    'છ': '6', 'chha': '6',
    'સાત': '7',
    'આઠ': '8',
    'નવ': '9', 'nav': '9',
   
    # Kannada
    'ಸೊನ್ನೆ': '0', 'sonne': '0',
    'ಒಂದು': '1', 'ondu': '1',
    'ಎರಡು': '2', 'eradu': '2',
    'ಮೂರು': '3', 'mooru': '3',
    'ನಾಲ್ಕು': '4', 'naalku': '4',
    'ಐದು': '5', 'aidu': '5',
    'ಆರು': '6', 'aaru': '6',
    'ಏಳು': '7', 'elu': '7',
    'ಎಂಟು': '8', 'entu': '8',
    'ಒಂಬತ್ತು': '9', 'ombattu': '9',
   
    # Malayalam
    'പൂജ്യം': '0', 'poojyam': '0',
    'ഒന്ന്': '1', 'onnu': '1',
    'രണ്ട്': '2', 'randu': '2',
    'മൂന്ന്': '3', 'moonnu': '3',
    'നാല്': '4', 'naalu': '4',
    'അഞ്ച്': '5', 'anchu': '5',
    'ആറ്': '6', 'aaru': '6',
    'ഏഴ്': '7', 'ezhu': '7',
    'എട്ട്': '8', 'ettu': '8',
    'ഒമ്പത്': '9', 'ombathu': '9',
   
    # Punjabi
    'ਸਿਫ਼ਰ': '0', 'sifar': '0',
    'ਇੱਕ': '1', 'ikk': '1',
    'ਦੋ': '2',
    'ਤਿੰਨ': '3', 'tinn': '3',
    'ਚਾਰ': '4',
    'ਪੰਜ': '5', 'panj': '5',
    'ਛੇ': '6', 'chhe': '6',
    'ਸੱਤ': '7', 'satt': '7',
    'ਅੱਠ': '8', 'atth': '8',
    'ਨੌਂ': '9', 'naun': '9',
}

# mapping for faster lookup
DIGIT_MAPPING_LOWER = {k.lower(): v for k, v in DIGIT_MAPPINGS.items()}





# UTILITY FUNCTIONS 

#detects language of the text imput
def detect_language(text):
    
    try:
        lang_code = detect(text)
        lang_map = {
            'hi': 'hindi',
            'en': 'english',
            'ur': 'urdu',
            'pa': 'punjabi',
            'bn': 'bengali',
            'te': 'telugu',
            'mr': 'marathi',
            'ta': 'tamil',
            'gu': 'gujarati',
            'kn': 'kannada',
            'ml': 'malayalam'
        }
        return lang_map.get(lang_code, 'english')
    except:
        return 'english'


def convert_spoken_digits_to_numbers(text):
    """
    Convert spoken digits in any language to numeric digits.
    Handles mixed language scenarios.
    """
    # Split text into words
    words = text.split()
    converted_words = []
   
    for word in words:
        # remove punctuation but keep the word)
        cleaned_word = re.sub(r'[^\w\s]', '', word)
       
        # Check if this word is a digit word in any language
        digit = DIGIT_MAPPING_LOWER.get(cleaned_word.lower())
       
        if digit:
            converted_words.append(digit)
        else:
            # Keep original word if not a digit
            converted_words.append(word)
   
    return ' '.join(converted_words)



#extract PNR from the text
def extract_pnr_from_text(text):
    
    # Convert spoken digits to numeric digits
    text_with_digits = convert_spoken_digits_to_numbers(text)
   
    # lower text
    text_normalized = text_with_digits.lower()
   
    # Remove filler words
    fillers = ['pause', 'wait', 'uh', 'um', 'है', 'ha', 'hain', 'ka', 'ki', 'ke']
    for filler in fillers:
        text_normalized = text_normalized.replace(filler, ' ')
   
    # Extract all digit sequences
    digit_sequences = re.findall(r'\d+', text_normalized)
   
    # Try 1: Find any 10-digit sequence
    for seq in digit_sequences:
        if len(seq) == 10:
            return seq
   
    # Try 2: Combine consecutive digit groups to form 10 digits
    all_digits = ''.join(digit_sequences)
    if len(all_digits) >= 10:
        # Take first 10 digits
        return all_digits[:10]
   
    return None


# API ENDPOINTS 

@app.post("/speech_to_text")
async def speech_to_text(audio: UploadFile = File(...)):
    """Convert speech audio to text using Whisper with multi-language support"""
    temp_audio_path = None
   
    try:
        # Get original file extension
        orig_ext = os.path.splitext(getattr(audio, "filename", "") or "")[1].lower() or ".bin"
       
        # Save uploaded file
        with tempfile.NamedTemporaryFile(delete=False, suffix=orig_ext) as temp_audio:
            content = await audio.read()
            if not content or len(content) < 10:
                return JSONResponse(
                    status_code=400,
                    content={
                        "success": False,
                        "error": "Uploaded audio is empty or too small"
                    }
                )
            temp_audio.write(content)
            temp_audio_path = temp_audio.name
       
        # Transcribe using Whisper with language auto-detection
        # This will handle multilingual audio including code-switching
        result = whisper_model.transcribe(
            temp_audio_path,
            language=None,  # Auto-detect language
            fp16=False,
            verbose=False,
            # Enable word timestamps for better accuracy
            word_timestamps=True
        )
       
        text = result["text"].strip()
        detected_lang = result.get("language", "unknown")
       
        if not text:
            raise Exception("No speech detected in audio")
       
        # Map Whisper's language code to your format
        whisper_lang_map = {
            'en': 'english',
            'hi': 'hindi',
            'ur': 'urdu',
            'pa': 'punjabi',
            'bn': 'bengali',
            'te': 'telugu',
            'mr': 'marathi',
            'ta': 'tamil',
            'gu': 'gujarati',
            'kn': 'kannada',
            'ml': 'malayalam'
        }
       
        language = whisper_lang_map.get(detected_lang, detected_lang)
       
        # Also detect from text as fallback (for mixed language)
        try:
            text_detected_lang = detect_language(text)
            if text_detected_lang != 'english' and text_detected_lang != language:
                # Prefer text-based detection for mixed content
                language = text_detected_lang
        except:
            pass
       
        return {
            "success": True,
            "text": text,
            "language": language,
            "detected_language_code": detected_lang
        }
       
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": str(e)
            }
        )
   
    finally:
        # Clean up temp file
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
            except:
                pass


@app.post("/extract_pnr")
async def extract_pnr(data: TextInput):
    try:
        #extract pnr number from text
        pnr = extract_pnr_from_text(data.text)
       
        if pnr:
            return {
                "success": True,
                "pnr": pnr,
                "original_text": data.text
            }
        else:
            return {
                "success": False,
                "error": "No valid PNR found in the text",
                "original_text": data.text
            }
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )


@app.post("/get_pnr_status")
async def get_pnr_status(data: PNRInput):
    try:
        # SFetch PNR data using(API + Selenium)
        pnr_data = check_pnr_combined(data.pnr)
       
        if not pnr_data:
            return {
                "success": False,
                "error": "Unable to fetch PNR status. Please verify the PNR number."
            }
       
        # summary of the PNR data in the specified language
        summary = generate_pnr_summary(pnr_data, data.language)
       
        # Return
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
    temp_audio_path = None
   
    try:
        # Map language to gTTS language code
        lang_map = {
            'english': 'en',
            'hindi': 'hi',
            'urdu': 'ur',
            'punjabi': 'pa',
            'bengali': 'bn',
            'telugu': 'te',
            'marathi': 'mr',
            'tamil': 'ta',
            'gujarati': 'gu',
            'kannada': 'kn',
            'malayalam': 'ml'
        }
       
        lang_code = lang_map.get(data.language.lower(), 'en') # englsh by default
       
        # generate speech
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
    return {"message": "Railway Ticket Status Agent API is running"}


# TESTING ENDPOINT 
@app.post("/complete_pnr_flow_json")
async def complete_pnr_flow_json(audio: UploadFile = File(...)):
    "testing endpoint"
    temp_audio_path = None
   
    try:
        # Step 1: Convert speech to text
        orig_ext = os.path.splitext(getattr(audio, "filename", "") or "")[1].lower() or ".bin"
       
        with tempfile.NamedTemporaryFile(delete=False, suffix=orig_ext) as temp_audio:
            content = await audio.read()
            if not content or len(content) < 10:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Audio file is empty or too small"}
                )
            temp_audio.write(content)
            temp_audio_path = temp_audio.name
       
        # Transcribe
        result = whisper_model.transcribe(
            temp_audio_path,
            language=None,
            fp16=False,
            verbose=False,
            word_timestamps=True
        )
       
        text = result["text"].strip()
        detected_lang = result.get("language", "en")
       
        # Map language
        whisper_lang_map = {
            'en': 'english', 'hi': 'hindi', 'ur': 'urdu', 'pa': 'punjabi',
            'bn': 'bengali', 'te': 'telugu', 'mr': 'marathi', 'ta': 'tamil',
            'gu': 'gujarati', 'kn': 'kannada', 'ml': 'malayalam'
        }
        user_language = whisper_lang_map.get(detected_lang, 'english')
       
        # Detect from text as well
        try:
            text_detected_lang = detect_language(text)
            if text_detected_lang != 'english':
                user_language = text_detected_lang
        except:
            pass
       
        # Step 2: Extract PNR
        pnr = extract_pnr_from_text(text)
       
        if not pnr:
            return {
                "success": False,
                "error": "No PNR found",
                "transcribed_text": text,
                "detected_language": user_language
            }
       
        # Step 3: Get PNR status
        pnr_data = check_pnr_combined(pnr)
       
        if not pnr_data:
            return {
                "success": False,
                "error": "PNR status not found",
                "pnr": pnr,
                "detected_language": user_language
            }
       
        # Step 4: Generate summary
        summary = generate_pnr_summary(pnr_data, user_language)
       
        return {
            "success": True,
            "transcribed_text": text,
            "detected_language": user_language,
            "pnr": pnr,
            "pnr_data": pnr_data,
            "summary": summary,
            "note": "Use /text_to_speech endpoint to convert summary to audio"
        }
       
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(e)}
        )
   
    finally:
        if temp_audio_path and os.path.exists(temp_audio_path):
            try:
                os.unlink(temp_audio_path)
            except:
                pass


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)