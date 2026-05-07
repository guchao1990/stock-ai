"""
股票分析AI应用 - 轻量级版
支持: A股(通过东方财富API)、美股(yfinance)、港股
AI分析: DeepSeek API
"""

import os
import re
import json
import pandas as pd
import numpy as np
from flask import Flask, render_template, request, jsonify, send_from_directory
from dotenv import load_dotenv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta
import requests
from io import BytesIO
import base64

load_dotenv()

app = Flask(__name__, static_folder='static', template_folder='templates')
app.config['JSON_AS_ASCII'] = False

# API配置
API_KEY = os.getenv('API_KEY', '')
BASE_URL = os.getenv('BASE_URL', 'https://api.deepseek.com/v1')
MODEL_NAME = os.getenv('MODEL_NAME', 'deepseek-chat')

# 确保目录存在
os.makedirs('./output', exist_ok=True)
os.makedirs('./output/charts', exist_ok=True)


def get_stock_data_em_hk(stock_code):
    """使用东方财富API获取港股数据"""
    try:
        # 港股代码转换
        url = f"http://push2his.eastmoney.com/api/qt/stock/kline/get"
        params = {
            'secid': f"116.{stock_code}",  # 港股
            'fields1': 'f1,f2,f3,f4,f5,f6',
            'fields2': 'f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61',
            'klt': '101',  # 日K
            'fqt': '1',    # 前复权
            'end': '20500101',
            'lmt': '90'    # 最近90天
        }
        headers = {'User-Agent': 'Mozilla/5.0'}

        response = requests.get(url, params=params, headers=headers, timeout=10)
        data = response.json()

        if data['data']['klines']:
            klines = data['data']['klines']
            records = []
            for kline in klines:
                parts = kline.split(',')
                records.append({
                    'Date': pd.to_datetime(parts[0]),
                    'Open': float(parts[1]),
                    'High': float(parts[2]),
                    'Low': float(parts[3]),
                    'Close': float(parts[4]),
                    'Volume': float(parts[5])
                })
            df = pd.DataFrame(records)
            df.set_index('Date', inplace=True)
            return df
    except Exception as e:
        print(f"Eastmoney HK API error: {e}")
    return pd.DataFrame()


def get_stock_data_us(symbol, period='3mo'):
    """获取美股数据 through 东方财富"""
    try:
        # 东方财富美股API
        url = "http://push2his.eastmoney.com/api/qt/stock/kline/get"
        # 尝试直接获取数据
        headers = {'User-Agent': 'Mozilla/5.0'}

        # 使用新浪美股API作为备选
        try:
            sn_url = f"https://finance.sina.com.cn/realstock/company/{symbol}/hisdata/klc_kl.js"
            response = requests.get(sn_url, headers=headers, timeout=10)
            if response.status_code == 200:
                # 解析新浪数据
                text = response.text
                # 简单解析
                import re
                matches = re.findall(r'(\d{4}-\d{2}-\d{2}),(\d+\.\d+),(\d+\.\d+),(\d+\.\d+),(\d+\.\d+),(\d+)', text)
                if matches:
                    records = []
                    for m in matches[-90:]:
                        records.append({
                            'Date': pd.to_datetime(m[0]),
                            'Open': float(m[1]),
                            'High': float(m[2]),
                            'Low': float(m[3]),
                            'Close': float(m[4]),
                            'Volume': float(m[5])
                        })
                    df = pd.DataFrame(records)
                    df.set_index('Date', inplace=True)
                    return df
        except:
            pass

        # 使用Yahoo Finance API通过代理
        yf_url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        params = {'period1': int((datetime.now() - timedelta(days=90)).timestamp()),
                  'period2': int(datetime.now().timestamp()),
                  'interval': '1d'}
        response = requests.get(yf_url, params=params, headers=headers, timeout=10)
        data = response.json()

        if 'chart' in data and 'result' in data['chart'] and data['chart']['result']:
            result = data['chart']['result'][0]
            timestamps = result['timestamp']
            quotes = result['indicators']['quote'][0]

            records = []
            for i, ts in enumerate(timestamps):
                records.append({
                    'Date': pd.to_datetime(ts, unit='s'),
                    'Open': quotes['open'][i],
                    'High': quotes['high'][i],
                    'Low': quotes['low'][i],
                    'Close': quotes['close'][i],
                    'Volume': quotes['volume'][i]
                })
            df = pd.DataFrame(records)
            df.set_index('Date', inplace=True)
            return df
    except Exception as e:
        print(f"US Stock API error: {e}")
    return pd.DataFrame()


def get_stock_data_em(stock_code):
    """获取A股K线数据 through 腾讯K线API"""
    try:
        # 判断市场前缀
        if stock_code.startswith('6'):
            prefix = 'sh'  # 上海
        elif stock_code.startswith('0') or stock_code.startswith('3'):
            prefix = 'sz'  # 深圳
        else:
            # 港股
            return get_stock_data_yf(f"{stock_code}.HK")

        # 使用腾讯K线API
        url = f"https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
        params = {
            'param': f"{prefix}{stock_code},day,,,90,qfq",
            '_var': 'kline_dayqfq'
        }
        headers = {'User-Agent': 'Mozilla/5.0'}

        response = requests.get(url, params=params, headers=headers, timeout=15)
        text = response.text

        # 解析 kline_dayqfq={...} 格式
        if 'kline_dayqfq=' in text:
            json_str = text.replace('kline_dayqfq=', '')
            data = json.loads(json_str)

            if data.get('code') == 0 and data.get('data'):
                stock_data = data['data'].get(f"{prefix}{stock_code}", {})
                qfqday = stock_data.get('qfqday', [])

                if qfqday:
                    records = []
                    for kline in qfqday:
                        if len(kline) >= 6:
                            records.append({
                                'Date': pd.to_datetime(kline[0]),
                                'Open': float(kline[1]),
                                'Close': float(kline[2]),
                                'High': float(kline[3]),
                                'Low': float(kline[4]),
                                'Volume': float(kline[5])
                            })
                    df = pd.DataFrame(records)
                    df.set_index('Date', inplace=True)
                    return df

    except Exception as e:
        print(f"Tencent K-line API error: {e}")

    return pd.DataFrame()


