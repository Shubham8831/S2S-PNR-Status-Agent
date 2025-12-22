from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

import re
from gtts import gTTS # text to speech
import os
import tempfile
from langdetect import detect, DetectorFactory
from typing import Optional, List, Dict

from dotenv import load_dotenv
from langchain_groq import ChatGroq #llm

import whisper

whisper_model = whisper.load_model("medium") # speech to text

from status_extractor import check_pnr_combined, generate_pnr_summary

DetectorFactory.seed = 0 # this is set to get same output for same text at each run 

load_dotenv()
key = os.getenv("GROQ_API_KEY")
model = ChatGroq(model="llama-3.3-70b-versatile", api_key=key)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # allow all for now 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# dict to maintain state
sessions = {}



#pydantic data validations for endpoints 
class TextInput(BaseModel):
    text: str

class PNRInput(BaseModel):
    pnr: str
    language: str = "english"

class TTSRequest(BaseModel):
    text: str
    language: str

class SessionRequest(BaseModel):
    session_id: str
    audio: Optional[UploadFile] = None

# mappings for hindi 
DIGIT_MAPPINGS = {
    'शून्य': '0', 'shuny': '0', 'shunya': '0',
    'एक': '1', 'ek': '1',
    'दो': '2', 'do': '2',
    'तीन': '3', 'teen': '3', 'tin': '3',
    'चार': '4', 'char': '4', 'chaar': '4',
    'पाँच': '5', 'paanch': '5', 'panch': '5', 'punch': '5',
    'छह': '6', 'chhah': '6', 'chha': '6', 'chhe': '6',
    'सात': '7', 'saat': '7', 'sat': '7',
    'आठ': '8', 'aath': '8', 'ath': '8',
    'नौ': '9', 'nau': '9', 'no': '9',
    'zero': '0', 'one': '1', 'two': '2', 'three': '3', 'four': '4',
    'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9',
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

DIGIT_MAPPING_LOWER = {k.lower(): v for k, v in DIGIT_MAPPINGS.items()}


# given text this fn detects the language
def detect_language(text):
    try:
        lang_code = detect(text)
        lang_map = {
            'hi': 'hindi', 'en': 'english', 'ur': 'urdu', 'pa': 'punjabi',
            'bn': 'bengali', 'te': 'telugu', 'mr': 'marathi', 'ta': 'tamil',
            'gu': 'gujarati', 'kn': 'kannada', 'ml': 'malayalam'
        }
        return lang_map.get(lang_code, 'english')# default set eng
    except:
        return 'english'


#this funtion converts spoken digits to numbers
def convert_spoken_digits_to_numbers(text):
    words = text.split()
    converted_words = []
    for word in words:
        cleaned_word = re.sub(r'[^\w\s]', '', word)
        digit = DIGIT_MAPPING_LOWER.get(cleaned_word.lower())
        if digit:
            converted_words.append(digit)
        else:
            converted_words.append(word)
    return ' '.join(converted_words)


#this funtion extracts pnr number from the text
def extract_pnr_from_text(text):
    text_with_digits = convert_spoken_digits_to_numbers(text)
    text_normalized = text_with_digits.lower()
    fillers = ['pause', 'wait', 'uh', 'um', 'है', 'ha', 'hain', 'ka', 'ki', 'ke']
    for filler in fillers:
        text_normalized = text_normalized.replace(filler, ' ')
    digit_sequences = re.findall(r'\d+', text_normalized)
    for seq in digit_sequences:
        if len(seq) == 10:
            return seq
    all_digits = ''.join(digit_sequences)
    if len(all_digits) >= 10:
        return all_digits[:10]
    return None

# this creates the state dict if not present and if present it gets it
def get_or_create_session(session_id: str) -> Dict:
    
    if session_id not in sessions:
        sessions[session_id] = {
            "pnr": None, # at start/first run it is set to none
            "last_status": None,
            "history": [],
            "language": "english" #default language
        }
    return sessions[session_id]


# taeks input session data and language and then return response
def generate_contextual_response(text: str, session: Dict, detected_lang: str) -> tuple:
    
    # extract pnr number
    new_pnr = extract_pnr_from_text(text)
    
    # update session language
    session["language"] = detected_lang
    
    # if new pnr comes
    if new_pnr:
        session["pnr"] = new_pnr
        session["last_status"] = None
        return ("", True)  # Fetch status for new PNR
    
    # if no pnr in session then ask for pnr from user
    if not session["pnr"]:
        lang_prompts = {
            'hindi': 'कृपया अपना PNR नंबर बताइए',
            'english': 'Please provide your PNR number',
            'tamil': 'தயவுசெய்து உங்கள் PNR எண்ணைச் சொல்லுங்கள்',
            'telugu': 'దయచేసి మీ PNR నంబర్‌ను చెప్పండి',
            'bengali': 'অনুগ্রহ করে আপনার PNR নম্বর বলুন',
            'marathi': 'कृपया तुमचा PNR नंबर सांगा',
            'gujarati': 'કૃપા કરીને તમારો PNR નંબર આપો',
            'kannada': 'ದಯವಿಟ್ಟು ನಿಮ್ಮ PNR ಸಂಖ್ಯೆಯನ್ನು ಹೇಳಿ',
            'malayalam': 'ദയവായി നിങ്ങളുടെ PNR നമ്പർ നൽകുക',
            'punjabi': 'ਕਿਰਪਾ ਕਰਕੇ ਆਪਣਾ PNR ਨੰਬਰ ਦੱਸੋ',
            'urdu': 'براہ کرم اپنا PNR نمبر بتائیں'
        }
        return (lang_prompts.get(detected_lang, lang_prompts['english']), False)
    
    # if pnr is there but no status
    if not session["last_status"]:
        return ("", True)  # Fetch status
    
    # if ave pnr and status then ask llm for response
    return (generate_followup_answer(text, session, detected_lang), False)


#this function generate answer for the follow-up questions 
def generate_followup_answer(question: str, session: Dict, language: str) -> str:
  
    
    import json
    status_data = session["last_status"] # take last status and pnr from the state
    pnr = session["pnr"]
    
    # make conversation history
    history_context = ""
    if session["history"]:
        history_context = "\n\nPrevious conversation:\n"
        for item in session["history"][-3:]:
            history_context += f"User: {item['user']}\nAssistant: {item['assistant']}\n"
    
    prompt = f"""You are an Indian Railway PNR assistant helping users with follow-up questions.

Current context:
PNR: {pnr}
Language: {language}
{history_context}

Ticket Status (JSON):
{json.dumps(status_data, indent=2)}

User's question: "{question}"

Instructions:
- Answer the user's question directly based on the ticket status data
- Keep response SHORT and conversational (2-3 sentences max)
- Use {language} language
- Be natural and friendly
- If data not available, say so politely
- Do NOT repeat information unnecessarily

Answer:"""

    try:
        response = model.invoke(prompt)
        answer = response.content.strip()
        
        # Add to history
        session["history"].append({
            "user": question,
            "assistant": answer
        })
        
        return answer
    except Exception as e:
        return f"Sorry, I couldn't process your question. Error: {str(e)}"


#main endpoint 
@app.post("/unified_voice_input")
async def unified_voice_input(audio: UploadFile = File(...), session_id: str = "default"): #takes audio
    
    temp_audio_path = None
    
    try:
        # either get or create session data
        session = get_or_create_session(session_id)
        
        # speech to text 
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
        
        # Fallback detection
        try:
            text_detected_lang = detect_language(text)
            if text_detected_lang != 'english':
                user_language = text_detected_lang
        except:
            pass
        
        # generate contextual response
        response_text, should_fetch = generate_contextual_response(text, session, user_language)
        
        # fetch pnr data 
        if should_fetch and session["pnr"]:
            pnr_data = check_pnr_combined(session["pnr"])
            
            if not pnr_data:
                return {
                    "success": False,
                    "error": "Unable to fetch PNR status",
                    "transcribed_text": text,
                    "detected_language": user_language,
                    "session_id": session_id
                }
            
            session["last_status"] = pnr_data
            
            # generate summary
            response_text = generate_pnr_summary(pnr_data, user_language)
            
            # add to dict data
            session["history"].append({
                "user": text,
                "assistant": response_text
            })
        
        return {
            "success": True,
            "transcribed_text": text,
            "detected_language": user_language,
            "pnr": session["pnr"],
            "response": response_text,
            "pnr_data": session["last_status"],
            "session_id": session_id,
            "has_context": len(session["history"]) > 0
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



#endpoint to convert text to audio with gtts :)
@app.post("/text_to_speech")
async def text_to_speech(data: TTSRequest):
    temp_audio_path = None
    
    try:
        lang_map = {
            'english': 'en', 'hindi': 'hi', 'urdu': 'ur', 'punjabi': 'pa',
            'bengali': 'bn', 'telugu': 'te', 'marathi': 'mr', 'tamil': 'ta',
            'gujarati': 'gu', 'kannada': 'kn', 'malayalam': 'ml'
        }
        
        lang_code = lang_map.get(data.language.lower(), 'en')
        tts = gTTS(text=data.text, lang=lang_code, slow=False)
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as temp_audio:
            tts.save(temp_audio.name)
            temp_audio_path = temp_audio.name
        
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



#endpoint to clear session data
@app.post("/clear_session")
async def clear_session(session_id: str = "default"):
    """Clear session data"""
    if session_id in sessions:
        del sessions[session_id]
    return {"success": True, "message": "Session cleared"}



#endpoint to get current session data
@app.get("/session_status")
async def session_status(session_id: str = "default"):
    """gives current session details"""
    session = get_or_create_session(session_id)
    return {
        "session_id": session_id,
        "has_pnr": session["pnr"] is not None,
        "pnr": session["pnr"],
        "has_status": session["last_status"] is not None,
        "language": session["language"],
        "history_count": len(session["history"])
    }

@app.get("/")
async def root():
    return {"message": "S2S PNR Agent"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)