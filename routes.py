import os
import logging
from flask import render_template, request, jsonify
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse, Connect, Stream
from app import app, db
from models import Call

# Twilio configuration
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_PHONE_NUMBER = os.environ.get("TWILIO_PHONE_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/initiate_call', methods=['POST'])
def initiate_call():
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')
        
        if not phone_number:
            return jsonify({'error': 'Phone number is required'}), 400
        
        # Create call record
        call = Call(phone_number=phone_number, status='initiating')
        db.session.add(call)
        db.session.commit()
        
        # Get the public URL for webhook (you'll need to set this)
        webhook_url = os.environ.get("WEBHOOK_URL", "https://your-domain.com") + "/webhook"
        
        # Initiate Twilio call
        twilio_call = twilio_client.calls.create(
            to=phone_number,
            from_=TWILIO_PHONE_NUMBER,
            url=webhook_url,
            method='POST'
        )
        
        # Update call record with Twilio call SID
        call.call_sid = twilio_call.sid
        call.status = 'calling'
        db.session.commit()
        
        logging.info(f"Call initiated to {phone_number} with SID: {twilio_call.sid}")
        
        return jsonify({
            'success': True,
            'call_id': call.id,
            'call_sid': twilio_call.sid
        })
        
    except Exception as e:
        logging.error(f"Error initiating call: {str(e)}")
        return jsonify({'error': f'Failed to initiate call: {str(e)}'}), 500

@app.route('/webhook', methods=['POST'])
def webhook():
    """Twilio webhook endpoint - called when call is answered"""
    try:
        call_sid = request.form.get('CallSid')
        call_status = request.form.get('CallStatus')
        
        logging.info(f"Webhook called - CallSid: {call_sid}, Status: {call_status}")
        
        # Update call status in database
        call = Call.query.filter_by(call_sid=call_sid).first()
        if call:
            call.status = call_status
            db.session.commit()
        
        # Create TwiML response to establish Media Stream
        response = VoiceResponse()
        
        if call_status == 'answered':
            # Get WebSocket URL for media streaming
            websocket_url = os.environ.get("WEBSOCKET_URL", "wss://your-domain.com") + "/media_stream"
            
            connect = Connect()
            stream = Stream(url=websocket_url)
            connect.append(stream)
            response.append(connect)
            
            logging.info(f"Media stream established for call {call_sid}")
        
        return str(response), 200, {'Content-Type': 'text/xml'}
        
    except Exception as e:
        logging.error(f"Webhook error: {str(e)}")
        return str(VoiceResponse()), 500, {'Content-Type': 'text/xml'}

@app.route('/call_status/<int:call_id>')
def call_status(call_id):
    """Get current status of a call"""
    call = Call.query.get_or_404(call_id)
    return jsonify({
        'id': call.id,
        'phone_number': call.phone_number,
        'status': call.status,
        'call_sid': call.call_sid,
        'created_at': call.created_at.isoformat() if call.created_at else None
    })
