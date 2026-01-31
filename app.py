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

# --- 1. GET DATA & CALCULATE PROTEIN (GRAMS) ---
@st.cache_data(ttl=600) 
def get_meal_data():
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        st.error(f"Error reading Sheet: {e}")
        return None

    all_meals = []
    # Smart column mapping to catch "Snack" vs "Snacks"
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
            # Drop empty rows
            items = [x for x in df[actual_col].tolist() if str(x).strip() != ""]
            for item in items:
                all_meals.append({"category": category, "name": item})

    if not all_meals:
        st.error("No meals found in the sheet!")
        return None

    # Prompt Gemini for specific grams
    prompt = f"""
    You are a nutritionist. Analyze this list of Indian meals:
    {json.dumps([m['name'] for m in all_meals])}

    For EACH meal, return a JSON object:
    1. "name": The exact name provided.
    2. "ingredients": List of 3 main ingredients (lowercase). 
       (e.g., "paneer", "rice", "wheat", "chickpeas").
    3. "protein_g": ESTIMATED Protein in GRAMS (Integer only). 
       (e.g., Dal=7, 2 Eggs=12, Paneer Curry=15, Snack=3).

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

# --- 2. GENERATE BALANCED SCHEDULE ---
def generate_schedule(meal_db):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # "Deck of Cards" System: 
    # Create a pile for each category. Shuffle it. Deal one card per day.
    # This guarantees we don't repeat a main dish until we've eaten everything else.
    decks = {}
    for cat in ["Breakfast", "Lunch", "Snack", "Dinner"]:
        items = meal_db.get(cat, [])
        random.shuffle(items)
        decks[cat] = items

    week_plan = []
    
    # Allowed Repeats (Staples)
    STAPLES = {"rice", "roti", "chapati", "curd", "yogurt", "bread", "ghee", "tea", "coffee", "milk"}

    for day in days:
        daily_menu = {}
        daily_grams = 0
        daily_ingredients = set()

        for cat in ["Breakfast", "Lunch", "Snack", "Dinner"]:
            deck = decks.get(cat, [])
            
            # If deck is empty (e.g. you have 5 meals but need 7 days), refill & reshuffle
            if not deck:
                deck = meal_db.get(cat, [])[:]
                random.shuffle(deck)
                decks[cat] = deck
            
            selected = None
            
            # Try to pick a card that doesn't clash with TODAY's other meals
            for i, candidate in enumerate(deck):
                cand_ings = set(candidate.get('ingredients', []))
                critical_ings = cand_ings - STAPLES
                
                if critical_ings.isdisjoint(daily_ingredients):
                    selected = deck.pop(i) # Use it and remove from deck
                    break
            
            # If everything conflicts (rare), just take the top one
            if not selected and deck:
                selected = deck.pop(0)

            if selected:
                daily_menu[cat] = selected
                daily_ingredients.update(set(selected.get('ingredients', [])) - STAPLES)
                daily_grams += selected.get('protein_g', 0)

        week_plan.append({
            "Day": day,
            "Breakfast": daily_menu.get('Breakfast', {}).get('name', ''),
            "Lunch": daily_menu.get('Lunch', {}).get('name', ''),
            "Snack": daily_menu.get('Snack', {}).get('name', ''),
            "Dinner": daily_menu.get('Dinner', {}).get('name', ''),
            "Total Protein (g)": daily_grams
        })

    return pd.DataFrame(week_plan)

# --- 3. UI ---
st.set_page_config(page_title="Meal Planner", page_icon="🥗", layout="centered")
st.title("🥗 Weekly Meal Planner")

if st.button("Generate New Menu"):
    st.cache_data.clear() # Clear cache to fetch fresh data
    with st.spinner("Calculating macros & Shuffling menu..."):
        db = get_meal_data()
        if db:
            df = generate_schedule(db)
            st.success("Menu Generated!")
            
            # Show the table
            st.table(df)
            
            # Create a CSV for download
            csv = df.to_csv(index=False).encode('utf-8')
            
            st.download_button(
                label="📥 Download Plan (CSV)",
                data=csv,
                file_name="my_weekly_meal_plan.csv",
                mime="text/csv",
                key='download-csv'
            )
