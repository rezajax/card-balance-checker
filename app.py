#!/usr/bin/env python3
"""
Card Balance Checker Panel
Flask web application with modern UI and real-time logging
Integrated with Google Sheets
"""

import asyncio
import json
import queue
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify, Response
from card_checker import CardChecker, TailscaleManager, get_api_key_tracker
from sheets_manager import SheetsManager
import logging
import os

# Custom log handler to capture logs for streaming
class QueueHandler(logging.Handler):
    def __init__(self, log_queue):
        super().__init__()
        self.log_queue = log_queue
        
    def emit(self, record):
        try:
            msg = self.format(record)
            self.log_queue.put(msg)
        except Exception:
            self.handleError(record)

# Global log queue for streaming
log_queue = queue.Queue()

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Add queue handler for streaming logs
queue_handler = QueueHandler(log_queue)
queue_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
logging.getLogger().addHandler(queue_handler)

app = Flask(__name__)
app.secret_key = os.urandom(24)

# Store check history
check_history = []

# Google Sheets Manager (lazy initialization)
sheets_manager = None

def get_sheets_manager():
    """Get or create sheets manager"""
    global sheets_manager
    if sheets_manager is None:
        sheets_manager = SheetsManager(
            credentials_file='/home/rez/cursor/credentials.json'
        )
        sheets_manager.connect()
    return sheets_manager

# Store current status
current_status = {
    'running': False,
    'step': '',
    'progress': 0,
    'cancelled': False,
    'current_task': None  # Description of current task
}

# Global reference to current checker for force cancel
current_checker = None


def update_status(step: str, progress: int = 0):
    """Update current status and log it"""
    global current_status
    current_status['step'] = step
    current_status['progress'] = progress
    logger.info(f"[STEP] {step}")


@app.route('/')
def index():
    """Main panel page"""
    return render_template('index.html', history=check_history[-10:])


@app.route('/check_balance', methods=['POST'])
def check_balance():
    """
    API to check card balance
    """
    global current_status
    
    try:
        data = request.get_json()
        
        # Validate data
        card_number = data.get('card_number', '').replace('-', '').replace(' ', '')
        exp_month = data.get('exp_month', '')
        exp_year = data.get('exp_year', '')
        cvv = data.get('cvv', '')
        
        # Validate fields
        if len(card_number) != 16:
            return jsonify({
                'success': False,
                'error': 'Card number must be 16 digits'
            }), 400
            
        if not (1 <= int(exp_month) <= 12):
            return jsonify({
                'success': False,
                'error': 'Invalid expiration month'
            }), 400
            
        if len(cvv) != 3:
            return jsonify({
                'success': False,
                'error': 'CVV must be 3 digits'
            }), 400
        
        current_status['running'] = True
        current_status['cancelled'] = False
        current_status['current_task'] = f"Checking card ****{card_number[-4:]}"
        update_status(f"Starting balance check for card: ****{card_number[-4:]}", 10)
        
        # Get options from request
        headless = data.get('headless', False)  # Default: show browser
        max_retries = data.get('max_retries', 5)  # Default: 5 exit node retries
        
        update_status(f"Max exit node retries: {max_retries}", 12)
        
        # Cancel check callback
        def check_cancelled():
            return current_status.get('cancelled', False)
        
        # Get captcha mode from settings or request
        captcha_mode = data.get('captcha_mode', app_settings.get('captcha_mode', 'auto'))
        
        # Get exit node settings
        always_use_exit_node = data.get('always_use_exit_node', app_settings.get('always_use_exit_node', False))
        disconnect_after_task = data.get('disconnect_after_task', app_settings.get('disconnect_after_task', False))
        
        # Connect to exit node before checking if enabled
        if always_use_exit_node:
            current_node = TailscaleManager.get_current_exit_node()
            if not current_node:
                exit_nodes = TailscaleManager.get_available_exit_nodes()
                available_nodes = [n for n in exit_nodes if not n.get('active')]
                if available_nodes:
                    import random
                    selected_node = random.choice(available_nodes)
                    update_status(f"Connecting to exit node: {selected_node['hostname']}...", 8)
                    if TailscaleManager.switch_exit_node(selected_node['hostname']):
                        update_status(f"Connected to {selected_node['hostname']}", 9)
                        import time
                        time.sleep(2)
                    else:
                        update_status(f"Failed to connect to exit node, continuing anyway...", 9)
                else:
                    update_status("No exit nodes available, continuing without...", 9)
            else:
                update_status(f"Already connected to exit node: {current_node}", 9)
        
        # Prepare Gemini settings if in gemini mode
        # Get the correct prompt based on preset (supports custom_0, custom_1, etc.)
        prompt_preset = app_settings.get('gemini_prompt_preset', 'detailed')
        gemini_prompt = get_prompt_by_preset(prompt_preset, app_settings)
        
        gemini_settings = {
            'gemini_api_keys': app_settings.get('gemini_api_keys', []),
            'gemini_current_key_index': app_settings.get('gemini_current_key_index', 0),
            'gemini_model': app_settings.get('gemini_model', 'gemini-2.0-flash'),
            'gemini_prompt': gemini_prompt,
            'gemini_prompt_preset': prompt_preset,  # Track which preset is being used
            'gemini_dynamic_recheck': app_settings.get('gemini_dynamic_recheck', True),
            'gemini_debug_save': app_settings.get('gemini_debug_save', False)
        }
        
        # Run automation - headless=False means you can SEE the browser
        global current_checker
        checker = CardChecker(headless=headless, status_callback=update_status, max_retries=max_retries, cancel_check=check_cancelled, captcha_mode=captcha_mode, gemini_settings=gemini_settings)
        current_checker = checker  # Store for force cancel
        result = asyncio.run(checker.check_balance(
            card_number=card_number,
            exp_month=exp_month,
            exp_year=exp_year,
            cvv=cvv
        ))
        current_checker = None  # Clear reference
        
        current_status['running'] = False
        current_status['current_task'] = None
        
        # Disconnect from exit node after task if enabled
        if disconnect_after_task:
            update_status("Disconnecting from exit node...", 99)
            TailscaleManager.disable_exit_node()
            update_status("Exit node disconnected", 99)
        
        # Check if cancelled
        if result.get('cancelled'):
            update_status("Task cancelled", 0)
            return jsonify(result)
        
        update_status("Completed", 100)
        
        # Save to history
        history_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'card_last4': card_number[-4:],
            'success': result['success'],
            'balance': result.get('balance', 'N/A'),
            'message': result.get('message', '')
        }
        check_history.append(history_entry)
        
        return jsonify(result)
        
    except ValueError as e:
        current_status['running'] = False
        current_status['current_task'] = None
        logger.error(f"Validation error: {e}")
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400
        
    except Exception as e:
        current_status['running'] = False
        current_status['current_task'] = None
        logger.error(f"Error checking balance: {e}")
        return jsonify({
            'success': False,
            'error': f'System error: {str(e)}'
        }), 500


