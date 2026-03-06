from flask import Flask, request, jsonify, send_file, send_from_directory
from flask_cors import CORS
import requests
import re
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.units import inch
from io import BytesIO
from datetime import datetime
import json
import os
from groq import Groq


GROQ_API_KEY = "" 

GOOGLE_PLACES_API_KEY = ""
api_key = os.getenv("GROQ_API_KEY")


groq_client = Groq(api_key=GROQ_API_KEY) if GROQ_API_KEY != "YOUR_GROQ_API_KEY_HERE" else None



GROQ_MODELS_PRIORITY = [
    "llama-3.3-70b-versatile",  # Most capable, latest Llama 3.3
    "llama3-70b-8192",          # Fast, very capable
    "llama3-8b-8192",           # Fastest, good for quick tasks
    "mixtral-8x7b-32768",       
]

# Default models for different use cases
GROQ_FAST_MODEL = "llama3-70b-8192"      # For chat and quick responses
GROQ_SMART_MODEL = "llama-3.3-70b-versatile"  # For complex tasks like PDF generation

# Cache working model
_working_groq_model = None

def get_groq_response(prompt, model=None, system_prompt=None, temperature=0.7, max_tokens=2048):
    """
    Robust Groq API wrapper with automatic fallback.
    
    Args:
        prompt: The user message/query
        model: Specific model to use (optional)
        system_prompt: System instructions (optional)
        temperature: Creativity (0-2, default 0.7)
        max_tokens: Max response length
    """
    global _working_groq_model
    
    if not groq_client:
        return "⚠️ Groq API key not configured. Please add your API key to app.py"
    
    # Build message list
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": prompt})
    
    # Try specified model first, then fallbacks
    models_to_try = GROQ_MODELS_PRIORITY.copy()
    if model and model in models_to_try:
        models_to_try.remove(model)
        models_to_try.insert(0, model)
    
    # If we have a known working model, prioritize it
    if _working_groq_model and _working_groq_model in models_to_try:
        models_to_try.remove(_working_groq_model)
        models_to_try.insert(0, _working_groq_model)
    
    errors = []
    for model_name in models_to_try:
        try:
            completion = groq_client.chat.completions.create(
                model=model_name,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False
            )
            
            response_text = completion.choices[0].message.content.strip()
            
            if response_text:
                # Cache this working model
                if not _working_groq_model:
                    _working_groq_model = model_name
                    print(f"✅ Groq model selected: {model_name}")
                return response_text
                
        except Exception as e:
            err_str = str(e)
            errors.append(f"{model_name}: {err_str[:100]}")
            
            # Check if it's an API key issue - stop trying
            if "api" in err_str.lower() and ("key" in err_str.lower() or "auth" in err_str.lower()):
                raise Exception(f"Groq API Key Error: {err_str}. Get your free key at https://console.groq.com/keys")
            
            # Rate limit - wait and retry once
            if "rate" in err_str.lower() or "429" in err_str:
                import time
                time.sleep(1)
                try:
                    completion = groq_client.chat.completions.create(
                        model=model_name,
                        messages=messages,
                        temperature=temperature,
                        max_tokens=max_tokens
                    )
                    return completion.choices[0].message.content.strip()
                except:
                    continue
            
            # Model not found - try next
            continue
    
    raise Exception(f"All Groq models failed. Errors: {'; '.join(errors)}")

# =============================================
# FLASK APP SETUP
# =============================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=BASE_DIR, static_url_path="")

CORS(app,
     resources={r"/*": {"origins": "*"}},
     methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
     allow_headers=["Content-Type", "Authorization"],
     supports_credentials=False
)

@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type,Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET,PUT,POST,DELETE,OPTIONS')
    return response

@app.before_request
def handle_preflight():
    if request.method == "OPTIONS":
        from flask import make_response
        response = make_response()
        response.headers.add("Access-Control-Allow-Origin", "*")
        response.headers.add("Access-Control-Allow-Headers", "*")
        response.headers.add("Access-Control-Allow-Methods", "*")
        return response

# Serve frontend
@app.route("/")
def serve_frontend():
    return send_from_directory(BASE_DIR, "index.html")

@app.route("/<path:filename>")
def serve_static(filename):
    api_routes = ["chat", "calories", "generate-workout-pdf", "create-session",
                  "get-coaching", "complete-session", "save-profile", "get-profile",
                  "workout-guidelines", "health"]
    if any(filename.startswith(route) for route in api_routes):
        from flask import abort
        abort(404)
    filepath = os.path.join(BASE_DIR, filename)
    if os.path.exists(filepath) and os.path.isfile(filepath):
        return send_from_directory(BASE_DIR, filename)
    return send_from_directory(BASE_DIR, "index.html")

# Storage
user_profiles = {}
active_sessions = {}

# =============================================
# HELPER FUNCTIONS
# =============================================
PLACE_KEYWORDS = ["nearest", "nearby", "closest", "find", "where is", "show me", "near me", "in the area", "around"]
POI_TYPES = ["gym", "fitness", "restaurant", "hospital", "pharmacy", "cafe", "park", "hotel", "atm", "bank", "school"]

def is_location_query(text):
    t = text.lower()
    if any(k in t for k in PLACE_KEYWORDS) and any(p in t for p in POI_TYPES):
        return True
    if any(p in t for p in POI_TYPES) and ("in " in t or "near " in t or "at " in t or "nearby" in t):
        return True
    return False

def extract_poi_and_location(text):
    t = text.strip()
    poi = None
    location = None
    for p in POI_TYPES:
        if re.search(r'\b' + re.escape(p) + r's?\b', t, re.IGNORECASE):
            poi = p
            break
    m = re.search(r'\b(?:in|near|around|at)\s+([A-Za-z0-9 ,.-]+)', t, re.IGNORECASE)
    if m:
        loc = m.group(1).strip()
        loc = re.sub(r'[\?\!]+$', '', loc).strip()
        location = loc
    return poi, location

