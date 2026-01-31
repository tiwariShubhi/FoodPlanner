import streamlit as st
import pandas as pd
import google.generativeai as genai
import random
import json

# --- 1. SETUP & CONFIGURATION ---

# Access secrets securely
# We will set these up in the Streamlit dashboard later
api_key = st.secrets["GENAI_API_KEY"]
#sheet_id = st.secrets["SHEET_ID"]

# Construct the CSV export URL
#sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"
sheet_url = st.secrets["SHEET_URL"]
# Configure Gemini
genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 2. INTELLIGENCE (The "Brain") ---

@st.cache_data(ttl=3600) # Cache data for 1 hour to save API calls
def get_meal_data():
    """Fetches data from Google Sheets and enriches it with Gemini."""
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        st.error(f"Error reading Sheet: {e}")
        return None

    # Prepare list for Gemini
    all_meals = []
    for category in ["Breakfast", "Lunch", "Snack", "Dinner"]:
        if category in df.columns:
            # Get only non-empty cells
            items = df[category].dropna().tolist()
            for item in items:
                all_meals.append({"category": category, "name": item})

    if not all_meals:
        st.warning("Your Google Sheet appears to be empty!")
        return None

    # Ask Gemini to classify them
    prompt = f"""
    You are a nutritionist. Analyze this list of meals:
    {json.dumps([m['name'] for m in all_meals])}

    For EACH meal, return a JSON object with:
    1. "name": The exact name provided.
    2. "ingredients": List of 3 main ingredients (lowercase, e.g. ["rice", "lentils", "potato"]).
    3. "protein": "High" (if >15g), "Medium" (5-15g), or "Low" (<5g).

    Output strictly a JSON list. No markdown.
    """

    try:
        response = model.generate_content(prompt)
        cleaned_text = response.text.replace("```json", "").replace("```", "").strip()
        enriched_data = json.loads(cleaned_text)

        # Re-organize into a dictionary by category
        final_db = {"Breakfast": [], "Lunch": [], "Snack": [], "Dinner": []}
        
        # We need to map the enriched data back to their categories
        # Since names are unique, we map name -> category from our original list
        name_to_cat = {m['name']: m['category'] for m in all_meals}

        for item in enriched_data:
            cat = name_to_cat.get(item['name'])
            if cat:
                final_db[cat].append(item)
                
        return final_db

    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- 3. LOGIC (The "Solver") ---

def generate_schedule(meal_db):
    week_plan = []
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # Track usage to avoid repetition across the whole week if possible
    # For now, we just track yesterday to prevent back-to-back repeats
    
    prev_day_ingredients = set()
    
    for day in days:
        daily_menu = {}
        daily_ingredients = set()
        daily_score = 0
        attempts = 0
        
        # Try 20 times to find a valid combination for this day
        while attempts < 20:
            temp_menu = {}
            temp_ingredients = set()
            temp_score = 0
            valid = True
            
            protein_map = {"High": 3, "Medium": 2, "Low": 1}

            for cat in ["Breakfast", "Lunch", "Snack", "Dinner"]:
                options = meal_db.get(cat, [])
                random.shuffle(options)
                
                selected = None
                for opt in options:
                    ing = set(opt['ingredients'])
                    
                    # Constraint 1: Don't repeat ingredients TODAY
                    if not ing.isdisjoint(temp_ingredients):
                        continue
                    # Constraint 2: Don't repeat ingredients from YESTERDAY
                    if not ing.isdisjoint(prev_day_ingredients):
                        continue
                        
                    selected = opt
                    break
                
                if selected:
                    temp_menu[cat] = selected
                    temp_ingredients.update(selected['ingredients'])
                    temp_score += protein_map.get(selected['protein'], 1)
                else:
                    valid = False
                    break
            
            # Constraint 3: Minimum Protein Score (e.g., 7 points)
            if valid and temp_score >= 7:
                daily_menu = temp_menu
                daily_ingredients = temp_ingredients
                daily_score = temp_score
                break # Success!
            
            attempts += 1
        
        if daily_menu:
            week_plan.append({
                "Day": day,
                "Breakfast": daily_menu['Breakfast']['name'],
                "Lunch": daily_menu['Lunch']['name'],
                "Snack": daily_menu['Snack']['name'],
                "Dinner": daily_menu['Dinner']['name'],
                "Protein Level": "🔥 High" if daily_score > 8 else "✅ Good"
            })
            prev_day_ingredients = daily_ingredients
        else:
            week_plan.append({"Day": day, "Error": "Could not balance. Add more meals!"})

    return pd.DataFrame(week_plan)

# --- 4. UI (The "App") ---

st.set_page_config(page_title="Weekly Meal Planner", page_icon="🥗")
st.title("🥗 Smart Weekly Meal Planner")

if st.button("Generate New Week"):
    with st.spinner("Reading your Google Sheet & Consulting AI..."):
        db = get_meal_data()
        if db:
            schedule = generate_schedule(db)
            st.table(schedule)
            st.success("Plan ready! Edit your Google Sheet to add more options.")
