import streamlit as st
import pandas as pd
import google.generativeai as genai
import random
import json

# --- CONFIGURATION ---
api_key = st.secrets["GENAI_API_KEY"]
sheet_url = st.secrets["SHEET_URL"]

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-1.5-flash')

# --- 1. INTELLIGENCE ---
@st.cache_data(ttl=600) # Reduced cache to 10 mins so you see updates faster
def get_meal_data():
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        st.error(f"Error reading Sheet. Check URL in secrets. Error: {e}")
        return None

    all_meals = []
    # Flexible column matching (handles "Snacks", "Snack", "Evening Snack")
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
    2. "ingredients": List of 3-4 main ingredients (lowercase). Exclude salt, oil, water.
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

# --- 2. LOGIC (The "Solver") ---
def generate_schedule(meal_db):
    week_plan = []
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # STAPLES: Ingredients allowed to repeat in the same day
    ALLOWED_REPEATS = {"rice", "roti", "chapati", "curd", "yogurt", "bread", "ghee", "oil", "spices"}
    
    for day in days:
        daily_menu = {}
        daily_ingredients = set()
        daily_score = 0
        attempts = 0
        
        while attempts < 100: # Try 100 combinations
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
                    # Get ingredients for this option
                    opt_ings = set(opt.get('ingredients', []))
                    
                    # CHECK: specific repeating ingredients (excluding staples)
                    # We subtract allowed staples from the check
                    critical_ings = opt_ings - ALLOWED_REPEATS
                    
                    # If any critical ingredient is already used today, skip
                    if not critical_ings.isdisjoint(daily_ingredients):
                        continue
                        
                    selected = opt
                    break
                
                if selected:
                    temp_menu[cat] = selected
                    # Track critical ingredients (ignore staples)
                    daily_ingredients.update(set(selected['ingredients']) - ALLOWED_REPEATS)
                    temp_score += protein_map.get(selected['protein'], 1)
                else:
                    # If we can't find a non-repeating meal, just pick a random one
                    # (Better to have a plan with repeats than no plan)
                    if options:
                        selected = random.choice(options)
                        temp_menu[cat] = selected
                        temp_score += protein_map.get(selected['protein'], 1)
            
            # Acceptance Criteria
            if temp_score >= 5: 
                daily_menu = temp_menu
                daily_score = temp_score
                break
            
            attempts += 1
        
        # If still failed after 100 tries, use the last attempted menu
        if not daily_menu:
             daily_menu = temp_menu

        week_plan.append({
            "Day": day,
            "Breakfast": daily_menu.get('Breakfast', {}).get('name', '-'),
            "Lunch": daily_menu.get('Lunch', {}).get('name', '-'),
            "Snack": daily_menu.get('Snack', {}).get('name', '-'),
            "Dinner": daily_menu.get('Dinner', {}).get('name', '-'),
            "Protein Score": daily_score
        })

    return pd.DataFrame(week_plan)

# --- 3. UI ---
st.set_page_config(page_title="Meal Planner", page_icon="🥗")
st.title("🥗 Indian Diet Planner")

if st.button("Generate New Week"):
    st.cache_data.clear() # AUTO-CLEAR CACHE ON CLICK
    with st.spinner("Analyzing Menu..."):
        db = get_meal_data()
        if db:
            schedule = generate_schedule(db)
            st.table(schedule)
        else:
            st.error("Data check failed.")
