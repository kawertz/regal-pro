# v1.2 RC Stable
import streamlit as st
import json
import math
import pgeocode
import time
import os
import sys
from datetime import datetime, timedelta, timezone, time as dt_time
from curl_cffi import requests as c_requests

IS_CLOUD = os.getenv('USER') == 'appuser' or "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION" in os.environ

# --- Resource Path Resolution for Desktop Executable ---
def get_resource_path(relative_path):
    """ Get absolute path to resource, works for dev and for bundled EXE """
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Page Configuration ---
st.set_page_config(page_title="Regal Reactive Pro", layout="wide")

# --- CSS for Navigation ---
st.markdown("""
    <style>
    .stRadio > div[role="radiogroup"] {
        flex-direction: row; gap: 2rem; background-color: #f0f2f6;
        padding: 10px 20px; border-radius: 10px; margin-bottom: 20px;
    }
    .stRadio [data-testid="stMarkdownContainer"] p { font-size: 1.1rem; font-weight: 600; }
    </style>
""", unsafe_allow_html=True)

# --- Constants & Headers ---
THEATERS_FILE = get_resource_path("theatre_list.json")
BASE_REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:145.0) Gecko/20100101 Firefox/145.0",
    "Accept": "*/*", "Accept-Language": "en-US,en;q=0.5", "Referer": "https://www.regmovies.com/",
}

# --- Utility Functions ---

@st.cache_data(ttl=300) # Cache for 5 minutes to save proxy data
def get_proxy_health():
    if not IS_CLOUD:
        return "Local Bypass", "System IP"
    
    try:
        p_user = st.secrets["proxy"]["username"]
        p_pass = st.secrets["proxy"]["password"]
        p_addr = st.secrets["proxy"]["address"]
        p_port = st.secrets["proxy"]["port"]
        
        auth_user = f"user-{p_user}-session-healthcheck"
        proxy_url = f"http://{auth_user}:{p_pass}@{p_addr}:{p_port}"
        proxies = {"http": proxy_url, "https": proxy_url}
        
        test_resp = c_requests.get(
            "https://httpbin.org/ip", 
            proxies=proxies, 
            impersonate="chrome120", 
            timeout=10
        )
        
        if test_resp.status_code == 200:
            return "Active", test_resp.json().get('origin')
        return "Connection Error", "None"
    except Exception:
        return "Offline / Config Error", "None"

