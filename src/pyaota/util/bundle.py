"""
Bundle PDF documents from a directory into uniform-sized bundles.

Optionally generates a "co-bundle" consisting of the last page of each
input document concatenated into a single PDF.
"""

from __future__ import annotations

import math
from pathlib import Path

import PyPDF2

import logging
logger = logging.getLogger(__name__)


def bundle_pdfs(input_dir: Path, output_dir: Path, bundle_size: int,
                co_bundle: bool = False) -> int:
    """
    Bundle all PDFs in *input_dir* into new PDF files, each containing
    *bundle_size* documents concatenated in sorted order.

    Parameters
    ----------
    input_dir : Path
        Directory to scan for ``*.pdf`` files.
    output_dir : Path
        Directory where bundle PDFs (and optional co-bundle) are written.
    bundle_size : int
        Number of source documents per bundle.
    co_bundle : bool
        If True, also produce a PDF that concatenates the last page of
        every source document.

    Returns
    -------
    int
        0 on success, 1 on error.
    """
    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"No PDF files found in {input_dir}")
        return 1

    output_dir.mkdir(parents=True, exist_ok=True)

    num_bundles = math.ceil(len(pdf_files) / bundle_size)
    print(f"Found {len(pdf_files)} PDFs; creating {num_bundles} bundle(s) "
          f"of up to {bundle_size} documents each.")

    for bundle_idx in range(num_bundles):
        start = bundle_idx * bundle_size
        end = min(start + bundle_size, len(pdf_files))
        chunk = pdf_files[start:end]

        writer = PyPDF2.PdfWriter()
        for doc_idx, pdf_path in enumerate(chunk):
            reader = PyPDF2.PdfReader(str(pdf_path))
            for page in reader.pages:
                writer.add_page(page)
            # Insert a blank page after every document except the last
            if doc_idx < len(chunk) - 1:
                last_page = reader.pages[-1]
                w = float(last_page.mediabox.width)
                h = float(last_page.mediabox.height)
                writer.add_blank_page(width=w, height=h)

        bundle_name = f"bundle_{bundle_idx + 1:03d}.pdf"
        bundle_path = output_dir / bundle_name
        with open(bundle_path, "wb") as f:
            writer.write(f)
        print(f"  {bundle_name}: {len(chunk)} documents")

    if co_bundle:
        writer = PyPDF2.PdfWriter()
        for pdf_path in pdf_files:
            reader = PyPDF2.PdfReader(str(pdf_path))
            if len(reader.pages) > 0:
                writer.add_page(reader.pages[-1])

        co_bundle_path = output_dir / "co_bundle.pdf"
        with open(co_bundle_path, "wb") as f:
            writer.write(f)
        print(f"  co_bundle.pdf: last page from each of {len(pdf_files)} documents")

    print("Done.")
    return 0


def bundle_subcommand(args) -> int:
    """CLI entry point for the ``bundle`` subcommand."""
    input_dir = Path(args.input_dir)
    output_dir = Path(args.output_dir)

    if not input_dir.is_dir():
        print(f"Input directory does not exist: {input_dir}")
        return 1

    return bundle_pdfs(
        input_dir=input_dir,
        output_dir=output_dir,
        bundle_size=args.bundle_size,
        co_bundle=args.co_bundle,
    )