def google_places_text_search(query, api_key, limit=6):
    url = "https://maps.googleapis.com/maps/api/place/textsearch/json"
    params = {"query": query, "key": api_key}
    try:
        resp = requests.get(url, params=params, timeout=8)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for r in data.get("results", [])[:limit]:
            loc = r.get("geometry", {}).get("location", {})
            results.append({
                "name": r.get("name"),
                "address": r.get("formatted_address"),
                "rating": r.get("rating"),
                "user_ratings_total": r.get("user_ratings_total"),
                "lat": loc.get("lat"),
                "lng": loc.get("lng"),
                "place_id": r.get("place_id"),
                "types": r.get("types", []),
            })
        return results
    except Exception:
        return []

def nominatim_search(query, limit=6):
    url = "https://nominatim.openstreetmap.org/search"
    params = {"q": query, "format": "json", "addressdetails": 1, "limit": limit}
    headers = {"User-Agent": "FitPulseChatbot/1.0"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=8)
        if resp.status_code != 200:
            return []
        data = resp.json()
        results = []
        for r in data:
            display = r.get("display_name")
            lat = r.get("lat")
            lon = r.get("lon")
            results.append({
                "name": display.split(",")[0] if display else "Place",
                "address": display,
                "lat": float(lat) if lat else None,
                "lng": float(lon) if lon else None,
                "place_id": None,
                "rating": None,
                "user_ratings_total": None,
                "types": []
            })
        return results
    except Exception:
        return []

# =============================================
# WORKOUT GUIDELINES DATABASE  
# =============================================
WORKOUT_GUIDELINES = {
    "bicep_curl": {
        "name": "Bicep Curl",
        "tips": ["Keep elbows close to body", "Don't swing body", "Full range of motion"],
        "dos_donts": {
            "dos": ["Keep elbows pinned", "Full ROM", "Squeeze at top"],
            "donts": ["No swinging", "No momentum", "No partial reps"]
        },
        "demo_video": "https://www.youtube.com/embed/ykJmrZ5v0Oo"
    },
    "squat": {
        "name": "Squat",
        "tips": ["Chest up, core tight", "Push through heels", "Knees over toes"],
        "dos_donts": {
            "dos": ["Full depth", "Knees out", "Chest up"],
            "donts": ["No caving knees", "No rising toes", "No rounding back"]
        },
        "demo_video": "https://www.youtube.com/embed/ultWZbUMPL8"
    },
    "pushup": {
        "name": "Push-up",
        "tips": ["Straight body line", "Lower chest to ground", "45° elbows"],
        "dos_donts": {
            "dos": ["Straight line", "Full depth", "Engage core"],
            "donts": ["No sag", "No flaring", "No half-rep"]
        },
        "demo_video": "https://www.youtube.com/embed/IODxDxX7oi4"
    },
    "shoulder_press": {
        "name": "Shoulder Press",
        "tips": ["Core tight", "Press straight overhead", "Don't arch back"],
        "dos_donts": {
            "dos": ["Core engaged", "Full lockout", "Wrists straight"],
            "donts": ["No arching", "No dropping", "No flaring"]
        },
        "demo_video": "https://www.youtube.com/embed/qEwKCR5JCog"
    },
    "deadlift": {
        "name": "Deadlift",
        "tips": ["Bar close to body", "Neutral spine", "Drive through heels"],
        "dos_donts": {
            "dos": ["Neutral spine", "Bar close", "Hip extension"],
            "donts": ["No rounding", "No jerking", "No looking up"]
        },
        "demo_video": "https://www.youtube.com/embed/op9kVnSso6Q"
    },
    "plank": {
        "name": "Plank",
        "tips": ["Straight line body", "Engage core", "Breathe steadily"],
        "dos_donts": {
            "dos": ["Straight line", "Engage glutes", "Breathe"],
            "donts": ["No sag", "No raised hips", "No holding breath"]
        },
        "demo_video": "https://www.youtube.com/embed/pSHjTRCQxIw"
    },
    "lunges": {
        "name": "Lunges",
        "tips": ["Knee over ankle", "Upright torso", "Push through heel"],
        "dos_donts": {
            "dos": ["Knee alignment", "Upright", "Heel drive"],
            "donts": ["No knee past toes", "No leaning", "No rushing"]
        },
        "demo_video": "https://www.youtube.com/embed/QOVaHwm-Q6U"
    },
    "pull_up": {
        "name": "Pull-up",
        "tips": ["Full hang start", "Chin over bar", "No kipping"],
        "dos_donts": {
            "dos": ["Full hang", "Chin over", "Controlled"],
            "donts": ["No kipping", "No swinging", "No half-rep"]
        },
        "demo_video": "https://www.youtube.com/embed/eGo4IYlbE5g"
    },
    "dips": {
        "name": "Dips",
        "tips": ["Lower to 90°", "Shoulders down", "Lean slightly forward"],
        "dos_donts": {
            "dos": ["90° bend", "Forward lean", "Full extension"],
            "donts": ["No shrugging", "No too deep", "No flaring"]
        },
        "demo_video": "https://www.youtube.com/embed/2z8JmcrW-As"
    },
    "bench_press": {
        "name": "Bench Press",
        "tips": ["Bar to mid-chest", "Feet flat", "Maintain arch"],
        "dos_donts": {
            "dos": ["Mid-chest", "Feet flat", "Stable"],
            "donts": ["No bouncing", "No flaring", "No feet up"]
        },
        "demo_video": "https://www.youtube.com/embed/rT7DgCr-3pg"
    },
    "lateral_raise": {
        "name": "Lateral Raise",
        "tips": ["Raise to shoulder height", "Slight elbow bend", "No swinging"],
        "dos_donts": {
            "dos": ["Lead elbows", "Slight bend", "Controlled"],
            "donts": ["No swinging", "No above shoulder", "No shrugging"]
        },
        "demo_video": "https://www.youtube.com/embed/3VcKaXpzqRo"
    },
    "barbell_row": {
        "name": "Barbell Row",
        "tips": ["Hinge at hips", "Pull to lower chest", "Squeeze blades"],
        "dos_donts": {
            "dos": ["Flat back", "Squeeze blades", "Pull to chest"],
            "donts": ["No rounding", "No momentum", "No looking up"]
        },
        "demo_video": "https://www.youtube.com/embed/FWJR5Ve8bnQ"
    }
}

