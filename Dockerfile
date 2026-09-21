FROM python:3.11-slim

WORKDIR /app

# نصب library های مورد نیاز
RUN pip install --no-cache-dir pyTelegramBotAPI

# دایرکتوری برای دیتابیس رو ساخت و صحیح تنظیم کن
RUN mkdir -p /data && chmod 755 /data

# کپی کردن کد ربات
COPY casinomeowicop.py .

# اجرای ربات
CMD ["python", "casinomeowicop.py"]
