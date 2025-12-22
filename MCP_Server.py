from fastmcp import FastMCP
from typing import Optional, Dict, Any, List
import json
import re
from langdetect import detect, DetectorFactory

# Import from existing modules
from status_extractor import (
    check_pnr_combined, 
    generate_pnr_summary,
    check_pnr_rapidapi,
    check_pnr_automation
)

DetectorFactory.seed = 0

# Initialize MCP server
mcp = FastMCP("PNR Status Assistant")

# Store session data (in production, use proper database)
sessions: Dict[str, Dict[str, Any]] = {}

# Digit mappings for extracting PNR from spoken text
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
}

DIGIT_MAPPING_LOWER = {k.lower(): v for k, v in DIGIT_MAPPINGS.items()}


def detect_language(text: str) -> str:
    """Detect language from text"""
    try:
        lang_code = detect(text)
        lang_map = {
            'hi': 'hindi', 'en': 'english', 'ur': 'urdu', 'pa': 'punjabi',
            'bn': 'bengali', 'te': 'telugu', 'mr': 'marathi', 'ta': 'tamil',
            'gu': 'gujarati', 'kn': 'kannada', 'ml': 'malayalam'
        }
        return lang_map.get(lang_code, 'english')
    except:
        return 'english'


def convert_spoken_digits_to_numbers(text: str) -> str:
    """Convert spoken digits to numeric form"""
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


def extract_pnr_from_text(text: str) -> Optional[str]:
    """Extract 10-digit PNR number from text"""
    text_with_digits = convert_spoken_digits_to_numbers(text)
    text_normalized = text_with_digits.lower()
    
    # Remove fillers
    fillers = ['pause', 'wait', 'uh', 'um', 'है', 'ha', 'hain', 'ka', 'ki', 'ke']
    for filler in fillers:
        text_normalized = text_normalized.replace(filler, ' ')
    
    # Find digit sequences
    digit_sequences = re.findall(r'\d+', text_normalized)
    
    # Look for exactly 10 digits
    for seq in digit_sequences:
        if len(seq) == 10:
            return seq
    
    # Combine all digits and take first 10
    all_digits = ''.join(digit_sequences)
    if len(all_digits) >= 10:
        return all_digits[:10]
    
    return None


def get_or_create_session(session_id: str) -> Dict[str, Any]:
    """Get or create session data"""
    if session_id not in sessions:
        sessions[session_id] = {
            "pnr": None,
            "last_status": None,
            "history": [],
            "language": "english"
        }
    return sessions[session_id]


@mcp.tool()
def check_pnr_status(
    pnr_number: str,
    method: str = "combined"
) -> Dict[str, Any]:
    """
    Check Indian Railway PNR status
    
    Args:
        pnr_number: 10-digit PNR number
        method: "combined" (try API then automation), "api" (RapidAPI only), or "automation" (Selenium only)
    
    Returns:
        Dictionary containing ticket details including train info, passenger status, etc.
    """
    # Validate PNR
    if len(str(pnr_number)) != 10 or not str(pnr_number).isdigit():
        return {
            "success": False,
            "error": "Invalid PNR. Must be exactly 10 digits."
        }
    
    try:
        if method == "api":
            result = check_pnr_rapidapi(pnr_number)
        elif method == "automation":
            result = check_pnr_automation(str(pnr_number))
        else:  # combined
            result = check_pnr_combined(pnr_number)
        
        if result:
            return {
                "success": True,
                "data": result
            }
        else:
            return {
                "success": False,
                "error": "Unable to fetch PNR status. Please verify the PNR number and try again."
            }
    
    except Exception as e:
        return {
            "success": False,
            "error": f"Error checking PNR: {str(e)}"
        }


@mcp.tool()
def generate_summary(
    pnr_data: Dict[str, Any],
    language: str = "english",
    conversation_history: Optional[List[Dict]] = None
) -> str:
    """
    Generate natural language summary of PNR status
    
    Args:
        pnr_data: PNR status data from check_pnr_status
        language: Output language (english, hindi, tamil, etc.)
        conversation_history: Previous conversation context
    
    Returns:
        Human-friendly summary of the ticket status
    """
    try:
        summary = generate_pnr_summary(pnr_data, language, conversation_history)
        return summary
    except Exception as e:
        return f"Error generating summary: {str(e)}"