def get_stock_info_tencent(stock_code):
    """通过腾讯API获取股票基本信息(市值、市盈率、市净率、换手率、成交额等)"""
    info = {}
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
        }

        # 判断市场前缀
        if stock_code.startswith('6'):
            prefix = 'sh'  # 上海
        else:
            prefix = 'sz'  # 深圳

        url = f"https://qt.gtimg.cn/q={prefix}{stock_code}"
        response = requests.get(url, headers=headers, timeout=10)

        text = response.text
        if '="' in text:
            data_str = text.split('="')[1].rstrip('";')
            fields = data_str.split('~')

            if len(fields) > 40:
                info['code'] = fields[2]
                info['name'] = fields[1]
                info['price'] = float(fields[3]) if fields[3] else 0
                info['yesterday_close'] = float(fields[4]) if fields[4] else 0
                info['open'] = float(fields[5]) if fields[5] else 0
                info['volume'] = int(fields[6]) if fields[6] else 0  # 成交量(手)
                info['amount'] = float(fields[37]) if fields[37] else 0  # 成交额(元)
                info['turnover_rate'] = float(fields[38]) if fields[38] else 0  # 换手率%
                info['pe_ratio'] = float(fields[39]) if fields[39] else 0  # 市盈率
                info['pb_ratio'] = float(fields[46]) if fields[46] else 0  # 市净率
                info['high'] = float(fields[33]) if fields[33] else 0  # 最高
                info['low'] = float(fields[34]) if fields[34] else 0  # 最低
                info['amplitude'] = float(fields[43]) if fields[43] else 0  # 振幅%
                info['float_market_cap'] = float(fields[44]) * 100000000 if fields[44] else 0  # 流通市值(元)
                info['float_market_cap_yi'] = float(fields[44]) if fields[44] else 0  # 流通市值(亿元)
                info['total_market_cap'] = float(fields[45]) * 100000000 if fields[45] else 0  # 总市值(元)
                info['total_market_cap_yi'] = float(fields[45]) if fields[45] else 0  # 总市值(亿元)

        return info

    except Exception as e:
        print(f"get_stock_info_tencent error: {e}")
        return {}


def get_stock_info_em(stock_code):
    """获取股票的基本信息(市值、市盈率、市净率、换手率、成交额等) - 东方财富API备用"""
    info = {}
    try:
        import warnings
        warnings.filterwarnings('ignore')

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'application/json',
        }

        if stock_code.startswith('6'):
            market = '1'
        elif stock_code.startswith('0') or stock_code.startswith('3'):
            market = '0'
        else:
            market = '0'

        # 使用push2delay API (更稳定)
        url = f"https://push2delay.eastmoney.com/api/qt/stock/get?secid={market}.{stock_code}&fields=f57,f58,f84,f85,f116,f117,f162,f167,f168,f169,f170,f171,f173,f177,f179,f180,f184,f185"

        response = requests.get(url, headers=headers, timeout=10, verify=False)
        data = response.json()

        if data.get('data'):
            sd = data['data']

            info['code'] = sd.get('f57', '')
            info['name'] = sd.get('f58', '')

            total_cap = sd.get('f116', 0)
            float_cap = sd.get('f117', 0)
            if total_cap:
                info['total_market_cap'] = total_cap
                info['total_market_cap_yi'] = round(total_cap / 100000000, 2)
            if float_cap:
                info['float_market_cap'] = float_cap
                info['float_market_cap_yi'] = round(float_cap / 100000000, 2)

            if sd.get('f162') is not None:
                info['pe_ratio'] = sd.get('f162')
            if sd.get('f167') is not None:
                info['pb_ratio'] = sd.get('f167')

            if sd.get('f171') is not None:
                info['turnover_rate'] = round(sd.get('f171') / 100, 2) if sd.get('f171') > 0 else sd.get('f171')

            if sd.get('f84') is not None:
                info['volume_amount'] = sd.get('f84')
                info['volume_amount_yi'] = round(sd.get('f84') / 100000000, 2)

            if sd.get('f173') is not None:
                info['volume_ratio'] = sd.get('f173')

            if sd.get('f179') is not None:
                info['total_shares'] = sd.get('f179')
            if sd.get('f180') is not None:
                info['float_shares'] = sd.get('f180')

    except Exception as e:
        print(f"get_stock_info_em error: {e}")

    return info
    """获取主力资金净流入排行前N只股票 - 东方财富数据"""
    try:
        # 东方财富主力资金流向排行API
        url = "http://push2.eastmoney.com/api/qt/clist/get"
        params = {
            'cb': 'jQuery',
            'pn': 1,
            'pz': limit,
            'po': 1,  # 降序排列
            'np': 1,
            'ut': 'bd1d9ddb04089700cf9c27f6f7426281',
            'fltt': 2,
            'invt': 2,
            'fid': 'f62',  # 主力净流入
            'fs': 'm:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23',
            'fields': 'f1,f2,f3,f4,f5,f6,f7,f12,f13,f14,f62,f184',
        }
        headers = {'User-Agent': 'Mozilla/5.0', 'Referer': 'http://quote.eastmoney.com/'}

        response = requests.get(url, params=params, headers=headers, timeout=15)
        text = response.text

        # 解析JSONP响应
        import re
        match = re.search(r'jQuery\((.*)\)', text)
        if match:
            data = json.loads(match.group(1))
        else:
            data = json.loads(text)

        stocks = []
        if data.get('data') and data['data'].get('diff'):
            for item in data['data']['diff']:
                stock = {
                    'code': str(item.get('f12', '')),
                    'name': item.get('f14', ''),
                    'price': item.get('f2', 0),
                    'change_pct': item.get('f3', 0),  # 涨跌幅 %
                    'main_force_inflow': item.get('f62', 0),  # 主力净流入(万元)
                    'turnover': item.get('f6', 0),  # 成交量(手)
                    'market_cap': item.get('f184', 0),  # 总市值(万元)
                }
                stocks.append(stock)

        return stocks
    except Exception as e:
        print(f"Main force stocks API error: {e}")
    return []


