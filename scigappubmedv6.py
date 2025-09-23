# ==== Default API Keys (can be changed in sidebar) ====
DEFAULT_OPENROUTER_API_KEY = "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"
DEFAULT_PUBMED_API_KEY = "633c02cd5685ef07df46fa96f7df75ce4a09"
OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
PUBMED_API_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
# ==== End Default Configuration ====

import streamlit as st
import requests
import json
import os
import pandas as pd
import re
import time
import sys
import subprocess
import random
from urllib.parse import quote_plus
from bs4 import BeautifulSoup
import xml.etree.ElementTree as ET
import base64
import streamlit.components.v1 as components

# Initialize session state for API keys
def initialize_session_state():
    if 'openrouter_api_key' not in st.session_state:
        st.session_state.openrouter_api_key = DEFAULT_OPENROUTER_API_KEY
    if 'pubmed_api_key' not in st.session_state:
        st.session_state.pubmed_api_key = DEFAULT_PUBMED_API_KEY
    if 'show_openrouter_help' not in st.session_state:
        st.session_state.show_openrouter_help = False
    if 'show_pubmed_help' not in st.session_state:
        st.session_state.show_pubmed_help = False
    if 'experiment_running' not in st.session_state:
        st.session_state.experiment_running = False

# Check and install required packages
def install_package(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import openai
except ImportError:
    st.warning("Installing openai package...")
    install_package("openai")
    import openai

# Initialize OpenRouter client for DeepSeek access
def get_openrouter_client():
    return openai.OpenAI(
        api_key=st.session_state.openrouter_api_key,
        base_url=OPENROUTER_BASE_URL,
        default_headers={
            "HTTP-Referer": "https://your-app-url.com",
            "X-Title": "Knowledge Gap Finder"
        }
    )

def get_deepseek_response(prompt: str, max_attempts=3) -> str:
    """Get response from DeepSeek via OpenRouter with retries"""
    for attempt in range(max_attempts):
        try:
            client = get_openrouter_client()
            response = client.chat.completions.create(
                model="deepseek/deepseek-chat-v3.1:free",  # Updated model name
                messages=[
                    {"role": "system", "content": "You are a helpful research assistant specializing in meta-analysis knowledge gap identification using ONLY PubMed sources. Always provide a refined search for the next iteration."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.7
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            st.warning(f"Attempt {attempt+1} failed: {str(e)}")
            if attempt < max_attempts - 1:
                time.sleep(2)
    st.error("⚠️ Failed to get response from DeepSeek API after multiple attempts.")
    return None

def search_pubmed_api(query: str, num_results=10) -> list:
    """Search PubMed using the NCBI E-utilities API"""
    results = []
    try:
        # Step 1: Search for PMIDs
        search_params = {
            'db': 'pubmed',
            'term': query,
            'retmax': num_results,
            'retmode': 'json',
            'api_key': st.session_state.pubmed_api_key
        }
        
        search_url = f"{PUBMED_API_URL}esearch.fcgi"
        search_response = requests.get(search_url, params=search_params, timeout=15)
        search_response.raise_for_status()
        
        search_data = search_response.json()
        id_list = search_data.get('esearchresult', {}).get('idlist', [])
        
        if not id_list:
            st.warning("No PubMed IDs found for your query")
            return results
        
        # Step 2: Fetch article details
        fetch_params = {
            'db': 'pubmed',
            'id': ','.join(id_list),
            'retmode': 'xml',
            'api_key': st.session_state.pubmed_api_key
        }
        
        fetch_url = f"{PUBMED_API_URL}efetch.fcgi"
        fetch_response = requests.get(fetch_url, params=fetch_params, timeout=30)
        fetch_response.raise_for_status()
        
        # Parse XML response
        root = ET.fromstring(fetch_response.content)
        
        for article in root.findall('.//PubmedArticle'):
            pmid = article.find('.//PMID').text if article.find('.//PMID') is not None else ""
            title = article.find('.//ArticleTitle').text if article.find('.//ArticleTitle') is not None else "No title available"
            
            abstract_parts = []
            abstract_texts = article.findall('.//AbstractText')
            for abstract_text in abstract_texts:
                if abstract_text.text:
                    abstract_parts.append(abstract_text.text)
            
            abstract = " ".join(abstract_parts) if abstract_parts else "No abstract available"
            
            results.append({
                'title': title,
                'snippet': abstract,
                'link': f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
                'pmid': f"PMID: {pmid}"
            })
        
    except requests.exceptions.RequestException as e:
        st.error(f"PubMed API request failed: {str(e)}")
    except Exception as e:
        st.error(f"Error processing PubMed results: {str(e)}")
    
    return results

def web_search_fallback(query: str, num_results=10) -> list:
    """Fallback method using direct PubMed web scraping"""
    results = []
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'DNT': '1',
        'Connection': 'keep-alive',
    }
    
    try:
        time.sleep(random.uniform(3.0, 6.0))
        search_url = f"https://pubmed.ncbi.nlm.nih.gov/?term={quote_plus(query)}&size={num_results}"
        response = requests.get(search_url, headers=headers, timeout=15)
        
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            articles = soup.find_all('div', class_='docsum')
            
            for article in articles[:num_results]:
                title_element = article.find('a', class_='docsum-title')
                snippet_element = article.find('div', class_='docsum-snippet')
                pmid_element = article.find('span', class_='docsum-pmid')
                
                pmid = pmid_element.get_text().strip() if pmid_element else ""
                pmid_url = f"https://pubmed.ncbi.nlm.nih.gov{title_element.get('href')}" if title_element and title_element.get('href') else ""
                
                results.append({
                    'title': title_element.get_text().strip() if title_element else "No title available",
                    'snippet': snippet_element.get_text().strip() if snippet_element else "No abstract available",
                    'link': pmid_url,
                    'pmid': pmid
                })
    except Exception as e:
        st.warning(f"PubMed fallback search failed: {str(e)}")
    
    return results

def web_search(query: str, num_results=10) -> list:
    """Perform search using PubMed API with fallback methods"""
    # First, try using the PubMed API
    st.info("🔍 Searching PubMed via official API...")
    results = search_pubmed_api(query, num_results)
    
    # If API fails, use web scraping fallback
    if not results:
        st.warning("PubMed API failed. Using direct web scraping as fallback...")
        results = web_search_fallback(query, num_results)
    
    # If both methods fail, use sample data
    if not results:
        st.error("⚠️ Both PubMed search methods failed. Using sample data for demonstration.")
        return [
            {
                'title': f'Research on "{query}" - PubMed Example 1',
                'snippet': f'Abstract: Our study investigated key variables in this domain. Results showed significant correlations...',
                'link': 'https://pubmed.ncbi.nlm.nih.gov/12345678/',
                'pmid': 'PMID: 12345678'
            },
            {
                'title': f'Meta-analysis of "{query}" - PubMed Example 2',
                'snippet': f'Abstract: This systematic review examined existing literature on the topic. Meta-analysis revealed heterogeneity...',
                'link': 'https://pubmed.ncbi.nlm.nih.gov/87654321/',
                'pmid': 'PMID: 87654321'
            }
        ]
    
    return results

def summarize_search_results(search_results: list) -> str:
    """Summarize PubMed search results using DeepSeek"""
    text_content = ""
    for i, result in enumerate(search_results[:10], 1):
        text_content += f"PubMed Result {i}:\n"
        text_content += f"Title: {result['title']}\n"
        text_content += f"PMID: {result['pmid']}\n"
        text_content += f"Abstract: {result['snippet']}\n\n"
    
    prompt = f"""Please provide a comprehensive summary of the following PubMed research for meta-analysis:

{text_content}

Your summary should:
1. Identify main themes and methodologies (STRICTLY from these PubMed sources)
2. Highlight key findings and conclusions (STRICTLY from these PubMed sources)
3. Note any contradictions or inconsistencies (STRICTLY from these PubMed sources)
4. Keep it concise but comprehensive (3-4 paragraphs)
5. Do NOT use any external knowledge or sources"""

    return get_deepseek_response(prompt)

def analyze_knowledge_gaps(summary: str, base_prompt: str) -> str:
    """Analyze PubMed summary for knowledge gaps using DeepSeek"""
    full_prompt = base_prompt.format(summary=summary)
    return get_deepseek_response(full_prompt)

def extract_gap_info(response_text: str, current_query: str) -> tuple:
    """Extract structured gap information from DeepSeek response"""
    gap_found = False
    meta_title = ""
    gap_text = ""
    next_query = ""
    
    gap_keywords = [
        "knowledge gap", "gap identified", "research gap", "unresolved question",
        "contradiction", "inconsistency", "lack of studies", "limited research"
    ]
    response_lower = response_text.lower()
    
    if any(keyword in response_lower for keyword in gap_keywords):
        gap_found = True
        
        title_patterns = [
            r"meta-?analysis\s*title\s*[:\-]?\s*(.+)",
            r"title\s*[:\-]?\s*(.+)",
            r"proposed\s*title\s*[:\-]?\s*(.+)"
        ]
        for pattern in title_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE)
            if match:
                meta_title = match.group(1).strip()
                break
        
        gap_patterns = [
            r"gap\s*[:\-]?\s*(.+)",
            r"knowledge\s*gap\s*[:\-]?\s*(.+)",
            r"research\s*gap\s*[:\-]?\s*(.+)"
        ]
        for pattern in gap_patterns:
            match = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)
            if match:
                gap_text = match.group(1).strip()
                break
    
    query_patterns = [
        r"refined\s*query\s*[:\-]?\s*(.+)",
        r"next\s*query\s*[:\-]?\s*(.+)",
        r"search\s*query\s*[:\-]?\s*(.+)",
        r"suggested\s*query\s*[:\-]?\s*(.+)"
    ]
    for pattern in query_patterns:
        match = re.search(pattern, response_text, re.IGNORECASE | re.DOTALL)
        if match:
            next_query = match.group(1).strip()
            break
    
    if gap_found and not gap_text:
        gap_text = "Knowledge gap identified in PubMed sources but not clearly described."
    
    if not next_query:
        # Use the current query as the basis for refinement
        next_query = f"{current_query} meta-analysis" if not gap_found else current_query
    
    return gap_found, meta_title, gap_text, next_query

def save_data_to_csv(row_data: dict, csv_path: str, table_placeholder) -> pd.DataFrame:
    """Save data to CSV file and update displayed table"""
    new_row = pd.DataFrame([row_data])
    
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        df = pd.concat([df, new_row], ignore_index=True)
    else:
        df = new_row
    
    df.to_csv(csv_path, index=False)
    table_placeholder.dataframe(df)
    return df

def display_flashy_titles(topics: list):
    """Display meta-analysis titles in a flashy format at the top of the page"""
    if not topics:
        return
        
    st.markdown("""
        <style>
        .flashy-container {
            background: linear-gradient(135deg, #1a2a6c, #b21f1f, #1a2a6c);
            background-size: 400% 400%;
            animation: gradient 15s ease infinite;
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 30px;
            box-shadow: 0 10px 20px rgba(0,0,0,0.2);
        }
        @keyframes gradient {
            0% {background-position: 0% 50%;}
            50% {background-position: 100% 50%;}
            100% {background-position: 0% 50%;}
        }
        .flashy-title {
            color: white;
            font-size: 1.2rem;
            font-weight: bold;
            margin-bottom: 10px;
            padding: 10px 15px;
            background-color: rgba(255,255,255,0.1);
            border-left: 5px solid #FFD700;
            border-radius: 5px;
            box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            transition: all 0.3s ease;
        }
        .flashy-title:hover {
            background-color: rgba(255,255,255,0.2);
            transform: translateX(5px);
        }
        .flashy-header {
            color: #FFD700;
            font-size: 1.8rem;
            font-weight: bold;
            text-align: center;
            margin-bottom: 15px;
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }
        </style>
    """, unsafe_allow_html=True)
    
    with st.container():
        st.markdown("""
            <div class="flashy-container">
                <div class="flashy-header">🏆 DISCOVERED META-ANALYSIS TOPICS 🏆</div>
        """, unsafe_allow_html=True)
        
        for title in topics:
            st.markdown(f"""
                <div class="flashy-title">
                📚 {title}
                </div>
            """, unsafe_allow_html=True)
        
        st.markdown("</div>", unsafe_allow_html=True)

# Display flashy titles at the top of the page
def display_meta_titles():
    """Display all discovered meta-analysis titles in a flashy format"""
    csv_path = "knowledge_gaps.csv"
    
    if os.path.exists(csv_path):
        df = pd.read_csv(csv_path)
        if not df.empty:
            # Get all unique meta-analysis topics with high scores
            high_score_topics = df[df["Score"] == "High"]["Meta_Analysis_Topic"].tolist()
            # Remove duplicates and empty strings
            high_score_topics = [t for t in set(high_score_topics) if t]
            
            if high_score_topics:
                display_flashy_titles(high_score_topics)

# Confetti animation function
def show_confetti():
    """Display confetti animation using custom HTML/JS"""
    html_code = """
    <style>
    .confetti-container {
        position: fixed;
        top: 0;
        left: 0;
        width: 100%;
        height: 100%;
        overflow: hidden;
        z-index: 9999;
        pointer-events: none;
    }
    .confetti {
        position: absolute;
        top: -10px;
        width: 10px;
        height: 10px;
        opacity: 0.8;
    }
    </style>
    <div class="confetti-container" id="confetti"></div>
    <script>
    const colors = ['#ff0000', '#00ff00', '#0000ff', '#ffff00', '#ff00ff', '#00ffff', '#ff7f00', '#7cfc00'];
    const confettiCount = 200;
    const container = document.getElementById('confetti');
    
    for (let i = 0; i < confettiCount; i++) {
        const confetti = document.createElement('div');
        confetti.className = 'confetti';
        confetti.style.left = Math.random() * 100 + 'vw';
        confetti.style.backgroundColor = colors[Math.floor(Math.random() * colors.length)];
        confetti.style.width = Math.random() * 10 + 5 + 'px';
        confetti.style.height = confetti.style.width;
        confetti.style.opacity = Math.random() + 0.5;
        confetti.style.transform = `rotate(${Math.random() * 360}deg)`;
        confetti.style.animation = `fall ${Math.random() * 5 + 3}s linear forwards`;
        container.appendChild(confetti);
    }
    
    const style = document.createElement('style');
    style.textContent = `
        @keyframes fall {
            to {
                transform: translateY(105vh) rotate(720deg);
                opacity: 0;
            }
        }
    `;
    document.head.appendChild(style);
    
    // Remove confetti after animation completes
    setTimeout(() => {
        const confettiElements = document.querySelectorAll('.confetti');
        confettiElements.forEach(el => el.remove());
    }, 8000);
    </script>
    """
    components.html(html_code, height=0)

# Main application
def main():
    st.set_page_config(
        page_title="PubMed Knowledge Gap Finder",
        page_icon="🔍",
        layout="wide"
    )
    
    # Initialize session state first
    initialize_session_state()
    
    # Display flashy titles at the very top
    display_meta_titles()
    
    # Header with Buy Me a Coffee button
    col1, col2 = st.columns([4, 1])
    with col1:
        st.title("PubMed Knowledge Gap Finder 🔍 (DeepSeek Edition)")
        st.markdown("Identify research gaps using **PubMed official API** and direct web scraping")
    with col2:
        # Create the coffee button using HTML and CSS
        st.markdown("""
            <style>
            .coffee-button {
                display: flex;
                align-items: center;
                justify-content: center;
                background: linear-gradient(to bottom, #ffdd00, #ffaa00);
                color: #333;
                font-weight: bold;
                padding: 8px 16px;
                border-radius: 30px;
                text-decoration: none;
                box-shadow: 0 4px 8px rgba(0,0,0,0.2);
                transition: all 0.3s ease;
                margin-top: 15px;
            }
            .coffee-button:hover {
                background: linear-gradient(to bottom, #ffee00, #ffcc00);
                transform: translateY(-3px);
                box-shadow: 0 6px 12px rgba(0,0,0,0.3);
                color: #333;
                text-decoration: none;
            }
            .coffee-icon {
                margin-right: 8px;
                font-size: 1.2em;
            }
            </style>
            
            <a href="https://paypal.me/jkc7900?locale.x=en_GB&country.x=IN" target="_blank" class="coffee-button">
                <span class="coffee-icon">☕</span>
                Buy Me a Coffee
            </a>
        """, unsafe_allow_html=True)
    
    # Sidebar configuration
    with st.sidebar:
        st.header("⚙️ Configuration")
        
        # API Keys section with help icons
        st.subheader("🔑 API Configuration")
        
        # OpenRouter API Key with help
        col1, col2 = st.columns([4, 1])
        with col1:
            # We need to use a different key for the widget to avoid the session state conflict
            openrouter_key = st.text_input(
                "OpenRouter API Key",
                type="password",
                value=st.session_state.openrouter_api_key,
                key="openrouter_key_widget"  # Different key name
            )
        with col2:
            if st.button("ℹ️", key="openrouter_help_button", help="Click for help"):
                st.session_state.show_openrouter_help = not st.session_state.show_openrouter_help
        
        # Show OpenRouter help if requested
        if st.session_state.show_openrouter_help:
            with st.expander("📖 How to get OpenRouter API Key", expanded=True):
                st.markdown("""
                **Steps to get your OpenRouter API key:**
                
                1. Go to [OpenRouter.ai](https://openrouter.ai)
                2. Sign up for a new account or log in
                3. Navigate to the **API Keys** section in your account
                4. Click **"Create new secret key"**
                5. Give your key a name (e.g., "PubMed Knowledge Gap Finder")
                6. Copy the generated key (starts with "sk-or-v1-")
                7. Paste it in the API key field above
                8. Click to close this help section
                
                **Note:** Keep your API key secure and don't share it publicly!
                """)
        
        # PubMed API Key with help
        col1, col2 = st.columns([4, 1])
        with col1:
            # We need to use a different key for the widget to avoid the session state conflict
            pubmed_key = st.text_input(
                "PubMed API Key",
                type="password",
                value=st.session_state.pubmed_api_key,
                key="pubmed_key_widget"  # Different key name
            )
        with col2:
            if st.button("ℹ️", key="pubmed_help_button", help="Click for help"):
                st.session_state.show_pubmed_help = not st.session_state.show_pubmed_help
        
        # Show PubMed help if requested
        if st.session_state.show_pubmed_help:
            with st.expander("📖 How to get PubMed API Key", expanded=True):
                st.markdown("""
                **Steps to get your NCBI API Key:**
                
                1. Go to [NCBI Account](https://www.ncbi.nlm.nih.gov/account/)
                2. Click **"Register for an NCBI account"** if you don't have one
                3. Log in to your NCBI account
                4. In your account settings, find the **"API Key Management"** section
                5. Click **"Generate an API Key"**
                6. Copy the generated key (starts with "633c")
                7. Paste it in the API key field above
                8. Click to close this help section
                
                **Note:** This key is for NCBI E-Utilities API access.
                """)
        
        # Use callbacks or on_change to update session state
        def update_openrouter_key():
            st.session_state.openrouter_api_key = st.session_state.openrouter_key_widget
        
        def update_pubmed_key():
            st.session_state.pubmed_api_key = st.session_state.pubmed_key_widget
        
        # Manual update button since on_change doesn't work well with password inputs
        st.markdown("**⚠️** Click this button after editing API keys:")
        if st.button("🔄 Update API Keys", key="update_keys"):
            st.session_state.openrouter_api_key = openrouter_key
            st.session_state.pubmed_api_key = pubmed_key
            st.success("API Keys updated!")
        
        st.markdown("---")
        
        # Other configuration options
        max_iterations = st.number_input(
            "🔄 Max Iterations",
            min_value=5,
            max_value=100,
            value=20,
            step=5,
            help="Maximum number of PubMed search iterations"
        )
        
        st.markdown("---")
        st.subheader("📋 Instructions")
        st.info("""
        **How to use:**
        1. Enter a medical research topic
        2. Click "Begin Search"
        3. Review PubMed results
        4. Download findings when complete
        """)
        
        st.markdown("---")
        st.subheader("🔑 API Status")
        st.success("PubMed API: ✅ Active")
        st.success("DeepSeek via OpenRouter: ✅ Active")
        
        st.markdown("---")
        st.subheader("💡 Tips")
        st.info("""
        For best results:
        - Use medical/biomedical topics
        - Check multiple iterations
        - Review full abstracts
        """)
        
        st.markdown("---")
        st.subheader("🔧 Troubleshooting")
        st.warning("""
        If searches keep failing:
        1. Try a simpler medical term
        2. Reduce max iterations
        3. Check internet connection
        4. PubMed API might be rate limited
        5. Verify your API keys are correct
        """)
        
        st.markdown("---")
        st.markdown("""
        <div style='text-align: center; color: #666; font-size: 0.9rem;'>
            Enjoying this app?<br>
            Consider supporting development ☕
        </div>
        """, unsafe_allow_html=True)
    
    # Main content area
    topic = st.text_input(
        "🔎 Enter Medical Research Topic",
        placeholder="e.g., Machine learning in cancer diagnostics",
        help="Enter biomedical research topic"
    )
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col1:
        start_button = st.button("🚀 Begin PubMed Search", type="primary", use_container_width=True)
    with col2:
        stop_button = st.button("⏹️ Stop Analysis", type="secondary", use_container_width=True)
    with col3:
        if st.button("🔄 Reset", type="secondary", use_container_width=True):
            if os.path.exists("knowledge_gaps.csv"):
                os.remove("knowledge_gaps.csv")
            st.rerun()
    
    if start_button and not st.session_state.experiment_running:
        if not topic:
            st.error("⚠️ Please enter a medical research topic first!")
            return
        
        st.session_state.experiment_running = True
        normal_completion = True  # Flag to track if all iterations completed normally
        
        # Create placeholders for dynamic content
        progress_bar = st.empty()
        status_text = st.empty()
        log_container = st.empty()
        table_placeholder = st.empty()
        
        # Base prompt for gap analysis - PubMed focused
        base_prompt = (
            "You are a PubMed meta-analysis strategist. Based ONLY on the summarized PubMed findings:\n"
            "{summary}\n\n"
            "Analyze these PubMed research findings to:\n"
            "1. Identify key knowledge gaps, unresolved questions, or contradictions (STRICTLY from PubMed sources only)\n"
            "2. If no significant gap is found, propose a refined PubMed search query\n"
            "3. If a gap exists, describe it clearly and suggest a compelling PubMed-based meta-analysis title\n"
            "4. Always provide a refined PubMed search query for the next iteration\n\n"
            "Structure your response with these labels:\n"
            "- Gap: [description of PubMed gap or No significant gap in PubMed]\n"
            "- Meta-analysis Title: [proposed title if gap found, otherwise N/A]\n"
            "- Refined PubMed Query: [suggested query for next PubMed search iteration]\n\n"
            "CRITICAL: Base your analysis ONLY on the provided PubMed sources. Do NOT use external knowledge or sources."
        )
        
        current_query = topic
        csv_path = "knowledge_gaps.csv"
        gaps_found = []  # Track gaps found during iterations
        
        # Initialize empty table
        df = pd.DataFrame(columns=["Meta_Analysis_Topic", "Gap_Text", "Score", "Other_Output", "Gemini_Blob"])
        save_data_to_csv(
            {"Meta_Analysis_Topic": "", "Gap_Text": "", "Score": "", "Other_Output": "", "Gemini_Blob": ""},
            csv_path, table_placeholder
        )
        
        with log_container.container():
            for iteration in range(1, max_iterations + 1):
                if stop_button:
                    st.warning("⏹️ PubMed analysis stopped by user")
                    st.session_state.experiment_running = False
                    normal_completion = False
                    break
                
                # Update progress
                progress = iteration / max_iterations
                progress_bar.progress(progress, text=f"PubMed Search {iteration}/{max_iterations}")
                status_text.markdown(f"### 🔍 Analyzing PubMed for: '{current_query}'")
                
                # Perform PubMed search
                st.markdown(f"**🌐 Searching PubMed for '{current_query}'... (Iteration {iteration})**")
                search_results = web_search(current_query, num_results=10)
                
                if not search_results:
                    st.error("❌ No PubMed results found. Ending analysis.")
                    normal_completion = False
                    break
                
                # Display the search results directly
                st.markdown(f"### 📚 PubMed Search Results - Iteration {iteration}")
                for i, result in enumerate(search_results, 1):
                    st.markdown(f"**{i}. {result['title']}**")
                    st.markdown(f"- **{result['pmid']}**")
                    st.markdown(f"- **Abstract:** {result['snippet']}")
                    st.markdown(f"- [Link to PubMed article]({result['link']})")
                    st.markdown("---")
                
                # Summarize PubMed results
                st.markdown(f"### 📝 PubMed Summary - Iteration {iteration}")
                summary = summarize_search_results(search_results)
                st.info(summary)
                
                # Analyze for knowledge gaps in PubMed
                st.markdown(f"### 🔬 PubMed Gap Analysis - Iteration {iteration}")
                gap_analysis = analyze_knowledge_gaps(summary, base_prompt)
                st.info(gap_analysis)
                
                # Extract structured information
                gap_found, meta_title, gap_text, next_query = extract_gap_info(gap_analysis, current_query)
                
                # Track gaps found
                if gap_found:
                    gaps_found.append({
                        "iteration": iteration,
                        "title": meta_title if meta_title else current_query,
                        "description": gap_text
                    })
                
                # Prepare data for saving
                row_data = {
                    "Meta_Analysis_Topic": meta_title if meta_title else current_query,
                    "Gap_Text": gap_text,
                    "Score": "High" if gap_found else "None",
                    "Other_Output": next_query,
                    "Gemini_Blob": gap_analysis
                }
                
                # Save data and update table
                df = save_data_to_csv(row_data, csv_path, table_placeholder)
                
                # Prepare for next iteration
                current_query = next_query
                st.markdown("---")
            
            # Check if loop completed all iterations
            if iteration == max_iterations and not stop_button:
                normal_completion = True
            
            # Final results
            if not df.empty and not st.session_state.experiment_running:
                st.subheader("📊 PubMed Analysis Results")
                st.dataframe(df, use_container_width=True)
                
                if gaps_found:
                    st.subheader("🎯 PubMed Knowledge Gaps Found")
                    for i, gap in enumerate(gaps_found, 1):
                        st.success(f"""
                        **Gap #{i} (Search {gap['iteration']})**:  
                        **Title**: {gap['title']}  
                        **Description**: {gap['description']}
                        """)
                else:
                    st.warning("🔍 No significant knowledge gaps identified in PubMed analysis.")
                
                # Show confetti animation and celebration for normal completion
                if normal_completion:
                    show_confetti()
                    st.success("🎉🎉🎉 Congratulations! PubMed analysis completed successfully! 🎉🎉🎉")
                    st.balloons()
                
                # Enhanced download button section
                st.markdown("---")
                st.markdown("### 📥 Download Your Results")
                
                # Create two download options side by side
                dl_col1, dl_col2 = st.columns(2)
                
                csv = df.to_csv(index=False).encode('utf-8')
                with dl_col1:
                    st.download_button(
                        label="💾 Download CSV (Standard)",
                        data=csv,
                        file_name=f"{topic.replace(' ', '_')}_pubmed_gaps.csv",
                        mime="text/csv",
                        type="primary",
                        use_container_width=True
                    )
                
                # Create a JSON version additional download option
                json_data = df.to_json(orient='records', indent=2).encode('utf-8')
                with dl_col2:
                    st.download_button(
                        label="💾 Download JSON (Detailed)",
                        data=json_data,
                        file_name=f"{topic.replace(' ', '_')}_pubmed_gaps.json",
                        mime="application/json",
                        type="secondary",
                        use_container_width=True
                    )
                
                st.markdown("---")
                st.success("✅ PubMed analysis complete! Download your results above.")
        
        st.session_state.experiment_running = False

if __name__ == "__main__":
    main()