"""Generate two synthetic PDFs for manual and live-provider regression checks."""

from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


def main():
    root = Path("output/pdf/regression")
    root.mkdir(parents=True, exist_ok=True)
    pdfmetrics.registerFont(TTFont("Fixture", "C:/Windows/Fonts/arial.ttf"))
    for name, narrow in [("repeated-contract", False), ("repeated-table", True)]:
        pdf = canvas.Canvas(str(root / f"{name}.pdf"))
        pdf.setTitle("Синтетический тест обезличивания")
        for page in range(2):
            pdf.setFont("Fixture", 15)
            pdf.drawString(45, 795, "Синтетический тест: " + ("таблица" if narrow else "договор"))
            pdf.setFont("Fixture", 11)
            lines = [
                "Поставщик: ООО «Тестовый Вектор».",
                "Представитель: Иванов Иван Иванович.",
                "Покупатель: ООО «Учебная Орбита».",
                "Адрес: г. Москва, ул. Тестовая, д. 17.",
                "Почта: contact@example.test",
                "Повтор: ООО «Тестовый Вектор».",
                "Подпись: Иванов Иван Иванович.",
                "Повтор: ООО «Учебная Орбита».",
                "Адрес: г. Москва, ул. Тестовая, д. 17.",
                "Почта: contact@example.test",
            ]
            for index, text in enumerate(lines):
                y = 750 - index * 38
                if narrow:
                    pdf.rect(40, y - 9, 510, 30)
                    pdf.line(105, y - 9, 105, y + 21)
                    pdf.drawString(48, y, str(index + 1))
                pdf.drawString(115 if narrow else 45, y, text)
            pdf.drawString(45, 300, "Многострочное имя: Иванов Иван")
            pdf.drawString(45, 286, "Иванович. Соседний текст должен сохраниться.")
            pdf.drawString(45, 245, "Договор № 7. Короткое поле для длинной подписи.")
            pdf.drawString(45, 75, f"Страница {page + 1}. Все данные вымышлены.")
            pdf.showPage()
        pdf.save()


if __name__ == "__main__":
    main()
