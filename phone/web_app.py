#!/usr/bin/env python3
"""
Phone Automation Web Interface
==============================
Flask web app for controlling phone with live screen and logs.
"""

import sys
import os
import time
import json
import threading
import base64
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict
from io import BytesIO

from flask import Flask, render_template, jsonify, request, Response
from flask_cors import CORS

sys.path.insert(0, str(Path(__file__).parent.parent))

from phone.adb_controller import ADBController
from phone.scrcpy_manager import ScrcpyManager, ScrcpyPresets
from phone.browser_automation import PhoneBrowserAutomation
from phone.screen_reader import ScreenReader
from phone.logger import PhoneLogger, set_logger
from phone.card_checker import PhoneCardChecker, CardInfo, CheckStatus

app = Flask(__name__, 
            template_folder=str(Path(__file__).parent / 'templates'),
            static_folder=str(Path(__file__).parent / 'static'))
CORS(app)

# Global instances
logger: Optional[PhoneLogger] = None
adb: Optional[ADBController] = None
scrcpy: Optional[ScrcpyManager] = None
browser: Optional[PhoneBrowserAutomation] = None
screen_reader: Optional[ScreenReader] = None
card_checker: Optional[PhoneCardChecker] = None
device_info: Dict = {}
log_history: List[Dict] = []
MAX_LOGS = 100
card_check_status: Dict = {'status': 'idle', 'progress': 0, 'message': ''}


def init_phone():
    """Initialize phone automation components."""
    global logger, adb, scrcpy, browser, screen_reader, card_checker, device_info
    
    logger = PhoneLogger()
    set_logger(logger)
    
    # Register callback to capture logs
    logger.register_callback(capture_log)
    
    try:
        adb = ADBController(logger=logger)
        device_info = adb.get_device_info()
        scrcpy = ScrcpyManager(device_serial=adb.device_serial, logger=logger)
        browser = PhoneBrowserAutomation(adb, browser='brave', logger=logger)
        screen_reader = ScreenReader(adb, logger=logger)
        card_checker = PhoneCardChecker(
            adb=adb,
            browser=browser,
            screen_reader=screen_reader,
            logger=logger,
            status_callback=update_card_status
        )
        logger.info("Phone automation initialized", log_type='SYSTEM')
        return True
    except Exception as e:
        logger.error(f"Failed to initialize: {e}", log_type='SYSTEM')
        return False


def update_card_status(message: str, progress: int):
    """Update card check status for web display."""
    global card_check_status
    card_check_status = {
        'status': 'running',
        'progress': progress,
        'message': message,
        'timestamp': datetime.now().isoformat()
    }


def capture_log(entry: Dict):
    """Capture log entry for web display."""
    global log_history
    log_history.append(entry)
    if len(log_history) > MAX_LOGS:
        log_history.pop(0)


@app.route('/')
def index():
    """Main page."""
    return render_template('phone.html')


@app.route('/api/status')
def get_status():
    """Get current status."""
    return jsonify({
        'initialized': adb is not None,
        'device': device_info,
        'scrcpy_running': scrcpy.is_running() if scrcpy else False,
        'device_serial': adb.device_serial if adb else None
    })


@app.route('/api/logs')
def get_logs():
    """Get recent logs."""
    return jsonify(log_history[-50:])


@app.route('/api/logs/stream')
def stream_logs():
    """Stream logs via Server-Sent Events."""
    def generate():
        last_count = 0
        while True:
            if len(log_history) > last_count:
                new_logs = log_history[last_count:]
                for log in new_logs:
                    yield f"data: {json.dumps(log)}\n\n"
                last_count = len(log_history)
            time.sleep(0.5)
    
    return Response(generate(), mimetype='text/event-stream')


