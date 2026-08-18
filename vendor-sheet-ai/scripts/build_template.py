"""One-off pilot: duplicate the sample instruction-manual doc and swap the
product-specific text for {{PLACEHOLDER}} tokens, so the result can be
reviewed before it's used for real per-product generation."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.google_auth import docs_service, drive_service

SOURCE_DOC_ID = "1p9glXgcbocTr67nhO2w14FTP9DcVkPPSnHJcZ96oyq0"

# Ordered longest/most-specific first, so a shorter token (e.g. "FBH") isn't
# consumed as part of a longer one (e.g. "GOSAVE ECO MAXIS FBH") beforehand.
REPLACEMENTS = [
    ("GOSAVE ECO MAXIS FBH", "{{PRODUCT_NAME}}"),
    ("GOSAVE PRO", "{{MEREK}}"),
    ("P001962", "{{TIPE}}"),
    ("Harness Pengaman Tubuh", "{{NAMA_BARANG_DESKRIPSI}}"),
    ("FBH", "{{ITEM_NAME}}"),
    (
        "GOSAVE ECO Maxis {{ITEM_NAME}} adalah full body harness yang dirancang untuk membantu "
        "memberikan perlindungan saat bekerja di ketinggian. Dengan desain ergonomis dan material "
        "webbing yang kuat, harness ini membantu menjaga posisi tubuh tetap stabil sehingga "
        "memberikan rasa aman dan nyaman selama bekerja.",
        "{{DESKRIPSI_PRODUK}}",
    ),
    (
        "Digunakan sebagai alat pelindung diri untuk membantu mengurangi risiko jatuh saat bekerja "
        "di ketinggian.",
        "{{FUNGSI_PRODUK}}",
    ),
    (
        "- Double lanyard with absorber\n- Double big hook\n- Big carabiner\n- Carmantel rope\n"
        "- Plastic webbing back pad",
        "{{SPEC_DETAILS}}",
    ),
    ("CE EN354:2010, EN355:2022", "{{SERTIFIKAT}}"),
    ("15kN", "{{KAPASITAS}}"),
    ("China", "{{MADE_IN}}"),
    ("1 Set Body Harness", "{{ISI_KEMASAN}}"),
    (
        "- GOSAVE ECO MAXIS {{ITEM_NAME}} ABSORBER SINGLE BIG HOOK WITH CARABINER\n"
        "- GOSAVE ECO MAXIS {{ITEM_NAME}} ABSORBER DOUBLE BIG HOOK WITH CARABINER",
        "{{VARIAN_PRODUK}}",
    ),
    (
        "1. Webbing polyester yang kuat membantu menopang tubuh dengan aman saat bekerja.\n"
        "   2. Desain full body membantu mendistribusikan beban secara lebih merata.\n"
        "   3. Strap adjustable memudahkan penyesuaian agar lebih pas dan nyaman digunakan.\n"
        "   4. Metal buckle kokoh membantu memberikan penguncian yang lebih aman.\n"
        "   5. Cocok digunakan untuk pekerjaan konstruksi, maintenance, proyek, dan industri.",
        "{{FITUR_PRODUK}}",
    ),
    (
        "1. Kenakan harness dengan posisi yang benar pada tubuh.\n"
        "2. Sesuaikan seluruh strap hingga pas dan nyaman digunakan.\n"
        "3. Kaitkan lanyard ke anchor point yang aman sebelum mulai bekerja.\n"
        "4. Pastikan seluruh buckle telah terkunci dengan baik sebelum digunakan.",
        "{{CARA_PENGGUNAAN}}",
    ),
    (
        "1. Periksa kondisi webbing, buckle, dan jahitan sebelum digunakan.\n"
        "2. Bersihkan dari debu dan kotoran setelah pemakaian.\n"
        "3. Simpan di tempat yang kering dan terhindar dari sinar matahari langsung.\n"
        "4. Jangan gunakan apabila terdapat kerusakan pada harness.",
        "{{PERAWATAN}}",
    ),
]


def main() -> None:
    drive = drive_service()
    copy = drive.files().copy(
        fileId=SOURCE_DOC_ID,
        body={"name": "TEMPLATE (placeholder) - Instruction Manual"},
    ).execute()
    new_id = copy["id"]

    requests = [
        {
            "replaceAllText": {
                "containsText": {"text": find, "matchCase": True},
                "replaceText": replace,
            }
        }
        for find, replace in REPLACEMENTS
    ]

    docs = docs_service()
    response = docs.documents().batchUpdate(documentId=new_id, body={"requests": requests}).execute()

    print(f"New doc: https://docs.google.com/document/d/{new_id}/edit\n")
    print("Replacement results:")
    for (find, replace), result in zip(REPLACEMENTS, response.get("replies", [])):
        count = result.get("replaceAllText", {}).get("occurrencesChanged", 0)
        preview = find if len(find) <= 50 else find[:47] + "..."
        print(f"  [{count}x] {preview!r} -> {replace!r}")


if __name__ == "__main__":
    main()
