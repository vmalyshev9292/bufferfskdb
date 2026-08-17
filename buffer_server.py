from flask import Flask, request, jsonify
import uuid
import time

app = Flask(__name__)

anketas = {}

@app.route('/api/anketa', methods=['POST'])
def submit_anketa():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'Нет данных'}), 400
    anketa_id = str(uuid.uuid4())
    data['id'] = anketa_id
    data['timestamp'] = time.time()
    anketas[anketa_id] = data
    return jsonify({'status': 'ok', 'id': anketa_id}), 201

@app.route('/api/anketa', methods=['GET'])
def get_anketas():
    return jsonify(list(anketas.values()))

@app.route('/api/anketa/<anketa_id>', methods=['DELETE'])
def delete_anketa(anketa_id):
    if anketa_id in anketas:
        del anketas[anketa_id]
        return jsonify({'status': 'ok'}), 200
    return jsonify({'error': 'Не найдено'}), 404

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
