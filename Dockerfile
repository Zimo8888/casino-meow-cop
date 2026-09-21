FROM python:3.11-slim

WORKDIR /app

# نصب library های مورد نیاز
RUN pip install --no-cache-dir pyTelegramBotAPI

# کپی کردن کد ربات
COPY casinomeowicop_fixed.py .

# تنظیم دایرکتوری برای دیتابیس
RUN mkdir -p /data

# اجرای ربات
CMD ["python", "casinomeowicop_fixed.py"]
