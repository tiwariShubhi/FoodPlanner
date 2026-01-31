import streamlit as st
import pandas as pd
import google.generativeai as genai
import random
import json

# --- CONFIGURATION ---
# 1. Fetch secrets
api_key = st.secrets["GENAI_API_KEY"]
sheet_url = st.secrets["SHEET_URL"]

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 1. THE BRAIN (Fetch & Analyze) ---
@st.cache_data(ttl=600) # Cache for 10 mins
def get_meal_data():
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        st.error(f"Error reading Sheet. Check URL in secrets. Error: {e}")
        return None

    all_meals = []
    
    # SMART COLUMN MAPPING
    # This checks for "Snack", "Snacks", "Evening snacks" automatically
    col_map = {
        "Breakfast": ["Breakfast"], 
        "Lunch": ["Lunch"], 
        "Snack": ["Snack", "Snacks", "Evening snacks", "Evening Snacks"], 
        "Dinner": ["Dinner"]
    }
    
    found_cols = df.columns.tolist()
    
    for category, possible_names in col_map.items():
        # Find which column name actually exists in the sheet
        actual_col = next((c for c in possible_names if c in found_cols), None)
        if actual_col:
            items = df[actual_col].dropna().tolist()
            for item in items:
                all_meals.append({"category": category, "name": item})

    if not all_meals:
        st.error("Could not find columns! Check headers.")
        return None

    # Ask Gemini to classify
    prompt = f"""
    You are a nutritionist. Analyze this list of Indian meals:
    {json.dumps([m['name'] for m in all_meals])}

    For EACH meal, return a JSON object:
    1. "name": The exact name provided.
    2. "ingredients": List of 3-4 main ingredients (lowercase). Exclude salt, oil, water, spices.
    3. "protein": "High" (if >12g like Dal, Paneer, Eggs, Soya), "Medium" (5-12g), "Low" (<5g).

    Return ONLY a valid JSON list.
    """

    try:
        response = model.generate_content(prompt)
        text = response.text.replace("```json", "").replace("```", "").strip()
        enriched_data = json.loads(text)
        
        final_db = {"Breakfast": [], "Lunch": [], "Snack": [], "Dinner": []}
        name_to_cat = {m['name']: m['category'] for m in all_meals}

        for item in enriched_data:
            cat = name_to_cat.get(item['name'])
            if cat:
                final_db[cat].append(item)
        return final_db

    except Exception as e:
        st.error(f"AI Error: {e}")
        return None

# --- 2. THE SOLVER (With Indian Context) ---
def generate_schedule(meal_db):
    week_plan = []
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # STAPLES: These are allowed to repeat every day
    STAPLES = {"rice", "roti", "chapati", "curd", "yogurt", "bread", "ghee", "coffee", "tea"}
    
    # To track variety across the week (prevent eating Chole twice in a row)
    history_ingredients = set()

    for day in days:
        daily_menu = {}
        daily_ingredients = set() # Track what we eat TODAY
        daily_score = 0
        attempts = 0
        
        # Try 50 combinations to build a balanced day
        while attempts < 50:
            temp_menu = {}
            temp_ing = set()
            temp_score = 0
            valid = True
            
            protein_map = {"High": 3, "Medium": 2, "Low": 1}

            for cat in ["Breakfast", "Lunch", "Snack", "Dinner"]:
                options = meal_db.get(cat, [])
                if not options: continue
                
                random.shuffle(options)
                
                selected = None
                for opt in options:
                    # Get ingredients
                    opt_ings = set(opt.get('ingredients', []))
                    
                    # FILTER: Ignore staples when checking for repetition
                    # We care if 'Paneer' repeats, not if 'Roti' repeats.
                    critical_ings = opt_ings - STAPLES
                    
                    # Rule 1: Variety WITHIN the day (e.g., Don't have Paneer for Lunch AND Dinner)
                    if not critical_ings.isdisjoint(temp_ing):
                        continue
                        
                    # Rule 2: Variety ACROSS the week (e.g., Don't have Rajma on Mon AND Tue)
                    # We allow a little overlap (len check) but mostly try to avoid it
                    if not critical_ings.isdisjoint(history_ingredients):
                         # If it's a "High" protein item, we are stricter about repetition
                         if opt['protein'] == 'High':
                             continue
                        
                    selected = opt
                    break
                
                # If strict rules failed, just pick ANY random meal 
                # (Better to have a repeated meal than no meal at all)
                if not selected and options:
                    selected = random.choice(options)

                if selected:
                    temp_menu[cat] = selected
                    # Add non-staples to our tracking lists
                    temp_ing.update(set(selected['ingredients']) - STAPLES)
                    temp_score += protein_map.get(selected['protein'], 1)
            
            # Acceptance: Is protein decent? (Score > 5)
            if temp_score >= 5: 
                daily_menu = temp_menu
                daily_ingredients = temp_ing
                daily_score = temp_score
                break
            
            attempts += 1
        
        # Fallback: If logic failed 50 times, take the last attempt
        if not daily_menu:
             daily_menu = temp_menu
             daily_score = temp_score

        # Update History: We only "remember" today's main ingredients for tomorrow
        history_ingredients = daily_ingredients

        week_plan.append({
            "Day": day,
            "Breakfast": daily_menu.get('Breakfast', {}).get('name', '-'),
            "Lunch": daily_menu.get('Lunch', {}).get('name', '-'),
            "Snack": daily_menu.get('Snack', {}).get('name', '-'),
            "Dinner": daily_menu.get('Dinner', {}).get('name', '-'),
            "Protein Level": "🔥 High" if daily_score > 7 else "✅ Good"
        })

    return pd.DataFrame(week_plan)

# --- 3. UI ---
st.set_page_config(page_title="Indian Meal Planner", page_icon="🥗")
st.title("🥗 Indian Diet Planner")

if st.button("Generate New Week"):
    st.cache_data.clear() # Force reload from Google Sheets
    with st.spinner("Analyzing your Menu..."):
        db = get_meal_data()
        if db:
            schedule = generate_schedule(db)
            st.table(schedule)
        else:
            st.error("Something went wrong. Check your Sheet.")
