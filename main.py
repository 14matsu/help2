import streamlit as st
st.set_page_config(layout="wide")

@st.cache_data(ttl=3600)
def get_cached_shifts(year, month):
    start_date = pd.Timestamp(year, month, 16)
    end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(days=1)
    return db.get_shifts(start_date, end_date)

import pandas as pd
from datetime import datetime
import io
import base64
import asyncio
from database import db
from pdf_generator import generate_help_table_pdf, generate_individual_pdf, generate_store_pdf
from constants import EMPLOYEES, EMPLOYEE_AREAS, SHIFT_TYPES, STORE_COLORS, WEEKDAY_JA, AREAS
from utils import parse_shift, format_shifts, update_session_state_shifts, highlight_weekend_and_holiday, highlight_filled_shifts

async def save_shift_async(date, employee, shift_str, repeat_weekly=False, selected_dates=None):
    if not repeat_weekly:
        await asyncio.to_thread(db.save_shift, date, employee, shift_str)
    else:
        # 選択された日付のみ保存
        for target_date in selected_dates:
            await asyncio.to_thread(db.save_shift, target_date, employee, shift_str)
    
    current_month = date.replace(day=1)
    next_month = current_month + pd.DateOffset(months=1)
    previous_month = current_month - pd.DateOffset(months=1)
    
    # キャッシュをクリア
    get_cached_shifts.clear()
    get_cached_shifts(current_month.year, current_month.month)
    get_cached_shifts(next_month.year, next_month.month)
    get_cached_shifts(previous_month.year, previous_month.month)
    
    st.experimental_rerun()

def initialize_shift_data(year, month):
    if 'shift_data' not in st.session_state or st.session_state.current_year != year or st.session_state.current_month != month:
        start_date = pd.Timestamp(year, month, 16)
        end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(days=1)
        date_range = pd.date_range(start=start_date, end=end_date)
        st.session_state.shift_data = pd.DataFrame(
            index=date_range,
            columns=EMPLOYEES,
            data='-'
        )
        st.session_state.current_year = year
        st.session_state.current_month = month

def calculate_shift_count(shift_data):
    def count_shift(shift):
        if pd.isna(shift) or shift == '-':
            return 0
        shift_type = shift.split(',')[0] if ',' in shift else shift
        if shift_type in ['1日可', '鹿屋', 'かご北', 'リクルート'] or shift_type.startswith('その他'):
            return 1
        elif shift_type in ['AM可', 'PM可']:
            return 0.5
        return 0

    # 変更前
    return shift_data.applymap(count_shift).sum()

