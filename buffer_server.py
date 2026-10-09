from flask import Flask, request, jsonify, send_from_directory
import uuid
import time
import os
import json
from datetime import datetime, timezone, timedelta

app = Flask(__name__)

# Папки
UPLOAD_FOLDER = 'uploads'
PREFILL_FOLDER = 'prefill_data'
STATIC_FOLDER = 'static'

os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(PREFILL_FOLDER, exist_ok=True)
os.makedirs(STATIC_FOLDER, exist_ok=True)

# API-токен для защиты служебных эндпоинтов
BUFFER_API_TOKEN = os.environ.get(
    'BUFFER_API_TOKEN',
    'caoXLvI1fGleTDN32_l5AQn2TUf6faa7NiyP8DBSzd-XswZAfbknFbbH1ccP-Uu0',
)

# Хранилище анкет
anketas = {}


# ============================================================
# АВТОРИЗАЦИЯ
# ============================================================
def _check_token():
    """Проверяет Bearer-токен. Возвращает (ok, error_response)."""
    auth = request.headers.get('Authorization', '') or ''
    if not auth.startswith('Bearer '):
        return False, (jsonify({'error': 'Unauthorized'}), 401)
    token = auth[7:].strip()
    if token != BUFFER_API_TOKEN:
        return False, (jsonify({'error': 'Unauthorized'}), 401)
    return True, None


# ============================================================
# CORS
# ============================================================
@app.after_request
def after_request(response):
    response.headers.add('Access-Control-Allow-Origin', '*')
    response.headers.add('Access-Control-Allow-Headers', 'Content-Type, Authorization')
    response.headers.add('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
    return response


@app.route('/api/anketa', methods=['OPTIONS'])
def options_anketa():
    return '', 200


@app.route('/api/anketa/prefill', methods=['OPTIONS'])
def options_prefill():
    return '', 200


# ============================================================
# ПУБЛИЧНЫЕ ЭНДПОИНТЫ
# ============================================================
@app.route('/', methods=['GET'])
def root():
    return jsonify({'status': 'ok', 'service': 'bufferfskdb'})


@app.route('/anketa.html', methods=['GET'])
def anketa_html():
    return send_from_directory(STATIC_FOLDER, 'anketa.html')


# ============================================================
# PREFILL — защищён Bearer
# ============================================================
@app.route('/api/anketa/prefill', methods=['POST'])
def save_prefill():
    ok, err = _check_token()
    if not ok:
        return err

    try:
        payload = request.get_json(force=True)
    except Exception:
        return jsonify({'error': 'Invalid JSON'}), 400

    token = (payload.get('token') or '').strip()
    encrypted = payload.get('encrypted') or ''
    iv = payload.get('iv') or ''

    if not token or not encrypted or not iv:
        return jsonify({'error': 'Missing fields'}), 400

    safe_token = ''.join(c for c in token if c.isalnum() or c in '-_')
    if len(safe_token) < 10:
        return jsonify({'error': 'Invalid token'}), 400

    record = {
        'token': token,
        'encrypted': encrypted,
        'iv': iv,
        'received_at': datetime.now(
            timezone(timedelta(hours=3))
        ).isoformat(timespec='seconds'),
    }

    path = os.path.join(PREFILL_FOLDER, f'{safe_token}.json')
    with open(path, 'w', encoding='utf-8') as f:
        json.dump(record, f, ensure_ascii=False)

    return jsonify({'status': 'ok', 'token': token}), 200


@app.route('/api/anketa/prefill', methods=['GET'])
def get_prefill():
    # ВАЖНО: этот эндпоинт вызывается из браузера соискателя через fetch.
    # Значит, он должен быть ПУБЛИЧНЫМ. Токен соискателя — это и есть
    # его ключ доступа. Проверять Bearer здесь нельзя.
    token = (request.args.get('token') or '').strip()
    if not token:
        return jsonify({'error': 'Missing token'}), 400

    safe_token = ''.join(c for c in token if c.isalnum() or c in '-_')
    path = os.path.join(PREFILL_FOLDER, f'{safe_token}.json')

    if not os.path.exists(path):
        return jsonify({'error': 'Not found'}), 404

    with open(path, 'r', encoding='utf-8') as f:
        record = json.load(f)

    return jsonify(record), 200


# ============================================================
# ПРИЁМ АНКЕТЫ — публичный (соискатель)
# ============================================================
@app.route('/api/anketa', methods=['POST'])
def submit_anketa():
    data = request.form.to_dict()
    files = request.files.getlist('files')

    if not data:
        return jsonify({'error': 'Нет данных'}), 400

    client_ip = request.remote_addr
    if request.headers.get('X-Real-IP'):
        client_ip = request.headers.get('X-Real-IP').strip()
    elif request.headers.get('X-Forwarded-For'):
        client_ip = request.headers.get('X-Forwarded-For').split(',')[0].strip()

    user_agent = request.headers.get('User-Agent', '')[:500]
    msk = timezone(timedelta(hours=3))
    received_at = datetime.now(msk).isoformat(timespec="seconds")

    data['client_ip'] = client_ip
    data['user_agent'] = user_agent
    data['received_at'] = received_at

    file_infos = []
    if files:
        for file in files:
            if file.filename == '':
                continue
            ext = os.path.splitext(file.filename)[1]
            new_filename = f"{uuid.uuid4()}{ext}"
            filepath = os.path.join(UPLOAD_FOLDER, new_filename)
            file.save(filepath)
            file_infos.append({
                'original_name': file.filename,
                'saved_name': new_filename,
                'size': os.path.getsize(filepath)
            })

    anketa_id = str(uuid.uuid4())
    data['id'] = anketa_id
    data['timestamp'] = time.time()
    data['files'] = file_infos

    anketas[anketa_id] = data

    return jsonify({'status': 'ok', 'id': anketa_id}), 201


# ============================================================
# СПИСОК АНКЕТ — защищён Bearer
# ============================================================
@app.route('/api/anketa', methods=['GET'])
def get_anketas():
    ok, err = _check_token()
    if not ok:
        return err
    return jsonify(list(anketas.values()))


@app.route('/api/anketa/<anketa_id>', methods=['DELETE'])
def delete_anketa(anketa_id):
    ok, err = _check_token()
    if not ok:
        return err

    if anketa_id in anketas:
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


# ============================================================
# СКАЧИВАНИЕ ФАЙЛА — защищён Bearer
# ============================================================
@app.route('/api/files/<filename>', methods=['GET'])
def get_file(filename):
    ok, err = _check_token()
    if not ok:
        return err

    filepath = os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(filepath):
        return send_from_directory(UPLOAD_FOLDER, filename)
    return jsonify({'error': 'File not found'}), 404


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