@app.route('/logs')
def stream_logs():
    """Server-Sent Events endpoint for real-time logs"""
    def generate():
        while True:
            try:
                # Wait for log message with timeout
                msg = log_queue.get(timeout=1)
                yield f"data: {json.dumps({'log': msg})}\n\n"
            except queue.Empty:
                # Send heartbeat to keep connection alive
                yield f"data: {json.dumps({'heartbeat': True})}\n\n"
                
    return Response(generate(), mimetype='text/event-stream')


@app.route('/status')
def get_status():
    """Get current automation status"""
    return jsonify(current_status)


@app.route('/cancel', methods=['POST'])
def cancel_task():
    """Force cancel the current running task - kills browser and disconnects exit node"""
    global current_status, current_checker
    import subprocess
    
    logger.info("=" * 50)
    logger.info("FORCE CANCEL REQUESTED!")
    logger.info("=" * 50)
    
    # Set cancelled flag first
    current_status['cancelled'] = True
    
    # Force cancel checker if exists
    if current_checker:
        try:
            current_checker.force_cancel()
            logger.info("Checker force_cancel called")
        except Exception as e:
            logger.warning(f"Error calling force_cancel: {e}")
    
    # Kill all chromium processes - most reliable way
    try:
        logger.info("Killing chromium processes...")
        result = subprocess.run(['pkill', '-9', '-f', 'chromium'], capture_output=True)
        logger.info(f"pkill chromium result: {result.returncode}")
    except Exception as e:
        logger.warning(f"Error killing chromium: {e}")
    
    # Also try to kill playwright
    try:
        subprocess.run(['pkill', '-9', '-f', 'playwright'], capture_output=True)
    except:
        pass
    
    # Disconnect exit node
    try:
        logger.info("Disconnecting exit node...")
        TailscaleManager.disable_exit_node()
        logger.info("Exit node disconnected")
    except Exception as e:
        logger.warning(f"Error disconnecting exit node: {e}")
    
    # Reset status
    current_status['running'] = False
    current_status['step'] = 'Force Cancelled'
    current_status['progress'] = 0
    current_status['current_task'] = None
    
    logger.info("=" * 50)
    logger.info("FORCE CANCEL COMPLETE!")
    logger.info("=" * 50)
    
    return jsonify({
        'success': True,
        'message': 'Task force cancelled! Browser killed, exit node disconnected.'
    })


@app.route('/history')
def get_history():
    """Return check history"""
    return jsonify(check_history[-20:])


@app.route('/clear_history', methods=['POST'])
def clear_history():
    """Clear history"""
    global check_history
    check_history = []
    return jsonify({'success': True, 'message': 'History cleared'})


@app.route('/clear_logs', methods=['POST'])
def clear_logs():
    """Clear log queue"""
    while not log_queue.empty():
        try:
            log_queue.get_nowait()
        except queue.Empty:
            break
    return jsonify({'success': True, 'message': 'Logs cleared'})


# ============================================
# Google Sheets Routes
# ============================================

