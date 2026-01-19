# v1.5 RC
import streamlit as st
import json
import math
import pgeocode
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import time
import os
import sys
from datetime import datetime, timedelta, timezone, time as dt_time
from curl_cffi import requests as c_requests
from streamlit_js_eval import get_geolocation, set_cookie, get_cookie

IS_CLOUD = "STREAMLIT_SERVER_ENABLE_XSRF_PROTECTION" in os.environ
debug_mode = None

# --- Resource Path Resolution for Desktop Executable ---
def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

# --- Page Configuration ---
st.set_page_config(page_title="Regal Pro", layout="wide", page_icon="🎬")

# --- CSS for Navigation ---
st.markdown("""
    <style>
    .stRadio > div[role="radiogroup"] {
        flex-direction: row; gap: 2rem; background-color: #f0f2f6;
        padding: 10px 20px; border-radius: 10px; margin-bottom: 20px;
    }
    .stRadio [data-testid="stMarkdownContainer"] p { font-size: 1.1rem; font-weight: 600; }
    }
    </style>
""", unsafe_allow_html=True)

# --- Constants & Headers ---
THEATERS_FILE = get_resource_path("theater_list.json")

AJAX_HEADERS = {
    "Host": "www.regmovies.com",
    "sec-ch-ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
    "sec-fetch-site": "same-origin",
    "sec-fetch-mode": "cors",
    "sec-fetch-dest": "empty",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en-US,en;q=0.9",
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
        port = st.session_state.get('current_proxy_port', 10001)
        
        auth_user = f"user-{p_user}-session-healthcheck"
        proxy_url = f"http://{auth_user}:{p_pass}@{p_addr}:{port}"
        proxies = {"http": proxy_url, "https": proxy_url}
        
        test_resp = c_requests.get(
            "https://httpbin.org/ip", 
            proxies=proxies, 
            impersonate="chrome124", 
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

def is_dst(dt):
    year = dt.year
    dst_start = datetime(year, 3, 8) + timedelta(days=(6 - datetime(year, 3, 8).weekday()))
    dst_end = datetime(year, 11, 1) + timedelta(days=(6 - datetime(year, 11, 1).weekday()))
    return dst_start <= dt.replace(tzinfo=None) < dst_end

def get_location_cookie():
    with st.container(height=1, border=False):
        st.html("<style>div[height='1']{display:none;}</style>")
        location_cookie = get_cookie('RegalProUserGeoLocation')
        latitude = get_cookie('RegalProUserGeoLatitude')
        longitude = get_cookie('RegalProUserGeoLongitude')
        zip_code = get_cookie('RegalProUserZipCode')

    if location_cookie and latitude is not None and longitude is not None:
        try:
            with st.container(height=1, border=False):
                st.html("<style>div[height='1']{display:none;}</style>")
                set_cookie('RegalProUserGeoLocation', True, 400)
                set_cookie('RegalProUserGeoLatitude', latitude, 400)
                set_cookie('RegalProUserGeoLongitude', longitude, 400)
                set_cookie('RegalProUserZipCode', zip_code, 400)
            
            return location_cookie, float(latitude), float(longitude), zip_code
        except (ValueError, TypeError):
            return None, None, None, None
    else:
        location = get_geolocation()
        if location and location.get('coords'):
            lat = location['coords']['latitude']
            lon = location['coords']['longitude']
            z_code = get_zip_code_from_lat_lon(lat, lon)
            
            with st.container(height=1, border=False):
                st.html("<style>div[height='1']{display:none;}</style>")
                set_cookie('RegalProUserGeoLocation', True, 400)
                set_cookie('RegalProUserGeoLatitude', lat, 400)
                set_cookie('RegalProUserGeoLongitude', lon, 400)
                set_cookie('RegalProUserZipCode', z_code, 400)
            return None, None, None, None
        else:
            return None, None, None, None

def get_zip_code_from_lat_lon(latitude, longitude):
    geolocator = Nominatim(user_agent="regal_pro_v1.4")
    geocode = RateLimiter(geolocator.reverse, min_delay_seconds=1)
    coordinates = (latitude, longitude)

    location = geocode(coordinates)

    if location and 'address' in location.raw and 'postcode' in location.raw['address']:
        return location.raw['address']['postcode']
    else:
        return None

def get_offset_from_lon(lon, state=None, target_date=None):
    if state in ['OH', 'WV', 'VA', 'NC', 'SC', 'GA', 'PA', 'NY', 'NJ', 'MD', 'DE', 'CT', 'RI', 'MA', 'VT', 'NH', 'ME', 'IN']: 
        base_offset = -5
    elif state in ['IL', 'WI', 'AL', 'MS', 'LA', 'AR', 'MO', 'IA', 'MN', 'OK']: 
        base_offset = -6
    elif state in ['CO', 'ID', 'MT', 'NM', 'UT', 'WY', 'AZ']: 
        base_offset = -7
    elif state in ['CA', 'NV', 'OR', 'WA']: 
        base_offset = -8
    elif state == 'AK':
        base_offset = -9
    elif state == 'HI':
        base_offset = -10
    elif state in ['FL','KY','TN','MI']:
        base_offset = -5 if lon > -86 else -6
    elif state in ['KS','NE','ND','SD']:
        base_offset = -6 if lon > -101 else -7
    elif state == 'TX':
        base_offset = -6 if lon > -105 else -7
    else: 
        base_offset = -5
    
    if state not in ['HI', 'AZ'] and target_date:
        if is_dst(target_date):
            base_offset += 1
            
    return base_offset

def calculate_haversine_distance(lat1, lon1, lat2, lon2):
    R = 3958.8 
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlam = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi/2)**2 + math.cos(phi1)*math.cos(phi2)*math.sin(dlam/2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))