WORKOUT_TEMPLATES = {
    "push": {
        "name": "Push Day",
        "primary_muscles": ["Chest", "Shoulders", "Triceps"],
        "exercises": [
            {"name": "bench_press", "sets": 4, "reps": 10},
            {"name": "shoulder_press", "sets": 3, "reps": 12},
            {"name": "pushup", "sets": 3, "reps": 15},
            {"name": "dips", "sets": 3, "reps": 10}
        ]
    },
    "pull": {
        "name": "Pull Day",
        "primary_muscles": ["Back", "Biceps"],
        "exercises": [
            {"name": "pull_up", "sets": 4, "reps": 8},
            {"name": "barbell_row", "sets": 4, "reps": 10},
            {"name": "bicep_curl", "sets": 3, "reps": 12},
            {"name": "deadlift", "sets": 3, "reps": 8}
        ]
    },
    "leg": {
        "name": "Leg Day",
        "primary_muscles": ["Quads", "Hamstrings", "Glutes"],
        "exercises": [
            {"name": "squat", "sets": 4, "reps": 12},
            {"name": "deadlift", "sets": 3, "reps": 10},
            {"name": "lunges", "sets": 3, "reps": 12}
        ]
    },
    "upper": {
        "name": "Upper Body",
        "primary_muscles": ["Chest", "Back", "Shoulders", "Arms"],
        "exercises": [
            {"name": "bench_press", "sets": 3, "reps": 10},
            {"name": "barbell_row", "sets": 3, "reps": 10},
            {"name": "shoulder_press", "sets": 3, "reps": 12},
            {"name": "pull_up", "sets": 3, "reps": 8},
            {"name": "bicep_curl", "sets": 3, "reps": 12}
        ]
    },
    "lower": {
        "name": "Lower Body",
        "primary_muscles": ["Quads", "Hamstrings", "Glutes"],
        "exercises": [
            {"name": "squat", "sets": 4, "reps": 12},
            {"name": "deadlift", "sets": 3, "reps": 10},
            {"name": "lunges", "sets": 3, "reps": 12}
        ]
    },
    "core": {
        "name": "Core & Abs",
        "primary_muscles": ["Core", "Abs"],
        "exercises": [
            {"name": "plank", "sets": 3, "reps": 60}
        ]
    }
}

WARMUP_EXERCISES = [
    {"name": "Arm Circles", "duration": 60},
    {"name": "Leg Swings", "duration": 60},
    {"name": "Torso Twists", "duration": 60},
    {"name": "Light Jogging", "duration": 120}
]

COOLDOWN_EXERCISES = [
    {"name": "Chest Stretch", "duration": 60},
    {"name": "Shoulder Stretch", "duration": 60},
    {"name": "Quad Stretch", "duration": 60},
    {"name": "Hamstring Stretch", "duration": 60}
]

# =============================================
# API ENDPOINTS
# =============================================

@app.route("/chat", methods=["POST", "OPTIONS"])
def chat():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    messages = data.get("messages", [])
    image_data = data.get("image", None)
    user_profile = data.get("user_profile", None)

    if not messages and not image_data:
        return jsonify({"reply": "⚠️ No input received"}), 400

    try:
        last = messages[-1].get("content", "") if messages else ""

        # Workout day query
        workout_pattern = r'\b(push|pull|leg|upper|lower|chest|back|arm|shoulder|core|full body)\s+day\b'
        match = re.search(workout_pattern, last, re.IGNORECASE)
        if match:
            day_type = match.group(1).lower()
            workout_plan = generate_daily_workout_plan(day_type, user_profile)
            messages.append({"role": "assistant", "content": workout_plan})
            return jsonify({"reply": workout_plan, "messages": messages})

        # Location query
        if is_location_query(last):
            poi, location = extract_poi_and_location(last)
            query = f"{poi} in {location}" if (poi and location) else last
            places = []
            try:
                places = google_places_text_search(query, GOOGLE_PLACES_API_KEY, limit=8)
            except:
                pass
            if not places:
                try:
                    places = nominatim_search(query, limit=6)
                except:
                    pass
            if not places:
                reply_text = f"Sorry — I couldn't find any results for \"{query}\"."
                return jsonify({"reply": reply_text, "places": [], "messages": messages})

            lines = [f"Here are the top {len(places)} results for \"{query}\":"]
            structured = []
            for i, p in enumerate(places, start=1):
                name = p.get("name") or "Unknown"
                addr = p.get("address") or ""
                rating = p.get("rating")
                total = p.get("user_ratings_total")
                lat = p.get("lat")
                lng = p.get("lng")
                place_id = p.get("place_id")
                if lat and lng:
                    maps_url = f"https://www.google.com/maps/search/?api=1&query={lat},{lng}"
                elif place_id:
                    maps_url = f"https://www.google.com/maps/place/?q=place_id:{place_id}"
                else:
                    maps_url = None
                rating_str = f" — ⭐ {rating} ({total})" if rating else ""
                lines.append(f"{i}. {name} — {addr}{rating_str}")
                structured.append({
                    "name": name, "address": addr, "rating": rating,
                    "user_ratings_total": total, "lat": lat, "lng": lng,
                    "place_id": place_id, "maps_url": maps_url
                })
            reply_text = "\n".join(lines)
            return jsonify({"reply": reply_text, "places": structured, "messages": messages})

        # Regular chat with Groq
        profile_context = ""
        if user_profile:
            profile_context = (
                f"\n\nUser Profile:\n"
                f"- Age: {user_profile.get('age', 'N/A')} years\n"
                f"- Gender: {user_profile.get('gender', 'N/A')}\n"
                f"- Height: {user_profile.get('height', 'N/A')} cm\n"
                f"- Weight: {user_profile.get('weight', 'N/A')} kg\n"
                f"- Goal: {user_profile.get('goal', 'General Fitness')}\n"
                f"Personalize your response accordingly."
            )

        system_prompt = (
            "You are FitBuddy Pro, an expert AI fitness coach. "
            "Provide helpful, accurate fitness advice. "
            "Format responses clearly with bullet points when listing items. "
            "Be encouraging and motivating. Keep responses concise but thorough."
            + profile_context
        )

        # Build conversation
        conversation = ""
        for msg in messages[-10:]:
            role = "User" if msg["role"] == "user" else "Assistant"
            conversation += f"{role}: {msg['content']}\n"
        conversation += "Assistant:"

        # Note: Groq doesn't support image input yet - inform user if image was sent
        if image_data:
            conversation = "The user uploaded an image but Groq doesn't support image analysis yet. Politely inform them and help with their text query instead.\n\n" + conversation

        bot_reply = get_groq_response(
            conversation,
            model=GROQ_FAST_MODEL,
            system_prompt=system_prompt,
            temperature=0.7,
            max_tokens=2048
        )

        messages.append({"role": "assistant", "content": bot_reply})
        return jsonify({"reply": bot_reply, "messages": messages})

    except Exception as e:
        print(f"Chat error: {e}")
        return jsonify({"reply": f"⚠️ Error: {str(e)}"}), 500


