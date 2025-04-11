import pandas as pd
import streamlit as st
import jpholiday
from constants import AREAS, SHIFT_TYPES, STORE_COLORS, FILLED_HELP_BG_COLOR, SATURDAY_BG_COLOR,HOLIDAY_BG_COLOR, KANOYA_BG_COLOR, KAGOKITA_BG_COLOR,RECRUIT_BG_COLOR

#シフト文字列を解析し、シフトタイプ、時間、店舗に分割
def parse_shift(shift_str):
    """シフト文字列を解析し、シフトタイプ、時間、店舗に分割"""
    # 特殊なケースの処理
    if pd.isna(shift_str) or shift_str in ['-', '休み', '鹿屋', 'かご北', 'リクルート'] or isinstance(shift_str, (int, float)):
        return shift_str, [], []

    # 「その他」の場合の処理
    if isinstance(shift_str, str) and shift_str.startswith('その他'):
        parts = shift_str.split(',')
        if len(parts) == 1:  # 「その他」のみの場合
            return 'その他', [], []
        elif len(parts) == 2:  # 内容のみの場合（例：その他,研修）
            return 'その他', [parts[1]], []
        else:  # 内容と時間/店舗情報がある場合
            times = []
            stores = []
            # その他の内容は別途保持
            other_content = parts[1]
            # 3番目以降の要素を時間と店舗として処理
            for part in parts[2:]:
                if '@' in part:
                    time, store = part.strip().split('@')
                    times.append(time)
                    stores.append(store)
                else:
                    times.append(part.strip())
                    stores.append('')
            # その他の内容を最初の要素として返す
            return 'その他', [other_content] + times, stores

    try:
        # 通常のシフト処理
        parts = str(shift_str).split(',')
        shift_type = parts[0] if parts[0] in ['AM可', 'PM可', '1日可', '休み', '鹿屋', 'かご北', 'リクルート', 'その他'] else ''
        
        times_stores = []
        for part in parts[1:]:
            if '@' in part:
                time, store = part.strip().split('@')
                times_stores.append((time, store))
            else:
                times_stores.append((part.strip(), ''))
        
        times, stores = zip(*times_stores) if times_stores else ([], [])
        return shift_type, list(times), list(stores)
    except:
        return '-', [], []
    

#シフトデータを表示用にフォーマット
def format_shifts(val):
    if pd.isna(val) or val == '-' or isinstance(val, (int, float)):
        return val
    if val == '休み':
        return f'<div style="background-color: {HOLIDAY_BG_COLOR};">{val}</div>'
    if val == '鹿屋':
        return f'<div style="background-color: {KANOYA_BG_COLOR};">{val}</div>'
    if val == 'かご北':
        return f'<div style="background-color: {KAGOKITA_BG_COLOR};">{val}</div>'
    if val == 'リクルート':
        return f'<div style="background-color: {RECRUIT_BG_COLOR};">{val}</div>'
    if isinstance(val, str) and val.startswith('その他'):
        parts = val.split(',')
        if len(parts) > 1:
            # その他の内容を取得
            content = parts[1]
            # 時間と店舗の情報を処理
            shift_parts = []
            for part in parts[2:]:
                if '@' in part:
                    time, store = part.strip().split('@')
                    color = STORE_COLORS.get(store, "#000000")
                    shift_parts.append(f'<span style="color: {color}">{time}@{store}</span>')
                else:
                    shift_parts.append(part.strip())
            
            # その他の内容と時間/店舗情報を改行で区切って表示
            shifts_str = chr(10).join(shift_parts) if shift_parts else ''
            return f'<div style="background-color: {RECRUIT_BG_COLOR}; white-space: pre-line">その他: {content}\n{shifts_str}</div>'
        return f'<div style="background-color: {RECRUIT_BG_COLOR};">その他: {parts[1]}</div>'
    
    try:
        parts = str(val).split(',')
        shift_type = parts[0]
        formatted_shifts = []
        
        for part in parts[1:]:
            if '@' in part:
                time, store = part.strip().split('@')
                if store == 'かご北':
                    # かご北の場合は背景色を適用
                    formatted_shifts.append(f'<span style="background-color: {KAGOKITA_BG_COLOR}">{time}@{store}</span>')
                else:
                    # その他の店舗は通常の色のみ
                    color = STORE_COLORS.get(store, "#000000")
                    formatted_shifts.append(f'<span style="color: {color}">{time}@{store}</span>')
            else:
                formatted_shifts.append(part.strip())
        
        if shift_type in ['AM可', 'PM可', '1日可']:
            if formatted_shifts:
                return f'<div style="white-space: pre-line">{shift_type}\n{chr(10).join(formatted_shifts)}</div>'
            else:
                return shift_type
        else:
            return f'<div style="white-space: pre-line">{chr(10).join(formatted_shifts)}</div>' if formatted_shifts else '-'
    except Exception as e:
        print(f"Error formatting shift: {val}. Error: {e}")
        return str(val)
    
#セッション状態のシフトデータを更新
def update_session_state_shifts(shifts):
    for date, row in shifts.iterrows():
        if date in st.session_state.shift_data.index:
            for employee, shift in row.items():
                if pd.notna(shift):
                    st.session_state.shift_data.loc[date, employee] = str(shift)
                else:
                    st.session_state.shift_data.loc[date, employee] = '-'

#土曜日と日曜日の行に背景色を適用
def is_holiday(date):
    return jpholiday.is_holiday(date)

def highlight_weekend_and_holiday(row):
    weekday = row['曜日']
    date = pd.to_datetime(row['日付'])
    if weekday == '日' or is_holiday(date):
        return ['background-color: ' + HOLIDAY_BG_COLOR] * len(row)
    elif weekday == '土':
        return ['background-color: ' + SATURDAY_BG_COLOR] * len(row)
    return [''] * len(row)


def get_store_index(store):
    all_stores = [s for stores in AREAS.values() for s in stores]
    return all_stores.index(store) if store in all_stores else 0

def get_shift_type_index(shift_type):
    return SHIFT_TYPES.index(shift_type) if shift_type in SHIFT_TYPES else 0


#シフトが埋まっているかどうかをチェック
def is_shift_filled(shift):
    if pd.isna(shift) or shift == '-':
        return False, []
    shift_type, times, stores = parse_shift(shift)
    return bool(times and stores), stores


#埋まっているシフトをハイライト
def highlight_filled_shifts(row, shift_data):
    styles = [''] * len(row)
    date = pd.to_datetime(row['日付'])
    if date not in shift_data.index:
        return styles
    
    all_stores = [store for stores in AREAS.values() for store in stores]
    for i, store in enumerate(all_stores):
        if store in row.index:
            store_shifts = shift_data.loc[date]
            if any(is_shift_filled(shift)[0] and store in is_shift_filled(shift)[1] for shift in store_shifts if pd.notna(shift)):
                styles[row.index.get_loc(store)] = FILLED_HELP_BG_COLOR
    return styles