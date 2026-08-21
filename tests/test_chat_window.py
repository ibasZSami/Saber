import threading

from PySide6.QtWidgets import QApplication

from src.ui.chat_window import ChatWindow


class TestAppendMessageEscaping:
    def test_escapes_html_special_characters(self):
        """Regression test: append_message() used to interpolate sender/text
        straight into an HTML string handed to QTextEdit.append(), which
        auto-detects rich text — so a message containing '<' or '>' (e.g. a
        code snippet, or "x < 5 and y > 3") got parsed as tag syntax and
        silently mangled instead of shown literally."""
        window = ChatWindow("Silva")
        window.append_message("Você", "x < 5 and y > 3")
        QApplication.processEvents()

        assert "x &lt; 5 and y &gt; 3" in window.chat_display.toHtml()
        assert "x < 5 and y > 3" in window.chat_display.toPlainText()


class TestAppendMessageThreadSafety:
    def test_safe_to_call_from_a_background_thread(self):
        """Regression test: EventBus subscribers (spontaneous speech,
        background-task announcements) call append_message() from a daemon
        thread, not the GUI thread. append_message used to touch the
        QTextEdit directly — an unsafe cross-thread Qt call. It now just
        queues a signal, so calling it off-thread must not raise and the
        text must show up once the GUI thread processes its event queue."""
        window = ChatWindow("Silva")

        thread = threading.Thread(target=window.append_message, args=("Silva", "oi de outra thread"))
        thread.start()
        thread.join()

        QApplication.processEvents()

        assert "oi de outra thread" in window.chat_display.toPlainText()
