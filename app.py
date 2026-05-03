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
        meal_col = next((c for c in df.columns if c.lower() == slot.lower()), None)
        prot_col = next((c for c in df.columns if slot.lower() in c.lower() and 'prot' in c.lower()), None)
        col_map[slot] = {'meal': meal_col, 'prot': prot_col}

    # Tracking for uniqueness
    used_this_week = set() # To ensure B, L, D don't repeat
    special_counts = {'chole': 0, 'rajma': 0} # Limit to 1/week
    
    plan_data = []

    for day in days:
        daily_plan = {"Day": day}
        used_prots_today = set()
        
        for slot in slots:
            m_col = col_map[slot]['meal']
            p_col = col_map[slot]['prot']
            
            if not m_col:
                daily_plan[slot] = "N/A"
                continue

            # Get all possible rows for this slot
            options = df[df[m_col].notna()].to_dict('records')
            random.shuffle(options)
            
            selected_meal = None
            
            for opt in options:
                meal_name = opt[m_col]
                meal_lower = meal_name.lower()
                prot_source = find_protein(meal_name, opt.get(p_col, ""))
                
                # --- RULE 1: Daily Protein Variety ---
                if prot_source != 'other' and prot_source in used_prots_today:
                    continue
                
                # --- RULE 2: Weekly Uniqueness (Exclude Snacks) ---
                if slot != "Snack" and meal_name in used_this_week:
                    continue
                
                # --- RULE 3: Special Limits (Chole/Rajma) ---
                if 'chole' in meal_lower and special_counts['chole'] >= 1:
                    continue
                if 'rajma' in meal_lower and special_counts['rajma'] >= 1:
                    continue

                # If it passed all checks, select it!
                selected_meal = meal_name
                
                # Update Trackers
                if slot != "Snack":
                    used_this_week.add(meal_name)
                
                if prot_source != 'other':
                    used_prots_today.add(prot_source)
                
                if 'chole' in meal_lower: special_counts['chole'] += 1
                if 'rajma' in meal_lower: special_counts['rajma'] += 1
                break
            
            # Fallback: if rules are too strict and no meal found, 
            # pick anything that doesn't break the daily protein rule
            if not selected_meal:
                for opt in options:
                    if find_protein(opt[m_col], "") not in used_prots_today:
                        selected_meal = opt[m_col]
                        break
                selected_meal = selected_meal or "Explore New Recipe!"

            daily_plan[slot] = selected_meal
        
        plan_data.append(daily_plan)
    
    return pd.DataFrame(plan_data)

# --- UI ---
st.title("🍲 Aahaar: Smarter Meal Planner")
st.markdown("Rules applied: No B/L/D repeats this week. Chole/Rajma once a week. Diverse daily protein.")

db = load_meal_db()

if db is not None:
    if st.button("Generate Fresh Weekly Plan", type="primary"):
        st.session_state['active_plan'] = get_weekly_plan(db)

    if 'active_plan' in st.session_state:
        plan = st.session_state['active_plan']
        st.dataframe(plan, use_container_width=True, hide_index=True)

        # Downloads
        col1, col2 = st.columns(2)
        csv = plan.to_csv(index=False).encode('utf-8')
        col1.download_button("📥 Download CSV", data=csv, file_name="weekly_plan.csv")
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            plan.to_excel(writer, index=False)
        col2.download_button("📥 Download Excel", data=output.getvalue(), file_name="weekly_plan.xlsx")
