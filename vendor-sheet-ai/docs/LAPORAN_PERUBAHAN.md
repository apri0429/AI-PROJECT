# Laporan Perubahan Backend — Vendor Sheet AI

Tanggal: 24 Juli 2026

## Ringkasan

Backend aplikasi Vendor Sheet AI (FastAPI + Gemini) mengalami beberapa perbaikan: migrasi library AI yang deprecated, migrasi database dari file lokal (SQLite) ke MySQL (Laragon), dan perbaikan performa saat memproses Google Sheet berukuran besar.

## 1. Migrasi library Gemini

**Masalah:** Backend pakai `google.generativeai`, package yang sudah resmi dihentikan dukungannya oleh Google (muncul `FutureWarning` tiap server jalan).

**Perbaikan:** Migrasi ke package pengganti resmi, `google.genai`. Perubahan di `adapters/llm.py` dan `requirements.txt`. Tidak ada perubahan perilaku dari sisi pengguna.

## 2. Migrasi database: SQLite → MySQL (Laragon)

**Sebelumnya:** Semua data (riwayat file diproses, baris data vendor/produk, link Google Sheet) disimpan di satu file lokal `storage/state.db` (SQLite).

**Sekarang:** Data disimpan di MySQL yang jalan lewat Laragon (database `vendor_sheet_ai`), dengan struktur tabel yang sama (`processed_files`, `sheet_rows`, `linked_sheets`). Kredensial pakai default Laragon (`root`, tanpa password, port `3306`), dikonfigurasi lewat file `.env`.

**Catatan penting:** MySQL di Laragon harus dinyalakan dulu (klik **Start All** di Laragon) sebelum menjalankan backend, karena backend akan gagal connect kalau MySQL belum aktif.

File `storage/state.db` (SQLite lama) dan `sample.csv` (contoh data yang sudah tidak dipakai) sudah dihapus karena tidak relevan lagi.

## 3. Perbaikan performa saat link Google Sheet

**Masalah ditemukan:** Salah satu Google Sheet yang di-link ternyata berisi **1.201 baris data**. Proses lama membuat ringkasan (summary) pakai AI Gemini **satu per satu untuk setiap baris** saat sheet di-link — untuk 1.200+ baris ini bisa memakan waktu berjam-jam dan boros kuota API, padahal seharusnya hanya proses link/simpan data.

**Perbaikan:** Saat link Google Sheet, sistem sekarang **hanya menyimpan data mentahnya** ke database tanpa generate ringkasan AI per baris. Hasilnya, proses link sheet yang tadinya bisa berjam-jam sekarang selesai dalam hitungan detik.

## 4. Auto-sync Google Sheet yang sudah di-link

**Masalah:** Setelah di-link, data di database tidak otomatis mengikuti perubahan di Google Sheet aslinya (harus link ulang manual).

**Perbaikan:** Ditambahkan proses background di backend yang otomatis mengambil ulang data dari semua Google Sheet yang sudah di-link, setiap **5 menit** (bisa diubah lewat `SHEET_SYNC_INTERVAL_SECONDS` di `.env`). Jadi data di database akan selalu mengikuti isi Google Sheet dengan jeda maksimal ±5 menit, tanpa perlu link ulang manual.

## 5. Chat jadi jauh lebih cepat

**Masalah:** Sebelumnya, setiap kali chat/tanya ke AI, backend mengambil ulang data Google Sheet secara langsung (live) dari internet — ini membuat setiap pertanyaan terasa lambat karena tergantung koneksi ke server Google.

**Perbaikan:** Karena data sekarang sudah disinkron otomatis ke MySQL (lihat poin 4), fitur chat cukup membaca dari database lokal saja, tidak perlu fetch live lagi. Waktu respons chat turun drastis, dari berpotensi berjam-jam menjadi ±3 detik.

## 6. Soal efisiensi token AI

Ditinjau juga bagaimana biaya/penggunaan token ke Gemini saat chat, khususnya karena database sekarang berisi ribuan baris. Ternyata kode sudah punya mekanisme pembatasan bawaan (`core/prompts.py`):