def filter_main_force_stocks(stocks, filters=None):
    """对主力资金股票进行初筛过滤"""
    if filters is None:
        filters = {}

    # 默认筛选条件
    min_market_cap = filters.get('min_market_cap', 500000)  # 默认50亿=500000万
    max_market_cap = filters.get('max_market_cap', 50000000)  # 默认5000亿=50000000万
    max_change_pct = filters.get('max_change_pct', 30)  # 默认涨跌幅<30%
    exclude_st = filters.get('exclude_st', True)  # 默认去除ST股票

    filtered = []
    for stock in stocks:
        # 去除ST股票
        if exclude_st and 'ST' in stock.get('name', '') or 'st' in stock.get('name', '').lower():
            continue

        # 去除数据不完整的股票
        if not stock.get('code') or not stock.get('name'):
            continue
        if stock.get('price', 0) <= 0:
            continue
        if stock.get('market_cap', 0) <= 0:
            continue

        # 市值范围筛选 (单位是万元，转亿要/10000)
        market_cap_wan = stock.get('market_cap', 0)
        if market_cap_wan < min_market_cap or market_cap_wan > max_market_cap:
            continue

        # 涨跌幅控制 (<30%避免追高)
        change_pct = stock.get('change_pct', 0)
        if change_pct > max_change_pct:
            continue

        filtered.append(stock)

    return filtered


def calculate_filter_score(stock, filters=None):
    """根据筛选条件计算股票评分"""
    if filters is None:
        filters = {}

    score = 0

    # 涨跌幅筛选 (优选涨幅适中或超跌反弹)
    change_pct = stock.get('change_pct', 0)
    max_change = filters.get('max_change', 30)
    min_change = filters.get('min_change', -999)

    if min_change <= change_pct <= max_change:
        score += 30

    # 主力净流入越大越好
    inflow = abs(stock.get('main_force_inflow', 0))
    if inflow > 10000:  # 超过1亿
        score += 40
    elif inflow > 5000:  # 超过5000万
        score += 30
    elif inflow > 1000:  # 超过1000万
        score += 20
    else:
        score += 10

    # 市值筛选 (优选中大型市值)
    cap = stock.get('market_cap', 0)
    min_cap = filters.get('min_market_cap', 500000)
    max_cap = filters.get('max_market_cap', 50000000)

    if min_cap <= cap <= max_cap:
        score += 30
    elif cap >= min_cap:
        score += 15

    return score


def calculate_indicators(df):
    """计算技术指标"""
    if df.empty:
        return {}

    close = df['Close']

    # 移动平均线
    ma5 = close.rolling(window=5).mean()
    ma10 = close.rolling(window=10).mean()
    ma20 = close.rolling(window=20).mean()

    # RSI
    delta = close.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))

    # MACD
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal

    # 布林带
    bb_middle = close.rolling(window=20).mean()
    bb_std = close.rolling(window=20).std()
    bb_upper = bb_middle + 2 * bb_std
    bb_lower = bb_middle - 2 * bb_std

    return {
        'ma5': ma5.iloc[-1] if not ma5.empty else None,
        'ma10': ma10.iloc[-1] if not ma10.empty else None,
        'ma20': ma20.iloc[-1] if not ma20.empty else None,
        'rsi': rsi.iloc[-1] if not rsi.empty else None,
        'macd': macd.iloc[-1] if not macd.empty else None,
        'signal': signal.iloc[-1] if not signal.empty else None,
        'histogram': histogram.iloc[-1] if not histogram.empty else None,
        'bb_upper': bb_upper.iloc[-1] if not bb_upper.empty else None,
        'bb_lower': bb_lower.iloc[-1] if not bb_lower.empty else None,
    }


def create_chart(df, stock_code, save_path='./output/charts'):
    """生成股票图表"""
    if df.empty:
        return None

    # 设置中文字体
    plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'DejaVu Sans']
    plt.rcParams['axes.unicode_minus'] = False

    fig, axes = plt.subplots(3, 1, figsize=(12, 10), dpi=80)

    # 价格图
    ax1 = axes[0]
    ax1.plot(df.index, df['Close'], label='Close', color='#2196F3', linewidth=1.5)

    # 移动平均线
    ma20 = df['Close'].rolling(window=20).mean()
    ma5 = df['Close'].rolling(window=5).mean()
    ax1.plot(df.index, ma20, label='MA20', color='#FF9800', linewidth=1, alpha=0.8)
    ax1.plot(df.index, ma5, label='MA5', color='#4CAF50', linewidth=1, alpha=0.8)

    # 布林带
    bb_middle = df['Close'].rolling(window=20).mean()
    bb_std = df['Close'].rolling(window=20).std()
    bb_upper = bb_middle + 2 * bb_std
    bb_lower = bb_middle - 2 * bb_std
    ax1.fill_between(df.index, bb_upper, bb_lower, alpha=0.1, color='gray')
    ax1.set_title(f'{stock_code} 价格走势', fontsize=14, fontweight='bold')
    ax1.legend(loc='upper left')
    ax1.grid(True, alpha=0.3)

    # 成交量
    ax2 = axes[1]
    colors = ['#26A69A' if df['Close'].iloc[i] >= df['Open'].iloc[i] else '#EF5350'
              for i in range(len(df))]
    ax2.bar(df.index, df['Volume'], color=colors, alpha=0.7)
    ax2.set_title('成交量', fontsize=12)
    ax2.grid(True, alpha=0.3)

    # MACD
    ax3 = axes[2]
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal

    ax3.plot(df.index, macd, label='MACD', color='#2196F3', linewidth=1)
    ax3.plot(df.index, signal, label='Signal', color='#FF9800', linewidth=1)
    colors = ['#26A69A' if h >= 0 else '#EF5350' for h in histogram]
    ax3.bar(df.index, histogram, color=colors, alpha=0.5)
    ax3.set_title('MACD', fontsize=12)
    ax3.legend(loc='upper left')
    ax3.grid(True, alpha=0.3)

    plt.tight_layout()

    # 保存图片
    chart_path = os.path.join(save_path, f'{stock_code}_chart.png')
    plt.savefig(chart_path, bbox_inches='tight', facecolor='white')
    plt.close()

    return chart_path