def generate_daily_workout_plan(day_type, user_profile):
    workout_plans = {
        "push": {"exercises": ["bench_press", "shoulder_press", "pushup", "dips"], "description": "Push Day - Chest, Shoulders, Triceps"},
        "pull": {"exercises": ["pull_up", "barbell_row", "bicep_curl", "deadlift"], "description": "Pull Day - Back, Biceps"},
        "leg": {"exercises": ["squat", "deadlift", "lunges"], "description": "Leg Day - Quads, Hamstrings, Glutes"},
        "chest": {"exercises": ["bench_press", "pushup", "dips"], "description": "Chest Day"},
        "back": {"exercises": ["pull_up", "barbell_row", "deadlift"], "description": "Back Day"},
        "shoulder": {"exercises": ["shoulder_press", "lateral_raise"], "description": "Shoulder Day"},
        "arm": {"exercises": ["bicep_curl", "dips"], "description": "Arms Day"},
        "core": {"exercises": ["plank"], "description": "Core Day"}
    }

    plan = workout_plans.get(day_type, workout_plans.get("push"))
    response = f"## 🏋️ {plan['description']} Workout Plan\n\n"

    if user_profile:
        response += (
            f"**Personalized for:** {user_profile.get('age')}yo {user_profile.get('gender')}, "
            f"{user_profile.get('height')}cm, {user_profile.get('weight')}kg\n"
            f"**Goal:** {user_profile.get('goal')}\n\n"
        )

    response += "### Today's Exercises:\n\n"
    for idx, exercise_key in enumerate(plan['exercises'], 1):
        exercise = WORKOUT_GUIDELINES.get(exercise_key)
        if exercise:
            response += f"{idx}. **{exercise['name']}**\n"
            response += f"   - Sets: 3-4 | Reps: 8-12\n"
            response += f"   - Rest: 60-90 seconds\n"
            response += f"   - Key Focus: {exercise['tips'][0]}\n\n"

    response += "\n💡 **Tip:** Use the Form Trainer or start a Guided Session!"
    return response


@app.route("/calories", methods=["POST", "OPTIONS"])
def calories():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    food_item = request.json.get("food", "").strip()
    user_profile = request.json.get("user_profile", None)

    if not food_item:
        return jsonify({"reply": "⚠️ Please enter a food item"}), 400

    try:
        profile_context = ""
        if user_profile:
            profile_context = (
                f"\nUser info: {user_profile.get('age')}yo, "
                f"{user_profile.get('weight')}kg, "
                f"Goal: {user_profile.get('goal')}"
            )

        prompt = (
            f"Provide detailed calorie and nutrition information for: {food_item}.\n"
            f"Present as a table with: Food Item | Serving Size | Calories | Protein (g) | Carbs (g) | Fats (g) | Fiber (g)\n"
            f"After the table, add 2-3 nutrition tips.{profile_context}"
        )

        bot_reply = get_groq_response(
            prompt,
            model=GROQ_FAST_MODEL,
            system_prompt="You are a nutrition expert providing accurate calorie and macro information.",
            temperature=0.3,
            max_tokens=1024
        )

        return jsonify({"reply": bot_reply})

    except Exception as e:
        print(f"Calories error: {e}")
        return jsonify({"reply": f"⚠️ Error: {str(e)}"}), 500


