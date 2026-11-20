"""Application entry point."""
from __future__ import annotations

import sys
from pathlib import Path

# Allow direct execution (`python app/main.py`) as well as `python -m app.main`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

# Absolute imports keep this file working both as `python -m app.main` and as
# the top-level entry script used by PyInstaller (where relative imports fail).
from app import APP_NAME
from app.bootstrap import AppContext
from app.utils.logging import get_logger
from app.utils.paths import resource_base

log = get_logger("main")


def load_stylesheet(app: QApplication) -> None:
    path = resource_base() / "assets" / "styles" / "theme.qss"
    if path.exists():
        try:
            app.setStyleSheet(path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not load stylesheet: %s", exc)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv if argv is None else argv)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setOrganizationName(APP_NAME)
    load_stylesheet(app)

    ctx = AppContext()
    try:
        if not ctx.settings.onboarding_complete:
            from app.ui.onboarding import OnboardingWizard
            wizard = OnboardingWizard(ctx)
            if wizard.exec() != QApplication.DialogCode.Accepted:
                return 0
        from app.ui.main_window import MainWindow
        window = MainWindow(ctx)
        window.show()
        return app.exec()
    except Exception as exc:  # noqa: BLE001
        log.exception("Fatal startup error")
        QMessageBox.critical(None, f"{APP_NAME} — startup error",
                             f"The application could not start:\n\n{exc}")
        return 1
    finally:
        ctx.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
