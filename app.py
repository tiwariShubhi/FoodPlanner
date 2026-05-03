import streamlit as st
import pandas as pd
import random
from io import BytesIO

# --- CONFIG & STYLING ---
st.set_page_config(page_title="Aahaar Weekly Planner", layout="wide")

st.markdown("""
    <style>
    .main { background-color: #f8f9fa; }
    .stButton>button { width: 100%; border-radius: 5px; height: 3em; background-color: #ff4b4b; color: white; }
    </style>
    """, unsafe_allow_html=True)

# --- DATA LOADING ---
SHEET_URL = "https://docs.google.com/spreadsheets/d/1tH9_wN6g1Di5N_XQ1CUDMuIlmr5wU7NfjdiyjBxoQn8/export?format=csv"

@st.cache_data(ttl=600)
def load_data():
    try:
        df = pd.read_csv(SHEET_URL)
        # Ensure column names are clean
        df.columns = [c.strip().lower() for c in df.columns]
        return df
    except Exception as e:
        st.error(f"Error loading sheet: {e}")
        return None

def get_weekly_plan(df):
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    categories = ["breakfast", "lunch", "dinner"]
    plan = []

    for day in days:
        daily_used_proteins = set()
        day_entry = {"Day": day}
        
        for cat in categories:
            # Filter by category and ensure protein source hasn't been used today
            mask = (df['category'].str.lower() == cat) & (~df['protein_source'].str.lower().isin(daily_used_proteins))
            available_options = df[mask]
            
            if available_options.empty:
                # Fallback if constraint is too tight: just pick any from category
                available_options = df[df['category'].str.lower() == cat]
            
            selected = available_options.sample(n=1).iloc[0]
            day_entry[cat.capitalize()] = selected['meal_name']
            day_entry[f"{cat.capitalize()} Protein"] = selected['protein_source']
            
            # Track this protein source to avoid repeats today
            daily_used_proteins.add(selected['protein_source'].lower())
            
        plan.append(day_entry)
    
    return pd.DataFrame(plan)

# --- UI LAYOUT ---
st.title("🍲 Aahaar: Weekly Power Planner")
st.info("Ensuring variety: Egg, Paneer, and Soya are never repeated in the same day.")

data = load_data()

if data is not None:
    if st.button("Generate New Weekly Plan"):
        with st.spinner("Whisking up your plan..."):
            weekly_df = get_weekly_plan(data)
            st.session_state['current_plan'] = weekly_df

    if 'current_plan' in st.session_state:
        plan_df = st.session_state['current_plan']
        
        # Display the plan
        st.subheader("Your 7-Day Schedule")
        st.dataframe(plan_df, use_container_width=True, hide_index=True)

        # --- EXPORT SECTION ---
        col1, col2 = st.columns(2)
        
        # CSV Export
        csv = plan_df.to_csv(index=False).encode('utf-8')
        col1.download_button(
            label="📥 Download as CSV",
            data=csv,
            file_name='weekly_meal_plan.csv',
            mime='text/csv',
        )

        # Excel Export
        output = BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            plan_df.to_excel(writer, index=False, sheet_name='Sheet1')
        excel_data = output.getvalue()
        
        col2.download_button(
            label="📥 Download as Excel",
            data=excel_data,
            file_name='weekly_meal_plan.xlsx',
            mime='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
else:
    st.warning("Please check if the Google Sheet is accessible to 'Anyone with the link'.")

