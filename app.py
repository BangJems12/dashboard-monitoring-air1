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
otomatis = st.sidebar.checkbox(
    "Penyegaran otomatis setiap 60 detik", value=False
)
st.sidebar.button("🔄 Muat ulang data sekarang")
st.sidebar.caption(
    "Mode manual aktif secara default untuk membantu pemeriksaan koneksi Supabase. "
    "Gunakan menu Rerun aplikasi atau aktifkan penyegaran otomatis setelah data muncul."
)


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

    if df["waktu_wib"].isna().all():
        raise ValueError("Kolom waktu pada respons Supabase tidak berisi timestamp valid.")

    df = df.dropna(subset=["waktu_wib"]).sort_values("waktu_wib")
    return df


def angka_terbaru(value, unit="", digit=2) -> str:
    if value is None or pd.isna(value):
        return "—"
    return f"{value:.{digit}f}{unit}"


def kategori_turbidity(adc, indeks) -> str:
    """Kategori relatif; bukan standar NTU atau penentu kelayakan minum."""
    if pd.isna(adc):
        return "Belum ada data"
    if adc <= 5:
        return "ADC mendekati 0 (tidak valid)"
    if adc >= 4090:
        return "ADC jenuh (tidak valid)"
    if pd.isna(indeks) or not 0 <= indeks <= 100:
        return "Indeks belum tersedia"
    if indeks < 20:
        return "BERSIH (indeks relatif)"
    if indeks < 40:
        return "SEDIKIT KERUH (indeks relatif)"
    if indeks < 60:
        return "SEDANG (indeks relatif)"
    if indeks < 80:
        return "KERUH (indeks relatif)"
    return "SANGAT KERUH (indeks relatif)"


def grafik(df: pd.DataFrame, kolom: str, judul: str, satuan: str) -> None:
    st.markdown(f"**{judul}**")
    data_grafik = df[["waktu_wib", kolom]].dropna()
    if data_grafik.empty:
        st.info(f"Belum ada data {judul.lower()} yang valid untuk grafik.")
    else:
        st.line_chart(
            data_grafik,
            x="waktu_wib",
            y=kolom,
            x_label="Waktu (WIB)",
            y_label=satuan,
            height=250,
        )


