"""JPEG thumbnail of the image shown in the main window."""

import pyqtgraph as pg
import pyqtgraph.exporters
from PySide6.QtCore import QBuffer, QByteArray, QIODevice


def jpeg_thumbnail(image: pg.ImageItem) -> bytes:
    """Encode `image` as a JPEG 200 pixels wide."""
    exporter = pyqtgraph.exporters.ImageExporter(image)
    exporter.parameters()["width"] = 200
    bitmap = exporter.export(toBytes=True)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    bitmap.save(buffer, "JPEG")
    return bytes(data.data())