def fetch_data(api_url, path_name, max_retries=3):
    proxies = None
    if IS_CLOUD:
        if "current_proxy_port" not in st.session_state:
            st.session_state.current_proxy_port = 10001
            if "proxy_session_id" not in st.session_state:
                st.session_state.proxy_session_id = os.urandom(4).hex()
        try:
            p = st.secrets["proxy"]
        except KeyError:
            st.error("Proxy secrets not configured!")
            return None

    for attempt in range(max_retries):
        if IS_CLOUD:
            auth = f"user-{p['username']}-session-{st.session_state.proxy_session_id}"
            proxy_url = f"http://{auth}:{p['password']}@{p['address']}:{st.session_state.current_proxy_port}"
            proxies = {"http": proxy_url, "https": proxy_url}

        if "api_session" not in st.session_state:
            st.session_state.api_session = c_requests.Session()
        
        st.session_state.api_session.proxies = proxies
        api_headers = AJAX_HEADERS.copy()
        api_headers["Referer"] = f"https://www.regmovies.com/theatres/{path_name}"

        if debug_mode:
            with st.expander("🛠️ Outgoing Request Log", expanded=False):
                st.json({
                    "API_URL": api_url,
                    "API_Headers": api_headers,
                    "Proxy": proxies["https"] if proxies else "None"
                })
    
        try:
            response = st.session_state.api_session.get(
                api_url, 
                headers=api_headers, 
                impersonate="chrome124",
                proxies=proxies,
                timeout=30
            )
            if response.status_code == 200: 
                return response.json()
            if response.status_code == 403:
                st.session_state.current_proxy_port = 10001 + (st.session_state.current_proxy_port - 10001 + 1) % 10
                st.session_state.proxy_session_id = os.urandom(4).hex()
                del st.session_state.api_session

                if attempt < max_retries - 1:
                    st.toast("Regal 403 detected. Rotating IP and retrying...")
                    time.sleep(8)
                    continue
                else:
                    st.error("Access Denied (403). Regal is blocking the request.")
                    return None
            response.raise_for_status()
        except:
            if attempt < max_retries - 1: time.sleep(1)
            continue
    return None

