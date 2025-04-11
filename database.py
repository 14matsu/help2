import os
from datetime import datetime
import pandas as pd
from supabase import create_client, Client
import streamlit as st
from constants import AREAS
from dotenv import load_dotenv

# ローカル環境の場合のみ.envファイルを読み込む
if not os.environ.get('STREAMLIT_CLOUD'):
    load_dotenv()

class SupabaseDB:
    def __init__(self):
        try:
            # .envファイルからの読み込みを優先
            load_dotenv()
            supabase_url = os.getenv("SUPABASE_URL")
            supabase_key = os.getenv("SUPABASE_KEY")
            
            # 値が取得できなければStreamlit Secretsを試す
            if not supabase_url or not supabase_key:
                if "database" in st.secrets:
                    supabase_url = st.secrets["database"]["supabase_url"]
                    supabase_key = st.secrets["database"]["supabase_key"]
                
            if not supabase_url or not supabase_key:
                st.error("データベース接続情報が見つかりません")
                st.write("Current values:", {
                    "url_exists": bool(supabase_url),
                    "key_exists": bool(supabase_key)
                })
                raise Exception("Supabase の認証情報が設定されていません")
            
            # デバッグ用に最初の数文字だけ表示
            st.write(f"URL: {supabase_url[:10]}...")
            st.write(f"Key: {supabase_key[:5]}...")
            
            self.supabase: Client = create_client(supabase_url, supabase_key)
            
        except Exception as e:
            st.error(f"データベース接続エラー: {str(e)}")
            raise
    
    def init_db(self):
        try:
            # テーブルの存在確認
            self.supabase.table('shifts').select("*").limit(1).execute()
            self.supabase.table('store_help_requests').select("*").limit(1).execute()
            return True
        except Exception as e:
            st.error(f"データベース接続エラー: {e}")
            return False

    def get_shifts(self, start_date, end_date):
        try:
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
            
            # Supabaseからデータを取得
            response = self.supabase.table('shifts')\
                .select("*")\
                .gte('date', start_date_str)\
                .lte('date', end_date_str)\
                .execute()
            
            if not response.data:
                return pd.DataFrame()
            
            # データフレームに変換
            df = pd.DataFrame(response.data)
            df['date'] = pd.to_datetime(df['date'])
            
            # ピボットテーブルを作成
            pivot_df = df.pivot(index='date', columns='employee', values='shift')
            return pivot_df
            
        except Exception as e:
            st.error(f"シフトデータの取得エラー: {e}")
            return pd.DataFrame()

    def save_shift(self, date, employee, shift_str):
        try:
            date_str = date.strftime('%Y-%m-%d')
            
            # データをUpsert（更新または挿入）
            self.supabase.table('shifts')\
                .upsert({
                    'date': date_str,
                    'employee': employee,
                    'shift': shift_str
                })\
                .execute()
            
            return True
        except Exception as e:
            st.error(f"シフトの保存エラー: {e}")
            return False

    def save_store_help_request(self, date, store, help_time):
        try:
            date_str = date.strftime('%Y-%m-%d')
            
            # データをUpsert
            self.supabase.table('store_help_requests')\
                .upsert({
                    'date': date_str,
                    'store': store,
                    'help_time': help_time
                })\
                .execute()
            
            return True
        except Exception as e:
            st.error(f"店舗ヘルプ希望の保存エラー: {e}")
            return False

    def get_store_help_requests(self, start_date, end_date):
        try:
            start_date_str = start_date.strftime('%Y-%m-%d')
            end_date_str = end_date.strftime('%Y-%m-%d')
            
            # Supabaseからデータを取得
            response = self.supabase.table('store_help_requests')\
                .select("*")\
                .gte('date', start_date_str)\
                .lte('date', end_date_str)\
                .execute()
            
            if not response.data:
                return pd.DataFrame()
            
            # データフレームに変換
            df = pd.DataFrame(response.data)
            df['date'] = pd.to_datetime(df['date'])
            
            # ピボットテーブルを作成
            pivot_df = df.pivot(index='date', columns='store', values='help_time').fillna('-')
            
            # 全ての店舗列が存在することを確認
            all_stores = [store for stores in AREAS.values() for store in stores]
            for store in all_stores:
                if store not in pivot_df.columns:
                    pivot_df[store] = '-'
            
            return pivot_df
            
        except Exception as e:
            st.error(f"店舗ヘルプ希望の取得エラー: {e}")
            return pd.DataFrame()

# データベースのシングルトンインスタンスを作成
db = SupabaseDB()