def display_shift_table(selected_year, selected_month):
    start_date = pd.Timestamp(selected_year, selected_month, 16)
    end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(days=1)
    
    date_range = pd.date_range(start=start_date, end=end_date)
    display_data = st.session_state.shift_data.loc[start_date:end_date].copy()
    
    for date in date_range:
        if date not in display_data.index:
            display_data.loc[date] = '-'
    
    display_data = display_data.sort_index()
    display_data['日付'] = display_data.index.strftime('%Y-%m-%d')
    display_data['曜日'] = display_data.index.strftime('%a').map(WEEKDAY_JA)
    
    # スタイルの設定
    st.markdown("""
    <style>
    table {
        font-size: 16px;
        width: 100%;
    }
    th, td {
        text-align: center;
        padding: 10px;
        white-space: pre-line;
        vertical-align: top;
    }
    th {
        background-color: #f0f0f0;
    }
    .shift-count {
        font-weight: bold;
        background-color: #e6f3ff;
    }
    </style>
    """, unsafe_allow_html=True)

    # エリアタブの作成
    tabs = st.tabs(list(EMPLOYEE_AREAS.keys()))
    
    for area, tab in zip(EMPLOYEE_AREAS.keys(), tabs):
        with tab:
            area_employees = EMPLOYEE_AREAS[area]
            area_display_data = display_data[['日付', '曜日'] + area_employees]
            
            items_per_page = 15
            total_pages = len(area_display_data) // items_per_page + (1 if len(area_display_data) % items_per_page > 0 else 0)
            
            if f'current_page_{area}' not in st.session_state:
                st.session_state[f'current_page_{area}'] = 1

            # ページネーション用のコントロール
            col1, col2, col3 = st.columns([2,3,2])
            with col1:
                if st.button('◀◀ 最初', key=f'first_page_{area}'):
                    st.session_state[f'current_page_{area}'] = 1
                if st.button('◀ 前へ', key=f'prev_page_{area}') and st.session_state[f'current_page_{area}'] > 1:
                    st.session_state[f'current_page_{area}'] -= 1
            with col2:
                st.write(f'ページ {st.session_state[f"current_page_{area}"]} / {total_pages}')
            with col3:
                if st.button('最後 ▶▶', key=f'last_page_{area}'):
                    st.session_state[f'current_page_{area}'] = total_pages
                if st.button('次へ ▶', key=f'next_page_{area}') and st.session_state[f'current_page_{area}'] < total_pages:
                    st.session_state[f'current_page_{area}'] += 1

            start_idx = (st.session_state[f'current_page_{area}'] - 1) * items_per_page
            end_idx = start_idx + items_per_page
            page_display_data = area_display_data.iloc[start_idx:end_idx]
            
            # テーブルの表示
            page_display_data = page_display_data.reset_index(drop=True)
            styled_df = page_display_data.style.format(format_shifts, subset=area_employees)\
                                            .apply(highlight_weekend_and_holiday, axis=1)
            
            st.write(styled_df.hide(axis="index").to_html(escape=False), unsafe_allow_html=True)

            # シフト日数の表示
            st.markdown(f"### {area}のシフト日数")
            area_shift_counts = calculate_shift_count(area_display_data[area_employees])
            shift_count_df = pd.DataFrame([area_shift_counts], columns=area_employees)
            styled_shift_count = shift_count_df.style.format("{:.1f}")\
                                                   .set_properties(**{'class': 'shift-count'})
            st.write(styled_shift_count.hide(axis="index").to_html(escape=False), unsafe_allow_html=True)

            # エリアごとのPDFダウンロードボタン
            if st.button(f"{area}のヘルプ表をPDFでダウンロード", key=f'pdf_download_{area}'):
                pdf = generate_help_table_pdf(area_display_data, selected_year, selected_month, area)
                st.download_button(
                    label=f"{area}のヘルプ表PDFをダウンロード",
                    data=pdf,
                    file_name=f"{area}_{selected_year}_{selected_month}.pdf",
                    mime="application/pdf",
                    key=f'pdf_download_button_{area}'
                )

def initialize_session_state():
    if 'editing_shift' not in st.session_state:
        st.session_state.editing_shift = False
    if 'current_shift' not in st.session_state:
        st.session_state.current_shift = None
    if 'selected_dates' not in st.session_state:
        st.session_state.selected_dates = {}
    if 'help_selected_dates' not in st.session_state:
        st.session_state.help_selected_dates = {}