- Jika data di database **≤ 20 baris**, semua dikirim ke AI.
- Jika **lebih dari 20 baris** (seperti kondisi sekarang, 1.245 baris), sistem mencari baris yang paling relevan berdasarkan kata kunci dari pertanyaan, dan hanya mengirim maksimal 20 baris yang paling relevan ke AI.
- Jika tidak ada baris yang cocok dengan kata kunci, AI hanya diberi daftar nama produk saja (jauh lebih hemat token) dan diminta menanyakan produk yang lebih spesifik ke pengguna.

Jadi penggunaan token per chat tetap terkendali meskipun jumlah data di database bertambah banyak — yang membesar hanya ukuran database, bukan biaya tiap chat.

**Catatan/temuan kecil (belum diperbaiki):** untuk pertanyaan yang sifatnya umum/meta (misal "ada berapa data yang kamu punya?"), pencocokan kata kunci bisa gagal menemukan baris relevan, sehingga jawaban AI kadang kurang akurat menggambarkan jumlah data sebenarnya. Ini area yang bisa disempurnakan lebih lanjut kalau diperlukan.

## Alasan Google Sheet tidak dijadikan database utama

Sempat didiskusikan kenapa tidak langsung pakai Google Sheet sebagai "database" tanpa disalin ke MySQL. Alasannya:

1. Google Sheet bukan database — tidak ada index/query cepat, semua akses harus download ulang isi sheet dan diproses manual.
2. Setiap akses ke Google Sheet butuh koneksi internet ke server Google dan berisiko kena rate limit kalau terlalu sering dipanggil.
3. Tidak efisien untuk menggabungkan data dari beberapa sumber (CSV upload + beberapa Google Sheet) dalam satu query cepat.

Kesimpulan: **Google Sheet tetap jadi sumber data asli** yang diedit tim secara manual, sedangkan **MySQL berfungsi sebagai salinan cepat** yang dipakai aplikasi untuk membaca data, dan disegarkan otomatis secara berkala.

## 7. Baca detail produk dari kolom "LINK DETAIL PRODUCT & GAMBAR DETAIL"

**Kebutuhan:** Kolom ini di sheet berisi tautan ke sheet lain per produk, yang isinya spesifikasi lengkap (ukuran, bahan, warna per varian, jumlah per karton, dll) — data yang tidak ada di sheet utama.

**Temuan:** Tautan di kolom ini bukan hyperlink teks biasa maupun formula `HYPERLINK()`, melainkan **"smart chip"** Google Sheets (link tertanam yang tidak ikut ter-export ke format CSV/HTML biasa). Untuk membacanya, dibutuhkan **Google Sheets API** (bukan cukup export CSV), sehingga dibuatkan API key baru khusus untuk itu (`GOOGLE_SHEETS_API_KEY` di `.env`), terpisah dari API key Gemini yang sudah ada. API key ini gratis (tidak perlu billing), dan aman karena sheet-nya memang sudah dibagikan sebagai "siapa saja yang punya link bisa melihat".

**Implementasi (2 tahap, biar tetap cepat):**
1. **Saat sync (setiap 5 menit):** Sistem mengambil URL asli di balik smart chip untuk semua baris sekaligus lewat 1 kali panggilan API (bukan per baris), lalu menyimpan URL tersebut sebagai kolom `detail_link` di database. Cepat dan murah — pada percobaan pertama berhasil menemukan 50 tautan detail produk.
2. **Saat chat (on-demand):** Kalau ada pertanyaan yang menyebut produk tertentu dan produk itu punya `detail_link`, barulah sheet detail-nya dibuka dan dibaca **saat itu juga**, lalu isinya digabung ke jawaban AI. Sheet detail lain yang tidak ditanyakan **tidak** ikut dibuka, supaya tidak lambat dan tidak boros kuota.

**Hasil pengujian:** Pertanyaan "kasih spesifikasi lengkap GOTO KERI BACKPACK KIDS" berhasil dijawab lengkap dengan ukuran per varian (26 x 25 x 11 cm), bahan (Oxford + eva), warna, jumlah per karton, kode HS, dll — data yang sebelumnya tidak tersedia di sheet utama. Waktu jawab untuk pertanyaan jenis ini sekitar 15 detik (karena perlu buka 1 sheet tambahan); pertanyaan umum yang tidak menyebut produk tertentu tetap ±3 detik seperti sebelumnya.
