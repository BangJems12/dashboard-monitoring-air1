# Dashboard Monitoring Kualitas Air — ESP32 + Supabase + Streamlit

Dashboard read-only untuk sensor pH, TDS, dan suhu ESP32, perangkat `esp32-01`.

## 1. Siapkan Supabase
1. Pastikan tabel `public.monitoring_air` sudah dibuat dan data dari ESP32 telah masuk.
2. Buka **SQL Editor** Supabase dan jalankan isi `sql_izin_baca.sql`.
3. **Catatan privasi:** SQL membuat kolom terpilih dari `esp32-01` dapat dibaca **publik** dengan publishable key. Jangan gunakan untuk dataset pribadi. Kebijakan INSERT ESP32 tidak diubah.

## 2. Jalankan di Windows (lokal)
1. Instal Python versi yang didukung Streamlit.
2. Buka terminal pada folder ini lalu jalankan:

   ```powershell
   py -m pip install -r requirements.txt
   ```

3. Buat `.streamlit/secrets.toml` sebagai salinan `.streamlit/secrets.toml.example`:

   ```powershell
   Copy-Item .streamlit\secrets.toml.example .streamlit\secrets.toml
   ```

4. Jalankan:

   ```powershell
   py -m streamlit run app.py
   ```

5. Buka `http://localhost:8501` jika tidak terbuka otomatis.

## 3. Deploy melalui Streamlit Community Cloud
1. Unggah `app.py`, `requirements.txt`, dan `.gitignore` ke repositori GitHub. Jangan unggah file `.streamlit/secrets.toml` lokal atau password Wi-Fi.
2. Kunjungi https://share.streamlit.io lalu pilih **Create app**.
3. Pilih repo, branch, dan entrypoint `app.py`.
4. Buka **Advanced settings → Secrets** dan isi variabel `SUPABASE_URL` dan `SUPABASE_KEY` menggunakan isi `.streamlit/secrets.toml.example` (tanpa baris komentar).
5. Deploy. Dashboard otomatis memuat data terbaru setiap 60 detik *ketika halamannya aktif*.

## Jika gagal
- HTTP 401: project key salah.
- HTTP 403 / kode 42501: cek `GRANT SELECT`, RLS, dan filter `device_id`.
- HTTP 404: URL proyek atau nama tabel salah.
- Data kosong: ESP32 belum mengirim atau device_id berbeda dari `esp32-01`.

**Catatan:** Pengukuran sensor belum dapat dijadikan bukti bahwa air aman diminum; pH perlu kalibrasi buffer dan sensor TDS butuh uji akurasi terhadap referensi.