def update_shift_input(current_shift, employee, date, selected_year, selected_month):
    initialize_session_state()
    
    if not st.session_state.editing_shift:
        st.session_state.current_shift = current_shift
        st.session_state.editing_shift = True
    
    shift_type, times, stores = parse_shift(st.session_state.current_shift)
    
    # シフト種類選択
    new_shift_type = st.selectbox('種類', ['AM可', 'PM可', '1日可', '-', '休み', '鹿屋', 'かご北', 'リクルート', 'その他'], 
                                 index=['AM可', 'PM可', '1日可', '-', '休み', '鹿屋', 'かご北', 'リクルート', 'その他'].index(shift_type) 
                                 if shift_type in ['AM可', 'PM可', '1日可', '休み', '鹿屋', 'かご北', 'リクルート', 'その他'] else 3)
        
    if new_shift_type in ['AM可', 'PM可', '1日可']:
        num_shifts = st.number_input('シフト数', min_value=1, max_value=5, value=len(times) or 1)
        
        new_times = []
        new_stores = []
        for i in range(num_shifts):
            col1, col2, col3 = st.columns(3)
            with col1:
                area_options = list(AREAS.keys())
                current_area = next((area for area, stores_list in AREAS.items() if stores[i] in stores_list), area_options[0]) if i < len(stores) else area_options[0]
                area = st.selectbox(f'エリア {i+1}', area_options, index=area_options.index(current_area), key=f'shift_area_{i}')
                
            with col2:
                store_options = [''] + AREAS[area] if area != 'なし' else ['']
                current_store = stores[i] if i < len(stores) and stores[i] in store_options else ''
                store = st.selectbox(f'店舗 {i+1}', store_options, index=store_options.index(current_store), key=f'shift_store_{i}')
            
            with col3:
                time = st.text_input(f'時間 {i+1}', value=times[i] if i < len(times) else '')
            
            if time:
                new_times.append(time)
                new_stores.append(store)
        
        if new_times:
            new_shift_str = f"{new_shift_type},{','.join([f'{t}@{s}' if s else t for t, s in zip(new_times, new_stores)])}"
        else:
            new_shift_str = new_shift_type
            
    elif new_shift_type == 'その他':
        # その他の内容を取得
        if shift_type == 'その他' and times and not times[0].endswith('@'):
            default_content = times[0]
            shift_times = times[1:] if len(times) > 1 else []
        else:
            default_content = ''
            shift_times = times
            
        other_content = st.text_input('内容を入力してください', value=default_content)
        
        # その他の場合も時間と店舗を登録できるようにする
        has_shift = st.checkbox('時間と店舗を登録する', value=bool(stores))
        
        if has_shift:
            num_shifts = st.number_input('シフト数', min_value=1, max_value=5, value=len(stores) or 1)
            
            new_times = []
            new_stores = []
            for i in range(num_shifts):
                col1, col2, col3 = st.columns(3)
                with col1:
                    area_options = list(AREAS.keys())
                    current_area = next((area for area, stores_list in AREAS.items() if stores[i] in stores_list), area_options[0]) if i < len(stores) else area_options[0]
                    area = st.selectbox(f'エリア {i+1}', area_options, index=area_options.index(current_area), key=f'other_shift_area_{i}')
                    
                with col2:
                    store_options = [''] + AREAS[area] if area != 'なし' else ['']
                    current_store = stores[i] if i < len(stores) and stores[i] in store_options else ''
                    store = st.selectbox(f'店舗 {i+1}', store_options, index=store_options.index(current_store), key=f'other_shift_store_{i}')
                
                with col3:
                    time = st.text_input(f'時間 {i+1}', value=shift_times[i] if i < len(shift_times) else '', key=f'other_time_{i}')
                
                if time:
                    new_times.append(time)
                    new_stores.append(store)
            
            if other_content and new_times:
                # その他の内容と時間/店舗情報を別々に保持
                new_shift_str = f"その他,{other_content},{','.join([f'{t}@{s}' if s else t for t, s in zip(new_times, new_stores)])}"
            elif other_content:
                new_shift_str = f"その他,{other_content}"
            else:
                new_shift_str = 'その他'
        else:
            new_shift_str = f"その他,{other_content}" if other_content else 'その他'
            
    elif new_shift_type in ['休み', '鹿屋', 'かご北', 'リクルート', '-']:
        new_shift_str = new_shift_type
    
    st.session_state.current_shift = new_shift_str

    # 繰り返し登録チェックボックス
    repeat_weekly = st.checkbox('繰り返し登録をする', help='同一シフトを一括登録します')
    
    # 選択可能な日付のリストを作成
    selected_dates = []
    if repeat_weekly:
        # 表示している期間の開始日と終了日を取得（選択された年月に基づく）
        period_start = pd.Timestamp(selected_year, selected_month, 16)
        period_end = (period_start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
        
        # 期間内のすべての日付を生成
        dates = pd.date_range(start=period_start, end=period_end).tolist()
        
        if dates:
            st.write('登録する日付を選択:')
            
            # セッション状態の初期化
            if 'selected_dates' not in st.session_state:
                st.session_state.selected_dates = {d.strftime("%Y/%m/%d"): True for d in dates}
            
            # 全選択/全解除ボタン
            col1, col2 = st.columns(2)
            with col1:
                if st.button('全て選択'):
                    for d in dates:
                        st.session_state.selected_dates[d.strftime("%Y/%m/%d")] = True
                    st.experimental_rerun()
            with col2:
                if st.button('全て解除'):
                    for d in dates:
                        st.session_state.selected_dates[d.strftime("%Y/%m/%d")] = False
                    st.experimental_rerun()
            
            # 日付選択用のチェックボックスを表示
            for d in dates:
                date_str = d.strftime("%Y/%m/%d")
                st.session_state.selected_dates[date_str] = st.checkbox(
                    f'{date_str} ({WEEKDAY_JA[d.strftime("%a")]})', 
                    value=st.session_state.selected_dates.get(date_str, True),
                    key=f'date_checkbox_{date_str}'
                )
                if st.session_state.selected_dates[date_str]:
                    selected_dates.append(d)
    
    return new_shift_str, repeat_weekly, selected_dates

def register_store_help(help_date, store, help_time, selected_year, selected_month):
    # 繰り返し登録チェックボックス
    repeat_weekly = st.checkbox('繰り返し登録をする', help='ヘルプ希望を一括登録します', key='help_repeat_weekly')
    
    selected_dates = []
    if repeat_weekly:
        # 表示している期間の開始日と終了日を取得（選択された年月に基づく）
        period_start = pd.Timestamp(selected_year, selected_month, 16)
        period_end = (period_start + pd.DateOffset(months=1)) - pd.Timedelta(days=1)
        
        # 期間内のすべての日付を生成
        dates = pd.date_range(start=period_start, end=period_end).tolist()
        
        if dates:
            st.write('登録する日付を選択:')
            
            # セッション状態の初期化
            if 'help_selected_dates' not in st.session_state:
                st.session_state.help_selected_dates = {d.strftime("%Y/%m/%d"): True for d in dates}
            
            # 全選択/全解除ボタン
            col1, col2 = st.columns(2)
            with col1:
                if st.button('全て選択', key='help_select_all'):
                    for d in dates:
                        st.session_state.help_selected_dates[d.strftime("%Y/%m/%d")] = True
                    st.experimental_rerun()
            with col2:
                if st.button('全て解除', key='help_clear_all'):
                    for d in dates:
                        st.session_state.help_selected_dates[d.strftime("%Y/%m/%d")] = False
                    st.experimental_rerun()
            
            # 日付選択用のチェックボックスを表示
            for d in dates:
                date_str = d.strftime("%Y/%m/%d")
                st.session_state.help_selected_dates[date_str] = st.checkbox(
                    f'{date_str} ({WEEKDAY_JA[d.strftime("%a")]})', 
                    value=st.session_state.help_selected_dates.get(date_str, True),
                    key=f'help_date_checkbox_{date_str}'
                )
                if st.session_state.help_selected_dates[date_str]:
                    selected_dates.append(d)
    
    return repeat_weekly, selected_dates

async def save_store_help_async(help_date, store, help_time, repeat_weekly=False, selected_dates=None):
    if not repeat_weekly:
        # 単一日付の登録
        db.save_store_help_request(help_date, store, help_time)
    else:
        # 選択された日付すべてに登録
        for target_date in selected_dates:
            db.save_store_help_request(target_date, store, help_time)

def display_store_help_requests(selected_year, selected_month):
    st.header('店舗ヘルプ希望')
    
    start_date = pd.Timestamp(selected_year, selected_month, 16)
    end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(days=1)
    
    store_help_requests = db.get_store_help_requests(start_date, end_date)
    
    if store_help_requests.empty:
        st.write("ヘルプ希望はありません。")
    else:
        store_help_requests['日付'] = store_help_requests.index.strftime('%Y-%m-%d')
        store_help_requests['曜日'] = store_help_requests.index.strftime('%a').map(WEEKDAY_JA)
        
        all_stores = [store for stores in AREAS.values() for store in stores]
        for store in all_stores:
            if store not in store_help_requests.columns:
                store_help_requests[store] = '-'
        
        store_help_requests = store_help_requests.reset_index(drop=True)

        area_tabs = [area for area in AREAS.keys() if area != 'なし']
        tabs = st.tabs(area_tabs)
        
        st.markdown("""
        <style>
        table {
            font-size: 14px;
            width: 100%;
            border-collapse: collapse;
        }
        th, td {
            text-align: center;
            padding: 8px;
            border: 1px solid #ddd;
        }
        th {
            background-color: #f2f2f2;
        }
        </style>
        """, unsafe_allow_html=True)
        
        for area, tab in zip(area_tabs, tabs):
            with tab:
                area_stores = AREAS[area]
                area_data = store_help_requests[['日付', '曜日'] + area_stores]
                area_data = area_data.fillna('-')

                shift_data = st.session_state.shift_data[
                    (st.session_state.shift_data.index >= start_date) & 
                    (st.session_state.shift_data.index <= end_date)
                ]
                shift_data.index = pd.to_datetime(shift_data.index)

                styled_df = area_data.style.apply(highlight_weekend_and_holiday, axis=1)\
                                        .apply(highlight_filled_shifts, shift_data=shift_data, axis=1)

                st.write(styled_df.to_html(escape=False, index=False), unsafe_allow_html=True)

async def main():
    st.title('ヘルプ管理アプリ📝')

    with st.sidebar:
        st.header('設定')
        current_year = datetime.now().year
        years = range(current_year - 1, current_year + 10)
        current_year_index = years.index(current_year)
        selected_year = st.selectbox('年を選択', years, index=current_year_index, key='year_selector')
        selected_month = st.selectbox('月を選択', range(1, 13), key='month_selector')

        initialize_shift_data(selected_year, selected_month)
        shifts = get_cached_shifts(selected_year, selected_month)
        update_session_state_shifts(shifts)

        st.header('シフト登録/修正')
        
        # エリアごとに従業員を選択できるように変更
        area = st.selectbox('エリアを選択', list(EMPLOYEE_AREAS.keys()), key='employee_area_selector')
        employee = st.selectbox('従業員を選択', EMPLOYEE_AREAS[area])
        
        start_date = datetime(selected_year, selected_month, 16)
        end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(days=1)
        default_date = max(min(datetime.now().date(), end_date.date()), start_date.date())
        date = st.date_input('日付を選択', min_value=start_date.date(), max_value=end_date.date(), value=default_date)
        
        if not isinstance(st.session_state.shift_data.index, pd.DatetimeIndex):
            st.session_state.shift_data.index = pd.to_datetime(st.session_state.shift_data.index)

        date = pd.Timestamp(date)

        if date in st.session_state.shift_data.index:
            current_shift = st.session_state.shift_data.loc[date, employee]
            if pd.isna(current_shift) or isinstance(current_shift, (int, float)):
                current_shift = '休み'
        else:
            current_shift = '休み'
        
        if 'last_employee' not in st.session_state or 'last_date' not in st.session_state or \
           st.session_state.last_employee != employee or st.session_state.last_date != date:
            st.session_state.editing_shift = False
        
        st.session_state.last_employee = employee
        st.session_state.last_date = date
        
        new_shift_str, repeat_weekly, selected_dates = update_shift_input(current_shift, employee, date, selected_year, selected_month)

        if st.button('保存'):
            await save_shift_async(date, employee, new_shift_str, repeat_weekly, selected_dates)
            st.session_state.shift_data.loc[date, employee] = new_shift_str
            if repeat_weekly and selected_dates:
                for next_date in selected_dates:
                    if next_date in st.session_state.shift_data.index:
                        st.session_state.shift_data.loc[next_date, employee] = new_shift_str
            st.session_state.editing_shift = False
            st.success('保存しました')
            st.experimental_rerun()

        st.header('店舗ヘルプ希望登録/修正')
        area = st.selectbox('エリアを選択', [key for key in AREAS.keys() if key != 'なし'], key='help_area')
        store = st.selectbox('店舗を選択', AREAS[area], key='help_store')
        help_default_date = max(min(datetime.now().date(), end_date.date()), start_date.date())
        
        help_date = st.date_input('日付を選択', min_value=start_date.date(), max_value=end_date.date(), value=help_default_date, key='help_date')
        help_time = st.text_input('時間帯')
        
        # 繰り返し登録のオプションを追加
        repeat_weekly, selected_dates = register_store_help(pd.Timestamp(help_date), store, help_time, selected_year, selected_month)
        
        if st.button('ヘルプ希望を登録'):
            await save_store_help_async(help_date, store, help_time, repeat_weekly, selected_dates)
            st.success('ヘルプ希望を登録しました')
            st.experimental_rerun()

        st.header('個別PDFのダウンロード')
        # エリアごとに従業員を選択できるように変更
        pdf_area = st.selectbox('エリアを選択', list(EMPLOYEE_AREAS.keys()), key='pdf_employee_area_selector')
        selected_employee = st.selectbox('従業員を選択', EMPLOYEE_AREAS[pdf_area], key='pdf_employee_selector')
        
        if st.button('PDFを生成'):
            employee_data = st.session_state.shift_data[selected_employee]
            pdf_buffer = generate_individual_pdf(employee_data, selected_employee, selected_year, selected_month)
            start_date = pd.Timestamp(selected_year, selected_month, 16)
            end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(days=1)
            file_name = f'{selected_employee}さん_{start_date.strftime("%Y年%m月%d日")}～{end_date.strftime("%Y年%m月%d日")}_シフト.pdf'
            st.download_button(
                label=f"{selected_employee}さんのPDFをダウンロード",
                data=pdf_buffer.getvalue(),
                file_name=file_name,
                mime="application/pdf"
            )

        st.header('店舗別PDFのダウンロード')
        selected_area = st.selectbox('エリアを選択', [key for key in AREAS.keys() if key != 'なし'], key='pdf_area_selector')
        selected_store = st.selectbox('店舗を選択', AREAS[selected_area], key='pdf_store_selector')
        if st.button('店舗PDFを生成'):
            start_date = pd.Timestamp(selected_year, selected_month, 16)
            end_date = start_date + pd.DateOffset(months=1) - pd.Timedelta(days=1)
            
            # シフトデータの取得
            store_data = st.session_state.shift_data.copy()
            
            try:
                # ヘルプ希望データの取得とデフォルト値の設定
                store_help_requests = db.get_store_help_requests(start_date, end_date)
                if store_help_requests.empty:
                    # ヘルプ希望データが空の場合、すべての日付で'-'を設定
                    date_range = pd.date_range(start=start_date, end=end_date)
                    store_help_requests = pd.DataFrame(index=date_range, columns=[selected_store])
                    store_help_requests[selected_store] = '-'
                elif selected_store not in store_help_requests.columns:
                    # 選択された店舗のデータが存在しない場合、'-'で列を追加
                    store_help_requests[selected_store] = '-'
                
                # シフトデータにヘルプ希望データを追加
                store_data[selected_store] = store_help_requests[selected_store]
                
                # PDFの生成
                pdf_buffer = generate_store_pdf(store_data, selected_store, selected_year, selected_month)
                file_name = f'{selected_month}月_{selected_store}.pdf'
                
                # ダウンロードボタンの表示
                st.download_button(
                    label=f"{selected_store}のPDFをダウンロード",
                    data=pdf_buffer.getvalue(),
                    file_name=file_name,
                    mime="application/pdf"
                )
                
            except Exception as e:
                st.error(f"PDFの生成中にエラーが発生しました。: {str(e)}")

    display_shift_table(selected_year, selected_month)
    display_store_help_requests(selected_year, selected_month)

if __name__ == '__main__':
    if db.init_db():
        asyncio.run(main())
    else:
        st.error("データベース接続に失敗しました")