def analyze_with_deepseek(stock_code, stock_name, detected_market, df, indicators, stock_news=None, market_news=None, stock_info=None):
    """使用DeepSeek API分析股票"""
    if not API_KEY:
        return "API密钥未配置"

    if df.empty:
        return "无法获取股票数据"

    stock_news = stock_news or []
    market_news = market_news or []

    # 构建提示
    latest_price = df['Close'].iloc[-1]

    # 添加股票基本信息(市值、市盈率、市净率、换手率、成交额)
    stock_info_text = ""
    if stock_info:
        stock_info_text = """
【六、基本面数据】
- 总市值: {}亿元
- 流通市值: {}亿元
- 市盈率(动态): {}
- 市净率: {}
- 换手率: {}%
- 成交额: {}元
""".format(
            stock_info.get('total_market_cap_yi', 'N/A'),
            stock_info.get('float_market_cap_yi', 'N/A'),
            stock_info.get('pe_ratio', 'N/A'),
            stock_info.get('pb_ratio', 'N/A'),
            stock_info.get('turnover_rate', 'N/A'),
            stock_info.get('amount', 'N/A'),
        )

    # 计算更多指标
    def safe_fmt(val, fmt='.2f'):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return 'N/A'
        return f'{val:{fmt}}'

    # 涨跌数据
    price_change_1d = ((df['Close'].iloc[-1] - df['Close'].iloc[-2]) / df['Close'].iloc[-2] * 100) if len(df) > 1 else 0
    price_change_1w = ((df['Close'].iloc[-1] - df['Close'].iloc[-5]) / df['Close'].iloc[-5] * 100) if len(df) > 4 else 0
    price_change_1m = ((df['Close'].iloc[-1] - df['Close'].iloc[0]) / df['Close'].iloc[0] * 100) if len(df) > 1 else 0

    # 成交量分析
    avg_volume = df['Volume'].mean()
    today_volume = df['Volume'].iloc[-1]
    volume_ratio = today_volume / avg_volume if avg_volume > 0 else 0

    # 波动性
    volatility = df['Close'].std() / df['Close'].mean() * 100 if df['Close'].mean() > 0 else 0

    # 技术指标
    ma5 = safe_fmt(indicators.get('ma5'))
    ma10 = safe_fmt(indicators.get('ma10'))
    ma20 = safe_fmt(indicators.get('ma20'))
    rsi = indicators.get('rsi')
    rsi_val = safe_fmt(rsi)
    macd = indicators.get('macd')
    signal = indicators.get('signal')
    macd_hist = indicators.get('histogram')

    # 布林带位置
    bb_upper = indicators.get('bb_upper')
    bb_lower = indicators.get('bb_lower')
    bb_position = 'N/A'
    if bb_upper and bb_lower and latest_price:
        if latest_price > bb_upper:
            bb_position = '突破上轨(超买)'
        elif latest_price < bb_lower:
            bb_position = '跌破下轨(超卖)'
        else:
            bb_position = '轨道内'

    # 市场强弱判断
    market_strength = '中性'
    ma5_val = indicators.get('ma5')
    ma10_val = indicators.get('ma10')
    ma20_val = indicators.get('ma20')
    if ma5_val is not None and ma10_val is not None and ma20_val is not None and latest_price is not None:
        if latest_price > ma5_val > ma10_val > ma20_val:
            market_strength = '强势(上升趋势)'
        elif latest_price < ma5_val < ma10_val < ma20_val:
            market_strength = '弱势(下降趋势)'
        elif latest_price > ma5_val and latest_price > ma20_val:
            market_strength = '偏强'
        elif latest_price < ma5_val and latest_price < ma20_val:
            market_strength = '偏弱'

    # 资金流向判断（基于成交量和价格变化）
    capital_flow = '中性'
    if len(df) > 1:
        price_up = df['Close'].iloc[-1] > df['Close'].iloc[-2]
        volume_high = volume_ratio > 1.2
        if price_up and volume_high:
            capital_flow = '主力净流入(看好)'
        elif not price_up and volume_high:
            capital_flow = '主力净流出(看空)'
        elif price_up:
            capital_flow = '温和流入'
        else:
            capital_flow = '温和流出'

    # 风险等级
    risk_level = '中等'
    if rsi:
        if rsi > 80:
            risk_level = '极高(严重超买)'
        elif rsi > 70:
            risk_level = '较高(超买)'
        elif rsi < 20:
            risk_level = '极高(严重超卖)'
        elif rsi < 30:
            risk_level = '较低(超卖)'

    # 格式化新闻
    news_text = ""
    if stock_news:
        news_text += "【个股新闻公告】\n"
        for i, news in enumerate(stock_news[:5], 1):
            news_text += f"{i}. [{news.get('type', '公告')}] {news.get('date', '')} - {news.get('title', '')}\n"
    else:
        news_text += "【个股新闻公告】暂无最新公告\n"

    if market_news:
        news_text += "\n【市场最新快讯】\n"
        for i, news in enumerate(market_news[:5], 1):
            news_text += f"{i}. {news.get('date', '')} - {news.get('title', '')}\n"
    else:
        news_text += "\n【市场最新快讯】暂无最新快讯\n"

    prompt = f"""请对股票 {stock_name}({stock_code}) 进行全面分析评估：

【一、市场概况】
- 最新价: {latest_price:.2f}
- 日涨跌: {price_change_1d:.2f}%
- 周涨跌: {price_change_1w:.2f}%
- 月涨跌: {price_change_1m:.2f}%
- 市场趋势: {market_strength}

【二、技术分析】
- MA5: {ma5} | MA10: {ma10} | MA20: {ma20}
- RSI(14): {rsi_val} - {risk_level}
- MACD: {safe_fmt(macd, '.4f')} | Signal: {safe_fmt(signal, '.4f')}
- 布林带: {bb_position}

【三、资金动向】
- 成交量比: {volume_ratio:.2f}倍
- 资金流向: {capital_flow}
- 波动率: {volatility:.2f}%

【四、新闻面分析】
{news_text}

【五、风险评估】
- RSI风险: {rsi_val} ({risk_level})
- 波动风险: {'高' if volatility > 5 else '中' if volatility > 2 else '低'}
- 趋势风险: {market_strength}

【六、基本面数据】
{stock_info_text}

请按以下格式给出分析：

## 一、市场分析
（基于价格走势和成交量）

## 二、技术分析
（基于MA、RSI、MACD、布林带）

## 三、资金分析
（基于成交量和资金流向）

## 四、新闻面分析
（基于最新公告和市场快讯）

## 五、风险提示
（列出主要风险因素）

## 六、基本面参考
（注：基本面数据需自行核实，此处仅基于技术面推测）

## 七、决策建议
【综合评分】(1-10分，10分最佳)
【操作建议】买入/卖出/观望
【目标价位】参考支撑位和压力位
【止损位】建议止损价
【仓位建议】轻仓/半仓/重仓/清仓
【理由】简述决策依据

请保持专业、客观，用中文回复。"""

    try:
        response = requests.post(
            f"{BASE_URL}/chat/completions",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {API_KEY}"
            },
            json={
                "model": MODEL_NAME,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": 0.7,
                "max_tokens": 2000
            },
            timeout=30
        )

        result = response.json()
        if 'choices' in result and len(result['choices']) > 0:
            return result['choices'][0]['message']['content']
        elif 'error' in result:
            return f"API错误: {result['error'].get('message', '未知错误')}"
        else:
            return f"未知响应: {result}"
    except Exception as e:
        return f"请求失败: {str(e)}"


