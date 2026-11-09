            x="waktu_wib",
            y=kolom,
            x_label="Waktu (WIB)",
            y_label=satuan,
            height=250,
        )


@st.fragment(run_every="60s")
def tampilkan_dashboard() -> None:
    try:
        df = ambil_data(banyak_data)
    except requests.HTTPError as exc:
        kode = exc.response.status_code if exc.response is not None else "?"
        st.error(f"Gagal mengambil data Supabase (HTTP {kode}).")
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

    if df.empty:
        st.info("Belum ada data yang dapat dibaca. Periksa ESP32, RLS, dan device_id.")
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