@app.route("/generate-workout-pdf", methods=["POST", "OPTIONS"])
def generate_workout_pdf():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    user_profile = data.get("user_profile", {})
    plan_type = data.get("plan_type", "balanced")

    try:
        prompt = (
            f"Create a detailed 7-day workout plan for:\n"
            f"- Age: {user_profile.get('age', 'N/A')} years\n"
            f"- Gender: {user_profile.get('gender', 'N/A')}\n"
            f"- Height: {user_profile.get('height', 'N/A')} cm\n"
            f"- Weight: {user_profile.get('weight', 'N/A')} kg\n"
            f"- Goal: {user_profile.get('goal', 'General Fitness')}\n"
            f"- Focus: {plan_type}\n\n"
            f"For each day:\n"
            f"1. Day name and muscle groups\n"
            f"2. 5-6 exercises with sets, reps, rest\n"
            f"3. One form tip per exercise\n"
            f"Include rest days. Make it professional and realistic."
        )

        plan_text = get_groq_response(
            prompt,
            model=GROQ_SMART_MODEL,
            system_prompt="You are an expert fitness coach creating personalized workout plans.",
            temperature=0.7,
            max_tokens=4096
        )

        # Build PDF
        buffer = BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=letter, topMargin=0.6*inch, bottomMargin=0.6*inch)
        styles = getSampleStyleSheet()

        title_style = ParagraphStyle('CustomTitle', parent=styles['Heading1'], fontSize=22,
                                     textColor=colors.HexColor('#1e40af'), spaceAfter=20, alignment=1, fontName='Helvetica-Bold')
        subtitle_style = ParagraphStyle('Subtitle', parent=styles['Normal'], fontSize=12,
                                        textColor=colors.HexColor('#6b7280'), spaceAfter=20, alignment=1)
        heading_style = ParagraphStyle('DayHeading', parent=styles['Heading2'], fontSize=14,
                                       textColor=colors.HexColor('#2563eb'), spaceAfter=8, spaceBefore=16, fontName='Helvetica-Bold')
        body_style = ParagraphStyle('Body', parent=styles['BodyText'], fontSize=10, leading=15, spaceAfter=4)

        story = []
        story.append(Paragraph("FitPulse Pro", title_style))
        story.append(Paragraph("Your Personalized 7-Day Workout Plan", subtitle_style))
        story.append(Spacer(1, 0.1*inch))

        # Profile table
        profile_data = [
            ['Profile', 'Value'],
            ['Age', f"{user_profile.get('age', 'N/A')} years"],
            ['Gender', str(user_profile.get('gender', 'N/A'))],
            ['Height', f"{user_profile.get('height', 'N/A')} cm"],
            ['Weight', f"{user_profile.get('weight', 'N/A')} kg"],
            ['Goal', str(user_profile.get('goal', 'General Fitness'))],
            ['Plan Type', plan_type.replace('_', ' ').title()],
            ['Generated', datetime.now().strftime('%B %d, %Y')]
        ]

        profile_table = Table(profile_data, colWidths=[2.5*inch, 3.5*inch])
        profile_table.setStyle(TableStyle([
            ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#1e40af')),
            ('TEXTCOLOR', (0,0), (-1,0), colors.white),
            ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
            ('FONTSIZE', (0,0), (-1,0), 12),
            ('ALIGN', (0,0), (-1,-1), 'LEFT'),
            ('PADDING', (0,0), (-1,-1), 8),
            ('BACKGROUND', (0,1), (0,-1), colors.HexColor('#eff6ff')),
            ('FONTNAME', (0,1), (0,-1), 'Helvetica-Bold'),
            ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#cbd5e1')),
        ]))
        story.append(profile_table)
        story.append(Spacer(1, 0.3*inch))
        story.append(Paragraph("Your Weekly Workout Schedule", heading_style))
        story.append(Spacer(1, 0.1*inch))

        # Parse plan
        lines = plan_text.split('\n')
        for line in lines:
            stripped = line.strip()
            if not stripped:
                story.append(Spacer(1, 0.05*inch))
                continue
            clean = stripped.lstrip('#').strip()
            if stripped.startswith('#') or re.match(r'^(Day\s+\d+|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|REST)', clean, re.IGNORECASE):
                story.append(Spacer(1, 0.1*inch))
                story.append(Paragraph(clean, heading_style))
            else:
                clean_line = re.sub(r'\*\*(.*?)\*\*', r'\1', clean)
                clean_line = re.sub(r'\*(.*?)\*', r'\1', clean_line)
                clean_line = re.sub(r'#{1,6}\s*', '', clean_line)
                if clean_line:
                    story.append(Paragraph(clean_line, body_style))

        doc.build(story)
        buffer.seek(0)

        return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                        download_name=f'FitPulse_Plan_{datetime.now().strftime("%Y%m%d")}.pdf')

    except Exception as e:
        print(f"PDF error: {e}")
        return jsonify({"error": str(e)}), 500


@app.route("/create-session", methods=["POST", "OPTIONS"])
def create_session():
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data = request.json
    user_profile = data.get("user_profile", {})
    session_config = data.get("session_config", {})

    workout_type = session_config.get("workout_type", "push")
    include_warmup = session_config.get("include_warmup", True)
    include_cardio = session_config.get("include_cardio", False)
    include_cooldown = session_config.get("include_cooldown", True)

    session_id = datetime.now().strftime("%Y%m%d%H%M%S")
    session = {
        "session_id": session_id,
        "user_profile": user_profile,
        "config": session_config,
        "phases": []
    }

    if include_warmup:
        session["phases"].append({
            "phase": "warmup",
            "title": "🔥 Warm-up",
            "duration": 300,
            "exercises": WARMUP_EXERCISES,
            "coaching_tips": ["Let's warm up!", "Increase blood flow.", "Prepare mentally."]
        })

    template = WORKOUT_TEMPLATES.get(workout_type, WORKOUT_TEMPLATES["push"])
    workout_exercises = []
    for exercise in template["exercises"]:
        key = exercise["name"]
        if key in WORKOUT_GUIDELINES:
            g = WORKOUT_GUIDELINES[key]
            workout_exercises.append({
                "key": key,
                "name": g["name"],
                "sets": exercise["sets"],
                "reps": exercise["reps"],
                "rest_between_sets": 60,
                "duration_per_set": 45,
                "tips": g["tips"][:3],
                "demo_video": g.get("demo_video", "")
            })

    session["phases"].append({
        "phase": "workout",
        "title": f"💪 {template['name']} - Main Workout",
        "target_muscles": template["primary_muscles"],
        "exercises": workout_exercises,
        "coaching_tips": ["Focus on form!", "Breathe properly.", "Stay hydrated."]
    })

    if include_cooldown:
        session["phases"].append({
            "phase": "cooldown",
            "title": "🧘 Cool-down",
            "duration": 300,
            "exercises": COOLDOWN_EXERCISES,
            "coaching_tips": ["Great work!", "Stretch it out.", "Breathe deeply."]
        })

    total_duration = sum(p.get("duration", 0) for p in session["phases"])
    for p in session["phases"]:
        if p["phase"] in ("workout",):
            for ex in p.get("exercises", []):
                total_duration += ex.get("sets", 3) * ex.get("duration_per_set", 45)
                total_duration += max(0, ex.get("sets", 3) - 1) * ex.get("rest_between_sets", 60)

    session["total_duration"] = total_duration
    session["total_duration_formatted"] = f"{max(1, total_duration // 60)} minutes"
    active_sessions[session_id] = session

    return jsonify({"status": "success", "session": session})