@app.route('/')
def index():
    """首页"""
    return render_template('index.html')


@app.route('/stock/')
def stock_index():
    """股票分析首页"""
    return render_template('index.html')


@app.route('/stock/analyze', methods=['POST'])
def analyze():
    """分析股票"""
    data = request.form
    stock_code = data.get('stock_code', '').strip()
    market = data.get('market', 'auto')  # auto, us, cn, hk

    if not stock_code:
        return jsonify({'error': '请输入股票代码'}), 400

    stock_name = stock_code  # 默认名称为代码
    detected_market = 'cn'  # 默认A股
    currency = '¥'  # 默认人民币

    # 根据市场选择数据源
    if market == 'us' or (market == 'auto' and not stock_code.isdigit()):
        df = get_stock_data_us(stock_code)
        if not df.empty:
            stock_name = stock_code.upper()
            detected_market = 'us'
            currency = '$'
    elif market == 'hk':
        df = get_stock_data_em_hk(stock_code)
        if not df.empty:
            stock_name = f"{stock_code}.HK"
            detected_market = 'hk'
            currency = 'HK$'
    else:
        # 尝试东方财富API (A股)
        df = get_stock_data_em(stock_code)
        if not df.empty:
            # 获取A股名称
            stock_name = get_stock_name_cn(stock_code) or stock_code
            detected_market = 'cn'
            currency = '¥'
        else:
            # 回退到港股API
            df = get_stock_data_em_hk(stock_code)
            if not df.empty:
                stock_name = f"{stock_code}.HK"
                detected_market = 'hk'
                currency = 'HK$'

    if df.empty:
        return jsonify({'error': f'无法获取股票 {stock_code} 的数据'}), 404

    # 计算指标
    indicators = calculate_indicators(df)

    # 生成图表
    chart_path = create_chart(df.tail(60), stock_code)  # 最近60天

    # 获取股票基本信息(市值、市盈率、市净率、换手率、成交额等)
    stock_info = get_stock_info_tencent(stock_code) if detected_market == 'cn' else {}

    # 获取新闻
    stock_news = get_stock_news_em(stock_code, detected_market)
    market_news = get_market_news() if detected_market == 'cn' else []

    # AI分析
    analysis = analyze_with_deepseek(stock_code, stock_name, detected_market, df, indicators, stock_news, market_news, stock_info)

    # 保存分析结果
    result_path = os.path.join('./output', f"{stock_code}_analysis.txt")
    with open(result_path, 'w', encoding='utf-8') as f:
        f.write(f"股票代码: {stock_code}\n")
        f.write(f"股票名称: {stock_name}\n")
        f.write(f"市场: {detected_market}\n")
        f.write(f"货币: {currency}\n")
        f.write(f"分析时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        f.write(f"最新价格: {df['Close'].iloc[-1]:.2f}\n")
        if stock_info:
            f.write("\n=== 基本信息 ===\n")
            f.write(f"总市值: {stock_info.get('total_market_cap_yi', 'N/A')}亿元\n")
            f.write(f"流通市值: {stock_info.get('float_market_cap_yi', 'N/A')}亿元\n")
            f.write(f"市盈率(动态): {stock_info.get('pe_ratio', 'N/A')}\n")
            f.write(f"市净率: {stock_info.get('pb_ratio', 'N/A')}\n")
            f.write(f"换手率: {stock_info.get('turnover_rate', 'N/A')}%\n")
            f.write(f"成交额: {stock_info.get('amount', 'N/A')}元\n")
        f.write("\n=== 技术指标 ===\n")
        for k, v in indicators.items():
            if v is not None and not pd.isna(v):
                f.write(f"{k}: {v:.4f}\n")
        f.write("\n=== AI分析 ===\n")
        f.write(analysis)

    # 市场中文映射
    market_names = {'cn': 'A股', 'hk': '港股', 'us': '美股'}
    market_cn = market_names.get(detected_market, detected_market)

    return jsonify({
        'success': True,
        'stock_code': stock_code,
        'stock_name': stock_name,
        'market': market_cn,
        'currency': currency,
        'latest_price': float(df['Close'].iloc[-1]),
        'stock_info': stock_info,
        'indicators': {k: float(v) if v is not None and not pd.isna(v) else None for k, v in indicators.items()},
        'chart': f'/output/charts/{stock_code}_chart.png',
        'chart_data': df.tail(60).to_dict('records'),
        'analysis': analysis
    })


def get_stock_name_em(market, code):
    """获取股票名称 - 使用东方财富搜索API"""
    try:
        # 东方财富搜索API
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {
            'input': code,
            'type': '14',
            'token': 'D43BF722C8E33BDC906FBFFDC85B389B',
            'count': '1'
        }
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()

        # 解析返回的JSON
        if data.get('QuotationCodeTable') and data['QuotationCodeTable'].get('Data'):
            stock_list = data['QuotationCodeTable']['Data']
            for stock in stock_list:
                if stock.get('Code') == code:
                    return stock.get('Name')

    except Exception as e:
        print(f"get_stock_name_em error: {e}")
    return None


def get_stock_name_cn(code):
    """获取A股股票名称"""
    # A股代码以6,0,3开头
    name = get_stock_name_em(None, code)
    return name


def get_stock_name_hk(code):
    """获取港股股票名称"""
    # 港股代码需要特殊处理，这里直接返回代码
    return f"{code}.HK"


def get_stock_name_us(code):
    """获取美股股票名称"""
    # 美股直接返回代码
    return code.upper()


def get_stock_news_em(code, market='cn'):
    """获取股票最新新闻和公告 - 东方财富API"""
    news_list = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://www.eastmoney.com'
        }

        if market == 'us':
            # 美股使用不同的API
            url = f"https://datacenter-web.eastmoney.com/api/data/v1/get?reportName=RPT_NEWS_QUOTE&columns=ALL&filter=(SECUCODE%3D%22{code}.US%22)&pageNumber=1&pageSize=5&source=WEB&client=web"
        else:
            # A股/港股使用公告API
            # 判断市场
            if code.startswith('6'):
                market_code = 'SHA'
            else:
                market_code = 'SZA'

            url = f"https://np-anotice-stock.eastmoney.com/api/security/ann?sr=-1&page_size=8&page_index=1&ann_type={market_code}&client_source=web&stock_list={code}"

        response = requests.get(url, headers=headers, timeout=10)
        data = response.json()

        if data.get('data') and data['data'].get('list'):
            for item in data['data']['list'][:8]:
                title = item.get('title_ch', '') or item.get('title', '')
                notice_date = item.get('notice_date', '') or item.get('display_time', '')[:10]
                column_name = ''
                if item.get('columns') and len(item['columns']) > 0:
                    column_name = item['columns'][0].get('column_name', '')
                if title:
                    news_list.append({
                        'title': title,
                        'date': notice_date[:10] if notice_date else '',
                        'type': column_name or '公告'
                    })

    except Exception as e:
        print(f"get_stock_news_em error: {e}")

    return news_list


