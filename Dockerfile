FROM python:3.14-slim

# Устанавливаем системные зависимости для работы с PostgreSQL
RUN apt-get update && apt-get install -y \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Копируем зависимости и устанавливаем без кэша (чтобы образ был легче)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем весь код проекта (включая manage.py и папку warehouse_project)
COPY . .

# Собираем статику для корректного отображения админки
RUN python manage.py collectstatic --noinput

# Запускаем Django через боевой сервер gunicorn
CMD ["gunicorn", "warehouse_project.wsgi:application", "--bind", "0.0.0.0:8001"]
