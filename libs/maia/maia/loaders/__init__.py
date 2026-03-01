from __future__ import annotations

from importlib import import_module

__all__ = [
    "AutoReader",
    "AzureAIDocumentIntelligenceLoader",
    "BaseReader",
    "PandasExcelReader",
    "ExcelReader",
    "MathpixPDFReader",
    "OCRAugmentedPDFReader",
    "OCRImageReader",
    "ImageReader",
    "OCRReader",
    "DirectoryReader",
    "UnstructuredReader",
    "DocxReader",
    "HtmlReader",
    "MhtmlReader",
    "AdobeReader",
    "TxtReader",
    "PDFThumbnailReader",
    "WebReader",
    "DoclingReader",
]

_EXPORTS = {
    "AutoReader": (".base", "AutoReader"),
    "BaseReader": (".base", "BaseReader"),
    "AzureAIDocumentIntelligenceLoader": (".azureai_document_intelligence_loader", "AzureAIDocumentIntelligenceLoader"),
    "PandasExcelReader": (".excel_loader", "PandasExcelReader"),
    "ExcelReader": (".excel_loader", "ExcelReader"),
    "MathpixPDFReader": (".mathpix_loader", "MathpixPDFReader"),
    "OCRAugmentedPDFReader": (".local_ocr_loader", "OCRAugmentedPDFReader"),
    "OCRImageReader": (".local_ocr_loader", "OCRImageReader"),
    "ImageReader": (".ocr_loader", "ImageReader"),
    "OCRReader": (".ocr_loader", "OCRReader"),
    "DirectoryReader": (".composite_loader", "DirectoryReader"),
    "UnstructuredReader": (".unstructured_loader", "UnstructuredReader"),
    "DocxReader": (".docx_loader", "DocxReader"),
    "HtmlReader": (".html_loader", "HtmlReader"),
    "MhtmlReader": (".html_loader", "MhtmlReader"),
    "AdobeReader": (".adobe_loader", "AdobeReader"),
    "TxtReader": (".txt_loader", "TxtReader"),
    "PDFThumbnailReader": (".pdf_loader", "PDFThumbnailReader"),
    "WebReader": (".web_loader", "WebReader"),
    "DoclingReader": (".docling_loader", "DoclingReader"),
}


def __getattr__(name: str):
    try:
        module_name, attribute_name = _EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc

    module = import_module(module_name, __name__)
    value = getattr(module, attribute_name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    return sorted(set(globals()) | set(__all__))