def get_market_news():
    """获取市场最新快讯"""
    news_list = []
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0',
            'Referer': 'https://www.eastmoney.com'
        }
        # 东方财富快讯API
        url = "https://newsapi.eastmoney.com/kuaixun/v1/getlist_102_ajaxResult_20_1_.html"
        response = requests.get(url, headers=headers, timeout=10)

        # 解析返回的JSONP
        text = response.text
        if 'ajaxResult=' in text:
            json_str = text.replace('ajaxResult=', '')
            data = json.loads(json_str)
            if data.get('LivesList'):
                for item in data['LivesList'][:10]:
                    news_list.append({
                        'title': item.get('title', ''),
                        'date': item.get('showtime', ''),
                        'type': '快讯'
                    })
    except Exception as e:
        print(f"get_market_news error: {e}")

    return news_list


@app.route('/stock/search', methods=['GET'])
def search_stocks():
    """搜索股票 by name or code"""
    keyword = request.args.get('keyword', '').strip()
    if not keyword:
        return jsonify({'error': '请输入搜索关键词'}), 400

    results = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        # 东方财富搜索API - 支持A股、港股、美股
        url = "https://searchapi.eastmoney.com/api/suggest/get"
        params = {
            'input': keyword,
            'type': '14',
            'token': 'D43BF722C8E33BDC906FBFFDC85B389B',
            'count': '10'
        }
        response = requests.get(url, params=params, headers=headers, timeout=5)
        data = response.json()

        if data.get('QuotationCodeTable') and data['QuotationCodeTable'].get('Data'):
            for stock in data['QuotationCodeTable']['Data']:
                code = stock.get('Code', '')
                name = stock.get('Name', '')
                market = stock.get('MktNum', '')  # 1=上证, 0=深证, 116=港股
                stock_type = stock.get('SecurityTypeName', '')

                # 判断市场
                if market == '116':
                    market_cn = '港股'
                    display_code = f"{code}.HK"
                elif code.startswith('6') or market == '1':
                    market_cn = 'A股'
                    display_code = code
                elif code.startswith(('0', '3')) or market == '0':
                    market_cn = 'A股'
                    display_code = code
                else:
                    market_cn = '美股'
                    display_code = code

                results.append({
                    'code': code,
                    'name': name,
                    'market': market_cn,
                    'display_code': display_code,
                    'type': stock_type
                })
    except Exception as e:
        print(f"Search error: {e}")

    return jsonify({'results': results})


