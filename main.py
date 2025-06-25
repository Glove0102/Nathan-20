from app import app, socketio

# For gunicorn deployment
application = socketio

if __name__ == '__main__':
    # Run the Flask-SocketIO app for development
    socketio.run(app, host='0.0.0.0', port=5000, debug=True, allow_unsafe_werkzeug=True)