@app.route("/get-coaching/<session_id>/<phase>/<exercise_index>", methods=["GET", "OPTIONS"])
def get_coaching(session_id, phase, exercise_index):
    if request.method == "OPTIONS":
        return jsonify({}), 200
    session = active_sessions.get(session_id)
    if not session:
        return jsonify({"phase": phase, "tips": ["Focus!", "Stay hydrated!"], "hydration_reminder": False, "motivation": "💪 Keep going!"})
    phase_data = next((p for p in session["phases"] if p["phase"] == phase), None)
    if not phase_data:
        return jsonify({"phase": phase, "tips": [], "hydration_reminder": False, "motivation": "💪 Keep going!"})
    coaching = {"phase": phase, "tips": phase_data.get("coaching_tips", []), "hydration_reminder": False, "motivation": ""}
    if phase == "warmup":
        coaching["motivation"] = "💪 Warm up those muscles!"
        coaching["hydration_reminder"] = True
    elif phase == "workout":
        idx = int(exercise_index)
        exs = phase_data.get("exercises", [])
        if idx < len(exs):
            ex = exs[idx]
            coaching["exercise_name"] = ex["name"]
            coaching["sets"] = ex["sets"]
            coaching["reps"] = ex["reps"]
            coaching["tips"] = ex.get("tips", [])
            coaching["motivation"] = f"🔥 Time for {ex['name']}! Focus on form!"
            if (idx + 1) % 3 == 0:
                coaching["hydration_reminder"] = True
    elif phase == "cooldown":
        coaching["motivation"] = "🧘 Cool down and stretch."
        coaching["hydration_reminder"] = True
    return jsonify(coaching)


@app.route("/complete-session/<session_id>", methods=["POST", "OPTIONS"])
def complete_session(session_id):
    if request.method == "OPTIONS":
        return jsonify({}), 200
    session = active_sessions.get(session_id)
    if not session:
        return jsonify({"status": "success", "summary": {"session_id": session_id, "total_duration": "N/A",
                        "exercises_completed": 0, "total_reps": 0, "phases_completed": 0,
                        "achievements": ["⭐ Workout completed!"], "message": "Great job!"}})
    data = request.json or {}
    total_reps = data.get("total_reps", 0)
    exercises_completed = data.get("exercises_completed", 0)
    achievements = []
    if total_reps >= 100:
        achievements.append("🔥 100+ reps!")
    if session["config"].get("include_cardio"):
        achievements.append("🏃 Cardio warrior!")
    achievements.append("⭐ Workout completed!")
    summary = {
        "session_id": session_id,
        "completion_time": datetime.now().isoformat(),
        "workout_type": session["config"].get("workout_type", "workout"),
        "total_duration": session.get("total_duration_formatted", "N/A"),
        "exercises_completed": exercises_completed,
        "total_reps": total_reps,
        "phases_completed": len(session["phases"]),
        "achievements": achievements,
        "message": "🎉 Amazing work!"
    }
    if session_id in active_sessions:
        del active_sessions[session_id]
    return jsonify({"status": "success", "summary": summary})


@app.route("/save-profile", methods=["POST", "OPTIONS"])
def save_profile():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    data = request.json
    user_id = data.get("user_id", "default_user")
    user_profiles[user_id] = {
        "age": data.get("age"),
        "gender": data.get("gender"),
        "height": data.get("height"),
        "weight": data.get("weight"),
        "goal": data.get("goal")
    }
    return jsonify({"status": "success", "message": "Profile saved"})


@app.route("/get-profile/<user_id>", methods=["GET", "OPTIONS"])
def get_profile(user_id):
    if request.method == "OPTIONS":
        return jsonify({}), 200
    return jsonify({"profile": user_profiles.get(user_id, None)})


@app.route("/workout-guidelines", methods=["GET", "OPTIONS"])
def get_workout_guidelines():
    if request.method == "OPTIONS":
        return jsonify({}), 200
    return jsonify({"workouts": WORKOUT_GUIDELINES})


@app.route("/workout-guidelines/<workout_type>", methods=["GET", "OPTIONS"])
def get_specific_workout(workout_type):
    if request.method == "OPTIONS":
        return jsonify({}), 200
    workout = WORKOUT_GUIDELINES.get(workout_type.lower())
    if workout:
        return jsonify({"workout": workout})
    return jsonify({"error": "Workout not found"}), 404


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok", "message": "FitPulse backend running with Groq AI + ACPF Cognitive Engine"})


