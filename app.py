# app.py
import os
import pickle
import urllib.parse
from typing import List
from dotenv import load_dotenv
import os

# Load .env file
load_dotenv()  # <-- this looks for a .env in the current working directory
import requests
import streamlit as st

# ---------- Config ----------
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8501/")
SCOPE = "user-top-read streaming user-read-private"

# Simple model path (replace with your model)
MODEL_PATH = os.getenv("MODEL_PATH", "model.pkl")

# ---------- Helpers ----------
def build_auth_url(state: str = "streamlit_state"):
    base = "https://accounts.spotify.com/authorize"
    params = {
        "client_id": SPOTIFY_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": state,
        "show_dialog": "true",
    }
    return f"{base}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(code: str):
    token_url = "https://accounts.spotify.com/api/token"
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": REDIRECT_URI,
    }
    auth = (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    r = requests.post(token_url, data=data, auth=auth, timeout=10)
    r.raise_for_status()
    return r.json()  # contains access_token, refresh_token, expires_in, etc.


def refresh_access_token(refresh_token: str):
    token_url = "https://accounts.spotify.com/api/token"
    data = {"grant_type": "refresh_token", "refresh_token": refresh_token}
    auth = (SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET)
    r = requests.post(token_url, data=data, auth=auth, timeout=10)
    r.raise_for_status()
    return r.json()


def get_user_top_tracks(access_token: str, limit: int = 20):
    headers = {"Authorization": f"Bearer {access_token}"}
    url = f"https://api.spotify.com/v1/me/top/tracks?limit={limit}"
    r = requests.get(url, headers=headers, timeout=10)
    r.raise_for_status()
    items = r.json().get("items", [])
    results = []
    for it in items:
        results.append({
            "id": it["id"],
            "name": it["name"],
            "artists": ", ".join(a["name"] for a in it["artists"]),
            "uri": it["uri"],
            "popularity": it["popularity"],
        })
    return results


# Example simple recommender: takes top track IDs / metadata and returns recommended track URIs
def simple_recommendation_model(top_tracks_meta: List[dict], k: int = 10):
    # THIS IS A STUB. Replace with your model's inference.
    # Strategy here: call Spotify recommendations endpoint using seed tracks.
    seed_tracks = [t["id"] for t in top_tracks_meta][:5]
    if not seed_tracks:
        return []

    params = {
        "limit": k,
        "seed_tracks": ",".join(seed_tracks),
        "market": "from_token",
    }
    # Use access token if available in session_state
    access_token = st.session_state.get("access_token")
    headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}

    r = requests.get("https://api.spotify.com/v1/recommendations", headers=headers, params=params, timeout=10)
    if r.status_code != 200:
        # fallback: return top_tracks themselves as recommendations
        return [t["uri"] for t in top_tracks_meta][:k]
    recs = r.json().get("tracks", [])
    return [t["uri"] for t in recs]


# Load your saved model (optional)
def load_model(path):
    if os.path.exists(path):
        with open(path, "rb") as f:
            return pickle.load(f)
    return None


# ---------- Streamlit UI ----------
st.set_page_config(page_title="Spotify Recon Streamlit", layout="centered")

st.title("🔁 Recommendation system — Streamlit + Spotify (Docker-ready)")

if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
    st.error("Missing SPOTIFY_CLIENT_ID or SPOTIFY_CLIENT_SECRET environment variables.")
    st.stop()

# Step 1: OAuth
params = st.experimental_get_query_params()
code = params.get("code", [None])[0]
state = params.get("state", [None])[0]

if "access_token" not in st.session_state:
    st.session_state["access_token"] = None
if "refresh_token" not in st.session_state:
    st.session_state["refresh_token"] = None

if code and not st.session_state["access_token"]:
    # Exchange code for token
    try:
        token_data = exchange_code_for_token(code)
        st.session_state["access_token"] = token_data["access_token"]
        st.session_state["refresh_token"] = token_data.get("refresh_token")
        st.experimental_set_query_params()  # clear query params for cleanliness
        st.success("Spotify authentication successful!")
    except Exception as e:
        st.error(f"Token exchange failed: {e}")

if st.session_state.get("access_token"):
    st.sidebar.success("Authenticated with Spotify")
    # fetch user top tracks
    try:
        top_tracks = get_user_top_tracks(st.session_state["access_token"], limit=20)
    except Exception as e:
        st.error(f"Failed to fetch top tracks: {e}")
        top_tracks = []

    st.subheader("Your Top Tracks (from Spotify)")
    for t in top_tracks:
        st.write(f"**{t['name']}** — {t['artists']} (pop: {t['popularity']})")
        # embed preview player (Spotify embed)
        st.markdown(f"""<iframe src="https://open.spotify.com/embed/track/{t['id']}" width="300" height="80" frameborder="0" allowtransparency="true" allow="encrypted-media"></iframe>""", unsafe_allow_html=True)

    st.subheader("Recommendations")
    # If you have a model: model = load_model(MODEL_PATH); outputs = model.recommend(top_tracks) etc.
    model = load_model(MODEL_PATH)
    if model:
        # Example: model should expose a method `recommend(track_meta, k)`
        try:
            rec_uris = model.recommend(top_tracks, k=10)
        except Exception:
            # fallback to simple spotify recommendations if custom model fails
            rec_uris = simple_recommendation_model(top_tracks, k=10)
    else:
        rec_uris = simple_recommendation_model(top_tracks, k=10)

    if rec_uris:
        for uri in rec_uris:
            # URI looks like spotify:track:<id> or spotify:episode:...
            if uri.startswith("spotify:track:"):
                track_id = uri.split(":")[-1]
            elif uri.startswith("https://open.spotify.com/track/"):
                track_id = uri.split("/")[-1].split("?")[0]
            else:
                track_id = uri.split(":")[-1]
            st.markdown(f"""<iframe src="https://open.spotify.com/embed/track/{track_id}" width="300" height="80" frameborder="0" allowtransparency="true" allow="encrypted-media"></iframe>""", unsafe_allow_html=True)
    else:
        st.info("No recommendations available yet.")

    if st.button("Refresh recommendations"):
        st.experimental_rerun()

else:
    st.write("Click below to authenticate with Spotify and allow the app to read your top tracks.")
    auth_url = build_auth_url()
    st.markdown(f"[Login with Spotify]({auth_url})")
    st.caption("After login you'll be returned to this page. If the redirect doesn't work, make sure your Redirect URI in the Spotify Developer Dashboard matches this app's REDIRECT_URI.")
