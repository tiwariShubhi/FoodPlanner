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

# --- 1. INTELLIGENCE (Get Grams & Specific Ingredients) ---
@st.cache_data(ttl=600) 
def get_meal_data():
    try:
        df = pd.read_csv(sheet_url)
    except Exception as e:
        st.error(f"Error reading Sheet: {e}")
        return None

    all_meals = []
    # Smart column mapping
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
            items = df[actual_col].dropna().tolist()
            for item in items:
                all_meals.append({"category": category, "name": item})

    if not all_meals:
        st.error("No meals found!")
        return None

    # Prompt requesting Grams
    prompt = f"""
    You are a nutritionist. Analyze this list of Indian meals:
    {json.dumps([m['name'] for m in all_meals])}

    For EACH meal, return a JSON object:
    1. "name": The exact name provided.
    2. "ingredients": List of 3 main ingredients (lowercase, specific). 
       Example: Use "moong dal" instead of just "dal". Use "paneer", "rice", "wheat".
    3. "protein_g": Estimated protein content in GRAMS (integer only). 
       (e.g., A bowl of Dal = 7, 2 Eggs = 12, Paneer Curry = 15).

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

# --- 2. LOGIC (Deck of Cards System) ---
def generate_schedule(meal_db):
    days = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    # "Deck of Cards" approach: 
    # We create a shuffled list for each category. We pop items off one by one.
    # This guarantees NO repeats until all items have been used once.
    decks = {}
    for cat in ["Breakfast", "Lunch", "Snack", "Dinner"]:
        items = meal_db.get(cat, [])
        random.shuffle(items)
        decks[cat] = items

    week_plan = []
    
    # Staples that are totally fine to repeat every day
    STAPLES = {"rice", "roti", "chapati", "curd", "yogurt", "bread", "ghee", "tea", "coffee", "milk"}

    for day in days:
        daily_menu = {}
        daily_grams = 0
        daily_ingredients = set()

        for cat in ["Breakfast", "Lunch", "Snack", "Dinner"]:
            deck = decks.get(cat, [])
            
            # If we ran out of meals in the deck (e.g. 5 options for 7 days), 
            # we refill it with the original list and reshuffle.
            if not deck:
                deck = meal_db.get(cat, [])[:] # copy original
                random.shuffle(deck)
                decks[cat] = deck
            
            # Try to pick a meal from the deck that doesn't clash with TODAY's lunch/dinner
            # We peek at the top cards
            selected = None
            
            for i, candidate in enumerate(deck):
                # Check variety within the day
                cand_ings = set(candidate.get('ingredients', []))
                critical_ings = cand_ings - STAPLES
                
                if critical_ings.isdisjoint(daily_ingredients):
                    selected = deck.pop(i) # Remove it from the deck so it won't repeat this week
                    break
            
            # If all cards clash (rare), just take the top card anyway
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
            "Protein (g)": daily_grams
        })

    return pd.DataFrame(week_plan)

# --- 3. UI (Editable) ---
st.set_page_config(page_title="Meal Planner", page_icon="🥗", layout="wide")
st.title("🥗 Interactive Weekly Planner")
st.caption("Click any cell to edit. The 'Protein' total updates when you generate.")

# Initialize session state to hold the data
if 'meal_plan' not in st.session_state:
    st.session_state.meal_plan = None

if st.button("Generate New Menu"):
    st.cache_data.clear()
    with st.spinner("Calculating macros & Shuffling deck..."):
        db = get_meal_data()
        if db:
            st.session_state.meal_plan = generate_schedule(db)

# Display Editable Table if data exists
if st.session_state.meal_plan is not None:
    # 1. Allow User to Edit
    edited_df = st.data_editor(
        st.session_state.meal_plan, 
        num_rows="dynamic",
        use_container_width=True,
        height=300
    )

    # 2. Download Button
    csv = edited_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        label="📥 Download Plan as CSV",
        data=csv,
        file_name="my_weekly_meal_plan.csv",
        mime="text/csv",
    )
    
    # 3. Stats
    avg_protein = edited_df["Protein (g)"].mean()
    st.metric("Average Daily Protein", f"{avg_protein:.1f} g")

else:
    st.info("Click 'Generate New Menu' to start.")
