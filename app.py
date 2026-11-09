"""Dashboard read-only kualitas air: ESP32 -> Supabase -> Streamlit."""

import pandas as pd
import requests
import streamlit as st


st.set_page_config(
    page_title="Dashboard Monitoring Kualitas Air",
    page_icon="💧",
    layout="wide",
)

st.title("💧 Dashboard Monitoring Kualitas Air")
st.caption("Smart Green Campus FILKOM | ESP32 → Supabase PostgreSQL → Streamlit")

# Gunakan publishable key; jangan masukkan service_role atau sb_secret_ ke dashboard.
try:
    SUPABASE_URL = str(st.secrets["SUPABASE_URL"]).strip().rstrip("/")
    SUPABASE_KEY = str(st.secrets["SUPABASE_KEY"]).strip()
except (KeyError, FileNotFoundError):
    st.error(
        "Secrets belum dikonfigurasi. Isi SUPABASE_URL dan SUPABASE_KEY "
        "melalui .streamlit/secrets.toml atau Streamlit Community Cloud."
    )
    st.stop()

if not SUPABASE_URL.startswith("https://") or not SUPABASE_KEY.startswith(
    "sb_publishable_"
):
    st.error("Gunakan URL proyek Supabase (https://) dan publishable key (sb_publishable_).")
    st.stop()


DEVICE_ID = "esp32-01"
KOLOM_NUMERIK = ["suhu_c", "ph", "tds_ppm", "adc_turbidity", "turbidity_index"]

st.sidebar.header("Pengaturan Dashboard")
banyak_data = st.sidebar.selectbox(
    "Jumlah data terbaru", [50, 100, 300, 500, 1000], index=2
)
sembunyikan_adc_invalid = st.sidebar.checkbox(
    "Sembunyikan ADC turbidity tidak valid dari tabel/CSV", value=True
)
st.sidebar.caption("Penyegaran otomatis setiap 60 detik selama dashboard aktif.")


def ambil_data(limit: int) -> pd.DataFrame:
    """Baca data sensor melalui REST API dengan izin SELECT/RLS."""
    endpoint = f"{SUPABASE_URL}/rest/v1/monitoring_air"
    headers = {"apikey": SUPABASE_KEY, "Accept": "application/json"}
    params = {
        "select": (
            "id,device_id,waktu,suhu_c,ph,tds_ppm,ph_warning,"
            "adc_turbidity,turbidity_index"
        ),
        "device_id": f"eq.{DEVICE_ID}",
        "order": "waktu.desc",
        "limit": str(limit),
    }

    response = requests.get(endpoint, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise ValueError("Respons Supabase bukan array JSON.")
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["waktu_wib"] = (
        pd.to_datetime(df["waktu"], errors="coerce", utc=True)
        .dt.tz_convert("Asia/Jakarta")
        .dt.tz_localize(None)
    )
    for kolom in KOLOM_NUMERIK:
        df[kolom] = pd.to_numeric(df[kolom], errors="coerce")

    # Supabase mengirim bool/null; null dianggap tidak ada peringatan tersimpan.
    df["ph_warning"] = df["ph_warning"].fillna(False).astype(bool)

    # ADC 0 dan 4095 adalah pembacaan tidak valid; jangan plot sebagai hasil air.
    # Batas 5/4090 mengikuti pemeriksaan pada firmware ESP32.
    df["turbidity_adc_valid"] = df["adc_turbidity"].between(6, 4089)
    index_valid = df["turbidity_index"].between(0, 100)
    df["turbidity_index_grafik"] = df["turbidity_index"].where(
        df["turbidity_adc_valid"] & index_valid
    )

    df = df.dropna(subset=["waktu_wib"]).sort_values("waktu_wib")
    return df


def angka_terbaru(value, unit="", digit=2) -> str:
    if value is None or pd.isna(value):
        return "—"
