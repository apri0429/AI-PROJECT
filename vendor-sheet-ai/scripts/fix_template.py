from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.google_auth import docs_service

DOC_ID = "1USMskP_kio9-4ELHVOogvcQaH4CSIBBGPkVj0KAPITI"

REPLACEMENTS = [
    (
        "- {{PRODUCT_NAME}} ABSORBER SINGLE BIG HOOK WITH CARABINER"
        "\x0b- {{PRODUCT_NAME}} ABSORBER DOUBLE BIG HOOK WITH CARABINER",
        "{{VARIAN_PRODUK}}",
    ),
    (
        "- Double lanyard with absorber\x0b- Double big hook\x0b- Big carabiner"
        "\x0b- Carmantel rope\x0b- Plastic webbing back pad",
        "{{SPEC_DETAILS}}",
    ),
    ("Webbing polyester yang kuat membantu menopang tubuh dengan aman saat bekerja.", "{{FITUR_1}}"),
    ("Desain full body membantu mendistribusikan beban secara lebih merata.", "{{FITUR_2}}"),
    ("Strap adjustable memudahkan penyesuaian agar lebih pas dan nyaman digunakan.", "{{FITUR_3}}"),
    ("Metal buckle kokoh membantu memberikan penguncian yang lebih aman.", "{{FITUR_4}}"),
    (
        "Cocok digunakan untuk pekerjaan konstruksi, maintenance, proyek, dan industri.",
        "{{FITUR_5}}",
    ),
]


def main() -> None:
    docs = docs_service()
    requests = [
        {"replaceAllText": {"containsText": {"text": find, "matchCase": True}, "replaceText": replace}}
        for find, replace in REPLACEMENTS
    ]
    response = docs.documents().batchUpdate(documentId=DOC_ID, body={"requests": requests}).execute()

    for (find, replace), result in zip(REPLACEMENTS, response.get("replies", [])):
        count = result.get("replaceAllText", {}).get("occurrencesChanged", 0)
        preview = find if len(find) <= 50 else find[:47] + "..."
        print(f"  [{count}x] {preview!r} -> {replace!r}")


if __name__ == "__main__":
    main()
