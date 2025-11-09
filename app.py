import streamlit as st
import requests
import json
from urllib.parse import urlparse

# --- Configuration ---
API_KEY = st.secrets["GOOGLE_API_KEY"]
CX = st.secrets["CSE_ID"]
RESULTS_PER_PAGE = 6
MAKE_WEBHOOK_URL = st.secrets["MAKE_WEBHOOK_URL"]

st.set_page_config(page_title="ScholarVerse | AI University & Scholarship Finder", layout="centered")

# --- Helper Function for Google Custom Search ---
def fetch_results(query, start=1, num=RESULTS_PER_PAGE):
    if not API_KEY or not CX:
        st.error("Missing API key or CX value.")
        return [], 0

    url = f"https://www.googleapis.com/customsearch/v1?key={API_KEY}&cx={CX}&q={query}&num={num}&start={start}"
    try:
        response = requests.get(url)
        response.raise_for_status()
        data = response.json()
        total = int(data.get("searchInformation", {}).get("totalResults", 0))
    except requests.exceptions.RequestException as e:
        st.error(f"Network error: {e}")
        return [], 0
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        return [], 0

    items = data.get("items", [])
    results = []
    for item in items:
        image = item.get("pagemap", {}).get("cse_image", [{}])[0].get("src", "")
        if not image:
            image = item.get("pagemap", {}).get("organization", [{}])[0].get("logo", "")
        results.append({
            "title": item["title"],
            "link": item["link"],
            "snippet": item.get("snippet", ""),
            "image": image or "https://via.placeholder.com/300x200.png?text=No+Image"
        })
    return results, total


# --- Send Data to Make.com (Gemini Analysis) ---
def send_to_make(profile_data, search_results):
    try:
        payload = {
            "user_profile": profile_data,
            "search_results": search_results
        }
        headers = {"Content-Type": "application/json"}

        response = requests.post(MAKE_WEBHOOK_URL, data=json.dumps(payload), headers=headers, timeout=40)

        if response.status_code != 200:
            st.error(f"Make.com returned error: {response.status_code} - {response.text}")
            return None

        try:
            data = response.json()
            if isinstance(data, dict) and "ai_feedback" in data:
                return data["ai_feedback"]
            else:
                return json.dumps(data, indent=2)
        except ValueError:
            return response.text.strip()

    except Exception as e:
        st.error(f"Error sending data to Make.com: {e}")
        return None


# --- UI & CSS ---
st.markdown("""
<link href="https://fonts.googleapis.com/css2?family=Noto+Sans:wght@700&display=swap" rel="stylesheet">
<style>
[data-testid="stAppViewContainer"] {
background-image: linear-gradient(to top, lightgrey 0%, lightgrey 1%, #e0e0e0 26%, #efefef 48%, #d9d9d9 75%, #bcbcbc 100%);
}
.title {
    font-family: 'Noto Sans', sans-serif;
    font-size: 72px;
    text-align: center;
    background: linear-gradient(90deg, #37474f, #607d8b);
    -webkit-background-clip: text;
    -webkit-text-fill-color: transparent;
    font-weight: 900;
    margin-top: -20px;
}
.subtitle {
    font-size: 18px;
    text-align: center;
    color: #37474f;
    max-width: 1000px;
    margin: 10px auto 40px auto;
    line-height: 1.6;
}
.card {
    background: rgba(255, 255, 255, 0.1);
    backdrop-filter: blur(10px);
    border-radius: 15px;
    padding: 20px;
    margin: 10px;
    transition: transform 0.3s, box-shadow 0.3s;
    box-shadow: 0 8px 32px 0 rgba(31, 38, 135, 0.37);
    min-height: 380px;
    color: #4e5252;
}
.card:hover {
    transform: translateY(-8px);
    box-shadow: 0 12px 40px 0 rgba(31, 38, 135, 0.6);
}
.card img {
    width: 100%;
    height: 180px;
    object-fit: cover;
    border-radius: 10px;
    margin-bottom: 10px;
}
.card-title {
    font-size: 17px;
    font-weight: bold;
    color: #4e5252;
    margin-bottom: 5px;
}
.card-title a {
    color: #4e5252;
    text-decoration: none;
    display: -webkit-box;
    -webkit-line-clamp: 3;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
    min-height: 44px;
}
.card-snippet {
    font-size: 14px;
    color: #4e5252;
    display: -webkit-box;
    -webkit-line-clamp: 4;
    -webkit-box-orient: vertical;
    overflow: hidden;
    text-overflow: ellipsis;
    min-height: 60px;
}
footer {
    text-align: center;
    font-size: 14px;
    color: #607d8b;
    margin-top: 50px;
}
</style>
""", unsafe_allow_html=True)

# --- Title ---
st.markdown("""
<h1 class="title">ScholarVerse</h1>
<p class="subtitle">
<strong>Tired of endlessly searching for the right university, scholarship, or funding program?<br>
Just search your interest and let <b>ScholarVerse</b> connect you with opportunities worldwide.</strong>
</p>
""", unsafe_allow_html=True)


# --- Search Input ---
with st.container():
    col_search, col_btn = st.columns([5, 1])
    with col_search:
        query_input = st.text_input("Search for opportunities", label_visibility="collapsed",
                                    placeholder="Type your degree and program (e.g., 'MS Physics in USA')")
    with col_btn:
        search_clicked = st.button("Search", key="search_btn", use_container_width=True)

# --- Session State ---
if "start_index" not in st.session_state:
    st.session_state.start_index = 1
