import streamlit as st
import pandas as pd
import random
from io import BytesIO

# --- CONFIG ---
st.set_page_config(page_title="Aahaar Meal Planner", layout="wide")

SHEET_ID = "1tH9_wN6g1Di5N_XQ1CUDMuIlmr5wU7NfjdiyjBxoQn8"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

@st.cache_data(ttl=300)
def load_meal_db():
    try:
        df = pd.read_csv(SHEET_URL)
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error fetching sheet: {e}")
        return None

def find_protein(meal_name, protein_val):
    text = f"{str(meal_name)} {str(protein_val)}".lower()
    if 'egg' in text: return 'egg'
    if 'paneer' in text: return 'paneer'
    if 'soya' in text: return 'soya'
    if 'dal' in text: return 'dal'
    return 'other'

def get_weekly_plan(df):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    slots = ["Breakfast", "Lunch", "Snack", "Dinner"]
    
    # Column Mapping
    col_map = {}
    for slot in slots:
        m_col = next((c for c in df.columns if c.lower() == slot.lower()), None)
        p_col = next((c for c in df.columns if slot.lower() in c.lower() and 'prot' in c.lower()), None)
        col_map[slot] = {'meal': m_col, 'prot': p_col}

    # Tracking for uniqueness (Normalized to lowercase/stripped)
    used_meals_this_week = set() 
    special_counts = {'chole': 0, 'rajma': 0}
    
    plan_data = []

    for day in days:
        daily_plan = {"Day": day}
        used_prots_today = set()
        
        for slot in slots:
            m_col, p_col = col_map[slot]['meal'], col_map[slot]['prot']
            if not m_col: continue

            # Get and shuffle options
            options = df[df[m_col].notna()].to_dict('records')
            random.shuffle(options)
            
            selected_meal = None
            
            # --- Tier 1: Strict Check (Unique protein + Unique weekly meal) ---
            for opt in options:
                raw_name = str(opt[m_col]).strip()
                norm_name = raw_name.lower()
                meal_lower = norm_name
                prot_source = find_protein(raw_name, opt.get(p_col, ""))
                
                # Validation Logic
                is_repeat_today = prot_source != 'other' and prot_source in used_prots_today
                is_repeat_week = slot != "Snack" and norm_name in used_meals_this_week
                is_limit_hit = ('chole' in meal_lower and special_counts['chole'] >= 1) or \
                               ('rajma' in meal_lower and special_counts['rajma'] >= 1)

                if not (is_repeat_today or is_repeat_week or is_limit_hit):
                    selected_meal = raw_name
                    if slot != "Snack": used_meals_this_week.add(norm_name)
                    if prot_source != 'other': used_prots_today.add(prot_source)
                    if 'chole' in meal_lower: special_counts['chole'] += 1
                    if 'rajma' in meal_lower: special_counts['rajma'] += 1
                    break

            # --- Tier 2: Emergency Fallback (Repeat permitted, but avoid same-day protein) ---
            if not selected_meal:
                for opt in options:
                    raw_name = str(opt[m_col]).strip()
                    prot_source = find_protein(raw_name, "")
                    if prot_source == 'other' or prot_source not in used_prots_today:
                        selected_meal = f"🔄 {raw_name}" # Visual indicator of repeat
                        break
                
            daily_plan[slot] = selected_meal or "Add More Options!"
        
        plan_data.append(daily_plan)
    
    return pd.DataFrame(plan_data)

# --- UI ---
st.title("🍲 Aahaar: Smarter Meal Planner")
st.info("Applying strict uniqueness for Breakfast, Lunch, and Dinner. Rajma/Chole capped at 1x/week.")

db = load_meal_db()
if db is not None:
    if st.button("Generate Fresh Weekly Plan", type="primary"):
        st.session_state['active_plan'] = get_weekly_plan(db)

    if 'active_plan' in st.session_state:
        st.dataframe(st.session_state['active_plan'], use_container_width=True, hide_index=True)
        
        # Download logic remains same
        csv = st.session_state['active_plan'].to_csv(index=False).encode('utf-8')
        st.download_button("📥 Download CSV", data=csv, file_name="meal_plan.csv")
