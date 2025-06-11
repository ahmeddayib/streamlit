import pdfplumber
import re
import zipfile
import io
import streamlit as st
import os
from datetime import datetime
import random

# ------------------------
# PDF Processing Functions
# ------------------------

def extract_page3_content(pdf_bytes):
    """Extract content from page 3 of HFPCP PDF with improved pattern matching"""
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            if len(pdf.pages) >= 3:
                page3 = pdf.pages[2]
                text = page3.extract_text()
                
                if not text:
                    return "", ""
                
                # Normalize text for better matching
                text = re.sub(r'\s+', ' ', text).lower()
                
                # Extract Areas in Need of Housing with flexible matching
                areas_pattern = r'areas? in need of housing(.*?)(support instructions|moving expenses|risks and risk mitigation|non-housing)'
                areas_match = re.search(areas_pattern, text, re.DOTALL | re.IGNORECASE)
                areas_content = areas_match.group(1).strip() if areas_match else ""
                
                # Extract Support Instructions with flexible matching
                support_pattern = r'support instructions(.*?)(moving expenses|risks and risk mitigation|non-housing|$)'
                support_match = re.search(support_pattern, text, re.DOTALL | re.IGNORECASE)
                support_content = support_match.group(1).strip() if support_match else ""
                
                return areas_content, support_content
            else:
                return "", ""
    except Exception as e:
        st.error(f"Error processing PDF: {str(e)}")
        return "", ""

def process_zip_file(zip_bytes):
    """Process all PDFs in a zip file and extract page 3 content"""
    patterns = []
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zip_ref:
            for file_name in zip_ref.namelist():
                if file_name.lower().endswith('.pdf'):
                    try:
                        with zip_ref.open(file_name) as pdf_file:
                            pdf_bytes = pdf_file.read()
                            areas, support = extract_page3_content(pdf_bytes)
                            if areas or support:
                                patterns.append({
                                    'file_name': file_name,
                                    'areas': areas,
                                    'support': support
                                })
                            else:
                                st.warning(f"Could not extract content from {file_name}")
                    except Exception as e:
                        st.warning(f"Error processing {file_name}: {str(e)}")
    except zipfile.BadZipFile:
        st.error("Error: The uploaded file is not a valid ZIP file")
    return patterns

def analyze_paragraphs(patterns):
    """Analyze patterns in the extracted paragraphs"""
    areas_insights = []
    support_insights = []
    
    for pattern in patterns:
        # Skip empty patterns
        if not pattern['areas'] and not pattern['support']:
            continue
            
        # Analyze structure of Areas in Need of Housing
        if pattern['areas']:
            sections = {}
            for section in ['communication', 'decision making', 'managing challenging behaviors']:
                section_match = re.search(fr'{section}:(.*?)(?=(communication|decision making|managing challenging behaviors|$))', 
                                        pattern['areas'], re.IGNORECASE | re.DOTALL)
                if section_match:
                    sections[section] = section_match.group(1).strip()
            
            if sections:
                areas_insights.append(sections)
        
        # Analyze Support Instructions
        if pattern['support']:
            service_type = "Transitional" if "transition" in pattern['support'].lower() else "Sustaining"
            actions = []
            referrals = []
            
            # Extract provider actions
            action_phrases = re.findall(r'(?:provider will|we will|they will|support will|assist|help)(.*?)(?:\.|\n|$)', 
                                      pattern['support'], re.IGNORECASE)
            actions.extend([phrase.strip() for phrase in action_phrases if phrase.strip()])
            
            # Extract referrals
            referral_phrases = re.findall(r'(?:connect|refer|link).*? (?:to|for) (.*?)(?:\.|\n|$)', 
                                       pattern['support'], re.IGNORECASE)
            referrals.extend([phrase.strip() for phrase in referral_phrases if phrase.strip()])
            
            if actions or referrals:
                support_insights.append({
                    'service_type': service_type,
                    'actions': actions,
                    'referrals': list(set(referrals))  # Remove duplicates
                })
    
    return areas_insights, support_insights

# ------------------------
# Paragraph Generation
# ------------------------