@app.route('/sheets/cards')
def get_sheet_cards():
    """Get all cards from Google Sheet"""
    try:
        manager = get_sheets_manager()
        cards = manager.get_all_cards()
        
        # Hide sensitive data for display
        safe_cards = []
        for card in cards:
            # A card is "checked" ONLY if it has BOTH initial_balance AND current_balance
            # (and they are actual values, not empty)
            init_bal = card['initial_balance'].strip() if card['initial_balance'] else ''
            curr_bal = card['current_balance'].strip() if card['current_balance'] else ''
            is_checked = bool(init_bal) and bool(curr_bal)
            
            # Check if it's a duplicate (has DUPLICATE in balance fields)
            is_duplicate = init_bal.upper() == 'DUPLICATE' or curr_bal.upper() == 'DUPLICATE'
            
            # Get last check date from result_json if exists
            last_check_date = None
            if card['result_json']:
                try:
                    result_data = json.loads(card['result_json'])
                    last_check_date = result_data.get('check_date', None)
                except:
                    pass
            
            safe_cards.append({
                'row_index': card['row_index'],
                'id': card['id'],
                'card_last4': card['card_number'][-4:] if card['card_number'] else '',
                'exp': f"{card['exp_month']}/{card['exp_year']}",
                'initial_balance': card['initial_balance'],
                'current_balance': card['current_balance'],
                'is_checked': is_checked,
                'is_duplicate': is_duplicate,
                'last_check_date': last_check_date
            })
        
        return jsonify({
            'success': True,
            'total': len(cards),
            'cards': safe_cards
        })
    except Exception as e:
        logger.error(f"Failed to get sheet cards: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sheets/unchecked')
def get_unchecked_cards():
    """Get cards without balance check"""
    try:
        manager = get_sheets_manager()
        cards = manager.get_unchecked_cards()
        
        safe_cards = []
        for card in cards:
            safe_cards.append({
                'row_index': card['row_index'],
                'id': card['id'],
                'card_last4': card['card_number'][-4:] if card['card_number'] else '',
                'exp': f"{card['exp_month']}/{card['exp_year']}"
            })
        
        return jsonify({
            'success': True,
            'total': len(cards),
            'cards': safe_cards
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sheets/check/<int:row_index>', methods=['POST'])
def check_card_from_sheet(row_index):
    """Check balance for a card from the sheet"""
    global current_status
    
    try:
        data = request.get_json() or {}
        headless = data.get('headless', False)
        max_retries = data.get('max_retries', 5)
        skip_duplicates = data.get('skip_duplicates', True)
        notes = data.get('notes', '')
        
        manager = get_sheets_manager()
        card = manager.get_card_by_row(row_index)
        
        if not card:
            return jsonify({'success': False, 'error': 'Card not found'}), 404
        
        # Check for duplicates and find if any has balance
        is_duplicate, all_matching_rows, card_with_balance = manager.get_duplicate_with_balance(
            card['card_number'], row_index
        )
        duplicate_rows = [r for r in all_matching_rows if r != row_index]
        
        # NEW LOGIC: If duplicate and one already has balance, just copy it
        if is_duplicate and card_with_balance:
            update_status(f"Card ****{card['card_number'][-4:]} is DUPLICATE! Row {card_with_balance['row_index']} already has balance: {card_with_balance['current_balance']}", 50)
            
            # Copy balance from existing duplicate and mark as DUPLICATE
            manager.copy_balance_from_duplicate(row_index, card_with_balance, all_matching_rows)
            update_status(f"Marked row {row_index} as DUPLICATE, balance from row {card_with_balance['row_index']}", 100)
            
            return jsonify({
                'success': True,
                'is_duplicate': True,
                'balance': card_with_balance['current_balance'],
                'source_row': card_with_balance['row_index'],
                'duplicate_rows': duplicate_rows,
                'message': f'Balance copied from row {card_with_balance["row_index"]}: {card_with_balance["current_balance"]}'
            })
        
        # If duplicate but NO ONE has balance, we need to check this card
        # After checking, we'll mark all others as DUPLICATE
        
        current_status['running'] = True
        current_status['cancelled'] = False
        current_status['current_task'] = f"Checking row {row_index}: ****{card['card_number'][-4:]}"
        update_status(f"Checking card from row {row_index}: ****{card['card_number'][-4:]}", 10)
        
        if is_duplicate:
            update_status(f"Card is duplicate (rows: {all_matching_rows}), but no balance found. Checking now...", 12)
        
        # Cancel check callback
        def check_cancelled():
            return current_status.get('cancelled', False)
        
        # Get captcha mode from settings or request
        captcha_mode = data.get('captcha_mode', app_settings.get('captcha_mode', 'auto'))
        
        # Get exit node settings
        always_use_exit_node = data.get('always_use_exit_node', app_settings.get('always_use_exit_node', False))
        disconnect_after_task = data.get('disconnect_after_task', app_settings.get('disconnect_after_task', False))
        
        # Connect to exit node before checking if enabled
        if always_use_exit_node:
            current_node = TailscaleManager.get_current_exit_node()
            if not current_node:
                # Not connected to any exit node, pick one
                exit_nodes = TailscaleManager.get_available_exit_nodes()
                available_nodes = [n for n in exit_nodes if not n.get('active')]
                if available_nodes:
                    import random
                    selected_node = random.choice(available_nodes)
                    update_status(f"Connecting to exit node: {selected_node['hostname']}...", 8)
                    if TailscaleManager.switch_exit_node(selected_node['hostname']):
                        update_status(f"Connected to {selected_node['hostname']}", 9)
                        import time
                        time.sleep(2)  # Wait for connection to stabilize
                    else:
                        update_status(f"Failed to connect to exit node, continuing anyway...", 9)
                else:
                    update_status("No exit nodes available, continuing without...", 9)
            else:
                update_status(f"Already connected to exit node: {current_node}", 9)
        
        # Prepare Gemini settings if in gemini mode
        # Get the correct prompt based on preset (supports custom_0, custom_1, etc.)
        prompt_preset = app_settings.get('gemini_prompt_preset', 'detailed')
        gemini_prompt = get_prompt_by_preset(prompt_preset, app_settings)
        
        gemini_settings = {
            'gemini_api_keys': app_settings.get('gemini_api_keys', []),
            'gemini_current_key_index': app_settings.get('gemini_current_key_index', 0),
            'gemini_model': app_settings.get('gemini_model', 'gemini-2.0-flash'),
            'gemini_prompt': gemini_prompt,
            'gemini_prompt_preset': prompt_preset,  # Track which preset is being used
            'gemini_dynamic_recheck': app_settings.get('gemini_dynamic_recheck', True),
            'gemini_debug_save': app_settings.get('gemini_debug_save', False)
        }
        
        # Run automation
        global current_checker
        checker = CardChecker(headless=headless, status_callback=update_status, max_retries=max_retries, cancel_check=check_cancelled, captcha_mode=captcha_mode, gemini_settings=gemini_settings)
        current_checker = checker  # Store for force cancel
        result = asyncio.run(checker.check_balance(
            card_number=card['card_number'],
            exp_month=card['exp_month'],
            exp_year=card['exp_year'],
            cvv=card['cvv']
        ))
        current_checker = None  # Clear reference
        
        current_status['running'] = False
        current_status['current_task'] = None
        
        # Disconnect from exit node after task if enabled
        if disconnect_after_task:
            update_status("Disconnecting from exit node...", 99)
            TailscaleManager.disable_exit_node()
            update_status("Exit node disconnected", 99)
        
        # Check if cancelled
        if result.get('cancelled'):
            update_status("Task cancelled", 0)
            return jsonify(result)
        
        # Update sheet with result (including duplicate info and notes)
        manager.update_card_result(row_index, result, notes=notes, is_duplicate=is_duplicate, duplicate_rows=duplicate_rows)
        update_status(f"Updated row {row_index} in sheet", 95)
        
        # NEW: If this was a duplicate and we got balance, mark all other duplicates
        if is_duplicate and result.get('success') and result.get('balance'):
            balance = result.get('balance', '').replace('$', '').replace(',', '').strip()
            update_status(f"Marking {len(duplicate_rows)} duplicate rows as DUPLICATE...", 97)
            manager.mark_duplicates_after_check(all_matching_rows, row_index, balance, result)
            update_status(f"Marked all duplicates. Original balance in row {row_index}", 100)
        
        # Add to history
        history_entry = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'card_last4': card['card_number'][-4:],
            'row_index': row_index,
            'success': result['success'],
            'balance': result.get('balance', 'N/A'),
            'is_duplicate': is_duplicate,
            'duplicates_marked': len(duplicate_rows) if is_duplicate else 0,
            'source': 'sheet'
        }
        check_history.append(history_entry)
        
        result['is_duplicate'] = is_duplicate
        result['duplicate_rows'] = duplicate_rows
        result['duplicates_marked'] = len(duplicate_rows) if is_duplicate and result.get('success') else 0
        return jsonify(result)
        
    except Exception as e:
        current_status['running'] = False
        current_status['current_task'] = None
        logger.error(f"Error checking card from sheet: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sheets/check_all', methods=['POST'])
def check_all_unchecked():
    """Start checking all unchecked cards (returns immediately, runs in background)"""
    # This would be better with a task queue like Celery
    # For now, just return info about unchecked cards
    try:
        manager = get_sheets_manager()
        unchecked = manager.get_unchecked_cards()
        
        return jsonify({
            'success': True,
            'message': f'Found {len(unchecked)} unchecked cards',
            'total_unchecked': len(unchecked),
            'note': 'Use /sheets/check/<row_index> to check individual cards'
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sheets/update/<int:row_index>', methods=['POST'])
def update_sheet_row(row_index):
    """Manually update a row in the sheet"""
    try:
        data = request.get_json()
        initial_balance = data.get('initial_balance')
        current_balance = data.get('current_balance')
        
        manager = get_sheets_manager()
        success = manager.update_balance(row_index, initial_balance, current_balance)
        
        return jsonify({'success': success})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sheets/stats')
def get_sheet_stats():
    """Get sheet statistics"""
    try:
        manager = get_sheets_manager()
        stats = manager.get_sheet_stats()
        return jsonify({'success': True, **stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sheets/check_range', methods=['POST'])
def check_cards_in_range():
    """Check cards in a specific row range"""
    global current_status
    
    try:
        data = request.get_json()
        start_row = data.get('start_row', 1)
        end_row = data.get('end_row', 100)
        headless = data.get('headless', False)
        max_retries = data.get('max_retries', 5)
        skip_duplicates = data.get('skip_duplicates', True)
        skip_checked = data.get('skip_checked', True)
        
        manager = get_sheets_manager()
        cards = manager.get_cards_in_range(start_row, end_row)
        
        if skip_checked:
            cards = [c for c in cards if not c['current_balance']]
        
        return jsonify({
            'success': True,
            'total_in_range': len(cards),
            'cards': [
                {
                    'row_index': c['row_index'],
                    'card_last4': c['card_number'][-4:] if c['card_number'] else '',
                    'exp': f"{c['exp_month']}/{c['exp_year']}",
                    'has_balance': bool(c['current_balance'])
                }
                for c in cards
            ],
            'message': f'Found {len(cards)} cards to check in rows {start_row}-{end_row}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/sheets/check_duplicate/<int:row_index>')
def check_card_duplicate(row_index):
    """Check if a card is duplicate"""
    try:
        manager = get_sheets_manager()
        card = manager.get_card_by_row(row_index)
        
        if not card:
            return jsonify({'success': False, 'error': 'Card not found'}), 404
        
        is_duplicate, duplicate_rows = manager.check_duplicate(card['card_number'], row_index)
        
        return jsonify({
            'success': True,
            'is_duplicate': is_duplicate,
            'duplicate_rows': duplicate_rows,
            'card_last4': card['card_number'][-4:]
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Tailscale / Exit Node Routes
# ============================================

@app.route('/exit_nodes')
def get_exit_nodes():
    """Get list of available Tailscale exit nodes"""
    try:
        nodes = TailscaleManager.get_available_exit_nodes()
        current = TailscaleManager.get_current_exit_node()
        
        return jsonify({
            'success': True,
            'current_node': current,
            'total': len(nodes),
            'nodes': nodes
        })
    except Exception as e:
        logger.error(f"Failed to get exit nodes: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/exit_nodes/switch', methods=['POST'])
def switch_exit_node():
    """Switch to a different exit node"""
    try:
        data = request.get_json()
        hostname = data.get('hostname')
        
        if not hostname:
            return jsonify({'success': False, 'error': 'hostname is required'}), 400
        
        success = TailscaleManager.switch_exit_node(hostname)
        
        if success:
            logger.info(f"Switched to exit node: {hostname}")
            return jsonify({
                'success': True,
                'message': f'Switched to {hostname}',
                'current_node': hostname
            })
        else:
            return jsonify({
                'success': False,
                'error': f'Failed to switch to {hostname}'
            }), 500
            
    except Exception as e:
        logger.error(f"Failed to switch exit node: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/exit_nodes/disable', methods=['POST'])
def disable_exit_node():
    """Disable exit node (direct connection)"""
    try:
        success = TailscaleManager.disable_exit_node()
        
        if success:
            return jsonify({
                'success': True,
                'message': 'Exit node disabled - using direct connection'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Failed to disable exit node'
            }), 500
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================
# Settings Routes
# ============================================

# Default settings
# Settings file path
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), 'settings.json')

# Default settings
DEFAULT_SETTINGS = {
    'headless': False,
    'max_retries': 5,
    'skip_duplicates': True,
    'skip_checked': True,
    'timeout': 60000,
    'auto_check_interval': 0,  # 0 means disabled
    'captcha_mode': 'auto',  # 'auto' = try exit nodes, 'ai' = YOLO model, 'gemini' = Gemini AI, 'manual' = wait for manual solve
    'always_use_exit_node': False,  # Connect to exit node before each check
    'disconnect_after_task': False,  # Disconnect from exit node after task completes
    'debug_logging': False,  # Enable verbose debug logging
    # Gemini AI CAPTCHA Solver settings
    'gemini_api_keys': [],  # List of API keys for rotation
    'gemini_current_key_index': 0,  # Current key being used
    'gemini_model': 'gemini-2.5-flash',  # Model to use (2.5-flash works with free tier)
    'gemini_dynamic_recheck': True,  # Re-analyze after each click in dynamic mode (recommended)
    'gemini_debug_save': False,  # Save CAPTCHA images and Gemini responses to debug folder
    'gemini_prompt_preset': 'detailed',  # Which preset prompt to use: 'detailed', 'simple', 'visual', 'expert', 'custom'
    'gemini_prompt': '',  # Custom prompt (only used when preset is 'custom')
    'custom_prompts': []  # List of user-defined custom prompts: [{'name': 'my_prompt', 'prompt': '...'}]
}

# ====== PROMPTS MANAGEMENT ======
PROMPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'prompts')

def load_prompt_from_file(filename: str) -> str:
    """Load a prompt from a markdown file in the prompts directory"""
    filepath = os.path.join(PROMPTS_DIR, filename)
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                # Extract prompt text (everything after the --- separator)
                if '---' in content:
                    parts = content.split('---', 2)
                    if len(parts) >= 2:
                        return parts[-1].strip()
                return content.strip()
    except Exception as e:
        logger.warning(f"Could not load prompt from {filename}: {e}")
    return None

def get_prompt_metadata(filename: str) -> dict:
    """Extract metadata (title, description) from a prompt file"""
    filepath = os.path.join(PROMPTS_DIR, filename)
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                metadata = {'name': filename.replace('.md', ''), 'description': ''}
                
                # Extract title from first # line
                for line in content.split('\n'):
                    if line.startswith('# '):
                        metadata['name'] = line[2:].strip()
                        break
                
                # Extract description from **Description:** line
                for line in content.split('\n'):
                    if '**Description:**' in line:
                        metadata['description'] = line.split('**Description:**')[1].strip()
                        break
                
                return metadata
    except Exception as e:
        logger.warning(f"Could not get metadata from {filename}: {e}")
    return {'name': filename, 'description': ''}

def list_available_prompts() -> list:
    """List all available prompt files"""
    prompts = []
    if os.path.exists(PROMPTS_DIR):
        for filename in os.listdir(PROMPTS_DIR):
            if filename.endswith('.md'):
                key = filename.replace('.md', '')
                metadata = get_prompt_metadata(filename)
                prompts.append({
                    'key': key,
                    'filename': filename,
                    'name': metadata['name'],
                    'description': metadata['description']
                })
    return sorted(prompts, key=lambda x: x['key'])

def save_prompt_to_file(key: str, name: str, description: str, prompt_text: str) -> bool:
    """Save a prompt to a markdown file"""
    try:
        os.makedirs(PROMPTS_DIR, exist_ok=True)
        filename = f"{key}.md"
        filepath = os.path.join(PROMPTS_DIR, filename)
        
        content = f"""# {name}

**Description:** {description}

---

{prompt_text}
"""
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        logger.info(f"Saved prompt to {filepath}")
        return True
    except Exception as e:
        logger.error(f"Could not save prompt: {e}")
        return False

def delete_prompt_file(key: str) -> bool:
    """Delete a prompt file"""
    try:
        filepath = os.path.join(PROMPTS_DIR, f"{key}.md")
        if os.path.exists(filepath):
            os.remove(filepath)
            logger.info(f"Deleted prompt file: {filepath}")
            return True
    except Exception as e:
        logger.error(f"Could not delete prompt: {e}")
    return False

# Cache for loaded prompts (to avoid reading files repeatedly)
_prompt_cache = {}

def get_prompt(key: str) -> str:
    """Get a prompt by its key (cached)"""
    if key not in _prompt_cache:
        prompt = load_prompt_from_file(f"{key}.md")
        if prompt:
            _prompt_cache[key] = prompt
    return _prompt_cache.get(key)

def clear_prompt_cache():
    """Clear the prompt cache (call after editing prompts)"""
    global _prompt_cache
    _prompt_cache = {}

# For backwards compatibility - load prompts on startup
def _load_all_prompts():
    """Load all prompts into a dict for backwards compatibility"""
    prompts = {}
    for p in list_available_prompts():
        prompt_text = load_prompt_from_file(p['filename'])
        if prompt_text:
            prompts[p['key']] = prompt_text
    return prompts

GEMINI_PROMPT_PRESETS = _load_all_prompts()

# ====== PROMPT STATISTICS TRACKING ======
PROMPT_STATS_FILE = 'prompt_stats.json'

def load_prompt_stats():
    """Load prompt statistics from file"""
    try:
        if os.path.exists(PROMPT_STATS_FILE):
            with open(PROMPT_STATS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Could not load prompt stats: {e}")
    return {
        'prompts': {},
        'total_attempts': 0,
        'total_successes': 0
    }

def save_prompt_stats(stats):
    """Save prompt statistics to file"""
    try:
        with open(PROMPT_STATS_FILE, 'w') as f:
            json.dump(stats, f, indent=2)
        return True
    except Exception as e:
        logger.error(f"Could not save prompt stats: {e}")
        return False

def record_prompt_result(prompt_name: str, success: bool, challenge_type: str = None, tiles_selected: int = 0):
    """Record the result of a prompt attempt"""
    stats = load_prompt_stats()
    
    if prompt_name not in stats['prompts']:
        stats['prompts'][prompt_name] = {
            'attempts': 0,
            'successes': 0,
            'failures': 0,
            'success_rate': 0.0,
            'by_challenge': {},
            'avg_tiles_selected': 0,
            'total_tiles': 0,
            'last_used': None
        }
    
    prompt_stats = stats['prompts'][prompt_name]
    prompt_stats['attempts'] += 1
    prompt_stats['total_tiles'] += tiles_selected
    prompt_stats['avg_tiles_selected'] = prompt_stats['total_tiles'] / prompt_stats['attempts']
    prompt_stats['last_used'] = datetime.now().isoformat()
    
    if success:
        prompt_stats['successes'] += 1
        stats['total_successes'] += 1
    else:
        prompt_stats['failures'] += 1
    
    stats['total_attempts'] += 1
    prompt_stats['success_rate'] = round(prompt_stats['successes'] / prompt_stats['attempts'] * 100, 1)
    
    # Track by challenge type
    if challenge_type:
        if challenge_type not in prompt_stats['by_challenge']:
            prompt_stats['by_challenge'][challenge_type] = {'attempts': 0, 'successes': 0}
        prompt_stats['by_challenge'][challenge_type]['attempts'] += 1
        if success:
            prompt_stats['by_challenge'][challenge_type]['successes'] += 1
    
    save_prompt_stats(stats)
    return stats

# Initialize prompt stats
prompt_stats = load_prompt_stats()

def get_prompt_by_preset(preset_name: str, settings: dict) -> str:
    """
    Get the prompt text based on preset name.
    Supports file-based prompts (detailed, simple, visual, expert, user-created)
    and inline 'custom' preset.
    """
    # Try from cache/loaded presets first
    if preset_name in GEMINI_PROMPT_PRESETS:
        return GEMINI_PROMPT_PRESETS[preset_name]
    
    # Inline 'custom' preset (uses gemini_prompt field)
    if preset_name == 'custom':
        return settings.get('gemini_prompt', GEMINI_PROMPT_PRESETS.get('detailed', ''))
    
    # Try loading from file directly (for new prompts not yet in cache)
    prompt_text = load_prompt_from_file(f"{preset_name}.md")
    if prompt_text:
        return prompt_text
    
    # Fallback to detailed
    return GEMINI_PROMPT_PRESETS.get('detailed', 'Identify tiles containing the target object. Respond with tile numbers only.')

def load_settings():
    """Load settings from file or return defaults"""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                # Merge with defaults (in case new settings were added)
                settings = DEFAULT_SETTINGS.copy()
                settings.update(saved)
                logger.info(f"Settings loaded from {SETTINGS_FILE}")
                return settings
    except Exception as e:
        logger.warning(f"Could not load settings: {e}")
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    """Save settings to file"""
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
        logger.info(f"Settings saved to {SETTINGS_FILE}")
        return True
    except Exception as e:
        logger.error(f"Could not save settings: {e}")
        return False

# Load settings on startup
app_settings = load_settings()

@app.route('/settings')
def get_settings():
    """Get current settings"""
    return jsonify({'success': True, 'settings': app_settings})


@app.route('/settings', methods=['POST'])
def update_settings():
    """Update settings and save to file"""
    global app_settings
    
    try:
        data = request.get_json()
        
        # Update only provided settings
        for key in ['headless', 'max_retries', 'skip_duplicates', 'skip_checked', 'timeout', 'auto_check_interval', 'captcha_mode', 'always_use_exit_node', 'disconnect_after_task', 'debug_logging', 'gemini_api_keys', 'gemini_current_key_index', 'gemini_model', 'gemini_prompt', 'gemini_prompt_preset', 'gemini_dynamic_recheck', 'gemini_debug_save', 'custom_prompts']:
            if key in data:
                app_settings[key] = data[key]
        
        # Update logging level based on debug setting
        if app_settings.get('debug_logging'):
            logging.getLogger().setLevel(logging.DEBUG)
            logger.info("Debug logging ENABLED - showing verbose logs")
        else:
            logging.getLogger().setLevel(logging.INFO)
            logger.info("Debug logging DISABLED - showing normal logs")
        
        # Save settings to file
        save_settings(app_settings)
        
        # Log settings without exposing API keys
        safe_settings = {k: v for k, v in app_settings.items() if k != 'gemini_api_keys'}
        safe_settings['gemini_api_keys_count'] = len(app_settings.get('gemini_api_keys', []))
        logger.info(f"Settings updated: {safe_settings}")
        return jsonify({'success': True, 'settings': app_settings})
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/rotate_key', methods=['POST'])
def rotate_gemini_key():
    """Rotate to the next Gemini API key"""
    global app_settings
    
    try:
        keys = app_settings.get('gemini_api_keys', [])
        if not keys:
            return jsonify({'success': False, 'error': 'No Gemini API keys configured'}), 400
        
        current_index = app_settings.get('gemini_current_key_index', 0)
        new_index = (current_index + 1) % len(keys)
        app_settings['gemini_current_key_index'] = new_index
        
        save_settings(app_settings)
        
        logger.info(f"Rotated to Gemini API key {new_index + 1}/{len(keys)}")
        return jsonify({
            'success': True,
            'current_key_index': new_index,
            'total_keys': len(keys),
            'message': f'Switched to key {new_index + 1} of {len(keys)}'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/test', methods=['POST'])
def test_gemini_key():
    """Test if current Gemini API key is working"""
    import requests
    
    try:
        keys = app_settings.get('gemini_api_keys', [])
        if not keys:
            return jsonify({'success': False, 'error': 'No Gemini API keys configured'}), 400
        
        current_index = app_settings.get('gemini_current_key_index', 0)
        current_key = keys[current_index]
        model = app_settings.get('gemini_model', 'gemini-2.0-flash')
        
        # Test API call
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={current_key}"
        response = requests.post(url, json={
            'contents': [{'parts': [{'text': 'Hello, respond with just "OK"'}]}]
        }, timeout=10)
        
        if response.status_code == 200:
            return jsonify({
                'success': True,
                'message': f'API key {current_index + 1} is working!',
                'model': model
            })
        elif response.status_code == 429:
            return jsonify({
                'success': False,
                'error': 'Rate limited - this key has exceeded its quota',
                'should_rotate': True
            })
        else:
            return jsonify({
                'success': False,
                'error': f'API error: {response.status_code} - {response.text[:200]}'
            })
            
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/prompt_presets')
def get_gemini_prompt_presets():
    """Get available Gemini prompt presets with FULL prompt text (from files)"""
    presets_info = {}
    
    # Load all prompts from files
    available = list_available_prompts()
    for p in available:
        prompt_text = load_prompt_from_file(p['filename'])
        presets_info[p['key']] = {
            'name': p['name'],
            'description': p['description'],
            'full_prompt': prompt_text or '',
            'is_builtin': p['key'] in ['detailed', 'simple', 'visual', 'expert']
        }
    
    # Add 'custom' option for inline custom prompt
    presets_info['custom'] = {
        'name': 'Custom (Inline)',
        'description': 'Use the custom prompt text field below',
        'full_prompt': app_settings.get('gemini_prompt', ''),
        'is_builtin': False
    }
    
    return jsonify({'success': True, 'presets': presets_info})


# ====== PROMPT STATISTICS ROUTES ======

@app.route('/gemini/prompt_stats')
def get_prompt_stats():
    """Get statistics for all prompts"""
    stats = load_prompt_stats()
    
    # Add current preset info
    current_preset = app_settings.get('gemini_prompt_preset', 'detailed')
    stats['current_preset'] = current_preset
    
    # Calculate overall stats
    if stats['total_attempts'] > 0:
        stats['overall_success_rate'] = round(stats['total_successes'] / stats['total_attempts'] * 100, 1)
    else:
        stats['overall_success_rate'] = 0.0
    
    # Sort prompts by success rate
    sorted_prompts = sorted(
        stats['prompts'].items(), 
        key=lambda x: (x[1]['success_rate'], x[1]['attempts']), 
        reverse=True
    )
    stats['ranking'] = [
        {'name': name, **data} 
        for name, data in sorted_prompts
    ]
    
    return jsonify({'success': True, 'stats': stats})


@app.route('/gemini/prompt_stats/record', methods=['POST'])
def record_prompt_stat():
    """Record a prompt attempt result (called after CAPTCHA attempt)"""
    try:
        data = request.get_json()
        prompt_name = data.get('prompt_name', app_settings.get('gemini_prompt_preset', 'detailed'))
        success = data.get('success', False)
        challenge_type = data.get('challenge_type')
        tiles_selected = data.get('tiles_selected', 0)
        
        stats = record_prompt_result(prompt_name, success, challenge_type, tiles_selected)
        return jsonify({'success': True, 'stats': stats})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/prompt_stats/reset', methods=['POST'])
def reset_prompt_stats():
    """Reset all prompt statistics"""
    try:
        empty_stats = {
            'prompts': {},
            'total_attempts': 0,
            'total_successes': 0
        }
        save_prompt_stats(empty_stats)
        return jsonify({'success': True, 'message': 'Statistics reset successfully'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ====== CUSTOM PROMPTS ROUTES ======

@app.route('/gemini/custom_prompts', methods=['GET'])
def get_custom_prompts():
    """Get all user-defined custom prompts"""
    custom_prompts = app_settings.get('custom_prompts', [])
    return jsonify({'success': True, 'custom_prompts': custom_prompts})


@app.route('/gemini/custom_prompts', methods=['POST'])
def add_custom_prompt():
    """Add a new custom prompt"""
    global app_settings
    
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        prompt = data.get('prompt', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'success': False, 'error': 'Prompt name is required'}), 400
        if not prompt:
            return jsonify({'success': False, 'error': 'Prompt text is required'}), 400
        
        custom_prompts = app_settings.get('custom_prompts', [])
        
        # Check for duplicate names
        for cp in custom_prompts:
            if cp.get('name', '').lower() == name.lower():
                return jsonify({'success': False, 'error': f'A prompt with name "{name}" already exists'}), 400
        
        # Add new prompt
        new_prompt = {
            'name': name,
            'prompt': prompt,
            'description': description or f'Custom prompt: {name}',
            'created_at': datetime.now().isoformat()
        }
        custom_prompts.append(new_prompt)
        app_settings['custom_prompts'] = custom_prompts
        
        save_settings(app_settings)
        
        logger.info(f"Added custom prompt: {name}")
        return jsonify({
            'success': True, 
            'message': f'Custom prompt "{name}" added successfully',
            'custom_prompts': custom_prompts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/custom_prompts/<int:index>', methods=['PUT'])
def update_custom_prompt(index):
    """Update an existing custom prompt"""
    global app_settings
    
    try:
        data = request.get_json()
        custom_prompts = app_settings.get('custom_prompts', [])
        
        if index < 0 or index >= len(custom_prompts):
            return jsonify({'success': False, 'error': 'Invalid prompt index'}), 400
        
        # Update fields
        if 'name' in data:
            custom_prompts[index]['name'] = data['name'].strip()
        if 'prompt' in data:
            custom_prompts[index]['prompt'] = data['prompt'].strip()
        if 'description' in data:
            custom_prompts[index]['description'] = data['description'].strip()
        
        custom_prompts[index]['updated_at'] = datetime.now().isoformat()
        
        app_settings['custom_prompts'] = custom_prompts
        save_settings(app_settings)
        
        return jsonify({
            'success': True,
            'message': 'Custom prompt updated successfully',
            'custom_prompts': custom_prompts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/custom_prompts/<int:index>', methods=['DELETE'])
def delete_custom_prompt(index):
    """Delete a custom prompt"""
    global app_settings
    
    try:
        custom_prompts = app_settings.get('custom_prompts', [])
        
        if index < 0 or index >= len(custom_prompts):
            return jsonify({'success': False, 'error': 'Invalid prompt index'}), 400
        
        deleted_name = custom_prompts[index].get('name', f'Custom {index}')
        custom_prompts.pop(index)
        
        app_settings['custom_prompts'] = custom_prompts
        save_settings(app_settings)
        
        logger.info(f"Deleted custom prompt: {deleted_name}")
        return jsonify({
            'success': True,
            'message': f'Custom prompt "{deleted_name}" deleted successfully',
            'custom_prompts': custom_prompts
        })
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


# ====== FILE-BASED PROMPT MANAGEMENT ======

@app.route('/gemini/prompts')
def list_prompts():
    """List all available prompts (from files)"""
    prompts = list_available_prompts()
    return jsonify({'success': True, 'prompts': prompts})


@app.route('/gemini/prompts/<key>', methods=['GET'])
def get_prompt_detail(key):
    """Get a specific prompt by key"""
    prompt_text = load_prompt_from_file(f"{key}.md")
    if prompt_text:
        metadata = get_prompt_metadata(f"{key}.md")
        return jsonify({
            'success': True,
            'prompt': {
                'key': key,
                'name': metadata['name'],
                'description': metadata['description'],
                'text': prompt_text
            }
        })
    return jsonify({'success': False, 'error': 'Prompt not found'}), 404


@app.route('/gemini/prompts/<key>', methods=['POST', 'PUT'])
def save_prompt_route(key):
    """Create or update a prompt file"""
    try:
        data = request.get_json()
        name = data.get('name', key)
        description = data.get('description', '')
        prompt_text = data.get('prompt', '')
        
        if not prompt_text:
            return jsonify({'success': False, 'error': 'Prompt text is required'}), 400
        
        # Don't allow overwriting built-in prompts via POST (only PUT for existing)
        builtin = ['detailed', 'simple', 'visual', 'expert']
        if key in builtin and request.method == 'POST':
            return jsonify({'success': False, 'error': 'Cannot create prompts with reserved names'}), 400
        
        if save_prompt_to_file(key, name, description, prompt_text):
            # Clear cache so changes are reflected immediately
            clear_prompt_cache()
            # Reload presets
            global GEMINI_PROMPT_PRESETS
            GEMINI_PROMPT_PRESETS = _load_all_prompts()
            
            return jsonify({
                'success': True,
                'message': f'Prompt "{name}" saved successfully'
            })
        else:
            return jsonify({'success': False, 'error': 'Failed to save prompt'}), 500
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/prompts/<key>', methods=['DELETE'])
def delete_prompt_route(key):
    """Delete a prompt file"""
    try:
        # Don't allow deleting built-in prompts
        builtin = ['detailed', 'simple', 'visual', 'expert']
        if key in builtin:
            return jsonify({'success': False, 'error': 'Cannot delete built-in prompts'}), 400
        
        if delete_prompt_file(key):
            # Clear cache
            clear_prompt_cache()
            # Reload presets
            global GEMINI_PROMPT_PRESETS
            GEMINI_PROMPT_PRESETS = _load_all_prompts()
            
            return jsonify({'success': True, 'message': f'Prompt "{key}" deleted'})
        else:
            return jsonify({'success': False, 'error': 'Prompt not found or could not be deleted'}), 404
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/keys_status')
def get_gemini_keys_status():
    """Get detailed status of all Gemini API keys including usage statistics"""
    try:
        keys = app_settings.get('gemini_api_keys', [])
        if not keys:
            return jsonify({
                'success': True,
                'total_keys': 0,
                'message': 'No Gemini API keys configured',
                'summary': None,
                'keys': []
            })
        
        # Get tracker instance
        tracker = get_api_key_tracker()
        
        # Get summary from tracker
        summary = tracker.get_summary(len(keys))
        
        # Add key masks for display (show only last 4 chars)
        keys_detail = []
        for i, status in enumerate(summary['keys_detail']):
            key_masked = f"...{keys[i][-4:]}" if len(keys[i]) > 4 else "****"
            keys_detail.append({
                **status,
                'key_masked': key_masked,
                'key_number': i + 1
            })
        
        return jsonify({
            'success': True,
            'total_keys': summary['total_keys'],
            'available_keys': summary['available_keys'],
            'total_remaining_requests': summary['total_remaining_requests'],
            'total_requests_made': summary['total_requests_made'],
            'total_rate_limits_hit': summary['total_rate_limits_hit'],
            'next_available_in': summary['next_available_in'],
            'limit_per_minute': tracker.requests_per_minute_limit,
            'keys': keys_detail
        })
        
    except Exception as e:
        logger.error(f"Error getting Gemini keys status: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/gemini/reset_stats', methods=['POST'])
def reset_gemini_stats():
    """Reset all API key usage statistics"""
    try:
        tracker = get_api_key_tracker()
        tracker.key_stats.clear()
        
        logger.info("Gemini API key statistics reset")
        return jsonify({
            'success': True,
            'message': 'API key statistics have been reset'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


if __name__ == '__main__':
    print("=" * 60)
    print("🚀 Card Balance Checker Panel")
    print("=" * 60)
    print("📌 Panel URL: http://127.0.0.1:5000")
    print("=" * 60)
    app.run(debug=True, host='0.0.0.0', port=5000, threaded=True)
