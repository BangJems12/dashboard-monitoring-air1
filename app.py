"""Dashboard kualitas air ESP32 -> Supabase REST API (read-only)."""

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

# Publishable key saja. Jangan gunakan sb_secret_ atau service_role di contoh ini.
try:
    SUPABASE_URL = st.secrets["SUPABASE_URL"].rstrip("/")
    SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
except (KeyError, FileNotFoundError):
    st.error(
        "Konfigurasi belum ada. Buat .streamlit/secrets.toml secara lokal "
        "atau isi bagian Secrets pada Streamlit Community Cloud."
    )
    st.stop()

if not SUPABASE_URL.startswith("https://") or not SUPABASE_KEY.startswith("sb_publishable_"):
    st.error("SUPABASE_URL atau SUPABASE_KEY tidak sesuai. Gunakan URL proyek dan publishable key.")
    st.stop()

st.sidebar.header("Pengaturan Dashboard")
banyak_data = st.sidebar.selectbox("Jumlah data terbaru", [50, 100, 300, 500, 1000], index=2)
st.sidebar.caption("Dashboard membaca data dari tabel monitoring_air. Penyegaran otomatis: 60 detik selama halaman aktif.")


def ambil_data(limit: int) -> pd.DataFrame:
    """Baca kolom yang diberikan hak SELECT oleh Supabase RLS."""
    endpoint = f"{SUPABASE_URL}/rest/v1/monitoring_air"
    headers = {"apikey": SUPABASE_KEY, "Accept": "application/json"}
    params = {
        "select": "id,device_id,waktu,suhu_c,ph,tds_ppm,ph_warning",
        "device_id": "eq.esp32-01",
        "order": "waktu.desc",
        "limit": str(limit),
    }
    response = requests.get(endpoint, headers=headers, params=params, timeout=15)
    response.raise_for_status()
    rows = response.json()
    if not isinstance(rows, list):
        raise ValueError("Respons Supabase bukan daftar data JSON.")
    if not rows:
        return pd.DataFrame()

    df = pd.DataFrame(rows)
    df["waktu_wib"] = (
        pd.to_datetime(df["waktu"], errors="coerce", utc=True)
        .dt.tz_convert("Asia/Jakarta")
        .dt.tz_localize(None)
    )
    for column in ["suhu_c", "ph", "tds_ppm"]:
        df[column] = pd.to_numeric(df[column], errors="coerce")
    df = df.dropna(subset=["waktu_wib"]).sort_values("waktu_wib")
    return df


def angka_terbaru(value, unit="", digit=2):
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{digit}f}{unit}"


@st.fragment(run_every="60s")
def tampilkan_dashboard():
    try:
        df = ambil_data(banyak_data)
    except requests.HTTPError as exc:
        code = exc.response.status_code if exc.response is not None else "?"
        st.error(f"Gagal membaca Supabase (HTTP {code}). Periksa izin SELECT/RLS dan konfigurasi URL/key.")
        return
    except (requests.RequestException, ValueError) as exc:
        st.error(f"Tidak dapat mengambil data dari Supabase: {exc}")
        return

    if df.empty:
        st.info("Belum ada data yang bisa dibaca. Periksa data ESP32, RLS, dan filter device_id.")
        return

    terbaru = df.iloc[-1]
    terakhir = terbaru["waktu_wib"].strftime("%d %b %Y, %H:%M:%S WIB")
    st.caption(f"Pengukuran terbaru: {terakhir} · Perangkat: {terbaru['device_id']} · {len(df)} data ditampilkan")

    kolom_ph, kolom_tds, kolom_suhu = st.columns(3)
    with kolom_ph:
        st.metric("pH terbaru", angka_terbaru(terbaru["ph"]))
    with kolom_tds:
        st.metric("TDS terbaru", angka_terbaru(terbaru["tds_ppm"], " ppm"))
    with kolom_suhu:
        st.metric("Suhu terbaru", angka_terbaru(terbaru["suhu_c"], " °C"))

    if bool(terbaru.get("ph_warning", False)):
        st.warning("Pembacaan pH terbaru memiliki peringatan ADC. Nilai pH perlu diperiksa kestabilan dan kalibrasinya.")
    else:
        st.info("Tidak ada peringatan ADC pH pada pembacaan terbaru; ini tidak membuktikan akurasi atau keamanan air.")

    st.subheader("Grafik historis")
    st.caption("Semua waktu grafik ditampilkan dalam WIB (Asia/Jakarta).")
    st.markdown("**pH**")
    st.line_chart(df, x="waktu_wib", y="ph", x_label="Waktu (WIB)", y_label="pH", height=250)
    kiri, kanan = st.columns(2)
    with kiri:
        st.markdown("**TDS**")
        st.line_chart(df, x="waktu_wib", y="tds_ppm", x_label="Waktu (WIB)", y_label="ppm", height=250)
    with kanan:
        st.markdown("**Suhu air**")
        st.line_chart(df, x="waktu_wib", y="suhu_c", x_label="Waktu (WIB)", y_label="°C", height=250)

    st.subheader("Riwayat pengukuran")
    riwayat = df[["waktu_wib", "device_id", "ph", "tds_ppm", "suhu_c", "ph_warning"]].copy()
    riwayat.columns = ["Waktu (WIB)", "Perangkat", "pH", "TDS (ppm)", "Suhu (°C)", "Peringatan pH"]
    riwayat = riwayat.sort_values("Waktu (WIB)", ascending=False)
    st.dataframe(riwayat, hide_index=True, use_container_width=True)
    st.download_button(
        "⬇️ Unduh riwayat CSV",
        data=riwayat.to_csv(index=False).encode("utf-8-sig"),
        file_name="riwayat_monitoring_air.csv",
        mime="text/csv",
    )

    st.caption(
        "Dashboard menunjukkan parameter sensor, bukan hasil uji kelayakan air minum. "
        "Pengukuran pH masih menggunakan parameter kalibrasi lama."
    )


tampilkan_dashboard()