@app.route('/api/screenshot')
def get_screenshot():
    """Get current screenshot as base64 (optimized for speed)."""
    if not adb:
        return jsonify({'error': 'Not initialized'}), 500
    
    try:
        # Take screenshot with lower quality for speed
        screenshot_path = Path(__file__).parent / 'screenshots' / 'live.jpg'
        
        # Use screencap and convert to smaller JPEG
        import subprocess
        
        # Capture and resize in one command for speed
        result = subprocess.run([
            'adb', '-s', adb.device_serial, 'exec-out', 
            'screencap', '-p'
        ], capture_output=True, timeout=3)
        
        if result.returncode == 0:
            # Convert PNG to smaller JPEG using PIL
            from PIL import Image
            from io import BytesIO
            
            img = Image.open(BytesIO(result.stdout))
            # Convert RGBA to RGB (remove alpha channel)
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            # Resize to 40% for speed
            new_size = (img.width * 2 // 5, img.height * 2 // 5)
            img = img.resize(new_size, Image.Resampling.LANCZOS)
            
            # Save as JPEG with lower quality
            buffer = BytesIO()
            img.save(buffer, format='JPEG', quality=50, optimize=True)
            img_data = base64.b64encode(buffer.getvalue()).decode('utf-8')
            
            return jsonify({
                'image': f'data:image/jpeg;base64,{img_data}',
                'timestamp': datetime.now().isoformat()
            })
        else:
            return jsonify({'error': 'Screenshot failed'}), 500
            
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/open_url', methods=['POST'])
def open_url():
    """Open a URL on the phone."""
    if not browser:
        return jsonify({'error': 'Not initialized'}), 500
    
    data = request.json
    url = data.get('url', '')
    
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
    
    try:
        success = browser.open_url(url)
        return jsonify({'success': success, 'url': url})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tap', methods=['POST'])
def tap():
    """Tap at coordinates (with optional duration for long press)."""
    if not adb:
        return jsonify({'error': 'Not initialized'}), 500
    
    data = request.json
    x = data.get('x', 0)
    y = data.get('y', 0)
    duration = data.get('duration', 0)  # 0 = normal tap, >0 = long press
    
    try:
        success = adb.tap(x, y, duration=duration)
        return jsonify({'success': success, 'x': x, 'y': y, 'duration': duration})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/swipe', methods=['POST'])
def swipe():
    """Swipe on screen."""
    if not adb:
        return jsonify({'error': 'Not initialized'}), 500
    
    data = request.json
    x1 = data.get('x1', 0)
    y1 = data.get('y1', 0)
    x2 = data.get('x2', 0)
    y2 = data.get('y2', 0)
    duration = data.get('duration', 300)
    
    try:
        success = adb.swipe(x1, y1, x2, y2, duration)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/key', methods=['POST'])
def press_key():
    """Press a key."""
    if not adb:
        return jsonify({'error': 'Not initialized'}), 500
    
    data = request.json
    key = data.get('key', '')
    
    key_map = {
        'home': 3,
        'back': 4,
        'enter': 66,
        'menu': 82,
        'app_switch': 187,
        'volume_up': 24,
        'volume_down': 25,
    }
    
    keycode = key_map.get(key.lower())
    if keycode is None:
        try:
            keycode = int(key)
        except:
            return jsonify({'error': f'Unknown key: {key}'}), 400
    
    try:
        success = adb.press_key(keycode)
        return jsonify({'success': success, 'key': key})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/input', methods=['POST'])
def input_text():
    """Input text."""
    if not adb:
        return jsonify({'error': 'Not initialized'}), 500
    
    data = request.json
    text = data.get('text', '')
    
    try:
        success = adb.input_text(text)
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scroll', methods=['POST'])
def scroll():
    """Scroll up or down."""
    if not adb:
        return jsonify({'error': 'Not initialized'}), 500
    
    data = request.json
    direction = data.get('direction', 'down')
    amount = data.get('amount', 500)
    
    try:
        width, height = adb.get_screen_size()
        center_x = width // 2
        center_y = height // 2
        
        if direction == 'down':
            success = adb.swipe(center_x, center_y, center_x, center_y - amount, 300)
        else:
            success = adb.swipe(center_x, center_y, center_x, center_y + amount, 300)
        
        return jsonify({'success': success, 'direction': direction})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scrcpy/start', methods=['POST'])
def start_scrcpy():
    """Start scrcpy."""
    if not scrcpy:
        return jsonify({'error': 'Not initialized'}), 500
    
    try:
        config = ScrcpyPresets.right_panel(1920)
        success = scrcpy.start(config)
        return jsonify({'success': success, 'pid': scrcpy.get_pid()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/scrcpy/stop', methods=['POST'])
def stop_scrcpy():
    """Stop scrcpy."""
    if not scrcpy:
        return jsonify({'error': 'Not initialized'}), 500
    
    try:
        success = scrcpy.stop()
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/info')
def get_screen_info():
    """Get current screen information (UI hierarchy)."""
    if not screen_reader:
        return jsonify({'error': 'Not initialized'}), 500
    
    try:
        summary = screen_reader.get_screen_summary()
        return jsonify(summary)
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/find', methods=['POST'])
def find_element():
    """Find element by text."""
    if not screen_reader:
        return jsonify({'error': 'Not initialized'}), 500
    
    data = request.json
    text = data.get('text', '')
    exact = data.get('exact', False)
    
    try:
        elements = screen_reader.find_by_text(text, exact=exact)
        results = []
        for e in elements:
            results.append({
                'text': e.text,
                'content_desc': e.content_desc,
                'resource_id': e.resource_id,
                'class': e.class_name,
                'bounds': e.bounds,
                'center': e.center,
                'clickable': e.clickable
            })
        return jsonify({'elements': results, 'count': len(results)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/tap_text', methods=['POST'])
def tap_text():
    """Find and tap element by text."""
    if not screen_reader:
        return jsonify({'error': 'Not initialized'}), 500
    
    data = request.json
    text = data.get('text', '')
    
    try:
        success = screen_reader.tap_text(text)
        return jsonify({'success': success, 'text': text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/text')
def get_all_text():
    """Get all text visible on screen."""
    if not screen_reader:
        return jsonify({'error': 'Not initialized'}), 500
    
    try:
        text = screen_reader.get_all_text()
        return jsonify({'text': text})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/screen/clickable')
def get_clickable():
    """Get all clickable elements."""
    if not screen_reader:
        return jsonify({'error': 'Not initialized'}), 500
    
    try:
        elements = screen_reader.find_clickable()
        results = []
        for e in elements:
            if e.display_text:  # Only include elements with visible text
                results.append({
                    'text': e.display_text,
                    'center': e.center,
                    'bounds': e.bounds
                })
        return jsonify({'elements': results, 'count': len(results)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================
# Card Checker API Endpoints
# ============================================

@app.route('/api/card/check', methods=['POST'])
def check_card():
    """Start card balance check."""
    global card_check_status
    
    if not card_checker:
        return jsonify({'error': 'Card checker not initialized'}), 500
    
    if card_checker.is_running:
        return jsonify({'error': 'Check already in progress'}), 400
    
    data = request.json
    card_number = data.get('card_number', '').replace(' ', '').replace('-', '')
    exp_month = data.get('exp_month', '')
    exp_year = data.get('exp_year', '')
    cvv = data.get('cvv', '')
    
    # Validation
    if not card_number or len(card_number) < 15:
        return jsonify({'error': 'Invalid card number'}), 400
    if not exp_month or not exp_year or not cvv:
        return jsonify({'error': 'Missing card information'}), 400
    
    # Create card info
    card = CardInfo(
        card_number=card_number,
        exp_month=exp_month.zfill(2),
        exp_year=exp_year[-2:] if len(exp_year) > 2 else exp_year.zfill(2),
        cvv=cvv
    )
    
    # Reset status
    card_check_status = {
        'status': 'starting',
        'progress': 0,
        'message': 'Starting card check...',
        'timestamp': datetime.now().isoformat()
    }
    
    # Start check in background
    def on_complete(result):
        global card_check_status
        card_check_status = {
            'status': 'completed' if result.success else 'failed',
            'progress': 100,
            'message': f"Balance: {result.balance}" if result.success else result.error,
            'result': {
                'success': result.success,
                'balance': result.balance,
                'error': result.error,
                'check_date': result.check_date,
                'screenshots': result.screenshots
            },
            'timestamp': datetime.now().isoformat()
        }
    
    card_checker.check_balance_async(card, callback=on_complete)
    
    return jsonify({
        'success': True,
        'message': f'Started checking card {card.masked()}',
        'card_masked': card.masked()
    })


@app.route('/api/card/status')
def get_card_status():
    """Get current card check status."""
    global card_check_status
    
    if card_checker:
        # Update from checker if running
        if card_checker.is_running:
            return jsonify({
                'status': card_checker.status.value,
                'progress': card_checker.progress,
                'message': card_check_status.get('message', ''),
                'is_running': True
            })
    
    return jsonify(card_check_status)


@app.route('/api/card/cancel', methods=['POST'])
def cancel_card_check():
    """Cancel ongoing card check."""
    global card_check_status
    
    if not card_checker:
        return jsonify({'error': 'Card checker not initialized'}), 500
    
    if not card_checker.is_running:
        return jsonify({'error': 'No check in progress'}), 400
    
    card_checker.cancel()
    card_check_status = {
        'status': 'cancelled',
        'progress': 0,
        'message': 'Check cancelled by user',
        'timestamp': datetime.now().isoformat()
    }
    
    return jsonify({'success': True, 'message': 'Check cancelled'})


@app.route('/api/card/result')
def get_card_result():
    """Get last card check result."""
    if not card_checker:
        return jsonify({'error': 'Card checker not initialized'}), 500
    
    result = card_checker.get_last_result()
    if result:
        return jsonify({
            'success': result.success,
            'balance': result.balance,
            'error': result.error,
            'message': result.message,
            'check_date': result.check_date,
            'screenshots': result.screenshots
        })
    
    return jsonify({'message': 'No result available'})


@app.route('/api/card/open_site', methods=['POST'])
def open_card_site():
    """Just open rcbalance.com without checking."""
    if not browser:
        return jsonify({'error': 'Browser not initialized'}), 500
    
    try:
        success = browser.open_url('https://rcbalance.com')
        return jsonify({'success': success, 'url': 'https://rcbalance.com'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def run_server(host='0.0.0.0', port=5001, debug=False):
    """Run the web server."""
    # Create required directories
    (Path(__file__).parent / 'templates').mkdir(exist_ok=True)
    (Path(__file__).parent / 'static').mkdir(exist_ok=True)
    (Path(__file__).parent / 'screenshots').mkdir(exist_ok=True)
    
    # Initialize phone
    init_phone()
    
    # Run Flask
    app.run(host=host, port=port, debug=debug, threaded=True)


if __name__ == '__main__':
    run_server(debug=True)
