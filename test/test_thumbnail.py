from collections.abc import Generator

import numpy as np
import pyqtgraph as pg
import pytest
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication

from brighteyes_mcs.ui.qt.thumbnail import jpeg_thumbnail


@pytest.fixture
def app() -> Generator[QApplication, None, None]:
    """Keep a Qt application alive for the test."""
    instance = QApplication.instance()
    yield instance if isinstance(instance, QApplication) else QApplication([])


@pytest.mark.usefixtures("app")
def test_thumbnail_is_a_jpeg_200_pixels_wide() -> None:
    """Encode an image item as a JPEG scaled to 200 pixels wide, keeping its aspect ratio."""
    view = pg.ImageView(view=pg.PlotItem())
    view.setImage(np.arange(400 * 100, dtype=np.float64).reshape(400, 100))

    jpeg = jpeg_thumbnail(view.imageItem)

    assert jpeg[:2] == b"\xff\xd8"
    image = QImage.fromData(jpeg)
    assert (image.width(), image.height()) == (200, 50)