if "all_results" not in st.session_state:
    st.session_state.all_results = []
if "total_results" not in st.session_state:
    st.session_state.total_results = 0
if "current_query" not in st.session_state:
    st.session_state.current_query = ""
if "has_searched" not in st.session_state:
    st.session_state.has_searched = False


def get_root_domain(url):
    try:
        domain = urlparse(url).netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except:
        return url


def handle_search(is_load_more=False):
    if not is_load_more:
        base_query = query_input.strip()
        if not base_query:
            st.warning("Please enter a search query.")
            return

        query_lower = base_query.lower()
        degree_level = ""
        country_filter = ""
        site_filter = ""

        if any(term in query_lower for term in ["bs", "bsc", "bachelor", "undergraduate"]):
            degree_level = '("BS" OR "BSc" OR "Bachelor" OR "Undergraduate")'
        elif any(term in query_lower for term in ["ms", "msc", "master", "graduate"]):
            degree_level = '("MS" OR "MSc" OR "Master" OR "Graduate")'
        elif any(term in query_lower for term in ["phd", "doctorate", "doctoral"]):
            degree_level = '("PhD" OR "Doctorate" OR "Doctoral")'

        if "usa" in query_lower or "united states" in query_lower:
            site_filter = "(site:.edu OR site:.us)"
            country_filter = '"United States" OR "USA"'
        elif "uk" in query_lower or "united kingdom" in query_lower:
            site_filter = "site:.ac.uk"
            country_filter = '"United Kingdom" OR "UK"'
        elif "canada" in query_lower:
            site_filter = "site:.ca"
            country_filter = '"Canada"'
        elif "australia" in query_lower:
            site_filter = "site:.edu.au"
            country_filter = '"Australia"'

        refined_query = (
            f'"{base_query.strip()}" {degree_level} "University" {country_filter} {site_filter} '
            '-"financial aid" -"scholarships" -"funding" -"jobs" -"forum" -"application tips" -"visa" -pdf'
        )

        st.session_state.current_query = refined_query
        st.session_state.start_index = 1
        st.session_state.all_results = []
        st.session_state.has_searched = True

    results, total = fetch_results(st.session_state.current_query, start=st.session_state.start_index)

    new_results_combined = st.session_state.all_results + results
    unique_domains = set()
    deduplicated_results = []

    for r in new_results_combined:
        domain = get_root_domain(r["link"])
        snippet = r.get("snippet", "").lower()
        if domain in unique_domains:
            continue
        unique_domains.add(domain)
        if any(k in snippet for k in ["program", "course", "curriculum", "department", "admissions", "overview"]):
            deduplicated_results.append(r)
        elif len(urlparse(r["link"]).path.strip("/").split("/")) <= 1:
            deduplicated_results.append(r)

    st.session_state.all_results = deduplicated_results
    st.session_state.total_results = total
    st.session_state.start_index += RESULTS_PER_PAGE


if search_clicked:
    handle_search(False)


def display_results(results):
    if not st.session_state.has_searched:
        return
    if not results:
        st.info("No results found. Try a different search term.")
        return

    for i in range(0, len(results), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            if i + j < len(results):
                r = results[i + j]
                with col:
                    st.markdown(f"""
                        <div class="card">
                            <img src="{r['image']}">
                            <div class="card-title">
                                <a href="{r['link']}" target="_blank">{r['title']}</a>
                            </div>
                            <div class="card-snippet">{r['snippet']}</div>
                        </div>
                    """, unsafe_allow_html=True)


display_results(st.session_state.all_results)

if st.session_state.all_results and st.session_state.start_index <= st.session_state.total_results:
    st.button("Load More", on_click=handle_search, args=[True], key="load_more_btn")

# --- Profile Analyzer ---
st.markdown("---")
st.markdown("## Analyze Your Profile")
st.markdown("""
Want to know which universities best fit your background and how to improve your chances? 
Fill out your details below and let ScholarVerse’s AI evaluate your profile.
""")

with st.form("profile_form"):
    col1, col2 = st.columns(2)
    with col1:
        major = st.text_input("Current Degree", placeholder="e.g. Computer Science, Business Analytics")
        skills = st.text_input("Key Skills / Courses", placeholder="e.g. Data Mining, Deep Learning")
    with col2:
        gpa = st.text_input("GPA / Grades", placeholder="e.g. 3.7 / 4.0 or 85%")
        projects = st.text_input("Achievements / Projects", placeholder="e.g. Internships, Research Papers")
    more_details = st.text_area("Additional Details (optional)",
                                placeholder="Goals, region preference, scholarship interests, etc.",
                                height=100)
    submit_profile = st.form_submit_button("Analyze My Profile")

if submit_profile:
    if not gpa or not major:
        st.warning("Please fill in at least your GPA and Major to continue.")
    else:
        user_profile = {
            "gpa": gpa,
            "major": major,
            "skills": skills,
            "projects": projects,
            "details": more_details
        }
        st.info("Sending your data to Make.com for AI analysis...")
        with st.spinner("Analyzing your profile and matching programs..."):
            ai_feedback = send_to_make(user_profile, st.session_state.all_results)
        if ai_feedback:
            st.success("Personalized AI recommendations received!")
            st.markdown('<b>AI Analysis Result:</b>', unsafe_allow_html=True)
            st.markdown(ai_feedback)
        else:
            st.warning("No valid response received yet. Please check your Make.com scenario or webhook.")

st.markdown('<footer>Developed by <b>Qasim</b> | ScholarVerse © 2025</footer>', unsafe_allow_html=True)
