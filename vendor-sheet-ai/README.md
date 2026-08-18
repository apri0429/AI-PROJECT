# Vendor Sheet AI

Aplikasi buat baca data vendor/produk (dari CSV upload atau Google Sheet), lalu tanya-jawab soal data itu lewat chat berbasis AI (Gemini).

## Cara jalanin

Backend:
```
python -m uvicorn server:app --host 0.0.0.0 --port 8000 --reload
```

Frontend:
```
cd frontend
npm run dev
```

## Struktur folder

```
vendor-sheet-ai/
├── server.py           # Entry point API (FastAPI) - semua endpoint /api/* ada di sini
├── main.py             # Entry point CLI (proses file CSV lewat terminal, tanpa server)
├── config.py            # Baca .env, definisi Settings (API key, path, dll)
├── models.py            # Struct data bersama (PipelineResult, NormalizedSheet, dll)
├── .env                  # API key & config lokal (JANGAN di-commit ke git)
│
├── core/                 # Logika murni, tidak ada koneksi ke API luar
│   ├── sheet_parser.py   # Parsing CSV mentah -> baris terstruktur (deteksi header, dedup kolom)
│   ├── validator.py      # Validasi baris (cek field wajib, format, dll)
│   ├── dieline.py        # Hitung ukuran dieline dari width/height
│   └── prompts.py        # Semua prompt yang dikirim ke Gemini (chat & summary)
│
├── adapters/             # Titik koneksi ke layanan luar (Gemini, Google Sheets, dll)
│   ├── llm.py            # Panggil Gemini API (generate_summary, answer_question)
│   ├── sheets.py         # Fetch CSV dari Google Sheets via link publik
│   ├── docs.py           # [STUB - belum beneran nulis ke Google Docs]
│   ├── drive.py          # [STUB - belum beneran connect ke Google Drive]
│   └── tracker.py        # [STUB - belum beneran update master sheet]
│
├── services/
│   └── pipeline.py       # Orkestrasi: gabungin parser + validator + llm + storage jadi satu alur
│
├── storage/
│   ├── state.py           # Akses SQLite (riwayat file diproses, sheet yang di-link, baris tersimpan)
│   └── state.db           # File database SQLite-nya
│
├── tests/                 # Unit test (pytest)
│
└── frontend/               # React app (Vite) - UI chat & upload
    └── src/
        ├── App.jsx
        └── components/     # Composer (kolom chat/link), ChatArea, Sidebar
```

## Alur data

1. **Upload CSV** (`/api/upload`) → `process_file()` di pipeline.py → tersimpan permanen di SQLite.
2. **Link Google Sheet** (`/api/sheets/process`) → `process_google_sheet()` → sheet-nya dicatat sebagai "linked" (bukan disalin).
3. **Chat** (`/api/chat`) → gabungan data CSV lokal (dari SQLite) + data sheet yang di-link (di-fetch **live** tiap kali chat, jadi selalu data terbaru, bukan basi).

## Yang masih stub (belum beneran jalan)

`adapters/docs.py`, `adapters/drive.py`, `adapters/tracker.py` cuma mengembalikan data dummy — belum benar-benar terhubung ke Google Docs/Drive. Untuk mengaktifkan itu perlu setup OAuth credential Google Cloud (lihat percakapan sebelumnya soal ini).
