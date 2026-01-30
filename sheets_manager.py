#!/usr/bin/env python3
"""
Google Sheets Manager - مدیریت اتصال به Google Sheets
برای خواندن کارت‌ها و نوشتن نتایج
"""

import gspread
from google.oauth2.service_account import Credentials
import logging
import json
from datetime import datetime
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Google Sheets API scopes
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets',
    'https://www.googleapis.com/auth/drive'
]

# Column indices (0-based)
COL_ID = 0
COL_UUID = 1
COL_CARD_NUMBER = 2
COL_EXP_MONTH = 3
COL_EXP_YEAR = 4
COL_CVV = 5
COL_INITIAL_BALANCE = 6
COL_CURRENT_BALANCE = 7
COL_RESULT_JSON = 8  # Now stores: check_date, notes, result data


class SheetsManager:
    """Manager for Google Sheets operations"""
    
    def __init__(self, credentials_file: str = 'credentials.json', sheet_url: str = None):
        """
        Initialize Google Sheets connection
        
        Args:
            credentials_file: Path to service account JSON file
            sheet_url: URL of the Google Sheet
        """
        self.credentials_file = credentials_file
        self.sheet_url = sheet_url or 'https://docs.google.com/spreadsheets/d/14b27s0J_cj_L3u0XxMszXpKXmj8-y5uDhNUGgQYV594/edit'
        self.client = None
        self.sheet = None
        self.worksheet = None
        
    def connect(self) -> bool:
        """Connect to Google Sheets"""
        try:
            creds = Credentials.from_service_account_file(
                self.credentials_file, 
                scopes=SCOPES
            )
            self.client = gspread.authorize(creds)
            self.sheet = self.client.open_by_url(self.sheet_url)
            self.worksheet = self.sheet.sheet1
            logger.info("Connected to Google Sheets")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Google Sheets: {e}")
            return False
    
    def get_all_cards(self) -> List[Dict]:
        """
        Get all cards from the sheet
        
        Returns:
            List of card dictionaries
        """
        try:
            rows = self.worksheet.get_all_values()
            cards = []
            
            for i, row in enumerate(rows):
                if len(row) >= 6 and row[COL_CARD_NUMBER]:  # Has card number
                    card = {
                        'row_index': i + 1,  # 1-based for gspread
                        'id': row[COL_ID] if len(row) > COL_ID else '',
                        'uuid': row[COL_UUID] if len(row) > COL_UUID else '',
                        'card_number': row[COL_CARD_NUMBER],
                        'exp_month': row[COL_EXP_MONTH] if len(row) > COL_EXP_MONTH else '',
                        'exp_year': row[COL_EXP_YEAR] if len(row) > COL_EXP_YEAR else '',
                        'cvv': row[COL_CVV] if len(row) > COL_CVV else '',
                        'initial_balance': row[COL_INITIAL_BALANCE] if len(row) > COL_INITIAL_BALANCE else '',
                        'current_balance': row[COL_CURRENT_BALANCE] if len(row) > COL_CURRENT_BALANCE else '',
                        'result_json': row[COL_RESULT_JSON] if len(row) > COL_RESULT_JSON else ''
                    }
                    cards.append(card)
            
            logger.info(f"Found {len(cards)} cards in sheet")
            return cards
            
        except Exception as e:
            logger.error(f"Failed to get cards: {e}")
            return []
    
    def get_unchecked_cards(self) -> List[Dict]:
        """
        Get cards that haven't been checked yet (no initial_balance OR no current_balance)
        A card is "checked" ONLY if it has BOTH initial_balance AND current_balance
        
        Returns:
            List of card dictionaries without balance
        """
        all_cards = self.get_all_cards()
        unchecked = []
        for c in all_cards:
            init_bal = c['initial_balance'].strip() if c['initial_balance'] else ''
            curr_bal = c['current_balance'].strip() if c['current_balance'] else ''
            # Skip if it's marked as DUPLICATE (considered as "checked")
            if init_bal.upper() == 'DUPLICATE' or curr_bal.upper() == 'DUPLICATE':
                continue
            # Unchecked if missing EITHER balance
            if not init_bal or not curr_bal:
                unchecked.append(c)
        logger.info(f"Found {len(unchecked)} unchecked cards")
        return unchecked
    
    def get_card_by_row(self, row_index: int) -> Optional[Dict]:
        """Get a specific card by row index (1-based)"""
        try:
            row = self.worksheet.row_values(row_index)
            if row and len(row) >= 6:
                return {
                    'row_index': row_index,
                    'id': row[COL_ID] if len(row) > COL_ID else '',
                    'uuid': row[COL_UUID] if len(row) > COL_UUID else '',
                    'card_number': row[COL_CARD_NUMBER],
                    'exp_month': row[COL_EXP_MONTH] if len(row) > COL_EXP_MONTH else '',
                    'exp_year': row[COL_EXP_YEAR] if len(row) > COL_EXP_YEAR else '',
                    'cvv': row[COL_CVV] if len(row) > COL_CVV else '',
                    'initial_balance': row[COL_INITIAL_BALANCE] if len(row) > COL_INITIAL_BALANCE else '',
                    'current_balance': row[COL_CURRENT_BALANCE] if len(row) > COL_CURRENT_BALANCE else '',
                    'result_json': row[COL_RESULT_JSON] if len(row) > COL_RESULT_JSON else ''
                }
            return None
        except Exception as e:
            logger.error(f"Failed to get card at row {row_index}: {e}")
            return None
    
    def check_duplicate(self, card_number: str, current_row: int = None) -> Tuple[bool, List[int]]:
        """
        Check if a card number is duplicate in the sheet
        
        Args:
            card_number: The card number to check
            current_row: Current row index to exclude from check
            
        Returns:
            Tuple of (is_duplicate, list of duplicate row indices)
        """
        try:
            all_cards = self.get_all_cards()
            duplicates = []
            
            for card in all_cards:
                if card['card_number'] == card_number:
                    if current_row is None or card['row_index'] != current_row:
                        duplicates.append(card['row_index'])
            
            is_duplicate = len(duplicates) > 0
            if is_duplicate:
                logger.warning(f"Card ****{card_number[-4:]} is duplicate! Found in rows: {duplicates}")
            
            return (is_duplicate, duplicates)
            
        except Exception as e:
            logger.error(f"Failed to check duplicate: {e}")
            return (False, [])
    
    def get_duplicate_with_balance(self, card_number: str, current_row: int = None) -> Tuple[bool, List[int], Optional[Dict]]:
        """
        Check duplicates and find if any has balance already
        
        Args:
            card_number: The card number to check
            current_row: Current row index to exclude from check
            
        Returns:
            Tuple of (is_duplicate, list of all duplicate row indices, card_with_balance or None)
        """
        try:
            all_cards = self.get_all_cards()
            all_matching_rows = []  # All rows with this card number (including current)
            card_with_balance = None
            
            for card in all_cards:
                if card['card_number'] == card_number:
                    all_matching_rows.append(card['row_index'])
                    # Check if this duplicate has balance (and it's not "DUPLICATE")
                    if card['initial_balance'] and card['initial_balance'].upper() != 'DUPLICATE':
                        if card['current_balance'] and card['current_balance'].upper() != 'DUPLICATE':
                            card_with_balance = card
            
            # Remove current row from duplicates list for return
            duplicates = [r for r in all_matching_rows if r != current_row]
            is_duplicate = len(duplicates) > 0
            
            if is_duplicate:
                if card_with_balance:
                    logger.info(f"Card ****{card_number[-4:]} is duplicate! Row {card_with_balance['row_index']} has balance: {card_with_balance['current_balance']}")
                else:
                    logger.info(f"Card ****{card_number[-4:]} is duplicate! No row has balance yet.")
            
            return (is_duplicate, all_matching_rows, card_with_balance)
            
        except Exception as e:
            logger.error(f"Failed to check duplicate with balance: {e}")
            return (False, [], None)
    
    def mark_duplicates_after_check(self, all_rows: List[int], checked_row: int, balance: str, result: Dict) -> bool:
        """
        After checking one card, mark all other duplicates with DUPLICATE
        
        Args:
            all_rows: All rows with this card number (including checked_row)
            checked_row: The row that was actually checked
            balance: The balance that was found
            result: The check result
        """
        try:
            for row in all_rows:
                if row == checked_row:
                    continue  # Skip the row we actually checked
                
                # Mark as DUPLICATE
                self.worksheet.update_cell(row, COL_INITIAL_BALANCE + 1, 'DUPLICATE')
                self.worksheet.update_cell(row, COL_CURRENT_BALANCE + 1, 'DUPLICATE')
                
                # Build result JSON for duplicate
                check_info = {
                    'check_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                    'is_duplicate': True,
                    'original_row': checked_row,
                    'original_balance': balance,
                    'status': f"DUPLICATE - Balance from row {checked_row}: {balance}",
                    'notes': f'Duplicate of row {checked_row} which has the actual balance',
                    'result': {'success': True, 'balance': balance, 'source': f'row_{checked_row}'}
                }
                
                result_json = json.dumps(check_info, ensure_ascii=False)
                self.worksheet.update_cell(row, COL_RESULT_JSON + 1, result_json)
                
                logger.info(f"Marked row {row} as DUPLICATE (original: row {checked_row})")
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark duplicates: {e}")
            return False
    
    def copy_balance_from_duplicate(self, target_row: int, source_card: Dict, all_rows: List[int]) -> bool:
        """
        Copy balance from an existing duplicate to target row
        
        Args:
            target_row: Row to copy balance to (mark as DUPLICATE)
            source_card: Card dictionary that has the balance
            all_rows: All duplicate rows
        """
        try:
            balance = source_card['current_balance']
            
            # Mark target as DUPLICATE
            self.worksheet.update_cell(target_row, COL_INITIAL_BALANCE + 1, 'DUPLICATE')
            self.worksheet.update_cell(target_row, COL_CURRENT_BALANCE + 1, 'DUPLICATE')
            
            # Build result JSON
            check_info = {
                'check_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'is_duplicate': True,
                'original_row': source_card['row_index'],
                'original_balance': balance,
                'all_duplicate_rows': all_rows,
                'status': f"DUPLICATE - Balance from row {source_card['row_index']}: {balance}",
                'notes': f'Balance already checked in row {source_card["row_index"]}',
                'result': {'success': True, 'balance': balance, 'source': f'row_{source_card["row_index"]}'}
            }
            
            result_json = json.dumps(check_info, ensure_ascii=False)
            self.worksheet.update_cell(target_row, COL_RESULT_JSON + 1, result_json)
            
            logger.info(f"Copied balance to row {target_row} from row {source_card['row_index']}: {balance}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to copy balance: {e}")
            return False
    
    def get_cards_in_range(self, start_row: int, end_row: int) -> List[Dict]:
        """
        Get cards in a specific row range
        
        Args:
            start_row: Starting row index (1-based)
            end_row: Ending row index (1-based)
            
        Returns:
            List of card dictionaries in the range
        """
        try:
            all_cards = self.get_all_cards()
            return [c for c in all_cards if start_row <= c['row_index'] <= end_row]
        except Exception as e:
            logger.error(f"Failed to get cards in range: {e}")
            return []
    
    def get_sheet_stats(self) -> Dict:
        """Get statistics about the sheet"""
        try:
            all_cards = self.get_all_cards()
            total = len(all_cards)
            
            # A card is "checked" ONLY if it has BOTH initial_balance AND current_balance
            # DUPLICATE cards are also considered "checked"
            checked = 0
            duplicates_marked = 0
            for c in all_cards:
                init_bal = c['initial_balance'].strip() if c['initial_balance'] else ''
                curr_bal = c['current_balance'].strip() if c['current_balance'] else ''
                
                if init_bal.upper() == 'DUPLICATE' or curr_bal.upper() == 'DUPLICATE':
                    checked += 1
                    duplicates_marked += 1
                elif init_bal and curr_bal:
                    checked += 1
            
            unchecked = total - checked
            
            # Find duplicate card numbers (same card in multiple rows)
            card_numbers = [c['card_number'] for c in all_cards]
            from collections import Counter
            counts = Counter(card_numbers)
            duplicate_cards = sum(1 for count in counts.values() if count > 1)
            
            return {
                'total': total,
                'checked': checked,
                'unchecked': unchecked,
                'duplicate_cards': duplicate_cards,  # Cards that appear more than once
                'duplicates_marked': duplicates_marked,  # Rows marked as DUPLICATE
                'first_row': all_cards[0]['row_index'] if all_cards else 0,
                'last_row': all_cards[-1]['row_index'] if all_cards else 0
            }
        except Exception as e:
            logger.error(f"Failed to get sheet stats: {e}")
            return {'total': 0, 'checked': 0, 'unchecked': 0, 'duplicate_cards': 0, 'duplicates_marked': 0, 'first_row': 0, 'last_row': 0}
    
    def update_card_result(self, row_index: int, result: Dict, notes: str = None, is_duplicate: bool = False, duplicate_rows: List[int] = None) -> bool:
        """
        Update card balance result in the sheet
        
        Args:
            row_index: Row number (1-based)
            result: Result dictionary from CardChecker
            notes: Optional notes/comments about the check
            is_duplicate: Whether this card is a duplicate
            duplicate_rows: List of rows where duplicates exist
            
        Returns:
            True if update successful
        """
        try:
            # Prepare values to update
            if result.get('success'):
                balance = result.get('balance', '')
                # Clean balance string (remove $ and spaces)
                balance_clean = balance.replace('$', '').replace(',', '').strip() if balance else ''
                
                # Get current initial balance
                current_row = self.worksheet.row_values(row_index)
                initial_balance = current_row[COL_INITIAL_BALANCE] if len(current_row) > COL_INITIAL_BALANCE else ''
                
                # If no initial balance set, set it now
                if not initial_balance and balance_clean:
                    self.worksheet.update_cell(row_index, COL_INITIAL_BALANCE + 1, balance_clean)
                    logger.info(f"Set initial balance for row {row_index}: {balance_clean}")
                
                # Update current balance
                self.worksheet.update_cell(row_index, COL_CURRENT_BALANCE + 1, balance_clean)
                logger.info(f"Updated current balance for row {row_index}: {balance_clean}")
            
            # Build enhanced result JSON with check info
            check_info = {
                'check_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'is_duplicate': is_duplicate,
                'duplicate_rows': duplicate_rows or [],
                'notes': notes or '',
                'result': result
            }
            
            # Add status text for quick reading
            if is_duplicate:
                check_info['status'] = f"DUPLICATE! Also in rows: {duplicate_rows}"
            elif result.get('success'):
                check_info['status'] = f"OK - Balance: {result.get('balance', 'N/A')}"
            else:
                check_info['status'] = f"ERROR - {result.get('error', 'Unknown error')[:50]}"
            
            result_json = json.dumps(check_info, ensure_ascii=False)
            self.worksheet.update_cell(row_index, COL_RESULT_JSON + 1, result_json)
            
            logger.info(f"Updated result for row {row_index}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update row {row_index}: {e}")
            return False
    
    def mark_as_duplicate(self, row_index: int, duplicate_rows: List[int]) -> bool:
        """
        Mark a card as duplicate without checking balance
        
        Args:
            row_index: Row to mark
            duplicate_rows: Other rows with same card
        """
        try:
            check_info = {
                'check_date': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'is_duplicate': True,
                'duplicate_rows': duplicate_rows,
                'status': f"DUPLICATE! Also in rows: {duplicate_rows}",
                'notes': 'Skipped - duplicate card detected',
                'result': {'success': False, 'error': 'Duplicate card - skipped'}
            }
            
            result_json = json.dumps(check_info, ensure_ascii=False)
            self.worksheet.update_cell(row_index, COL_RESULT_JSON + 1, result_json)
            
            logger.info(f"Marked row {row_index} as duplicate")
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark duplicate: {e}")
            return False
    
    def update_balance(self, row_index: int, initial_balance: str = None, current_balance: str = None) -> bool:
        """
        Update balance columns directly
        
        Args:
            row_index: Row number (1-based)
            initial_balance: Initial balance value
            current_balance: Current balance value
        """
        try:
            if initial_balance is not None:
                self.worksheet.update_cell(row_index, COL_INITIAL_BALANCE + 1, initial_balance)
            if current_balance is not None:
                self.worksheet.update_cell(row_index, COL_CURRENT_BALANCE + 1, current_balance)
            return True
        except Exception as e:
            logger.error(f"Failed to update balance: {e}")
            return False
    
    def batch_update_results(self, updates: List[Dict]) -> bool:
        """
        Batch update multiple rows at once (more efficient)
        
        Args:
            updates: List of {'row_index': int, 'result': dict}
        """
        try:
            # Prepare batch update
            batch_data = []
            
            for update in updates:
                row_index = update['row_index']
                result = update['result']
                
                if result.get('success'):
                    balance = result.get('balance', '').replace('$', '').replace(',', '').strip()
                    
                    # Current balance
                    batch_data.append({
                        'range': f'{gspread.utils.rowcol_to_a1(row_index, COL_CURRENT_BALANCE + 1)}',
                        'values': [[balance]]
                    })
                
                # Result JSON
                result_json = json.dumps(result, ensure_ascii=False)
                batch_data.append({
                    'range': f'{gspread.utils.rowcol_to_a1(row_index, COL_RESULT_JSON + 1)}',
                    'values': [[result_json]]
                })
            
            if batch_data:
                self.worksheet.batch_update(batch_data)
                logger.info(f"Batch updated {len(updates)} rows")
            
            return True
            
        except Exception as e:
            logger.error(f"Batch update failed: {e}")
            return False


# Test function
def test_connection():
    """Test the Google Sheets connection"""
    manager = SheetsManager(
        credentials_file='/home/rez/cursor/credentials.json'
    )
    
    if manager.connect():
        print("✅ Connected to Google Sheets!")
        
        # Get all cards
        cards = manager.get_all_cards()
        print(f"\n📋 Total cards: {len(cards)}")
        
        # Get unchecked cards
        unchecked = manager.get_unchecked_cards()
        print(f"⏳ Unchecked cards: {len(unchecked)}")
        
        # Show first unchecked card
        if unchecked:
            card = unchecked[0]
            print(f"\n🎴 First unchecked card:")
            print(f"   Row: {card['row_index']}")
            print(f"   Card: ****{card['card_number'][-4:]}")
            print(f"   Exp: {card['exp_month']}/{card['exp_year']}")
            print(f"   CVV: ***")
        
        return True
    else:
        print("❌ Failed to connect!")
        return False


if __name__ == '__main__':
    test_connection()