def generate_areas_paragraph(client_name, mental_health, communication_issues, decision_issues, behavior_issues, mobility_issues, selected_needs):
    """Generate Areas in Need of Housing paragraph"""
    # Introduction sentence
    base = f"{client_name} is currently navigating {mental_health}, while seeking housing services.\n\n"
    
    # Build each section based on selected needs
    paragraphs = []
    if 'Communication' in selected_needs and communication_issues:
        paragraphs.append(f"Communication: {communication_issues.capitalize()}")
    if 'Decision Making' in selected_needs and decision_issues:
        paragraphs.append(f"Decision Making: {decision_issues.capitalize()}")
    if 'Managing Challenging Behaviors' in selected_needs and behavior_issues:
        paragraphs.append(f"Managing Challenging Behaviors: {behavior_issues.capitalize()}")
    if 'Mobility' in selected_needs and mobility_issues:
        paragraphs.append(f"Mobility: {mobility_issues.capitalize()}")
    
    return base + "\n\n".join(paragraphs)

def generate_support_paragraph(client_name, service_type, housing_actions, support_actions, referrals):
    """Generate Support Instructions paragraph"""
    # Service type declaration
    service_str = service_type.lower()
    base = f"{client_name} is starting with {service_str} services.\n\n"
    
    # Build action sentences
    sentences = []
    
    # Housing search actions
    if housing_actions:
        sentences.append(f"A provider will assist {client_name} by {housing_actions}.")
    
    # Support actions
    if support_actions:
        sentences.append(f"They will also provide support with {support_actions}.")
    
    # Referrals
    if referrals:
        if len(referrals) > 1:
            referrals_str = ", ".join(referrals[:-1]) + ", and " + referrals[-1]
        else:
            referrals_str = referrals[0]
        
        sentences.append(f"Additionally, the provider will connect {client_name} with resources for {referrals_str}.")
    
    return base + " ".join(sentences)

# ------------------------
# Streamlit UI
# ------------------------

