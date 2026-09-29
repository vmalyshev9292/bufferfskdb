from flask import Flask, request, jsonify, send_from_directory
import uuid
import time
import os
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# Папка для загрузки файлов
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# === CORS (разрешаем запросы с любых сайтов) ===
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
    return response

@app.route('/api/anketa', methods=['OPTIONS'])
def options_anketa():
    return '', 200

# === ПРИЁМ АНКЕТЫ (ТЕКСТ + ФАЙЛЫ) ===
@app.route('/api/anketa', methods=['POST'])
def submit_anketa():
    # Берём текстовые поля
    data = request.form.to_dict()
    # Берём все загруженные файлы
    files = request.files.getlist('files')

    if not data:
        return jsonify({'error': 'Нет данных'}), 400

    # ===== БЛОК: IP, User-Agent, время (152-ФЗ) =====
    # IP: сначала X-Real-IP (если перед буфером nginx), потом X-Forwarded-For, потом remote_addr
    client_ip = request.remote_addr
    if request.headers.get('X-Real-IP'):
        client_ip = request.headers.get('X-Real-IP').strip()
    elif request.headers.get('X-Forwarded-For'):
        client_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()

    # User-Agent (браузер + ОС), обрезаем до 500 символов
    user_agent = request.headers.get('User-Agent', '')[:500]

    # Время получения — МСК (UTC+3), с явной таймзоной
    msk = timezone(timedelta(hours=3))
    received_at = datetime.now(msk).isoformat(timespec="seconds")

    data['client_ip'] = client_ip
    data['user_agent'] = user_agent
    data['received_at'] = received_at
    # ===== КОНЕЦ БЛОКА =====

    file_infos = []
    if files:
        for file in files:
            if file.filename == '':
                continue
            # Сохраняем файл с новым уникальным именем
            ext = os.path.splitext(file.filename)[1]
            new_filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, new_filename)
            file.save(filepath)
            file_infos.append({
                'original_name': file.filename,
                'saved_name': new_filename,
                'size': os.path.getsize(filepath)
            })

    # Генерируем ID анкеты
    anketa_id = str(uuid.uuid4())
    data['id'] = anketa_id
    data['timestamp'] = time.time()
    data['files'] = file_infos

    # Сохраняем в словарь (в памяти)
    anketas[anketa_id] = data

    return jsonify({'status': 'ok', 'id': anketa_id}), 201

# === ПОЛУЧЕНИЕ СПИСКА ВСЕХ АНКЕТ ===
@app.route('/api/anketa', methods=['GET'])
def get_anketas():
    return jsonify(list(anketas.values()))

# === УДАЛЕНИЕ АНКЕТЫ (И ФАЙЛОВ) ===
@app.route('/api/anketa/<anketa_id>', methods=['DELETE'])
def delete_anketa(anketa_id):
    if anketa_id in anketas:
        # Удаляем файлы
        files = anketas[anketa_id].get('files', [])
        for f in files:
            saved_name = f.get('saved_name')
            if saved_name:
                filepath = os.path.join(UPLOAD_FOLDER, saved_name)
                if os.path.exists(filepath):
                    os.remove(filepath)
        del anketas[anketa_id]
        return jsonify({'status': 'ok'}), 200
    return jsonify({'error': 'Не найдено'}), 404

# === СКАЧИВАНИЕ ФАЙЛА ПО ИМЕНИ ===
@app.route('/api/files/<filename>', methods=['GET'])
def get_file(filename):
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_from_directory(UPLOAD_FOLDER, filename)
    return jsonify({'error': 'File not found'}), 404

# Хранилище анкет (в оперативной памяти)
anketas = {}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
