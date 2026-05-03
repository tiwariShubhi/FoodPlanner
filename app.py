import streamlit as st
import pandas as pd
import random
from io import BytesIO

# --- CONFIG ---
st.set_page_config(page_title="Aahaar Meal Planner", layout="wide")

# --- DATA LOADING ---
SHEET_ID = "1tH9_wN6g1Di5N_XQ1CUDMuIlmr5wU7NfjdiyjBxoQn8"
SHEET_URL = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv"

@st.cache_data(ttl=300)
def load_meal_db():
    try:
        df = pd.read_csv(SHEET_URL)
        # Clean column names: remove spaces and make lowercase for matching
        df.columns = [str(c).strip() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error fetching sheet: {e}")
        return None

def find_protein(meal_name, protein_val):
    """Determines protein source from column or text analysis"""
    text_to_search = f"{str(meal_name)} {str(protein_val)}".lower()
    if 'egg' in text_to_search: return 'egg'
    if 'paneer' in text_to_search: return 'paneer'
    if 'soya' in text_to_search: return 'soya'
    if 'dal' in text_to_search: return 'dal'
    return 'other'

def get_weekly_plan(df):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    slots = ["Breakfast", "Lunch", "Snack", "Dinner"]
    
    # Robust Column Mapping
    col_map = {}
    for slot in slots:
        # Find meal column (e.g., column that is exactly "Lunch")
        meal_col = next((c for c in df.columns if c.lower() == slot.lower()), None)
        # Find protein column (e.g., column containing "Lunch" and "Protein")
        prot_col = next((c for c in df.columns if slot.lower() in c.lower() and 'prot' in c.lower()), None)
        col_map[slot] = {'meal': meal_col, 'prot': prot_col}

    # Show mapping in sidebar for debugging
    with st.sidebar:
        st.write("### Column Mapping Details")
        st.json(col_map)

    plan_data = []
    for day in days:
        daily_plan = {"Day": day}
        used_proteins_today = set()
        
        for slot in slots:
            m_col = col_map[slot]['meal']
            p_col = col_map[slot]['prot']
            
            if not m_col:
                daily_plan[slot] = "Col Not Found"
                continue

            # Get valid rows for this slot
            valid_options = df[df[m_col].notna()]
            
            # Filter for diversity
            options_list = valid_options.to_dict('records')
            random.shuffle(options_list)
            
            selected_meal = "Standard Meal"
            selected_prot = "other"
            
            for opt in options_list:
                meal_name = opt[m_col]
                prot_source = find_protein(meal_name, opt.get(p_col, ""))
                
                # If protein is not already used today, or it's 'other', pick it
                if prot_source == 'other' or prot_source not in used_proteins_today:
                    selected_meal = meal_name
                    selected_prot = prot_source
                    break
            
            daily_plan[slot] = selected_meal
            if selected_prot != 'other':
                used_proteins_today.add(selected_prot)
        
        plan_data.append(daily_plan)
    
    return pd.DataFrame(plan_data)

# --- UI ---
st.title("🍲 Aahaar: Weekly Power Planner")

db = load_meal_db()

if db is not None:
    if st.button("Generate Full Week Plan", type="primary"):
        weekly_df = get_weekly_plan(db)
        st.session_state['active_plan'] = weekly_df

    if 'active_plan' in st.session_state:
        plan = st.session_state['active_plan']
        st.subheader("Your 7-Day Schedule")
        st.dataframe(plan, use_container_width=True, hide_index=True)

        # Downloads
        csv = plan.to_csv(index=False).encode('utf-8')
        st.download_button("Download CSV", data=csv, file_name="meal_plan.csv")
        
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            plan.to_excel(writer, index=False)
        st.download_button("Download Excel", data=output.getvalue(), file_name="meal_plan.xlsx")
else:
    st.error("Cannot read spreadsheet. Check sharing permissions!")
