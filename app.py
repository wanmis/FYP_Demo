# This file takes in the predicted labels after running through the model and visualize the recommended songs, with its fallback version (SoundCloud,Spotify and Deezer)
import requests
import streamlit as st
import os
from dotenv import load_dotenv
import os

load_dotenv()

# ---------- Config ----------
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
REDIRECT_URI = os.getenv("REDIRECT_URI", "http://localhost:8501/")

import pandas as pd
import streamlit as st
from spotipy.oauth2 import SpotifyClientCredentials
import spotipy

st.set_page_config(
    page_title="Emotion-Based Recommender",
    layout="wide",  
    initial_sidebar_state="auto"
)


# Credential Manager
client_credentials_manager = SpotifyClientCredentials(client_id=SPOTIFY_CLIENT_ID, client_secret=SPOTIFY_CLIENT_SECRET)
sp = spotipy.Spotify(client_credentials_manager=client_credentials_manager)

# -----------------------------
# Obtain preview via Spotify, unavailable since Nov 2024 due to API changes
# -----------------------------
@st.cache_data
def get_track_details(spotify_id):
    try:
        return sp.track(spotify_id)
    except Exception as e:
        st.error(f"Error fetching details for {spotify_id}: {e}")
        return None

# -----------------------------
# Obtain preview via Deezer
# -----------------------------
@st.cache_data
def get_deezer_preview(track_name, artist_name):
    """Search Deezer API for a track preview."""
    query = f"{track_name} {artist_name}"
    url = f"https://api.deezer.com/search?q={query}"
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if data.get("data"):
            # Return the first result's preview URL
            return data["data"][0].get("preview")
    except Exception:
        pass
    return None

# -----------------------------
# Obtain preview via SoundCloud
# -----------------------------
@st.cache_data
def get_soundcloud_embed(track_name, artist_name):
    """Try to find a SoundCloud embed link using oEmbed."""
    search_query = f"{track_name} {artist_name}"
    search_url = f"https://soundcloud.com/oembed?url=https://soundcloud.com/search?q={search_query}&format=json"
    try:
        response = requests.get(search_url, timeout=5)
        if response.status_code == 200:
            data = response.json()
            return data.get("html")
    except Exception:
        pass
    return None

# -----------------------------
# Load Dataset after running through model
# -----------------------------
@st.cache_data
def load_df(path):
    return pd.read_feather(path)
audio_df = load_df('precompute.feather')

# -----------------------------
# Emotion Mapping (Rec and Counter)
# -----------------------------
emotion_map = {
    'Happy': {
        'recommended': 'predicted_happy / energetic_prob',
        'counter': 'predicted_sad / depressed_prob'
    },
    'Sad': {
        'recommended': 'predicted_sad / depressed_prob',
        'counter': 'predicted_happy / energetic_prob'
    },
    'Angry': {
        'recommended': 'predicted_angry / anxious_prob',
        'counter': 'predicted_calm / content_prob'
    },
    'Calm': {
        'recommended': 'predicted_calm / content_prob',
        'counter': 'predicted_angry / anxious_prob'
    }
}

# -----------------------------
# Input
# -----------------------------
user_emotion = st.selectbox("How are you feeling today?", ['Happy', 'Sad', 'Angry', 'Calm'])
recommended_column = emotion_map[user_emotion]['recommended']
counter_column = emotion_map[user_emotion]['counter']

# -----------------------------
# Compute Similarities
# -----------------------------
audio_df['recommended_similarity'] = audio_df[recommended_column]
audio_df['counter_similarity'] = audio_df[counter_column]

# -----------------------------
# Filter by Similarity, filtered to above percentiles
# -----------------------------
def filter_top_percentile(df, column, percentile=0.9):
    cutoff = df[column].quantile(percentile)
    return df[df[column] >= cutoff]


filtered_recommended_songs = filter_top_percentile(audio_df, 'recommended_similarity')
filtered_counter_songs = filter_top_percentile(audio_df, 'counter_similarity')

# -----------------------------
# Get Top n
# -----------------------------
def get_top_songs(df, n=10):
    if len(df) == 0:
        return pd.DataFrame()
    return df.sample(n=min(len(df), n))

top_n_recommended_songs = get_top_songs(filtered_recommended_songs)
top_n_counter_songs = get_top_songs(filtered_counter_songs)

# -----------------------------
# Display
# -----------------------------
if st.button('Show me recommended and counter emotion songs'):
    st.markdown(f"## Personalized Music Suggestions, displaying {len(top_n_recommended_songs)} songs")

    # Divisor between rec tab and opp tab
    col_left, spacer, col_right = st.columns([1, 0.5, 1])

    # Rec Tab
    with col_left:
        st.markdown(f"### Recommended songs for : {emotion_map[user_emotion]['recommended'][10:-5]}")
        if top_n_recommended_songs.empty:
            st.warning("No recommended songs found.")
        else:
            for _, row in top_n_recommended_songs.iterrows():
                spotify_id = row['spotify_id']
                track = get_track_details(spotify_id)
                if not track:
                    continue

                song_name = track['name']
                artists = ', '.join([a['name'] for a in track['artists']])
                preview_url = track['preview_url']
                spotify_link = f"https://open.spotify.com/track/{spotify_id}"

                # Fallback versions
                source_label = "Spotify"
                if not preview_url:
                    preview_url = get_deezer_preview(song_name, artists)
                    if preview_url:
                        source_label = "Deezer"
                    else:
                        sc_embed = get_soundcloud_embed(song_name, artists)
                        if sc_embed:
                            source_label = "SoundCloud"

                st.markdown(f"**{song_name}** by *{artists}*  \n[Listen on Spotify]({spotify_link})")
                st.caption(f"Source: {source_label} | Similarity: `{row['recommended_similarity']:.2f}`")

                if preview_url:
                    st.audio(preview_url, format='audio/mp3')
                elif 'sc_embed' in locals() and sc_embed:
                    st.components.v1.html(sc_embed, height=150)
                else:
                    st.caption("No preview available.")

                st.markdown("---")

    # Counter Tab
    with col_right:
        st.markdown(f"### Opposite-emotion songs: {emotion_map[user_emotion]['counter'][10:-5]}")
        if top_n_counter_songs.empty:
            st.warning("No counter-emotion songs found.")
        else:
            for _, row in top_n_counter_songs.iterrows():
                spotify_id = row['spotify_id']
                track = get_track_details(spotify_id)
                if not track:
                    continue

                song_name = track['name']
                artists = ', '.join([a['name'] for a in track['artists']])
                preview_url = track['preview_url']
                spotify_link = f"https://open.spotify.com/track/{spotify_id}"

                source_label = "Spotify"
                if not preview_url:
                    preview_url = get_deezer_preview(song_name, artists)
                    if preview_url:
                        source_label = "Deezer"
                    else:
                        sc_embed = get_soundcloud_embed(song_name, artists)
                        if sc_embed:
                            source_label = "SoundCloud"

                st.markdown(f"**{song_name}** by *{artists}*  \n[Listen on Spotify]({spotify_link})")
                st.caption(f"Source: {source_label} | Similarity: `{row['counter_similarity']:.2f}`")

                if preview_url:
                    st.audio(preview_url, format='audio/mp3')
                elif 'sc_embed' in locals() and sc_embed:
                    st.components.v1.html(sc_embed, height=150)
                else:
                    st.caption("No preview available.")

                st.markdown("---")