@mcp.tool()
def extract_pnr(text: str) -> Dict[str, Any]:
    """
    Extract PNR number from natural language text
    
    Args:
        text: Text that may contain PNR number (spoken or written)
    
    Returns:
        Dictionary with extracted PNR and detected language
    """
    pnr = extract_pnr_from_text(text)
    language = detect_language(text)
    
    return {
        "pnr": pnr,
        "language": language,
        "found": pnr is not None
    }


@mcp.tool()
def detect_text_language(text: str) -> str:
    """
    Detect the language of input text
    
    Args:
        text: Input text
    
    Returns:
        Detected language name (english, hindi, tamil, etc.)
    """
    return detect_language(text)


@mcp.tool()
def create_session(session_id: str = "default") -> Dict[str, Any]:
    """
    Create or get a conversation session
    
    Args:
        session_id: Unique session identifier
    
    Returns:
        Session status information
    """
    session = get_or_create_session(session_id)
    return {
        "session_id": session_id,
        "has_pnr": session["pnr"] is not None,
        "pnr": session["pnr"],
        "language": session["language"],
        "history_count": len(session["history"])
    }


@mcp.tool()
def update_session(
    session_id: str,
    pnr: Optional[str] = None,
    language: Optional[str] = None,
    add_to_history: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Update session data
    
    Args:
        session_id: Session identifier
        pnr: New PNR number to set
        language: New language preference
        add_to_history: Dict with 'user' and 'assistant' keys to add to conversation history
    
    Returns:
        Updated session status
    """
    session = get_or_create_session(session_id)
    
    if pnr is not None:
        session["pnr"] = pnr
    
    if language is not None:
        session["language"] = language
    
    if add_to_history is not None:
        session["history"].append(add_to_history)
    
    return {
        "session_id": session_id,
        "pnr": session["pnr"],
        "language": session["language"],
        "history_count": len(session["history"])
    }


@mcp.tool()
def clear_session(session_id: str) -> Dict[str, bool]:
    """
    Clear all data for a session
    
    Args:
        session_id: Session identifier to clear
    
    Returns:
        Success status
    """
    if session_id in sessions:
        del sessions[session_id]
    
    return {"success": True, "cleared": True}


@mcp.tool()
def get_session_history(session_id: str, limit: int = 10) -> Dict[str, Any]:
    """
    Get conversation history for a session
    
    Args:
        session_id: Session identifier
        limit: Maximum number of history items to return
    
    Returns:
        Session history and metadata
    """
    session = get_or_create_session(session_id)
    
    return {
        "session_id": session_id,
        "pnr": session["pnr"],
        "language": session["language"],
        "history": session["history"][-limit:],
        "total_interactions": len(session["history"])
    }


@mcp.tool()
def check_and_summarize(
    pnr_number: str,
    language: str = "english",
    session_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Combined tool: Check PNR status and generate summary in one call
    
    Args:
        pnr_number: 10-digit PNR number
        language: Output language for summary
        session_id: Optional session ID to store results
    
    Returns:
        Dictionary with PNR data and natural language summary
    """
    # Check status
    status_result = check_pnr_status(pnr_number)
    
    if not status_result["success"]:
        return status_result
    
    # Generate summary
    pnr_data = status_result["data"]
    summary = generate_summary(pnr_data, language)
    
    # Update session if provided
    if session_id:
        session = get_or_create_session(session_id)
        session["pnr"] = pnr_number
        session["last_status"] = pnr_data
        session["language"] = language
    
    return {
        "success": True,
        "pnr": pnr_number,
        "language": language,
        "data": pnr_data,
        "summary": summary,
        "session_id": session_id
    }


# Add resource for server information
@mcp.resource("server://info")
def get_server_info() -> str:
    """Get information about the PNR Status MCP server"""
    return json.dumps({
        "name": "PNR Status Assistant",
        "version": "1.0.0",
        "description": "Indian Railway PNR status checking and assistant system",
        "capabilities": [
            "Check PNR status via multiple methods (API + automation)",
            "Generate natural language summaries in 11+ Indian languages",
            "Extract PNR numbers from spoken/written text",
            "Language detection",
            "Session management for conversational interactions",
            "Multi-language support"
        ],
        "supported_languages": [
            "English", "Hindi", "Tamil", "Telugu", "Bengali",
            "Marathi", "Gujarati", "Kannada", "Malayalam", "Punjabi", "Urdu"
        ]
    }, indent=2)


if __name__ == "__main__":
    # Run the MCP server
    mcp.run(transport="http", host="0.0.0.0", port=8000)