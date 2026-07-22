#!/usr/bin/env python3
"""Remove a password from a PDF, writing an unencrypted copy.

Usage:
    python remove_pdf_password.py input.pdf [output.pdf] [-p PASSWORD]

If no output path is given, "<input>_decrypted.pdf" is used.
If no password is given with -p, you'll be prompted securely.

Requires: pypdf  (pip install pypdf)
"""
import argparse
import getpass
import sys
from pathlib import Path

try:
    from pypdf import PdfReader, PdfWriter
except ImportError:
    sys.exit("Missing dependency. Install it with:  pip install pypdf")


def remove_password(input_path: Path, output_path: Path, password: str) -> None:
    reader = PdfReader(str(input_path))

    if reader.is_encrypted:
        # decrypt() returns 0 on failure, non-zero on success
        if not reader.decrypt(password):
            sys.exit("Incorrect password — could not decrypt the PDF.")
    else:
        print("Note: this PDF is not encrypted; writing a plain copy anyway.")

    writer = PdfWriter()
    for page in reader.pages:
        writer.add_page(page)

    # copy over any document metadata
    if reader.metadata:
        writer.add_metadata(reader.metadata)

    with open(output_path, "wb") as f:
        writer.write(f)

    print(f"Done. Unlocked PDF written to: {output_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Remove the password from a PDF.")
    parser.add_argument("input", type=Path, help="path to the encrypted PDF")
    parser.add_argument("output", type=Path, nargs="?", help="output path (optional)")
    parser.add_argument("-p", "--password", help="PDF password (prompted if omitted)")
    args = parser.parse_args()

    if not args.input.is_file():
        sys.exit(f"Input file not found: {args.input}")

    output = args.output or args.input.with_name(f"{args.input.stem}_decrypted.pdf")
    password = args.password or getpass.getpass("PDF password: ")

    remove_password(args.input, output, password)


if __name__ == "__main__":
    main()
