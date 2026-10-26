import os

# The window imports PySide6 directly, so qtconsole and pyqtgraph must load
# the same binding even where QT_API names another one.
os.environ["QT_API"] = "pyside6"
os.environ["PYQTGRAPH_QT_LIB"] = "PySide6"

from .qt_locale import install_scientific_locale

install_scientific_locale()

from .main_window import MainWindow