def tampilkan_dashboard() -> None:
    try:
        with st.spinner("Mengambil data dari Supabase REST API..."):
            df = ambil_data(banyak_data)
    except requests.HTTPError as exc:
        kode = exc.response.status_code if exc.response is not None else "?"
        st.error(f"Gagal mengambil data Supabase (HTTP {kode}).")
        if exc.response is not None:
            try:
                pesan_server = exc.response.json()
                if isinstance(pesan_server, dict):
                    st.code(str(pesan_server.get("message", pesan_server)), language="text")
            except ValueError:
                st.caption("Respons kesalahan server bukan JSON.")
        if kode == 400:
            st.info(
                "Pastikan tabel public.monitoring_air sudah memiliki kolom "
                "adc_turbidity (int4) dan turbidity_index (float8)."
            )
        elif kode in (401, 403):
            st.info("Periksa publishable key dan kebijakan SELECT/RLS tabel monitoring_air.")
        return
    except (requests.RequestException, ValueError) as exc:
        st.error(f"Tidak dapat membaca data Supabase: {exc}")
        return
    except (KeyError, TypeError) as exc:
        st.error(f"Struktur data dari Supabase tidak sesuai: {exc}")
        return

    if df.empty:
        st.warning("Supabase REST API mengembalikan 0 baris untuk esp32-01.")
        st.info(
            "Jika SQL Editor menunjukkan 19 baris, periksa apakah role anon "
            "mempunyai hak SELECT dan kebijakan RLS SELECT, serta pastikan "
            "SUPABASE_URL mengarah ke proyek yang sama."
        )
        return

    terbaru = df.iloc[-1]
    waktu_terakhir = terbaru["waktu_wib"].strftime("%d %b %Y, %H:%M:%S WIB")
    st.caption(
        f"Pengukuran terbaru: {waktu_terakhir} · Perangkat: "
        f"{terbaru['device_id']} · {len(df)} data ditampilkan"
    )

    kolom_ph, kolom_tds, kolom_suhu, kolom_turbidity = st.columns(4)
    with kolom_ph:
        st.metric("pH terbaru", angka_terbaru(terbaru["ph"]))
    with kolom_tds:
        st.metric("TDS terbaru", angka_terbaru(terbaru["tds_ppm"], " ppm"))
    with kolom_suhu:
        st.metric("Suhu terbaru", angka_terbaru(terbaru["suhu_c"], " °C"))
    with kolom_turbidity:
        st.metric(
            "Turbidity (indeks)",
            angka_terbaru(terbaru["turbidity_index_grafik"], " %", 1),
        )
        st.caption(
            f"ADC: {angka_terbaru(terbaru['adc_turbidity'], digit=0)}"
        )

    if bool(terbaru["ph_warning"]):
        st.warning("pH terbaru memiliki peringatan ADC; periksa kestabilan dan kalibrasinya.")
    else:
        st.info("Tidak ada flag peringatan pH terbaru. Hal ini bukan bukti akurasi sensor.")

    if pd.isna(terbaru["adc_turbidity"]):
        st.info(
            "Turbidity belum terkirim. Pada kode ESP32, aktifkan "
            "KIRIM_TURBIDITY_SUPABASE = true setelah kolom database dibuat."
        )
    elif not bool(terbaru["turbidity_adc_valid"]):
        st.warning("ADC turbidity terbaru tidak valid dan tidak dipakai dalam grafik indeks.")
    elif pd.isna(terbaru["turbidity_index_grafik"]):
        st.warning("ADC turbidity terbaca, tetapi indeks belum tersedia/valid.")
    elif terbaru["turbidity_index_grafik"] == 0:
        st.info(
            "Indeks turbidity 0% dapat terjadi karena pembatasan nilai hasil rumus. "
            "Pastikan referensi ADC bersih dan keruh telah dikalibrasi ulang."
        )

    jumlah_adc_invalid = int(
        (df["adc_turbidity"].notna() & ~df["turbidity_adc_valid"]).sum()
    )
    if jumlah_adc_invalid:
        st.caption(
            f"{jumlah_adc_invalid} pembacaan ADC turbidity jenuh/rendah "
            "dikecualikan dari grafik indeks; data sensor lain tetap ditampilkan."
        )

    st.subheader("Grafik historis")
    st.caption("Seluruh waktu grafik ditampilkan dalam WIB (Asia/Jakarta).")
    kiri_atas, kanan_atas = st.columns(2)
    with kiri_atas:
        grafik(df, "ph", "pH", "pH")
    with kanan_atas:
        grafik(df, "tds_ppm", "TDS", "ppm")

    kiri_bawah, kanan_bawah = st.columns(2)
    with kiri_bawah:
        grafik(df, "suhu_c", "Suhu air", "°C")
    with kanan_bawah:
        grafik(df, "turbidity_index_grafik", "Turbidity", "Indeks relatif (%)")

    st.subheader("Riwayat pengukuran")
    riwayat = df.copy()
    if sembunyikan_adc_invalid:
        riwayat = riwayat[
            riwayat["adc_turbidity"].isna() | riwayat["turbidity_adc_valid"]
        ]

    riwayat["status_turbidity"] = riwayat.apply(
        lambda baris: kategori_turbidity(
            baris["adc_turbidity"], baris["turbidity_index"]
        ),
        axis=1,
    )
    riwayat = riwayat[
        [
            "waktu_wib", "device_id", "ph", "tds_ppm", "suhu_c",
            "adc_turbidity", "turbidity_index", "status_turbidity", "ph_warning",
        ]
    ].copy()
    riwayat.columns = [
        "Waktu (WIB)", "Perangkat", "pH", "TDS (ppm)", "Suhu (°C)",
        "ADC Turbidity", "Indeks Turbidity (%)", "Status Turbidity", "Peringatan pH",
    ]
    riwayat = riwayat.sort_values("Waktu (WIB)", ascending=False)
    st.dataframe(riwayat, hide_index=True, use_container_width=True)
    st.download_button(
        "⬇️ Unduh riwayat CSV",
        data=riwayat.to_csv(index=False).encode("utf-8-sig"),
        file_name="riwayat_monitoring_air_4_sensor.csv",
        mime="text/csv",
    )

    st.caption(
        "Indeks turbidity adalah skala relatif hasil kalibrasi sensor, bukan NTU. "
        "Dashboard tidak membuktikan kelayakan air minum. "
        "Nilai pH masih menggunakan parameter kalibrasi pada firmware ESP32."
    )


if otomatis:
    if hasattr(st, "fragment"):
        # Opsional setelah koneksi terbukti benar; sebelumnya dekorator ini
        # menyulitkan identifikasi area dashboard yang kosong.
        st.fragment(run_every="60s")(tampilkan_dashboard)()
    else:
        st.warning("Versi Streamlit belum mendukung st.fragment; memakai mode manual.")
        tampilkan_dashboard()
else:
    tampilkan_dashboard()