def flatten_data(data):
    flat_list = []
    
    if "global_movie_catalog" not in st.session_state:
        st.session_state.global_movie_catalog = {}

    for m in data.get('movies', []):
        m_code = m.get('MasterMovieCode')
        if m_code:
            st.session_state.global_movie_catalog[m_code] = {
                'title': m.get('Title', 'Unknown'),
                'rating': m.get('Rating', 'NR'), 
                'duration': int(m.get('Duration', '0'))
            }
    
    raw_attrs_list = data.get('attributes', [])
    attr_map = {a.get('Acronym', '').strip(): a.get('ShortName', '').strip() 
                for a in raw_attrs_list if a.get('Acronym')}

    shows = data.get("shows", [])
    active_movie_codes = set()
    
    for theater_show in shows:
        t_code = theater_show.get("TheatreCode")
        for movie in theater_show.get("Film", []):
            m_code = movie.get('MasterMovieCode')
            active_movie_codes.add(m_code)
            
            meta = st.session_state.global_movie_catalog.get(m_code, {
                'title': movie.get('Title', 'Unknown'),
                'rating': 'NR', 
                'duration': 0
            })
            
            for perf in movie.get("Performances", []):
                try:
                    show_dt = datetime.strptime(perf["CalendarShowTime"], "%Y-%m-%dT%H:%M:%S")
                except ValueError:
                    continue
                
                raw_codes = perf.get("PerformanceAttributes", [])
                expanded_names = sorted([attr_map.get(c.strip(), c) for c in raw_codes])
                
                flat_list.append({
                    "TheaterCode": t_code,
                    "Title": meta['title'], 
                    "Rating": meta['rating'], 
                    "Duration": meta['duration'],
                    "Showtime": show_dt, 
                    "Auditorium": str(perf.get("Auditorium", "?")),
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
                except ValueError:
                    formatted_dates.append(raw_date)
        future_data_map[m_code] = formatted_dates
    
    future_movies = []
    available_codes = set(m.get('MasterMovieCode') for m in data.get('movies', []))
    for code in available_codes:
        if code not in active_movie_codes:
            meta = st.session_state.global_movie_catalog.get(code, {})
            if meta:
                meta_copy = meta.copy()
                meta_copy['scheduled_dates'] = future_data_map.get(code, [])
                if meta_copy['scheduled_dates']:
                    future_movies.append(meta_copy)
    
    return flat_list, st.session_state.global_movie_catalog, attr_map, future_movies

def check_metadata_gaps(flat_list):
    gaps = {}
    for s in flat_list:
        if s['Duration'] == 0:
            # We only need to fetch from ONE theater that has this movie
            if s['master_code'] not in gaps:
                gaps[s['master_code']] = s['TheaterCode']
    return gaps

def get_attr_diff(screening_attrs, common_attrs):
    s_set = set([a.strip() for a in screening_attrs.split(",") if a.strip()])
    diff = s_set - common_attrs
    if not diff: return ""
    diff_str = ", ".join(sorted(diff))
    return diff_str

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

def find_itineraries(current_path, remaining_titles, screenings, p, selected_date, drive_map):
    valid_paths = []
    window_start = datetime.combine(selected_date, p['start'])
    window_end = datetime.combine(selected_date, p['end'])
    
    if window_end <= window_start: 
        window_end += timedelta(days=1)
    elif p['end'] == dt_time(23, 59): 
        window_end += timedelta(hours=6)

    for title in remaining_titles:
        potential_shows = [s for s in screenings if s['Title'] == title and s['TheaterCode'] in p['theaters']]
        if p['formats']: 
            potential_shows = [s for s in potential_shows if s['ScreenType'] in p['formats']]
        
        for s in potential_shows:
            show_start = s['Showtime']
            show_end = show_start + timedelta(minutes=s['Duration'])
            if show_start < window_start or show_end > window_end: 
                continue
            
            if current_path:
                prev = current_path[-1]
                prev_end = prev['Showtime'] + timedelta(minutes=prev['Duration'])
                if p['fudge']: 
                    prev_end -= timedelta(minutes=5)
                
                # ENFORCE TRAVEL BUFFER: Identify time regardless of direction
                drive_time = 0
                if s['TheaterCode'] != prev['TheaterCode']:
                    # Use primary_code passed in params to find the 'nearby' theater
                    nb_code = s['TheaterCode'] if s['TheaterCode'] != p['primary_code'] else prev['TheaterCode']
                    drive_time = drive_map.get(nb_code, {}).get('time', 20)
                
                req_buffer = p['long_buffer'] if p['break_after'] == len(current_path) else p['buffer']
                total_min_gap = drive_time + req_buffer
                
                if p['unlimited'] and show_start < prev['Showtime'] + timedelta(minutes=91): 
                    continue
                if show_start < prev_end + timedelta(minutes=total_min_gap): 
                    continue
                if (show_start - prev_end).total_seconds()/60 > p['gap_cap']: 
                    continue

            new_rem = [t for t in remaining_titles if t != title]
            sub = find_itineraries(current_path + [s], new_rem, screenings, p, selected_date, drive_map)
            if not sub: 
                valid_paths.append(current_path + [s])
            else: 
                valid_paths.extend(sub)
    return valid_paths

def get_conflict_report(path, missing_titles, all_screenings, p):
    conflicts = []
    for m_title in missing_titles:
        # Filter all screenings for the missing title that match preferred theaters and formats
        m_shows = [s for s in all_screenings if s['Title'] == m_title and s['TheaterCode'] in p['theaters']]
        if p['formats']: 
            m_shows = [s for s in m_shows if s['ScreenType'] in p['formats']]
        
        reasons = []
        if not m_shows: 
            reasons.append("No screenings match your selected formats or preferred theaters.")
        else:
            # Check for overlaps with already scheduled movies
            for ms in m_shows:
                ms_start = ms['Showtime']
                ms_end = ms_start + timedelta(minutes=ms['Duration'])
                
                for ps in path:
                    ps_start = ps['Showtime']
                    ps_end = ps_start + timedelta(minutes=ps['Duration'])
                    
                    # Logic for time overlap check
                    if not (ms_end <= ps_start or ms_start >= ps_end):
                        reasons.append(f"The {ms_start.strftime('%I:%M %p')} show overlaps with **{ps['Title']}**.")
                        break
        
        # Consolidate and display reasoning
        detail = reasons[0] if reasons else "No screenings fit your specified time window or buffer requirements."
        conflicts.append(f"❌ **{m_title}**: {detail}")
    return conflicts

# --- Main App ---
if "global_movie_catalog" not in st.session_state:
    st.session_state.global_movie_catalog = {}

st.title("🎬 Regal Pro")
theaters = load_theaters()

if "init_complete" not in st.session_state:
    url_t_code = st.query_params.get("theater")
    st.session_state.search_mode_pref = "Theater Code" if url_t_code else "Zip Code"
    st.session_state.init_complete = True
    st.session_state.initial_url_code = url_t_code
else:
    url_t_code = None

location, latitude,longitude, default_zip_code = get_location_cookie()

results = []
search_performed = False

st.sidebar.header("📍 Find Theater")

search_mode = st.sidebar.selectbox(
    "Search By", 
    ["Zip Code", "Theater Name", "Address/City", "Theater Code"],
    index=["Zip Code", "Theater Name", "Address/City", "Theater Code"].index(st.session_state.search_mode_pref),
    key="current_search_mode" # Unique key to prevent reset
)

if search_mode == "Theater Code":
    val = st.session_state.get('initial_url_code', "")
    code_in = st.sidebar.text_input("Theater Code", value=val)
    
    if "initial_url_code" in st.session_state and code_in != st.session_state.initial_url_code:
        del st.session_state.initial_url_code

    if code_in:
        search_performed = True
        match = next((t for t in theaters if t['item']['theatre_code'] == code_in), None)
        if match:
            results = [match]
            if 'nearby_theaters' in match['item']:
                nearby_codes = [n['code'] for n in match['item']['nearby_theaters']]
                results.extend([t for t in theaters if t['item']['theatre_code'] in nearby_codes])
elif search_mode == "Zip Code":
    zip_in = st.sidebar.text_input("Zip Code", placeholder="46201", value=default_zip_code)
    radius_in = st.sidebar.slider("Radius (miles)", 5, 200, 50)
    
    if zip_in:
        search_performed = True
        results = []
        nomi = pgeocode.Nominatim('us')
        z_data = nomi.query_postal_code(zip_in)
        if not math.isnan(z_data['latitude']):
            for t in theaters:
                d = calculate_haversine_distance(z_data['latitude'], z_data['longitude'], t['item']['latitude'], t['item']['longitude'])
                if d <= radius_in: results.append((t, d))
            results.sort(key=lambda x: x[1])
    elif location and not math.isnan(latitude):
        for t in theaters:
            d = calculate_haversine_distance(latitude, longitude, t['item']['latitude'], t['item']['longitude'])
            if d <= 50: results.append((t, d))
        results.sort(key=lambda x: x[1])
elif search_mode == "Theater Name":
    name_in = st.sidebar.text_input("Theater Name")
    if name_in: search_performed = True; results = [t for t in theaters if name_in.lower() in t['item']['name'].lower()]
elif search_mode == "Address/City":
    addr_in = st.sidebar.text_input("Address, City, or State")
    if addr_in: search_performed = True; results = [t for t in theaters if any(addr_in.lower() in t['item'].get(f, '').lower() for f in ['address', 'city', 'state'])]

if search_performed and not results: st.sidebar.warning("No theaters found matching your criteria.")

selected_theater = None

if results:
    opts = {f"{r[0]['item']['name'] if isinstance(r, tuple) else r['item']['name']} - {r[0]['item']['city'] if isinstance(r, tuple) else r['item']['city']}": (r[0] if isinstance(r, tuple) else r) for r in results}    
    
    if "active_theater_code" not in st.session_state:
        st.session_state.active_theater_code = st.query_params.get("theater")
    
    idx = 0
    for i, t in enumerate(opts.values()):
        if t['item']['theatre_code'] == st.session_state.active_theater_code: 
            idx = i
            break

    sel_label = st.sidebar.selectbox("Select Theater", options=list(opts.keys()), index=idx)
    selected_theater = opts[sel_label]
    new_code = selected_theater['item']['theatre_code']

    if new_code != st.session_state.active_theater_code:
        st.session_state.active_theater_code = new_code
        st.query_params["theater"] = new_code
        st.rerun()

if selected_theater:
    t_item = selected_theater['item']
    q_date = st.sidebar.date_input("Select Date", value="today", format="MM/DD/YYYY")

    t_lon = t_item.get('longitude')
    t_state = t_item.get('state_code')
    if t_lon:
        new_offset = get_offset_from_lon(t_lon,
                                         t_state,
                                         target_date=datetime.combine(q_date, dt_time(0,0)))
        st.session_state.auto_tz_offset = new_offset

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
            
            st.page_link("https://github.com/riyazusman/regal-pro", label="Source on Github")

    f_date = q_date.strftime('%m-%d-%Y')

    needs_fetch = True
    if 'raw_data' in st.session_state and st.session_state.get('last_fetch_date') == f_date:
        cached_codes = [s.get('TheatreCode') for s in st.session_state.raw_data.get('shows', [])]
        if t_item['theatre_code'] in cached_codes:
            needs_fetch = False

    if needs_fetch:
        with st.spinner("Fetching Cluster..."):
            primary_theater_code = t_item['theatre_code']
            target_codes = [primary_theater_code]
            if 'nearby_theaters' in t_item:
                target_codes.extend([n['code'] for n in t_item['nearby_theaters']])
            
            api_url = f"https://www.regmovies.com/api/getShowtimes?theatres={','.join(target_codes)}&date={f_date}"
            data = fetch_data(api_url, t_item['path_name'])
            
            if data:
                all_flat_data, _, _, _ = flatten_data(data)
                
                gaps = check_metadata_gaps(all_flat_data)
                
                if gaps:
                    anchor_theaters = list(set(gaps.values()))
                    st.toast(f"Filling metadata gaps from {len(anchor_theaters)} additional theaters...")
                    
                    for anchor in anchor_theaters:
                        rotated_codes = [anchor] + [c for c in target_codes if c != anchor]
                        sweep_url = f"https://www.regmovies.com/api/getShowtimes?theatres={','.join(rotated_codes)}&date={f_date}"
                        sweep_data = fetch_data(sweep_url, t_item['path_name'])
                        
                        if sweep_data:
                            flatten_data(sweep_data)
                
                st.session_state.raw_data = data
                st.session_state.last_fetch_date = f_date

st.sidebar.link_button("Report Bug / Request Feature","https://docs.google.com/forms/d/e/1FAIpQLSce6X3DtCwDJZUjf_Cc4IbJLA7q0Nvk_Grw7lOgyqLtxYIYPQ/viewform?usp=dialog")
st.sidebar.link_button("Buy Me a Coffee","https://buymeacoffee.com/riyazusman")

if selected_theater and 'raw_data' in st.session_state:
    if debug_mode:
        with st.expander("🛠️ Raw API Debug Output", expanded=False):
            st.json(st.session_state.raw_data)

    all_flat_data, movie_meta, attr_map, future_movies = flatten_data(st.session_state.raw_data)

    cluster_theaters = {t_item['theatre_code']: t_item['name']}
    master_name_map = {t['item']['theatre_code']: t['item']['name'] for t in theaters}
    if 'nearby_theaters' in t_item:
        for nt in t_item['nearby_theaters']:
            n_code = nt['code']
            n_name = master_name_map.get(n_code, nt.get('name', f"Theater {n_code}"))
            cluster_theaters[n_code] = n_name
        
    flat_data = [s for s in all_flat_data if s['TheaterCode'] == t_item['theatre_code']]
        
    st.session_state.update({
        "all_flat_data": all_flat_data,
        "flat_data": flat_data,
        "movie_meta": movie_meta,
        "attr_map": attr_map,
        "future_movies": future_movies
    })

    if 'flat_data' in st.session_state:
        flat_data = st.session_state.flat_data
        all_flat_data = st.session_state.all_flat_data
        movie_meta = st.session_state.movie_meta
        attr_map = st.session_state.attr_map
        future_movies = st.session_state.future_movies

    t_key = t_item['theatre_code']
    nav_key = f"nav_tab_{t_key}"

    tabs_list = ["🔎 Theater Explorer", "🎬 Movie Explorer", "🗓️ Smart Scheduler"]
    default_idx = 0
    if "nav_redirect" in st.session_state:
        # Force the widget's session_state key to match the redirect
        st.session_state[nav_key] = st.session_state.nav_redirect
        # Clear the flag so it doesn't stay locked in subsequent runs
        del st.session_state.nav_redirect

    nav_tab = st.radio(
            "Navigation", 
            ["🔎 Theater Explorer", "🎬 Movie Explorer", "🗓️ Smart Scheduler"], 
            horizontal=True, 
            label_visibility="collapsed",
            key=nav_key
        )

    if nav_tab == "🔎 Theater Explorer":
        if print_mode: st.markdown("<style>[data-testid='stSidebar'], [data-testid='stHeader'] {display: none;} .stExpander {border: none !important;}</style>", unsafe_allow_html=True)
        st.subheader("🔎 Theater Explorer")
        st.info(f"Viewing: **{t_item['name']}** on **{q_date.strftime('%A, %b %d')}**")

        tab_now, tab_nearby, tab_upcoming = st.tabs(["🍿 Now Playing", "🚗 Playing Nearby", "📅 Upcoming"])
        
        with tab_now:
            with st.expander("🔍 Filters & Sorting", expanded=not print_mode):
                c1, c2, c3, c4 = st.columns(4)
                with c1:
                    f_type = st.multiselect("Screen Type", 
                                            options=sorted(list(set(s['ScreenType'] for s in flat_data))), 
                                            placeholder="All",
                                            key=f"f_type_{t_key}") # Contextual Key
                    f_rating = st.multiselect("Rating", 
                                              options=sorted(list(set(s['Rating'] for s in flat_data))), 
                                              placeholder="All",
                                              key=f"f_rating_{t_key}")
                with c2:
                    f_audi = st.multiselect("Auditorium", 
                                            options=sorted(list(set(s['Auditorium'] for s in flat_data)), key=lambda x: int(x) if x.isdigit() else 999), 
                                            placeholder="All",
                                            key=f"f_audi_{t_key}")
                    
                    current_st = set(f_type) if f_type else set(s['ScreenType'] for s in flat_data)
                    all_expanded_attrs = set(a for s in flat_data for a in s['raw_attrs'])
                    deduped_attrs = sorted([a for a in all_expanded_attrs if a not in current_st])
                    
                    f_attr = st.multiselect("Additional Filters", 
                                            options=deduped_attrs, 
                                            placeholder="All",
                                            key=f"f_attr_{t_key}")
                with c3:
                    t_ranges = {"8AM - 12N": (8, 12), "12N - 4PM": (12, 16), "4PM - 8PM": (16, 20), "8PM - 12M": (20, 24)}
                    f_times = st.multiselect("Time Window", 
                                             options=list(t_ranges.keys()), 
                                             placeholder="All",
                                             key=f"f_times_{t_key}")
                    f_avail = st.checkbox("Hide past shows", value=True, key=f"f_avail_{t_key}")
                with c4:
                    sort_by = st.selectbox("Sort By", 
                                           ["Movie Title", "Showtime", "Auditorium"],
                                           key=f"sort_by_{t_key}")
                    view_mode = st.selectbox("View Mode", 
                                             ["Group by Movie", "Group by Auditorium", "Full Schedule"],
                                             key=f"view_mode_{t_key}")
                    
            filtered = [s for s in flat_data if (
                not f_type or s['ScreenType'] in f_type) and 
                (not f_rating or s['Rating'] in f_rating) and 
                (not f_audi or s['Auditorium'] in f_audi) and 
                (not f_attr or set(f_attr).issubset(s['raw_attrs'])) and 
                (not f_times or any(t_ranges[t][0] <= s['Showtime'].hour < t_ranges[t][1] for t in f_times)) and 
                (not f_avail or (s['Showtime'] > current_local_time if q_date == current_local_time.date() else True))]
            
            if sort_by == "Movie Title": filtered.sort(key=lambda x: (x['Title'], x['Showtime']))
            elif sort_by == "Showtime": filtered.sort(key=lambda x: (x['Showtime'], x['Title']))
            elif sort_by == "Auditorium": filtered.sort(key=lambda x: (int(x['Auditorium']) if x['Auditorium'].isdigit() else 999, x['Showtime']))
            
            st.write(f"Showing **{len(set(s['Title'] for s in filtered))}** movies and **{len(filtered)}** screenings.")

            if view_mode == "Full Schedule":
                for s in filtered:
                    with st.container(border=True):
                        col_t, col_info = st.columns([1.3, 5])
                        is_past = (q_date == current_local_time.date() and s['Showtime'] < current_local_time)
                        t_str = f"<span style=\"text-decoration: line-through;\">{s['Showtime'].strftime('%I:%M %p')}</span>" if is_past else f"{s['Showtime'].strftime('%I:%M %p')}"
                        d_str = f"~~{s['Title']}~~" if is_past else s['Title']
                        col_t.markdown(f"""<div style="line-height: 1;"><p style="color: grey; font-size: 0.8rem; margin-bottom: 2px; text-transform: uppercase; font-weight: bold;">{s['ScreenType']}</p><p style="font-size: 1.4rem; font-weight: 700; margin: 0; white-space: nowrap;">{t_str}</p></div>""", unsafe_allow_html=True)
                        col_info.markdown(f"### {d_str}")
                        col_info.markdown(f"**{s['Rating']}** | **{s['Duration']} min** | Audi {s['Auditorium']}")
                        if s['Attributes']: st.markdown(f'<p style="color: grey; font-size: 0.85em; margin-top: -10px;">{s["Attributes"]}</p>', unsafe_allow_html=True)
            elif view_mode == "Group by Auditorium":
                for audi in sorted(list(set(s['Auditorium'] for s in filtered)), key=lambda x: int(x) if x.isdigit() else 999):
                    with st.expander(f"🖼️ Auditorium {audi}", expanded=True):
                        for s in sorted([s for s in filtered if s['Auditorium'] == audi], key=lambda x: x['Showtime']):
                            col_t, col_info = st.columns([1, 5])
                            is_past = (q_date == current_local_time.date() and s['Showtime'] < current_local_time)
                            t_str = f"~~{s['Showtime'].strftime('%I:%M %p')}~~" if is_past else f"**{s['Showtime'].strftime('%I:%M %p')}**"
                            d_str = f"~~{s['Title']} ({s['ScreenType']}) — {s['Duration']}m~~" if is_past else f"**{s['Title']}** ({s['ScreenType']}) — {s['Duration']}m"
                            col_t.markdown(t_str)
                            col_info.markdown(d_str)
            else: # Group by Movie
                for title in list(dict.fromkeys([s['Title'] for s in filtered])):
                    m_shows = [s for s in filtered if s['Title'] == title]
                    
                    other_t = sorted([cluster_theaters.get(tc, f"Theater {tc}") 
                                    for tc in set(s['TheaterCode'] for s in all_flat_data if s['Title'] == title) 
                                    if tc != t_item['theatre_code']])
                    
                    with st.expander(f"🍿 {title} ({m_shows[0]['Rating']}) — {m_shows[0]['Duration']} min", expanded=True):
                        for mt in sorted(list(set(s['ScreenType'] for s in m_shows))):
                            ts = [s for s in m_shows if s['ScreenType'] == mt]
                            t_common = set.intersection(*(s['raw_attrs'] for s in ts)) if ts else set()
                            common_attribs = sorted(t_common - {mt})
                            st.markdown(f'<div style="background-color: #f0f2f6; padding: 4px 12px; border-radius: 4px; border-left: 4px solid #ff4b4b; margin-bottom: 6px;"><span style="font-weight: bold;">{mt}</span> <span style="color: grey; font-size: 0.85em; font-weight: normal; margin-left: 10px;">({", ".join(sorted(common_attribs)) if common_attribs else ""})</span></div>', unsafe_allow_html=True)

                            row = []
                            for s in ts:
                                is_past = (q_date == current_local_time.date() and s['Showtime'] < current_local_time)
                                delta_attribs = get_attr_diff(s['Attributes'], t_common)
                                t_str = s['Showtime'].strftime('%I:%M %p')
                                if is_past:
                                    final_time = f"<del>{t_str}</del>" 
                                    meta_text = f"  <small style='color:grey'><del>(Audi {s['Auditorium']}) {delta_attribs}</del></small>"
                                else:
                                    final_time = f"{t_str}" 
                                    meta_text = f"  <small style='color:grey'>(Audi {s['Auditorium']}) {delta_attribs}</small>"
                                row.append(f"{final_time}{meta_text}")
                            
                            st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{' | '.join(row)}", unsafe_allow_html=True)
                        
                        if other_t:
                            footer_col, link_col = st.columns([4, 1])
                            with footer_col:
                                st.markdown(f"<div style='font-size: 0.8rem; color: #666; padding-top: 5px;'><b>Also Playing At:</b> {', '.join(other_t)}</div>", unsafe_allow_html=True)
                            with link_col:
                                if st.button("📅 Full Schedule", key=f"link_{title}_{t_item['theatre_code']}", use_container_width=True):
                                    st.session_state.nav_redirect = "🎬 Movie Explorer"
                                    st.session_state.selected_movie = title
                                    st.rerun()

        with tab_nearby:
            primary_titles = set(s['Title'] for s in filtered)
            cluster_titles = set(s['Title'] for s in all_flat_data)
            nearby_only_titles = sorted(list(cluster_titles - primary_titles))

            if nearby_only_titles:
                st.subheader("🚗 Playing Nearby")
                st.caption("These movies are not at your selected theater but are playing at nearby locations.")
                
                nearby_cols = st.columns(3)
                for idx, title in enumerate(nearby_only_titles):
                    m_sample = next(s for s in all_flat_data if s['Title'] == title)
                    t_hosting = set(cluster_theaters.get(s['TheaterCode'], "Unknown") 
                                    for s in all_flat_data if s['Title'] == title)
                    
                    with nearby_cols[idx % 3]:
                        with st.container(border=True):
                            st.markdown(f"**{title}** ({m_sample['Rating']})")
                            st.markdown(f"<small style='color:grey'>📍 {', '.join(t_hosting)}</small>", unsafe_allow_html=True)
                            st.caption(f"{m_sample['Duration']} min")
            else:
                st.info("No exclusive nearby movies found for this date.")

        with tab_upcoming:
            if future_movies:
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
            else:
                st.info("No upcoming movies listed for this theater.")
                            
    elif nav_tab == "🎬 Movie Explorer":
        st.subheader("🎬 Movie Explorer")
        
        master_name_map = {t['item']['theatre_code']: t['item']['name'] for t in theaters}
        theater_info = {t_item['theatre_code']: {"name": t_item['name'], "dist": 0, "time": 0}}
        if 'nearby_theaters' in t_item:
            for nt in t_item['nearby_theaters']:
                n_code = nt['code']
                theater_info[n_code] = {
                    "name": master_name_map.get(n_code, f"Theater {n_code}"), 
                    "dist": nt.get('road_miles', 0), 
                    "time": nt.get('drive_min', 0)
                }
        
        movie_list_data = []
        titles_processed = set()
        for s in all_flat_data:
            if s['Title'] not in titles_processed:
                rating = movie_meta.get(s['master_code'], {}).get('rating', 'NR')
                movie_list_data.append({"title": s['Title'], "label": f"{s['Title']} ({rating})"})
                titles_processed.add(s['Title'])
        movie_list_data.sort(key=lambda x: x['title'])

        st.markdown("###### 🍿 Select a Movie")
        st.markdown("""
            <style>
            div.stButton > button {
                width: 100% !important;
                height: 40px !important;
                border-radius: 6px !important;
                background-color: white !important;
                border: 1px solid #d1d5db !important;
            }
            div.stButton > button div p {
                white-space: nowrap !important;
                overflow: hidden !important;
                text-overflow: ellipsis !important;
                font-size: 0.75rem !important;
                font-weight: 600 !important;
            }
            </style>
        """, unsafe_allow_html=True)

        if "selected_movie" not in st.session_state:
            st.session_state.selected_movie = movie_list_data[0]['title'] if movie_list_data else None

        with st.container(height=130, border=True):
            cols_per_row = 5
            for i in range(0, len(movie_list_data), cols_per_row):
                row_cols = st.columns(cols_per_row)
                for j, m_entry in enumerate(movie_list_data[i : i + cols_per_row]):
                    title = m_entry['title']
                    is_selected = (title == st.session_state.selected_movie)
                    label = f"✅ {m_entry['label']}" if is_selected else m_entry['label']
                    if row_cols[j].button(label, key=f"grid_{title}", use_container_width=True):
                        st.session_state.selected_movie = title
                        st.rerun()

        sel_movie = st.session_state.selected_movie
        if sel_movie:
            m_data = [s for s in all_flat_data if s['Title'] == sel_movie]
            meta = movie_meta.get(m_data[0]['master_code'], {})
            st.markdown(f"## {sel_movie} <small style='color:grey'>({meta.get('rating', 'NR')} | {meta.get('duration', 0)} min)</small>", unsafe_allow_html=True)
            
            with st.expander("🔍 Advanced Filters", expanded=False):
                f_col1, f_col2, f_col3 = st.columns(3)
                with f_col1:
                    m_formats = sorted(list(set(s['ScreenType'] for s in m_data)))
                    f_fmt = st.multiselect("Format", options=m_formats, placeholder="All")
                with f_col2:
                    t_ranges = {"8AM-12N": (8, 12), "12N-4PM": (12, 16), "4PM-8PM": (16, 20), "8PM-12M": (20, 24)}
                    f_win = st.multiselect("Time Window", options=list(t_ranges.keys()))
                with f_col3:
                    all_m_attrs = set(a for s in m_data for a in s['raw_attrs'])
                    f_extra = st.multiselect("Attributes", options=sorted(list(all_m_attrs - set(m_formats))))
                    f_hide = st.checkbox("Hide Past Shows", value=True)

            filtered_m = [s for s in m_data if 
                      (not f_fmt or s['ScreenType'] in f_fmt) and
                      (not f_win or any(t_ranges[w][0] <= s['Showtime'].hour < t_ranges[w][1] for w in f_win)) and
                      (not f_extra or set(f_extra).issubset(s['raw_attrs'])) and
                      (not f_hide or (s['Showtime'] > current_local_time if q_date == current_local_time.date() else True))]

            fmts_to_show = sorted(list(set(s['ScreenType'] for s in filtered_m)))
            
            for fmt in fmts_to_show:
                fmt_shows = [s for s in filtered_m if s['ScreenType'] == fmt]
                
                with st.expander(f"✨ {fmt}", expanded=True):
                    t_codes = sorted(list(set(s['TheaterCode'] for s in fmt_shows)), 
                                    key=lambda x: theater_info.get(x, {}).get('time', 999))
                    
                    for tc in t_codes:
                        t_shows = sorted([s for s in fmt_shows if s['TheaterCode'] == tc], key=lambda x: x['Showtime'])
                        info = theater_info.get(tc, {"name": f"Theater {tc}", "dist": 0, "time": 0})
                        
                        is_primary = (tc == t_item['theatre_code'])
                        t_icon = "📍" if is_primary else "🚗"
                        dist_txt = "(Current)" if is_primary else f"({info['time']}m / {info['dist']}mi)"
                        
                        st.markdown(f"**{t_icon} {info['name']}** <small style='color:grey'>{dist_txt}</small>", unsafe_allow_html=True)
                        
                        t_common = set.intersection(*(s['raw_attrs'] for s in t_shows)) if t_shows else set()
                        common_attribs = sorted(t_common - {fmt})
                        st.markdown(f"<p style='color:grey; font-size:0.8rem; margin-top:-10px; margin-bottom:5px;'>({', '.join(common_attribs) if common_attribs else ""})</p>", unsafe_allow_html=True)

                        row_items = []
                        for s in t_shows:
                            t_str = s['Showtime'].strftime('%I:%M %p')
                            delta_attribs = get_attr_diff(s['Attributes'], t_common)
                            
                            is_past = (q_date == current_local_time.date() and s['Showtime'] < current_local_time)
                            if is_past:
                                final_time = f"<del>{t_str}</del>" 
                                meta_text = f" <small style='color:grey'><del>(Audi {s['Auditorium']}) {delta_attribs}</del></small>"
                            else:    
                                final_time = f"**{t_str}**"
                                meta_text = f" <small style='color:grey'>(Audi {s['Auditorium']}) {delta_attribs}</small>"

                            row_items.append(f"{final_time}{meta_text}")
                        
                        st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;{' | '.join(row_items)}", unsafe_allow_html=True)
                        st.divider()
                        
    elif nav_tab == "🗓️ Smart Scheduler":
        st.subheader("🗓️ Smart Scheduler")
        st.info(f"Scheduling Cluster: **{t_item['name']}** on **{q_date.strftime('%A, %b %d')}**")

        cluster_theaters = {t_item['theatre_code']: t_item['name']}
        primary_code = t_item['theatre_code']
        drive_map = {t_item['theatre_code']: {'time': 0, 'dist': 0}}
        master_name_map = {t['item']['theatre_code']: t['item']['name'] for t in theaters}

        if 'nearby_theaters' in t_item:
            for nt in t_item['nearby_theaters']:
                n_code = nt['code']
                n_name = master_name_map.get(n_code, nt.get('name', f"Theater {n_code}"))
                cluster_theaters[n_code] = n_name
                drive_map[n_code] = {
                    'time': nt.get('drive_min', 20),
                    'dist': nt.get('road_miles', 0)
                }

        with st.expander("⚙️ Parameters", expanded=True):
            r1_c1, r1_c2 = st.columns(2)
            
            with r1_c1:
                t_opts = list(cluster_theaters.keys())
                target_theaters = st.multiselect(
                    "Select Theaters (Ordered by Preference)", 
                    options=t_opts, 
                    default=[t_item['theatre_code']],
                    format_func=lambda x: cluster_theaters.get(x),
                    key=f"target_theaters_{t_item['theatre_code']}"
                )
            
            with r1_c2:
                reactive_movies = sorted(list(set(
                    s['Title'] for s in all_flat_data 
                    if s['TheaterCode'] in target_theaters
                )))
                
                target_movies = st.multiselect(
                    "Select Movies (Ordered by Preference)", 
                    options=reactive_movies,
                    key=f"target_movies_{t_item['theatre_code']}"
                )

            with r1_c2:
                available_formats = sorted(list(set(
                    s['ScreenType'] for s in all_flat_data 
                    if s['Title'] in target_movies and s['TheaterCode'] in target_theaters
                ))) if target_movies else sorted(list(set(
                    s['ScreenType'] for s in all_flat_data 
                    if s['TheaterCode'] in target_theaters
                )))
                
                target_formats = st.multiselect(
                    "Preferred Formats", 
                    options=available_formats, 
                    placeholder="All",
                    key=f"target_formats_{t_item['theatre_code']}"
                )
            
            time_opts = ["Any Time"] + get_time_options()
            c1, c2, c3 = st.columns(3)
            with c1: 
                sel_start = st.selectbox("Earliest Start", options=time_opts, index=0)
                sel_end = st.selectbox("Latest End", options=time_opts, index=0)
                t_start = dt_time(0, 0) if sel_start == "Any Time" else datetime.strptime(sel_start, "%H:%M").time()
                t_end = dt_time(23, 59) if sel_end == "Any Time" else datetime.strptime(sel_end, "%H:%M").time()
            with c2: buff = st.slider("Buffer (min)", 0, 60, 15, help="Set the minimum gap between two movies"); g_cap = st.slider("Max Gap (min)", 30, 240, 120, help="Set the maximum gap between two movies")
            with c3: unlimited = st.checkbox("Regal Unlimited Rule (90-min gap)", help="Apply a minimum gap of 90-min between showtimes."); fudge = st.checkbox("Fudge Factor (5-min overlap)", help="Allow a 5 min overlap between showtimes if no better schedule possible.")
            
            c_b1, c_b2 = st.columns(2)
            with c_b1: 
                n_movies = len(target_movies)
                break_opts = [None] + list(range(1, n_movies)) if n_movies > 1 else [None]
                b_after = st.selectbox("Long break after movie #", options=break_opts, help="Set a longer break than after a specific movie.")
            with c_b2: b_val = st.slider("Break duration (min)", 30, 120, 60)
        
        if st.button("🚀 Generate Itineraries"):
            if len(target_movies) < 2:
                st.error("Please select at least 2 movies.")
            else:
                params = {
                    'start': t_start, 'end': t_end, 'buffer': buff, 'gap_cap': g_cap, 
                    'unlimited': unlimited, 'fudge': fudge, 'break_after': b_after, 
                    'long_buffer': b_val, 'formats': target_formats, 'theaters': target_theaters,
                    'primary_code': primary_code # Pass for travel enforcement
                }                
                paths = find_itineraries([], target_movies, all_flat_data, params, q_date, drive_map)
                
                if not paths: 
                    st.error("No valid schedules found.")
                else:
                    processed_paths = []
                    for p_raw in paths:
                        movie_count, hops, total_miles, total_gap = len(p_raw), 0, 0, 0
                        
                        for i in range(len(p_raw)-1):
                            curr, nxt = p_raw[i], p_raw[i+1]
                            curr_end = curr['Showtime'] + timedelta(minutes=curr['Duration'])
                            total_gap += int((nxt['Showtime'] - curr_end).total_seconds() / 60)
                            
                            if curr['TheaterCode'] != nxt['TheaterCode']:
                                hops += 1
                                # ACCUMULATE MILES: Find the non-primary theater's distance
                                nb_code = nxt['TheaterCode'] if nxt['TheaterCode'] != primary_code else curr['TheaterCode']
                                total_miles += drive_map.get(nb_code, {}).get('dist', 0)

                        f_score = (movie_count * 100) - (hops * 40) - (total_miles * 2)
                        p_id = "-".join([f"{s['master_code']}{s['Showtime'].timestamp()}" for s in p_raw])

                        processed_paths.append({
                            'path': p_raw, 'count': movie_count, 'hops': hops, 
                            'miles': total_miles, 'score': f_score, 'total_gap': total_gap, 'id': p_id
                        })

                    final_selections = []
                    seen_ids = set()

                    def add_selection(entry, label):
                        if entry and entry['id'] not in seen_ids:
                            final_selections.append((entry, label))
                            seen_ids.add(entry['id'])
                            return True
                        return False

                    # Ranking Pool using total_gap as tie-breaker for efficiency
                    ranked_pool = sorted(processed_paths, key=lambda x: (-x['score'], -x['count'], x['total_gap']))

                    # 1. Absolute Marathon (Volume + Compactness)
                    abs_mar = sorted(processed_paths, key=lambda x: (-x['count'], x['hops'], x['miles'], x['total_gap']))[0]
                    add_selection(abs_mar, "Absolute Marathon (Max Movies)")

                    # 2. Smart Marathon
                    add_selection(ranked_pool[0], "Smart Marathon (Best Efficiency)")

                    # 3. Single-Theater Max
                    st_p = sorted([pp for pp in processed_paths if pp['hops'] == 0], key=lambda x: (-x['count'], x['total_gap']))
                    if st_p: add_selection(st_p[0], "Single-Theater Max (Zero Hops)")

                    # 4. Priority Movie Match
                    if len(target_movies) >= 2:
                        top_two = set(target_movies[:2])
                        p_mov = sorted([pp for pp in processed_paths if top_two.issubset(set(s['Title'] for s in pp['path']))], key=lambda x: (-x['score'], x['total_gap']))
                        if p_mov: add_selection(p_mov[0], "Priority Movie Match (#1 & #2)")

                    # 5. Priority Theater Match
                    if target_theaters:
                        top_t = target_theaters[0]
                        p_t = sorted([pp for pp in processed_paths if all(s['TheaterCode'] == top_t for s in pp['path'])], key=lambda x: (-x['count'], x['total_gap']))
                        if p_t: add_selection(p_t[0], "Priority Theater Match (Home Base)")
                            
                    for entry in ranked_pool:
                        if len(final_selections) >= 5: break
                        add_selection(entry, "Alternative Optimized Path")

                    # Final Rendering Loop
                    for i, (entry, label) in enumerate(final_selections[:5]):
                        path, count, hops, miles = entry['path'], entry['count'], entry['hops'], entry['miles']
                        with st.container(border=True):
                            st.markdown(f"#### Option {i+1}: {count} Movies")
                            st.markdown(f"🏆 **{label}** | 🚗 {hops} Hops ({round(miles, 1)} mi travel)", unsafe_allow_html=True)
                            
                            for idx, s in enumerate(path):
                                t_name = cluster_theaters.get(s['TheaterCode'], "Unknown")
                                start_t, end_t = s['Showtime'], s['Showtime'] + timedelta(minutes=s['Duration'])
                                st.write(f"🕒 **{start_t.strftime('%I:%M %p')} - {end_t.strftime('%I:%M %p')}**: {s['Title']} (**{s['ScreenType']}**) @{t_name}")
                                
                                if idx < len(path) - 1:
                                    next_s = path[idx + 1]
                                    gap = int((next_s['Showtime'] - end_t).total_seconds() / 60)
                                    drive_info = ""
                                    if s['TheaterCode'] != next_s['TheaterCode']:
                                        nb_code = next_s['TheaterCode'] if next_s['TheaterCode'] != primary_code else s['TheaterCode']
                                        d_stats = drive_map.get(nb_code, {'time': 20, 'dist': 0})
                                        drive_info = f". Drive: {d_stats['time']} mins ({d_stats['dist']} mi)"
                                    st.markdown(f"&nbsp;&nbsp;&nbsp;&nbsp;<small style='color:grey'>Gap: {gap} mins{drive_info}</small>", unsafe_allow_html=True)
                            
                            st.divider()
                            # FIXED: Unique key using loop index and entry ID to prevent DuplicateElementKey error
                            st.download_button("📅 Download ICS", 
                                             generate_ics(path, t_item['name']), 
                                             file_name=f"movies_{q_date}.ics", 
                                             mime="text/calendar", 
                                             key=f"dl_{i}_{entry['id']}")
                            
                            if count < len(target_movies):
                                missing = [t for t in target_movies if t not in [s['Title'] for s in path]]
                                with st.expander("⚠️ Why were some movies left out?"):
                                    report = get_conflict_report(path, missing, all_flat_data, params)
                                    for line in report: st.write(line)
else: st.info("Search for a theater in the sidebar to begin.")