@st.cache_data
def load_theaters():
    try:
        with open(THEATERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("theatre_list", [])
    except Exception as e:
        st.error(f"Error loading theater list: {e}"); return []

def get_offset_from_lon(lon):
    if lon > -82.5: return -5    # Eastern
    if lon > -97.5: return -6    # Central
    if lon > -114.0: return -7   # Mountain
    if lon > -125.0: return -8   # Pacific
    if lon < -150.0: return -10  # Hawaii
    if lon < -140.0: return -9   # Alaska
    return -5 # Default to EST

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    R = 3958.8 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def fetch_data(api_url, path_name, max_retries=3):

    proxies = None

    if IS_CLOUD:
        try:
            p_user = st.secrets["proxy"]["username"]
            p_pass = st.secrets["proxy"]["password"]
            p_addr = st.secrets["proxy"]["address"]
            p_port = st.secrets["proxy"]["port"]

            if "proxy_session_id" not in st.session_state:
                st.session_state.proxy_session_id = f"regal_pro_{os.urandom(4).hex()}"
            
            auth_user = f"user-{p_user}-session-{st.session_state.proxy_session_id}"
            proxy_url = f"http://{auth_user}:{p_pass}@{p_addr}:{p_port}"
            proxies = {"http": proxy_url, "https": proxy_url}

            
        except KeyError:
            st.error("Proxy secrets not configured!")
            return None

    headers = BASE_REQUEST_HEADERS.copy()
    headers["Referer"] = f"https://www.regmovies.com/theatres/{path_name}"
    for attempt in range(max_retries):
        try:
            session = c_requests.Session()
            response = session.get(api_url, 
                                   headers=headers, 
                                   impersonate="chrome120", 
                                   proxies=proxies,
                                   timeout=30)
            if response.status_code == 200: 
                return response.json()
            if response.status_code == 403:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    st.error("Access Denied (403). Regal is blocking the request.")
                    return None
            response.raise_for_status()
        except:
            if attempt < max_retries - 1: time.sleep(1); continue
            return None
    return None

def flatten_data(data):
    flat_list = []
    raw_attrs_list = data.get('attributes', [])
    attr_map = {a.get('Acronym', '').strip(): a.get('ShortName', '').strip() 
                for a in raw_attrs_list if a.get('Acronym')}

    movie_meta = {}
    for m in data.get('movies', []):
        open_date_raw = m.get('RegalOpeningDate')
        dt_obj = datetime(2099, 12, 31) 
        formatted_date = "TBD"
        
        if open_date_raw:
            try:
                dt_obj = datetime.strptime(open_date_raw[:10], "%Y-%m-%d")
                formatted_date = dt_obj.strftime("%b %d, %Y")
            except: pass

        movie_meta[m['MasterMovieCode']] = {
            'title': m.get('Title', 'Unknown'),
            'rating': m.get('Rating', 'NR'), 
            'duration': int(m.get('Duration', '0')),
            'opening_date_str': formatted_date,
            'opening_date_dt': dt_obj
        }
    
    shows = data.get("shows", [])
    active_movie_codes = set()
    
    if shows:
        for movie in shows[0].get("Film", []):
            m_code = movie.get('MasterMovieCode')
            active_movie_codes.add(m_code)
            meta = movie_meta.get(m_code, {'rating': 'NR', 'duration': 0})
            for perf in movie.get("Performances", []):
                show_dt = datetime.strptime(perf["CalendarShowTime"], "%Y-%m-%dT%H:%M:%S")
                raw_codes = perf.get("PerformanceAttributes", [])
                expanded_names = sorted([attr_map.get(c.strip(), c) for c in raw_codes])
                
                flat_list.append({
                    "Title": movie['Title'], "Rating": meta['rating'], "Duration": meta['duration'],
                    "Showtime": show_dt, "Auditorium": str(perf.get("Auditorium", "?")),
                    "ScreenType": perf.get("PerformanceGroup") or "2D",
                    "Attributes": ", ".join(expanded_names),
                    "raw_attrs": set(expanded_names),
                    "master_code": m_code
                })
                
    future_data_map = {}
    for fs in data.get("futureShows", []):
        m_code = fs.get('hoCode')
        formatted_dates = []
        
        for d_entry in fs.get('dates', []):
            raw_date = d_entry.get('date')
            if raw_date:
                try:
                    dt_obj = datetime.strptime(raw_date[:10], "%m-%d-%Y")
                    formatted_dates.append(dt_obj.strftime("%b %d"))
                except:
                    formatted_dates.append(raw_date)
        
        future_data_map[m_code] = formatted_dates
    
    future_movies = []
    for code, meta in movie_meta.items():
        if code not in active_movie_codes:
            meta['scheduled_dates'] = future_data_map.get(code, [])
            future_movies.append(meta)
    
    future_movies.sort(key=lambda x: x['opening_date_dt'])

    return flat_list, movie_meta, attr_map, future_movies

def get_attr_diff_html(screening_attrs, common_attrs):
    s_set = set([a.strip() for a in screening_attrs.split(",") if a.strip()])
    diff = s_set - common_attrs
    if not diff: return ""
    diff_str = ", ".join(sorted(diff))
    return f' <small style="color:grey">({diff_str})</small>'

def get_time_options():
    times = []
    start = datetime.strptime("00:00", "%H:%M")
    for _ in range(288): 
        times.append(start.strftime("%H:%M")); start += timedelta(minutes=5)
    return times

def generate_ics(path, theater_name):
    ics_lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Regal Pro//EN", "CALSCALE:GREGORIAN", "METHOD:PUBLISH"]
    for s in path:
        start_t = s['Showtime'].strftime("%Y%m%dT%H%M%S")
        end_t = (s['Showtime'] + timedelta(minutes=s['Duration'])).strftime("%Y%m%dT%H%M%S")
        ics_lines.extend(["BEGIN:VEVENT", f"DTSTART:{start_t}", f"DTEND:{end_t}", f"SUMMARY:{s['Title']} ({s['ScreenType']})", f"LOCATION:{theater_name} - Audi {s['Auditorium']}", "END:VEVENT"])
    ics_lines.append("END:VCALENDAR")
    return "\n".join(ics_lines)

def find_itineraries(current_path, remaining_titles, screenings, p, selected_date):
    valid_paths = []
    window_start = datetime.combine(selected_date, p['start'])
    window_end = datetime.combine(selected_date, p['end'])
    if window_end <= window_start: window_end += timedelta(days=1)
    elif p['end'] == dt_time(23, 59): window_end += timedelta(hours=6)

    for title in remaining_titles:
        potential_shows = [s for s in screenings if s['Title'] == title]
        if p['formats']: potential_shows = [s for s in potential_shows if s['ScreenType'] in p['formats']]
        for s in potential_shows:
            show_start = s['Showtime']
            show_end = show_start + timedelta(minutes=s['Duration'])
            if show_start < window_start or show_end > window_end: continue
            if current_path:
                prev = current_path[-1]
                prev_end = prev['Showtime'] + timedelta(minutes=prev['Duration'])
                if p['fudge']: prev_end -= timedelta(minutes=5)
                req_buffer = p['long_buffer'] if p['break_after'] == len(current_path) else p['buffer']
                if p['unlimited']:
                    if show_start < prev['Showtime'] + timedelta(minutes=91): continue
                if show_start < prev_end + timedelta(minutes=req_buffer): continue
                if (show_start - prev_end).total_seconds()/60 > p['gap_cap']: continue
            new_rem = [t for t in remaining_titles if t != title]
            sub = find_itineraries(current_path + [s], new_rem, screenings, p, selected_date)
            if not sub: valid_paths.append(current_path + [s])
            else: valid_paths.extend(sub)
    return valid_paths

def get_conflict_report(path, missing_titles, all_screenings, p):
    conflicts = []
    for m_title in missing_titles:
        m_shows = [s for s in all_screenings if s['Title'] == m_title]
        if p['formats']: m_shows = [s for s in m_shows if s['ScreenType'] in p['formats']]
        reasons = []
        if not m_shows: reasons.append("No screenings match your selected formats.")
        else:
            for ms in m_shows:
                for ps in path:
                    ps_end = ps['Showtime'] + timedelta(minutes=ps['Duration'])
                    if not (ms['Showtime'] + timedelta(minutes=ms['Duration']) <= ps['Showtime'] or ms['Showtime'] >= ps_end):
                        reasons.append(f"The {ms['Showtime'].strftime('%I:%M %p')} show overlaps with **{ps['Title']}**.")
                        break
        conflicts.append(f"❌ **{m_title}**: {reasons[0] if reasons else 'No screenings fit your window.'}")
    return conflicts

# --- Main App ---

st.title("🎬 Regal Reactive Pro")
theaters = load_theaters()
url_t_code = st.query_params.get("theater")

st.sidebar.header("📍 Find Theater")

search_mode = st.sidebar.selectbox("Search By", ["Zip Code", "Theater Name", "Address/City", "Theater Code"])

results = []
search_performed = False

if search_mode == "Zip Code":
    zip_in = st.sidebar.text_input("Zip Code", placeholder="46201")
    radius_in = st.sidebar.slider("Radius (miles)", 5, 200, 50)
    if zip_in:
        search_performed = True
        nomi = pgeocode.Nominatim('us')
        z_data = nomi.query_postal_code(zip_in)

        if not math.isnan(z_data['latitude']):
            new_offset = get_offset_from_lon(z_data['longitude'])
            st.session_state.auto_tz_offset = new_offset
            for t in theaters:
                d = calculate_haversine_distance(z_data['latitude'], z_data['longitude'], t['item']['latitude'], t['item']['longitude'])
                if d <= radius_in: results.append((t, d))
            results.sort(key=lambda x: x[1])

elif search_mode == "Theater Name":
    name_in = st.sidebar.text_input("Theater Name")
    if name_in: search_performed = True; results = [t for t in theaters if name_in.lower() in t['item']['name'].lower()]
elif search_mode == "Address/City":
    addr_in = st.sidebar.text_input("Address, City, or State")
    if addr_in: search_performed = True; results = [t for t in theaters if any(addr_in.lower() in t['item'].get(f, '').lower() for f in ['address', 'city', 'state'])]
elif search_mode == "Theater Code":
    code_in = st.sidebar.text_input("Theater Code")
    if code_in: search_performed = True; results = [t for t in theaters if code_in == t['item']['theatre_code']]

if search_performed and not results: st.sidebar.warning("No theaters found matching your criteria.")

selected_theater = None
if url_t_code and not results:
    match = next((t for t in theaters if t['item']['theatre_code'] == url_t_code), None)
    if match: results = [match]

if results:
    opts = {f"{r[0]['item']['name'] if isinstance(r, tuple) else r['item']['name']} - {r[0]['item']['city'] if isinstance(r, tuple) else r['item']['city']}": (r[0] if isinstance(r, tuple) else r) for r in results}
    idx = 0
    for i, t in enumerate(opts.values()):
        if t['item']['theatre_code'] == url_t_code: idx = i
    sel_label = st.sidebar.selectbox("Select Theater", options=list(opts.keys()), index=idx)
    selected_theater = opts[sel_label]

if selected_theater:
    t_item = selected_theater['item']
    st.query_params["theater"] = t_item['theatre_code']
    q_date = st.sidebar.date_input("Select Date", value=datetime.today())

    t_lon = selected_theater['item'].get('longitude')
    if t_lon:
        st.session_state.auto_tz_offset = get_offset_from_lon(t_lon)

    with st.sidebar.expander("⚙️ Advanced Settings", expanded=False):
        st.write("🕒 Timezone Settings")
        local_now = datetime.now()
        utc_now = datetime.now(timezone.utc).replace(tzinfo=None)
        system_offset = round((local_now - utc_now).total_seconds() / 3600)
        default_offset = st.session_state.get('auto_tz_offset', system_offset)
        tz_offset = st.number_input("Selected Location Offset from UTC", value=int(default_offset), step=1)
        current_local_time = (datetime.now(timezone.utc) + timedelta(hours=tz_offset)).replace(tzinfo=None)
        st.write(f"Local Time for Selected Location: **{current_local_time.strftime('%I:%M %p')}**")
        st.divider()
        if st.button("🔄 Force Refresh"): st.session_state.last_fetch_key = None
        print_mode = st.checkbox("🖨️ Print View")
        debug_mode = st.checkbox("🐞 Debug Mode", value=False, help="Show raw API responses for troubleshooting.")
        status_label, ext_ip = get_proxy_health()
        
        if status_label == "Active":
            st.success(f"🌐 **Proxy:** {status_label}")
            st.caption(f"Masked IP: `{ext_ip.split(',')[0]}`")
        elif status_label == "Local Bypass":
            st.info(f"🏠 **Mode:** {status_label}")
            st.caption("Direct Connection Active")
        else:
            st.error(f"⚠️ **Proxy:** {status_label}")
            st.caption("Check Streamlit Secrets or Decodo Balance")

    f_key = f"{t_item['theatre_code']}_{q_date.strftime('%m-%d-%Y')}"
    if st.session_state.get('last_fetch_key') != f_key:
        with st.spinner("Fetching Data..."):
            data = fetch_data(f"https://www.regmovies.com/api/getShowtimes?theatres={t_item['theatre_code']}&date={q_date.strftime('%m-%d-%Y')}", t_item['path_name'])
            if data: st.session_state.raw_data, st.session_state.last_fetch_key = data, f_key

if 'raw_data' in st.session_state:
    # --- Debug Mode Output ---
    if debug_mode:
        with st.expander("🛠️ Raw API Debug Output", expanded=True):
            st.json(st.session_state.raw_data)

if 'raw_data' in st.session_state:
    flat_data, movie_meta, attr_map, future_movies = flatten_data(st.session_state.raw_data)
    nav_tab = st.radio("Navigation", ["🔎 Theater Explorer", "🗓️ Smart Scheduler"], horizontal=True, label_visibility="collapsed", key="active_nav")

    if nav_tab == "🔎 Theater Explorer":
        if print_mode: st.markdown("<style>[data-testid='stSidebar'], [data-testid='stHeader'] {display: none;} .stExpander {border: none !important;}</style>", unsafe_allow_html=True)
        st.subheader("🔎 Theater Explorer")
        st.info(f"Viewing: **{t_item['name']}** on **{q_date.strftime('%A, %b %d')}**")
        
        with st.expander("🔍 Filters & Sorting", expanded=not print_mode):
            c1, c2, c3, c4 = st.columns(4)
            with c1:
                f_type = st.multiselect("Screen Type", options=sorted(list(set(s['ScreenType'] for s in flat_data))), placeholder="All")
                f_rating = st.multiselect("Rating", options=sorted(list(set(s['Rating'] for s in flat_data))), placeholder="All")
            with c2:
                f_audi = st.multiselect("Auditorium", options=sorted(list(set(s['Auditorium'] for s in flat_data)), key=lambda x: int(x) if x.isdigit() else 999), placeholder="All")
                current_st = set(f_type) if f_type else set(s['ScreenType'] for s in flat_data)
                all_expanded_attrs = set(a for s in flat_data for a in s['raw_attrs'])
                deduped_attrs = sorted([a for a in all_expanded_attrs if a not in current_st])
                f_attr = st.multiselect("Additional Filters", options=deduped_attrs, placeholder="All")
            with c3:
                t_ranges = {"8AM - 12N": (8, 12), "12N - 4PM": (12, 16), "4PM - 8PM": (16, 20), "8PM - 12M": (20, 24)}
                f_times = st.multiselect("Time Window", options=list(t_ranges.keys()), placeholder="All")
                f_avail = st.checkbox("Hide past shows", value=True)
            with c4:
                sort_by = st.selectbox("Sort By", ["Movie Title", "Showtime", "Auditorium"])
                view_mode = st.selectbox("View Mode", ["Group by Movie", "Group by Auditorium", "Full Schedule"])

        filtered = [s for s in flat_data if (not f_type or s['ScreenType'] in f_type) and (not f_rating or s['Rating'] in f_rating) and (not f_audi or s['Auditorium'] in f_audi) and (not f_attr or set(f_attr).issubset(s['raw_attrs'])) and (not f_times or any(t_ranges[t][0] <= s['Showtime'].hour < t_ranges[t][1] for t in f_times)) and (not f_avail or (s['Showtime'] > current_local_time if q_date == current_local_time.date() else True))]
        
        if sort_by == "Movie Title": filtered.sort(key=lambda x: (x['Title'], x['Showtime']))
        elif sort_by == "Showtime": filtered.sort(key=lambda x: (x['Showtime'], x['Title']))
        elif sort_by == "Auditorium": filtered.sort(key=lambda x: (int(x['Auditorium']) if x['Auditorium'].isdigit() else 999, x['Showtime']))
        
        st.write(f"Showing **{len(set(s['Title'] for s in filtered))}** movies and **{len(filtered)}** screenings.")

        if view_mode == "Full Schedule":
            for s in filtered:
                with st.container(border=True):
                    col_t, col_info = st.columns([1.3, 5])
                    col_t.markdown(f"""<div style="line-height: 1;"><p style="color: grey; font-size: 0.8rem; margin-bottom: 2px; text-transform: uppercase; font-weight: bold;">{s['ScreenType']}</p><p style="font-size: 1.4rem; font-weight: 700; margin: 0; white-space: nowrap;">{s['Showtime'].strftime('%I:%M %p')}</p></div>""", unsafe_allow_html=True)
                    col_info.markdown(f"### {s['Title']}")
                    col_info.markdown(f"**{s['Rating']}** | **{s['Duration']} min** | Audi {s['Auditorium']}")
                    if s['Attributes']: st.markdown(f'<p style="color: grey; font-size: 0.85em; margin-top: -10px;">{s["Attributes"]}</p>', unsafe_allow_html=True)
        elif view_mode == "Group by Auditorium":
            for audi in sorted(list(set(s['Auditorium'] for s in filtered)), key=lambda x: int(x) if x.isdigit() else 999):
                with st.expander(f"🖼️ Auditorium {audi}", expanded=True):
                    for s in sorted([s for s in filtered if s['Auditorium'] == audi], key=lambda x: x['Showtime']):
                        col_t, col_info = st.columns([1, 5])
                        col_t.code(s['Showtime'].strftime('%I:%M %p')); col_info.markdown(f"**{s['Title']}** ({s['ScreenType']}) — {s['Duration']}m")
        else: # Group by Movie
            for title in list(dict.fromkeys([s['Title'] for s in filtered])):
                m_shows = [s for s in filtered if s['Title'] == title]
                with st.expander(f"🍿 {title} ({m_shows[0]['Rating']}) — {m_shows[0]['Duration']} min", expanded=True):
                    for mt in sorted(list(set(s['ScreenType'] for s in m_shows))):
                        ts = [s for s in m_shows if s['ScreenType'] == mt]
                        common = set.intersection(*(s['raw_attrs'] for s in ts)) if ts else set()
                        st.markdown(f'<div style="background-color: #f0f2f6; padding: 4px 12px; border-radius: 4px; border-left: 4px solid #ff4b4b; margin-bottom: 6px;"><span style="font-weight: bold;">{mt}</span> <span style="color: grey; font-size: 0.85em; font-weight: normal; margin-left: 10px;">({", ".join(sorted(common)) if common else ""})</span></div>', unsafe_allow_html=True)
                        row = [f"**{s['Showtime'].strftime('%I:%M %p')}** (Audi {s['Auditorium']}){get_attr_diff_html(s['Attributes'], common)}" for s in ts]
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{' | '.join(row)}", unsafe_allow_html=True)

        if future_movies:
            st.markdown("---")
            st.subheader("📅 Other Upcoming Titles")
            st.caption("Sorted by Opening Date")
            cols = st.columns(3)
            for i, f_movie in enumerate(future_movies):
                with cols[i % 3]:
                    with st.container(border=True):
                        st.markdown(f"**{f_movie['title']}** ({f_movie['rating']})")
                        if f_movie.get('scheduled_dates'):
                            dates_str = ", ".join(f_movie['scheduled_dates'])
                            st.markdown(f"<small style='color:red'>Scheduled Dates: {dates_str}</small>", unsafe_allow_html=True)
                        else:
                            st.markdown(f"<small style='color:red'>Opening: {f_movie['opening_date_str']}</small>", unsafe_allow_html=True)
                        st.caption(f"{f_movie['duration']} min")
                        
    elif nav_tab == "🗓️ Smart Scheduler":
        st.subheader("🗓️ Smart Scheduler")
        st.info(f"Scheduling: **{t_item['name']}** on **{q_date.strftime('%A, %b %d')}**")
        with st.expander("⚙️ Parameters", expanded=True):
            r1_c1, r1_c2 = st.columns(2)
            with r1_c1:
                target_movies = st.multiselect("Select Movies (Ordered by Preference)", options=sorted(list(set(s['Title'] for s in flat_data))))
            with r1_c2:
                available_formats = sorted(list(set(s['ScreenType'] for s in flat_data if s['Title'] in target_movies))) if target_movies else sorted(list(set(s['ScreenType'] for s in flat_data)))
                target_formats = st.multiselect("Preferred Formats", options=available_formats, placeholder="All")
            
            time_opts = ["Any Time"] + get_time_options()
            c1, c2, c3 = st.columns(3)
            with c1: 
                sel_start = st.selectbox("Earliest Start", options=time_opts, index=0)
                sel_end = st.selectbox("Latest End", options=time_opts, index=0)
                t_start = dt_time(0, 0) if sel_start == "Any Time" else datetime.strptime(sel_start, "%H:%M").time()
                t_end = dt_time(23, 59) if sel_end == "Any Time" else datetime.strptime(sel_end, "%H:%M").time()
            with c2: buff = st.slider("Buffer (min)", 0, 60, 15); g_cap = st.slider("Max Gap (min)", 30, 240, 120)
            with c3: unlimited = st.checkbox("Regal Unlimited Rule (90-min Rule)"); fudge = st.checkbox("Fudge Factor (5-min overlap)")
            
            c_b1, c_b2 = st.columns(2)
            with c_b1: 
                n_movies = len(target_movies)
                break_opts = [None] + list(range(1, n_movies)) if n_movies > 1 else [None]
                b_after = st.selectbox("Long break after movie #", options=break_opts)
            with c_b2: b_val = st.slider("Break duration (min)", 30, 120, 60)
        
        if st.button("🚀 Generate Itineraries"):
            if len(target_movies) < 2:
                st.error("Please select at least 2 movies to generate a schedule.")
            else:
                params = {'start': t_start, 'end': t_end, 'buffer': buff, 'gap_cap': g_cap, 'unlimited': unlimited, 'fudge': fudge, 'break_after': b_after, 'long_buffer': b_val, 'formats': target_formats}
                paths = find_itineraries([], target_movies, flat_data, params, q_date)
                
                if not paths: st.error("No valid schedules found.")
                else:
                    weights = {title: 10**(len(target_movies) - 1 - i) for i, title in enumerate(target_movies)}
                    processed_paths = []
                    for p in paths:
                        p_titles = [s['Title'] for s in p]
                        priority_score = sum(weights.get(t, 0) for t in p_titles)
                        gap_time = sum([(p[i+1]['Showtime'] - (p[i]['Showtime'] + timedelta(minutes=p[i]['Duration']))).total_seconds()/60 for i in range(len(p)-1)])
                        processed_paths.append({
                            'path': p, 'priority_score': priority_score, 'count': len(p), 'gap_time': gap_time, 
                            'id': "-".join([f"{s['master_code']}{s['Showtime'].timestamp()}" for s in p])
                        })
                    
                    top_priority = sorted(processed_paths, key=lambda x: (-x['priority_score'], x['gap_time']))
                    top_count = sorted(processed_paths, key=lambda x: (-x['count'], x['gap_time']))
                    
                    final_options = []
                    seen_ids = set()
                    for entry in top_priority[:2]:
                        final_options.append((entry, "Priority Match"))
                        seen_ids.add(entry['id'])
                    max_possible_count = top_count[0]['count']
                    p1_count = top_priority[0]['count']
                    if max_possible_count >= p1_count and top_count[0]['id'] not in seen_ids:
                        final_options.append((top_count[0], "Movie Marathon (Max Count)"))
                    else:
                        if len(top_priority) > 2: final_options.append((top_priority[2], "Priority Match"))

                    for i, (entry, label) in enumerate(final_options):
                        path, count = entry['path'], entry['count']
                        with st.container(border=True):
                            st.markdown(f"#### Option {i+1}: {count} Movies — <small style='color:grey'>{label}</small>", unsafe_allow_html=True)
                            for s in path: st.write(f"🕒 **{s['Showtime'].strftime('%I:%M %p')} - {(s['Showtime'] + timedelta(minutes=s['Duration'])).strftime('%I:%M %p')}**: {s['Title']} (**{s['ScreenType']}**)")
                            st.download_button("📅 Download ICS", generate_ics(path, t_item['name']), file_name=f"movies_{q_date}.ics", mime="text/calendar", key=f"dl_{i}")
                            if count < len(target_movies):
                                missing = [t for t in target_movies if t not in [s['Title'] for s in path]]
                                with st.expander("⚠️ Why were some movies left out?"):
                                    report = get_conflict_report(path, missing, flat_data, params)
                                    for line in report: st.write(line)
else: st.info("Search for a theater in the sidebar to begin.")