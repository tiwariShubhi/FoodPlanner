import streamlit as st
import pandas as pd
import random
from io import BytesIO

# --- CONFIG ---
st.set_page_config(page_title="Aahaar Meal Planner", layout="wide")

# --- STYLING ---
st.markdown("""
    <style>
    .stHeader { background-color: #f0f2f6; padding: 20px; border-radius: 10px; }
    .meal-card { padding: 15px; border-left: 5px solid #ff4b4b; background: white; margin-bottom: 10px; }
    </style>
    """, unsafe_allow_html=True)

# --- DATA LOADING ---
# Ensure your sheet is shared as "Anyone with the link can view"
SHEET_ID = "1tH9_wN6g1Di5N_XQ1CUDMuIlmr5wU7NfjdiyjBxoQn8"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

@st.cache_data(ttl=300)
def load_meal_db():
    try:
        df = pd.read_csv(SHEET_URL)
        # Clean column names
        df.columns = [c.strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error fetching sheet: {e}")
        return None

def get_weekly_plan(df):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    slots = ["Breakfast", "Lunch", "Snack", "Dinner"]
    
    # Identify Protein columns automatically (e.g., "Breakfast Protein" or "Lunch Protein")
    def get_col(slot, type="Meal"):
        if type == "Meal":
            return slot # Assumes column is exactly "Breakfast"
        return f"{slot} Protein" # Assumes column is "Breakfast Protein"

    plan_data = []

    for day in days:
        daily_plan = {"Day": day}
        used_proteins_today = set()
        
        for slot in slots:
            meal_col = get_col(slot, "Meal")
            prot_col = get_col(slot, "Protein")
            
            if meal_col not in df.columns or prot_col not in df.columns:
                daily_plan[slot] = "Check Sheet Columns"
                continue

            # Get valid options (not empty)
            options = df[[meal_col, prot_col]].dropna()
            
            # Filter options to avoid repeated proteins (Egg, Paneer, Soya)
            # We only filter if the protein is one of your "Major" ones
            major_proteins = ['egg', 'paneer', 'soya', 'dal + paneer', 'dal']
            
            diverse_options = options[
                ~options[prot_col].str.lower().isin(used_proteins_today) | 
                ~options[prot_col].str.lower().isin(major_proteins)
            ]

            if not diverse_options.empty:
                selection = diverse_options.sample(n=1).iloc[0]
            else:
                # Fallback if we run out of unique options
                selection = options.sample(n=1).iloc[0]

            daily_plan[slot] = selection[meal_col]
            
            # Track protein source to prevent same-day repeats
            prot_val = str(selection[prot_col]).lower()
            if any(p in prot_val for p in major_proteins):
                used_proteins_today.add(prot_val)
        
        plan_data.append(daily_plan)
    
    return pd.DataFrame(plan_data)

# --- UI ---
st.title("🍲 Aahaar: Power Meal Planner")
st.write("Generating high-protein weekly schedules with zero protein repetition per day.")

db = load_meal_db()

if db is not None:
    # Sidebar Info
    with st.sidebar:
        st.header("Database Info")
        st.success("Sheet Connected!")
        st.write("Detected Columns:", list(db.columns))
        st.info("Ensure you have columns for: Breakfast, Breakfast Protein, Lunch, Lunch Protein, etc.")

    # Main Action
    if st.button("Generate Full Week Plan", type="primary"):
        with st.spinner("Optimizing variety..."):
            weekly_df = get_weekly_plan(db)
            st.session_state['active_plan'] = weekly_df

    # Display and Download
    if 'active_plan' in st.session_state:
        current_plan = st.session_state['active_plan']
        
        st.subheader("Your 7-Day Plan")
        st.dataframe(current_plan, use_container_width=True, hide_index=True)

        # Download Buttons
        col1, col2 = st.columns(2)
        
        # CSV
        csv = current_plan.to_csv(index=False).encode('utf-8')
        col1.download_button("Download CSV", data=csv, file_name="meal_
