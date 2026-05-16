"""
Birni AI Chatbot Service Layer
------------------------------
This module handles the AI-powered civic assistance logic for Birnagar Municipality.
It implements a resilient 'Dual-Path' architecture:
1. Primary Path: Uses the ByteZ Unified API for high-performance model routing.
2. Fallback Path: Uses a direct Google Gemini API connection to ensure 100% uptime
   even if the primary proxy experiences latency or unauthorized errors.
"""
import os
import logging
import requests
from django.conf import settings

logger = logging.getLogger(__name__)

# API Keys from settings/env
BYTEZ_API_KEY = getattr(settings, 'BYTEZ_API_KEY', None)
GEMINI_API_KEY = getattr(settings, 'GEMINI_API_KEY', None)

# Model IDs
BYTEZ_MODEL = "gemini-1.5-flash"
GOOGLE_MODEL = "gemini-flash-latest"

SYSTEM_PROMPT = """
You are "Birni", the official AI Civic Assistant for Birnagar Municipality's "Mission Clean City" platform.
Your goal is to help citizens and administrators use the platform effectively.

PERSONALITY:
- Polite, helpful, and professional. Use a supportive tone.
- You represent the Birnagar Municipality (Nadia District, West Bengal).

KNOWLEDGE BASE:
- PLATFORM PURPOSE: Report civic issues (Complaints), submit suggestions, and manage waste collection.
- REGISTRATION: Users need Name, Mobile, Email, Aadhaar (stored securely), and Address (Ward No.).
- WARDS: Birnagar has 14 wards. Each ward has dedicated cleanliness staff.
- SERVICES: Garbage collection, street lighting, drainage management, and birth/death certificates.
- CONTACTS: Office: 03473-260227 | Email: birnagarmunicipality@rediffmail.com
- HISTORY: Birnagar is one of the oldest municipalities in Bengal (est. 1869).

GUIDELINES:
- If a user asks about a complaint, guide them to the "Track Issue" or "Complaints" section.
- If a user is not registered, explain the benefits of registration (tracking, priority support).
- Keep responses concise and focused on civic assistance.
"""

def get_chatbot_response(user_query, chat_history=None):
    """
    Attempts to get a response from Bytez, with a fallback to direct Google API.
    """
    # 1. Try Bytez Path (Primary)
    if BYTEZ_API_KEY and len(BYTEZ_API_KEY) > 10:
        response = _call_bytez(user_query, chat_history)
        if response and not response.startswith("Error:"):
            return response
        logger.warning(f"Bytez failed or returned error: {response}. Falling back to Direct Google API.")

    # 2. Try Direct Google Path (Fallback)
    if GEMINI_API_KEY and len(GEMINI_API_KEY) > 10:
        return _call_google_direct(user_query, chat_history)

    return "Birni is temporarily offline. Please try again in a few minutes."

def _call_bytez(user_query, chat_history):
    url = f"https://api.bytez.com/models/v2/google/{BYTEZ_MODEL}"
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if chat_history:
        for role, text in chat_history:
            messages.append({"role": "user" if role == "user" else "assistant", "content": text})
    messages.append({"role": "user", "content": user_query})

    headers = {
        "Authorization": f"Key {BYTEZ_API_KEY}",
        "provider-key": GEMINI_API_KEY,
        "Content-Type": "application/json"
    }
    try:
        res = requests.post(url, json={"messages": messages, "stream": False}, headers=headers, timeout=10)
        if res.status_code == 200:
            data = res.json()
            return data.get('output') or data.get('choices', [{}])[0].get('message', {}).get('content')
        return f"Error: Bytez Status {res.status_code}"
    except Exception as e:
        return f"Error: {str(e)}"

def _call_google_direct(user_query, chat_history):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GOOGLE_MODEL}:generateContent?key={GEMINI_API_KEY}"
    
    # Google uses a different message structure (contents/parts)
    contents = []
    # Add history
    if chat_history:
        for role, text in chat_history:
            contents.append({
                "role": "user" if role == "user" else "model",
                "parts": [{"text": text}]
            })
    
    # Add current prompt with system context
    prompt = f"SYSTEM CONTEXT: {SYSTEM_PROMPT}\n\nUSER: {user_query}"
    contents.append({
        "role": "user",
        "parts": [{"text": prompt}]
    })

    try:
        res = requests.post(url, json={"contents": contents}, headers={"Content-Type": "application/json"}, timeout=15)
        res.raise_for_status() # This will trigger the HTTPError block below if status is 4xx or 5xx
        
        data = res.json()
        return data['candidates'][0]['content']['parts'][0]['text']
        
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response else "unknown"
        logger.error(f"Google Direct Error {status}: {e.response.text if e.response else str(e)}")
        if status == 503:
            return "I'm receiving a lot of requests right now and need a quick breath! Please try sending your message again in a few seconds."
        if status == 429:
            return "I've been talking a bit too fast! Please wait a moment before our next message."
        return "I'm having a little trouble connecting to my brain right now. Please try again in a moment."
    except Exception as e:
        logger.error(f"Google Direct Error: {str(e)}")
        return "I'm having a little trouble connecting right now. Please try again in a moment."