@app.route('/stock/analyze_batch', methods=['POST'])
def analyze_batch():
    """批量分析多只股票"""
    data = request.form
    stock_input = data.get('stocks', '').strip()  # 逗号分隔: 600519,000001,AAPL

    if not stock_input:
        return jsonify({'error': '请输入股票代码'}), 400

    # 解析股票列表
    stock_list = [s.strip() for s in stock_input.split(',') if s.strip()]
    if len(stock_list) > 10:
        return jsonify({'error': '最多支持10只股票同时分析'}), 400

    results = []
    for stock_code in stock_list:
        try:
            stock_code = stock_code.strip()
            if not stock_code:
                continue

            # 自动识别市场
            detected_market = 'cn'
            currency = '¥'

            if stock_code.isdigit():
                if stock_code.startswith('6'):
                    detected_market = 'cn'
                    currency = '¥'
                elif stock_code.startswith(('0', '3')):
                    detected_market = 'cn'
                    currency = '¥'
                else:
                    detected_market = 'hk'
                    currency = 'HK$'
            else:
                # 可能是美股代码
                detected_market = 'us'
                currency = '$'

            # 获取数据
            if detected_market == 'us':
                df = get_stock_data_us(stock_code)
            elif detected_market == 'hk':
                df = get_stock_data_em_hk(stock_code)
            else:
                df = get_stock_data_em(stock_code)
                if df.empty:
                    # 回退到港股
                    df = get_stock_data_em_hk(stock_code)
                    if not df.empty:
                        detected_market = 'hk'
                        currency = 'HK$'

            if df.empty:
                results.append({
                    'stock_code': stock_code,
                    'error': f'无法获取股票 {stock_code} 的数据'
                })
                continue

            # 获取股票名称
            stock_name = get_stock_name_cn(stock_code) if detected_market == 'cn' else stock_code
            if detected_market == 'hk':
                stock_name = f"{stock_code}.HK"
            elif detected_market == 'us':
                stock_name = stock_code.upper()

            # 计算指标
            indicators = calculate_indicators(df)

            # 生成图表
            chart_path = create_chart(df.tail(60), f"{stock_code}_{detected_market}")

            # 获取新闻
            stock_news = get_stock_news_em(stock_code, detected_market)
            market_news = get_market_news() if detected_market == 'cn' else []

            # AI分析
            analysis = analyze_with_deepseek(stock_code, stock_name, detected_market, df, indicators, stock_news, market_news)

            # 市场中文映射
            market_names = {'cn': 'A股', 'hk': '港股', 'us': '美股'}
            market_cn = market_names.get(detected_market, detected_market)

            results.append({
                'stock_code': stock_code,
                'stock_name': stock_name,
                'market': market_cn,
                'currency': currency,
                'latest_price': float(df['Close'].iloc[-1]),
                'indicators': {k: float(v) if v is not None and not pd.isna(v) else None for k, v in indicators.items()},
                'chart': f'/output/charts/{stock_code}_{detected_market}_chart.png',
                'chart_data': df.tail(60).to_dict('records'),
                'analysis': analysis
            })
        except Exception as e:
            results.append({
                'stock_code': stock_code,
                'error': str(e)
            })

    return jsonify({
        'success': True,
        'count': len(results),
        'results': results
    })


@app.route('/stock/main_force_data', methods=['GET'])
def main_force_data():
    """获取主力资金流向排行数据"""
    limit = request.args.get('limit', 100, type=int)
    limit = min(limit, 200)  # 最多200条

    stocks = get_main_force_top_stocks(limit)

    if not stocks:
        return jsonify({'error': '无法获取主力资金数据'}), 500

    return jsonify({
        'success': True,
        'count': len(stocks),
        'stocks': stocks
    })


@app.route('/stock/main_force_pick', methods=['POST'])
def main_force_pick():
    """智能选股 - 基于主力资金精选3-5只优质标的"""
    data = request.form

    # 获取筛选参数
    min_change = data.get('min_change', type=float)
    max_change = data.get('max_change', type=float)
    min_market_cap_yi = data.get('min_market_cap', type=float)  # 亿元
    max_market_cap_yi = data.get('max_market_cap', type=float)  # 亿元

    # 默认筛选条件：市值50-5000亿，涨跌幅<30%，去除ST
    if min_market_cap_yi is None:
        min_market_cap_yi = 50
    if max_market_cap_yi is None:
        max_market_cap_yi = 5000

    max_change_pct = max_change if max_change else 30

    # 筛选参数（转换为万元单位）
    filters = {
        'min_change': min_change if min_change else -999,
        'max_change': max_change_pct,
        'min_market_cap': min_market_cap_yi * 10000,  # 亿元转万元
        'max_market_cap': max_market_cap_yi * 10000,
        'top_n': data.get('top_n', 50, type=int),
        'pick_count': data.get('pick_count', 5, type=int),
        'exclude_st': True
    }

    # 获取主力资金排行
    top_stocks = get_main_force_top_stocks(200)
    if not top_stocks:
        return jsonify({'error': '无法获取主力资金数据'}), 500

    # 初筛过滤
    filtered_stocks = filter_main_force_stocks(top_stocks, filters)

    # 如果过滤后股票太少，尝试放宽条件
    if len(filtered_stocks) < 10:
        filters_no_cap = filters.copy()
        filters_no_cap['min_market_cap'] = 0
        filters_no_cap['max_market_cap'] = 999999999
        filtered_stocks = filter_main_force_stocks(top_stocks, filters_no_cap)

    if len(filtered_stocks) < 5:
        return jsonify({'error': '符合筛选条件的股票数量不足，请调整筛选条件'}), 400

    # 计算评分并排序
    for stock in filtered_stocks:
        stock['filter_score'] = calculate_filter_score(stock, filters)

    # 按评分排序，取前N
    sorted_stocks = sorted(filtered_stocks, key=lambda x: x['filter_score'], reverse=True)
    selected = sorted_stocks[:filters['top_n']]

    # 调用AI进行精选
    try:
        selected_codes = [s['code'] for s in selected]
        analysis_prompt = f"""你是一位资深股票分析师。请从以下主力资金净流入排名靠前的股票中，精选{filters['pick_count']}只最值得关注的标的。

股票列表（按主力净流入排序）:
"""
        for i, s in enumerate(selected[:20], 1):
            analysis_prompt += f"{i}. {s['name']}({s['code']}) - 现价:{s['price']}元 涨跌幅:{s['change_pct']}% 主力净流入:{s['main_force_inflow']:.2f}万元\n"

        analysis_prompt += f"""
请从以下维度进行筛选：
1. 涨跌幅适中（最好在-3%到+5%之间，超跌或温和上涨更佳）
2. 主力净流入金额较大
3. 个股基本面良好
4. 行业分布合理（避免集中单一行业）

请直接给出你精选的3-5只股票代码和简要理由，格式如下：
【精选标的】
1. 股票代码:XXXX - 理由:...
2. ...

请只输出精选结果，不要其他内容。"""

        # 调用DeepSeek API
        headers = {
            'Authorization': f'Bearer {API_KEY}',
            'Content-Type': 'application/json'
        }
        payload = {
            'model': MODEL_NAME,
            'messages': [
                {'role': 'user', 'content': analysis_prompt}
            ],
            'temperature': 0.3,
            'max_tokens': 500
        }

        response = requests.post(f'{BASE_URL}/chat/completions', headers=headers, json=payload, timeout=30)
        result = response.json()

        ai_selection = ''
        if 'choices' in result and result['choices']:
            ai_selection = result['choices'][0]['message']['content']

        # 解析AI精选结果
        picked_codes = []
        for line in ai_selection.split('\n'):
            if '股票代码' in line or '代码' in line:
                import re
                codes = re.findall(r'\d{6}', line)
                picked_codes.extend(codes)

        # 去重并限制数量
        picked_codes = list(dict.fromkeys(picked_codes))[:filters['pick_count']]

        # 获取精选股票的详细信息
        picked_stocks = []
        for code in picked_codes:
            stock_info = next((s for s in filtered_stocks if s['code'] == code), None)
            if stock_info:
                picked_stocks.append(stock_info)

        # 如果AI精选不够，补充评分最高的
        if len(picked_stocks) < filters['pick_count']:
            for s in sorted_stocks:
                if s['code'] not in picked_codes:
                    picked_stocks.append(s)
                    if len(picked_stocks) >= filters['pick_count']:
                        break

        return jsonify({
            'success': True,
            'ai_selection': ai_selection,
            'picked_stocks': picked_stocks,
            'total_analyzed': len(selected)
        })

    except Exception as e:
        return jsonify({'error': f'AI精选失败: {str(e)}'}), 500


