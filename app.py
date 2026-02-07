import streamlit as st
import pandas as pd
import google.generativeai as genai
import random
import json

# --- CONFIGURATION ---
api_key = st.secrets["GENAI_API_KEY"]
sheet_url = st.secrets["SHEET_URL"]

genai.configure(api_key=api_key)
model = genai.GenerativeModel('gemini-2.5-flash')

# --- USER'S PROTEIN BOOSTERS ---
# The app will pick one of these if a meal is low in protein (< 15g)
BOOSTERS = [
    {"name": "2 Scrambled Eggs", "protein": 12},
    {"name": "2 Boiled Eggs", "protein": 12},
    {"name": "50g Raw Paneer", "protein": 9},
    {"name": "Paneer Bhurji (small bowl)", "protein": 12},
    {"name": "Soya Bhurji", "protein": 15},
    {"name": "Soya chunks chilly", "protein": 15}
]

# --- 1. FETCH & ANALYZE (Get Base Protein) ---
@st.cache_data(ttl=600) 
def get_meal_data():
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        st.error(f"Error reading Sheet: {e}")
        return None

    all_meals = []
    col_map = {
        "Breakfast": ["Breakfast"], 
        "Lunch": ["Lunch"], 
        "Snack": ["Snack", "Snacks", "Evening snacks", "Evening Snacks"], 
        "Dinner": ["Dinner"]
    }
    
    found_cols = df.columns.tolist()
    
    for category, possible_names in col_map.items():
        actual_col = next((c for c in possible_names if c in found_cols), None)
        if actual_col:
            items = [x for x in df[actual_col].tolist() if str(x).strip() != ""]
            for item in items:
                all_meals.append({"category": category, "name": item})

    if not all_meals:
        st.error("No meals found in the sheet!")
        return None

    # Ask Gemini for Base Protein
    prompt = f"""
    You are a nutritionist. Analyze this list of Indian meals:
    {json.dumps([m['name'] for m in all_meals])}

    For EACH meal, return a JSON object:
    1. "name": The exact name provided.
    2. "ingredients": List of 3 main ingredients (lowercase).
    3. "protein_g": ESTIMATED Protein in GRAMS (Integer only). 
       (e.g., Poha=4, Dal=7, 2 Eggs=12, Paneer Curry=14).

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

# --- 2. GENERATE WITH "AUTO-BOOST" ---
def generate_schedule(meal_db):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    decks = {}
    for cat in ["Breakfast", "Lunch", "Snack", "Dinner"]:
        items = meal_db.get(cat, [])
        random.shuffle(items)
        decks[cat] = items

    week_plan = []
    STAPLES = {"rice", "roti", "chapati", "curd", "yogurt", "bread", "ghee", "tea", "coffee"}

    for day in days:
        daily_menu = {}
        daily_total_protein = 0
        daily_ingredients = set()

        for cat in ["Breakfast", "Lunch", "Snack", "Dinner"]:
            deck = decks.get(cat, [])
            if not deck:
                deck = meal_db.get(cat, [])[:]
                random.shuffle(deck)
                decks[cat] = deck
            
            # 1. Pick a Meal
            selected = None
            for i, candidate in enumerate(deck):
                cand_ings = set(candidate.get('ingredients', []))
                critical_ings = cand_ings - STAPLES
                if critical_ings.isdisjoint(daily_ingredients):
                    selected = deck.pop(i)
                    break
            
            if not selected and deck:
                selected = deck.pop(0)

            # 2. THE BOOSTER LOGIC
            final_name = selected['name']
            protein_count = selected.get('protein_g', 0)
            
            # If protein is low (< 15g) and it's NOT a light snack (check logic)
            # We usually want to boost Breakfast, Lunch, Dinner. Snacks can stay light.
            if cat != "Snack" and protein_count < 15:
                # Pick a random booster
                booster = random.choice(BOOSTERS)
                
                # Update the name and protein
                final_name = f"{final_name} + {booster['name']}"
                protein_count += booster['protein']
            
            # Save to menu
            daily_menu[cat] = final_name
            daily_ingredients.update(set(selected.get('ingredients', [])) - STAPLES)
            daily_total_protein += protein_count

        week_plan.append({
            "Day": day,
            "Breakfast": daily_menu.get('Breakfast', '-'),
            "Lunch": daily_menu.get('Lunch', '-'),
            "Snack": daily_menu.get('Snack', '-'),
            "Dinner": daily_menu.get('Dinner', '-'),
            "Protein Goal": f"{daily_total_protein}g {'✅' if daily_total_protein >= 60 else '⚠️'}"
        })

    return pd.DataFrame(week_plan)

# --- 3. UI ---
st.set_page_config(page_title="High Protein Planner", page_icon="💪", layout="wide")
st.title("💪 High Protein Meal Planner")
st.caption("Automatically adds Eggs/Paneer/Soya if a meal is low in protein.")

if st.button("Generate Power Plan"):
    st.cache_data.clear()
    with st.spinner("Analyzing macros & Adding boosters..."):
        db = get_meal_data()
        if db:
            df = generate_schedule(db)
            
            # Styling the table to highlight the Goal
            st.dataframe(df, use_container_width=True)
            
            # Download
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Download Plan", csv, "protein_plan.csv", "text/csv")