def main():
    st.set_page_config(page_title="HFPCP Assistant", page_icon="🏠", layout="wide")
    
    # Initialize session state
    if 'patterns' not in st.session_state:
        st.session_state.patterns = []
    if 'examples' not in st.session_state:
        st.session_state.examples = []
    if 'debug_info' not in st.session_state:
        st.session_state.debug_info = []
    
    st.title("🏠 HFPCP Paragraph Generator")
    st.subheader("Create Compliant 'Areas in Need of Housing' and 'Support Instructions' Sections")
    
    # Sidebar for training data
    with st.sidebar:
        st.header("Step 1: Add Training Data")
        zip_file = st.file_uploader("Upload ZIP file of approved HFPCPs", type="zip")
        
        if zip_file is not None:
            with st.spinner("Analyzing HFPCP documents..."):
                patterns = process_zip_file(zip_file.getvalue())
                if patterns:
                    st.session_state.patterns = patterns
                    st.success(f"✅ Processed {len(patterns)} HFPCP documents")
                    
                    # Store raw content for debugging
                    st.session_state.debug_info = [(p['areas'], p['support']) for p in patterns]
                    
                    # Analyze patterns
                    areas_insights, support_insights = analyze_paragraphs(patterns)
                    if areas_insights or support_insights:
                        st.session_state.areas_insights = areas_insights
                        st.session_state.support_insights = support_insights
                    else:
                        st.warning("⚠️ Could not identify patterns in the documents")
                else:
                    st.warning("⚠️ No valid page 3 content found in the uploaded documents")
    
    # Debug view
    if st.session_state.get('debug_info'):
        with st.expander("Debug: View Raw Extracted Content", expanded=False):
            for i, (areas, support) in enumerate(st.session_state.debug_info):
                st.subheader(f"Document {i+1}")
                st.text_area(f"Areas Content", areas, height=150, key=f"areas_{i}")
                st.text_area(f"Support Content", support, height=150, key=f"support_{i}")
    
    # Main form
    with st.form("hfpcd_input"):
        st.header("Step 2: Client Information")
        
        col1, col2 = st.columns(2)
        
        with col1:
            client_name = st.text_input("Client Full Name", placeholder="e.g., Shamso Hussein")
            
            st.subheader("Diagnosis")
            diagnosis_options = [
                "Developmental Disability",
                "Learning Disability",
                "Mental Illness",
                "Physical Illness/Injury/Impairment",
                "Chemical Dependency"
            ]
            diagnosis = st.multiselect("Select one or more diagnoses", diagnosis_options)
            mental_health = st.text_input("Specific Conditions", "depression, anxiety", 
                                         help="Specific conditions affecting housing search")
            
            st.subheader("Assessed Needs")
            st.markdown("**Check one or more assessed needs (must reflect the areas that were identified in the assessment):**")
            needs_options = ["Mobility", "Communication", "Decision Making", "Managing Challenging Behaviors"]
            selected_needs = st.multiselect("Select needs", needs_options, default=["Communication", "Decision Making"])
            
            if 'Communication' in selected_needs:
                communication_issues = st.text_area("Communication Challenges", 
                                                "struggles to express needs to landlords, difficulty with phone calls",
                                                help="How communication issues affect housing")
            else:
                communication_issues = ""
            
            if 'Decision Making' in selected_needs:
                decision_issues = st.text_area("Decision Making Challenges", 
                                            "feels overwhelmed by choices, difficulty evaluating options",
                                            help="How decision-making challenges affect housing")
            else:
                decision_issues = ""
        
        with col2:
            if 'Managing Challenging Behaviors' in selected_needs:
                behavior_issues = st.text_area("Managing Challenging Behaviors", 
                                            "withdraws when stressed, difficulty managing frustration",
                                            help="How challenging behaviors affect housing")
            else:
                behavior_issues = ""
                
            if 'Mobility' in selected_needs:
                mobility_issues = st.text_area("Mobility Challenges",
                                            "difficulty navigating stairs, needs wheelchair accessible housing",
                                            help="How mobility issues affect housing")
            else:
                mobility_issues = ""
            
            st.subheader("Support Instructions")
            service_type = st.radio("Service Type", ["Transitional", "Sustaining"], index=0,
                                  help="Transitional = finding new housing, Sustaining = maintaining current housing")
            
            housing_actions = st.text_area("Housing Search Actions", 
                                         "searching for suitable apartments, scheduling viewings, contacting landlords",
                                         help="Specific actions for housing search")
            
            support_actions = st.text_area("Support Services", 
                                         "budgeting assistance, credit recovery, emotional support",
                                         help="Non-housing support services")
            
            referrals = st.multiselect("Referrals Needed", 
                                     ["therapy/counseling", "employment support", "financial management", 
                                      "childcare services", "medical care", "support groups"],
                                     default=["therapy/counseling", "financial management"])
        
        submitted = st.form_submit_button("Generate Paragraphs")
    
    # Show examples if available
    if st.session_state.get('patterns'):
        with st.expander("View Examples from Approved HFPCPs", expanded=False):
            tab1, tab2 = st.tabs(["Areas in Need of Housing", "Support Instructions"])
            
            with tab1:
                if st.session_state.patterns:
                    sample = random.choice(st.session_state.patterns)
                    st.text_area("Example Areas Content", sample['areas'], height=300, key="example_areas")
            
            with tab2:
                if st.session_state.patterns:
                    sample = random.choice(st.session_state.patterns)
                    st.text_area("Example Support Content", sample['support'], height=250, key="example_support")
    
    # Generate and display paragraphs
    if submitted:
        if not client_name:
            st.error("Please enter client name")
            return
        
        if not diagnosis:
            st.error("Please select at least one diagnosis")
            return
            
        if not selected_needs:
            st.error("Please select at least one assessed need")
            return
            
        with st.spinner("Generating compliant paragraphs..."):
            # Combine diagnosis and specific conditions
            full_diagnosis = ", ".join(diagnosis)
            if mental_health.strip():
                full_diagnosis += f" ({mental_health})"
            
            areas_paragraph = generate_areas_paragraph(
                client_name, full_diagnosis, communication_issues, 
                decision_issues, behavior_issues, mobility_issues, selected_needs
            )
            
            support_paragraph = generate_support_paragraph(
                client_name, service_type, housing_actions, 
                support_actions, referrals
            )
            
            st.header("Step 3: Generated Content")
            st.success("✅ Paragraphs created! Copy and paste these into Page 3 of the HFPCP form")
            
            col1, col2 = st.columns(2)
            
            with col1:
                st.subheader("Areas in Need of Housing")
                st.text_area("Copy this content:", areas_paragraph, height=300, key="areas_output")
                st.markdown(f"**Selected Assessed Needs:** {', '.join(selected_needs)}")
            
            with col2:
                st.subheader("Support Instructions")
                st.text_area("Copy this content:", support_paragraph, height=250, key="support_output")
                st.markdown(f"**Diagnosis:** {full_diagnosis}")
            
            # Download option
            st.download_button(
                label="📥 Download Both Sections",
                data=f"DIAGNOSIS: {full_diagnosis}\n\nASSESSED NEEDS: {', '.join(selected_needs)}\n\nAREAS IN NEED OF HOUSING\n\n{areas_paragraph}\n\n\nSUPPORT INSTRUCTIONS\n\n{support_paragraph}",
                file_name=f"{client_name.replace(' ', '_')}_HFPCP_Page3_Content.txt",
                mime="text/plain"
            )

if __name__ == "__main__":
    main()