@app.route('/stock/main_force_batch', methods=['POST'])
def main_force_batch():
    """批量分析主力资金净流入TOP N只股票"""
    data = request.form
    top_n = data.get('top_n', 10, type=int)  # 默认分析前10
    top_n = min(max(top_n, 1), 50)  # 限制1-50

    # 获取筛选参数
    min_market_cap_yi = data.get('min_market_cap', type=float)
    max_market_cap_yi = data.get('max_market_cap', type=float)
    max_change_pct = data.get('max_change_pct', type=float)

    # 默认筛选条件
    if min_market_cap_yi is None:
        min_market_cap_yi = 50
    if max_market_cap_yi is None:
        max_market_cap_yi = 5000
    if max_change_pct is None:
        max_change_pct = 30

    filters = {
        'min_market_cap': min_market_cap_yi * 10000,
        'max_market_cap': max_market_cap_yi * 10000,
        'max_change_pct': max_change_pct,
        'exclude_st': True
    }

    # 获取主力资金排行
    top_stocks = get_main_force_top_stocks(100)
    if not top_stocks:
        return jsonify({'error': '无法获取主力资金数据'}), 500

    # 初筛过滤
    filtered_stocks = filter_main_force_stocks(top_stocks, filters)

    # 取前N只（优先选择主力净流入最大的）
    selected = filtered_stocks[:top_n]

    # 如果过滤后不足，回退到原始排序
    if len(selected) < 5:
        selected = top_stocks[:top_n]

    stock_codes = [s['code'] for s in selected]

    # 构建结果
    results = []
    for stock_code in stock_codes:
        try:
            # 自动识别市场
            if stock_code.startswith('6'):
                detected_market = 'cn'
                currency = '¥'
            elif stock_code.startswith('5'):
                detected_market = 'hk'
                currency = 'HK$'
            else:
                detected_market = 'cn'
                currency = '¥'

            # 获取数据
            df = get_stock_data_em(stock_code)
            if df.empty:
                results.append({
                    'stock_code': stock_code,
                    'error': f'无法获取股票 {stock_code} 的数据'
                })
                continue

            # 获取股票名称
            stock_name = get_stock_name_cn(stock_code) or stock_code

            # 计算指标
            indicators = calculate_indicators(df)

            # 生成图表
            chart_path = create_chart(df.tail(60), f"{stock_code}_batch")

            # 获取新闻
            stock_news = get_stock_news_em(stock_code, detected_market)
            market_news = get_market_news() if detected_market == 'cn' else []

            # AI分析
            analysis = analyze_with_deepseek(stock_code, stock_name, detected_market, df, indicators, stock_news, market_news)

            # 获取主力资金数据
            stock_main_force = next((s for s in top_stocks if s['code'] == stock_code), {})

            results.append({
                'stock_code': stock_code,
                'stock_name': stock_name,
                'market': 'A股',
                'currency': currency,
                'latest_price': float(stock_main_force.get('price', df['Close'].iloc[-1])),
                'change_pct': stock_main_force.get('change_pct', 0),
                'main_force_inflow': stock_main_force.get('main_force_inflow', 0),
                'indicators': {k: float(v) if v is not None and not pd.isna(v) else None for k, v in indicators.items()},
                'chart': f'/output/charts/{stock_code}_batch_chart.png',
                'chart_data': df.tail(60).to_dict('records'),
                'analysis': analysis
            })
        except Exception as e:
            results.append({
                'stock_code': stock_code,
                'error': str(e)
            })

    return jsonify({
        'success': True,
        'count': len(results),
        'results': results
    })


@app.route('/output/charts/<path:filename>')
def serve_chart(filename):
    """提供图表文件"""
    return send_from_directory('./output/charts', filename)


if __name__ == '__main__':
    print("启动股票分析服务...")
    print(f"API: {BASE_URL}")
    print(f"Model: {MODEL_NAME}")
    app.run(host='0.0.0.0', port=5000, debug=False)