# =============================================
# COGNITIVE MODULES — LAZY INIT
# =============================================
# Engines are loaded only once on first use (saves startup time)
_emotion_engine  = None
_gaze_engine     = None
_breathing_engine= None
_sf_engine       = None
_acpf_instance   = None   # per-session ACPF; reset at session start

import sys
import os
sys.path.insert(0, os.path.join(BASE_DIR, 'cognitive'))

def get_emotion_engine():
    global _emotion_engine
    if _emotion_engine is None:
        try:
            from cognitive.emotion_engine import EmotionEngine
            _emotion_engine = EmotionEngine(
                model_path=os.path.join(BASE_DIR, 'models', 'emotion_model.h5')
            )
        except Exception as e:
            print(f"[ACPF] EmotionEngine init error: {e}")
    return _emotion_engine

def get_gaze_engine():
    global _gaze_engine
    if _gaze_engine is None:
        try:
            from cognitive.gaze_engine import GazeEngine
            _gaze_engine = GazeEngine(
                yolo_model_path=os.path.join(BASE_DIR, 'models', 'yolov8n-pose.pt'),
                cnn_model_path =os.path.join(BASE_DIR, 'models', 'eye_state_cnn_model_finetuned.keras')
            )
        except Exception as e:
            print(f"[ACPF] GazeEngine init error: {e}")
    return _gaze_engine

def get_breathing_engine():
    global _breathing_engine
    if _breathing_engine is None:
        try:
            from cognitive.breathing_engine import BreathingEngine
            _breathing_engine = BreathingEngine(sample_rate_hz=5.0)
        except Exception as e:
            print(f"[ACPF] BreathingEngine init error: {e}")
    return _breathing_engine

def get_sf_engine():
    global _sf_engine
    if _sf_engine is None:
        try:
            from cognitive.stress_fatigue_engine import StressFatigueEngine
            _sf_engine = StressFatigueEngine(smoothing=0.2)
        except Exception as e:
            print(f"[ACPF] StressFatigueEngine init error: {e}")
    return _sf_engine

def get_acpf(exercise_type_str='strength', athlete_name='Athlete', exercise_name='Exercise'):
    global _acpf_instance
    if _acpf_instance is None:
        try:
            from cognitive.acpf_algorithm import ACPFAlgorithm, ExerciseType
            et_map = {
                'strength':    ExerciseType.STRENGTH,
                'cardio':      ExerciseType.CARDIO,
                'balance':     ExerciseType.BALANCE,
                'flexibility': ExerciseType.FLEXIBILITY
            }
            et = et_map.get(exercise_type_str.lower(), ExerciseType.STRENGTH)
            _acpf_instance = ACPFAlgorithm(
                exercise_type=et,
                athlete_name=athlete_name,
                exercise_name=exercise_name
            )
        except Exception as e:
            print(f"[ACPF] ACPFAlgorithm init error: {e}")
    return _acpf_instance

# =============================================
# COGNITIVE API ROUTES
# =============================================

@app.route("/cognitive/process-frame", methods=["POST", "OPTIONS"])
def cognitive_process_frame():
    """
    Main cognitive processing endpoint.
    Called by the browser every ~500ms with a captured video frame.

    Payload (JSON):
    {
        "frame":              "<base64 JPEG>",
        "shoulder_landmarks": {"left_shoulder_y": 0.45, "right_shoulder_y": 0.46},
        "physical": {
            "form_score": 82,
            "range_of_motion": 75,
            "movement_smoothness": 80,
            "rep_count": 5,
            "angle": 145.2
        },
        "session_duration": 120,
        "exercise_type": "strength"
    }
    """
    if request.method == "OPTIONS":
        return jsonify({}), 200

    data       = request.json or {}
    b64_frame  = data.get("frame", "")
    shoulders  = data.get("shoulder_landmarks", {})
    phys_data  = data.get("physical", {})
    session_dur= float(data.get("session_duration", 0))
    ex_type    = data.get("exercise_type", "strength")

    result = {
        "emotion":    {},
        "gaze":       {},
        "breathing":  {},
        "sf":         {},
        "acpf":       {}
    }

    # ── 1. EMOTION ─────────────────────────────────────────────────────────
    try:
        ee = get_emotion_engine()
        if ee and b64_frame:
            result["emotion"] = ee.process_frame_b64(b64_frame)
    except Exception as e:
        result["emotion"] = {"error": str(e), "emotion": "Neutral",
                             "fitness_status": "📷 Detecting...", "score": 50}

    # ── 2. GAZE / FOCUS ────────────────────────────────────────────────────
    try:
        ge = get_gaze_engine()
        if ge and b64_frame:
            result["gaze"] = ge.process_frame_b64(b64_frame)
    except Exception as e:
        result["gaze"] = {"error": str(e), "focus_score": 50,
                          "left_eye": "OPEN", "right_eye": "OPEN"}

    # ── 3. BREATHING ───────────────────────────────────────────────────────
    try:
        be = get_breathing_engine()
        if be and shoulders:
            be.add_landmarks_from_dict(shoulders)
        if be:
            result["breathing"] = be.compute_bpm()
    except Exception as e:
        result["breathing"] = {"error": str(e), "bpm": 0, "pattern": "calibrating",
                               "status_message": "Calibrating..."}

    # ── 4. STRESS + FATIGUE + MOTIVATION ──────────────────────────────────
    try:
        sfe = get_sf_engine()
        if sfe:
            em_score  = result["emotion"].get("score", 50)
            em_energy = result["emotion"].get("energy", "medium")
            focus     = result["gaze"].get("focus_score", 50)
            bpm       = result["breathing"].get("bpm", 15)
            form      = float(phys_data.get("form_score", 70))
            reps      = int(phys_data.get("rep_count", 0))
            is_drowsy = result["gaze"].get("is_drowsy", False)

            result["sf"] = sfe.compute(
                emotion_score=em_score, emotion_energy=em_energy,
                focus_score=focus, bpm=bpm, form_score=form,
                rep_count=reps, session_duration=session_dur,
                is_drowsy=is_drowsy
            )
    except Exception as e:
        result["sf"] = {"error": str(e), "stress": 30, "fatigue": 20, "motivation": 60}

    # ── 5. ACPF FUSION ─────────────────────────────────────────────────────
    try:
        acpf = get_acpf(exercise_type_str=ex_type)
        if acpf:
            from cognitive.acpf_algorithm import PhysicalState, CognitiveState
            physical = PhysicalState(
                form_score          = float(phys_data.get("form_score", 70)),
                range_of_motion     = float(phys_data.get("range_of_motion", 70)),
                movement_smoothness = float(phys_data.get("movement_smoothness", 70)),
                rep_count           = int(phys_data.get("rep_count", 0)),
                angle               = float(phys_data.get("angle", 0))
            )
            cognitive = CognitiveState(
                focus_score    = result["gaze"].get("focus_score", 50),
                stress_index   = result["sf"].get("stress", 30),
                fatigue_level  = result["sf"].get("fatigue", 20),
                breathing_rate = result["breathing"].get("bpm", 15) or 15,
                emotion        = result["emotion"].get("emotion", "Neutral"),
                emotion_score  = result["emotion"].get("score", 50),
                motivation     = result["sf"].get("motivation", 60)
            )
            fused = acpf.fuse(physical, cognitive)
            result["acpf"] = fused.to_dict()
            result["acpf"]["trend"] = acpf.get_wellness_trend()
    except Exception as e:
        result["acpf"] = {"error": str(e), "overall_wellness": 60,
                          "acpf_score": 60, "risk_level": "SAFE",
                          "recommended_action": "Keep going!"}

    return jsonify({"status": "ok", "data": result})


@app.route("/cognitive/start-session", methods=["POST", "OPTIONS"])
def cognitive_start_session():
    """
    Reset all cognitive engines at the start of a new workout session.

    Payload: { "exercise_type": "strength", "athlete_name": "John", "exercise_name": "Squat" }
    """
    global _acpf_instance, _breathing_engine, _sf_engine

    if request.method == "OPTIONS":
        return jsonify({}), 200

    data           = request.json or {}
    exercise_type  = data.get("exercise_type", "strength")
    athlete_name   = data.get("athlete_name", "Athlete")
    exercise_name  = data.get("exercise_name", "Exercise")

    # Reset breathing
    try:
        be = get_breathing_engine()
        if be: be.reset()
    except: pass

    # Reset stress/fatigue
    try:
        sfe = get_sf_engine()
        if sfe: sfe.reset()
    except: pass

    # Reset gaze
    try:
        ge = get_gaze_engine()
        if ge: ge.reset()
    except: pass

    # Create fresh ACPF instance for this session
    _acpf_instance = None
    get_acpf(exercise_type_str=exercise_type,
             athlete_name=athlete_name,
             exercise_name=exercise_name)

    return jsonify({
        "status":  "ok",
        "message": f"Cognitive session started: {exercise_name} ({exercise_type})"
    })


@app.route("/cognitive/end-session", methods=["POST", "OPTIONS"])
def cognitive_end_session():
    """
    End the cognitive session — returns full summary for dashboard.
    """
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        acpf = get_acpf()
        if not acpf:
            return jsonify({"status": "error", "message": "No active ACPF session"})

        summary = acpf.get_session_summary()
        return jsonify({"status": "ok", "summary": summary})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})


@app.route("/cognitive/download-dashboard", methods=["POST", "OPTIONS"])
def download_dashboard():
    """
    Generate and return the interactive HTML dashboard for the completed session.
    """
    if request.method == "OPTIONS":
        return jsonify({}), 200

    try:
        acpf = get_acpf()
        if not acpf:
            return jsonify({"status": "error", "message": "No ACPF session data found."}), 400

        html_content = acpf.generate_dashboard()

        from flask import Response
        athlete_name  = acpf.athlete_name.replace(' ', '_')
        session_id    = acpf.session_id
        filename      = f"ACPF_Dashboard_{athlete_name}_{session_id}.html"

        return Response(
            html_content,
            mimetype="text/html",
            headers={"Content-Disposition": f"attachment; filename={filename}"}
        )

    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/cognitive/status", methods=["GET"])
def cognitive_status():
    """Check which cognitive engines are ready."""
    ee  = get_emotion_engine()
    ge  = get_gaze_engine()
    be  = get_breathing_engine()
    sfe = get_sf_engine()
    a   = get_acpf()

    return jsonify({
        "emotion_engine":   {"ready": ee is not None and ee.is_ready()},
        "gaze_engine":      {"ready": ge is not None and ge.is_ready()},
        "breathing_engine": {"ready": be is not None},
        "sf_engine":        {"ready": sfe is not None},
        "acpf":             {"ready": a is not None}
    })


# =============================================
# RUN
# =============================================
if __name__ == "__main__":
    print("\n" + "="*60)
    print("  FitPulse Pro - Starting with Groq AI")
    print("="*60)
    print()

    if not groq_client:
        print("⚠️  WARNING: Groq API key not set!")
        print("   Get your FREE key at: https://console.groq.com/keys")
        print("   Then paste it in app.py at line 23")
    else:
        print("Testing Groq API connection...")
        try:
            test = groq_client.chat.completions.create(
                model="llama3-70b-8192",
                messages=[{"role": "user", "content": "Hi"}],
                max_tokens=10
            )
            print(f"✅ Groq AI ready: {test.model}")
        except Exception as e:
            print(f"❌ Groq error: {e}")
            print("   Check your API key at https://console.groq.com/keys")

    print()
    print("  Server: http://localhost:5000")
    print("  Open that URL in your browser!")
    print("="*60 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000, use_reloader=False)
