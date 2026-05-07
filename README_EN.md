# AI-Kline - Stock Technical Analysis and AI Prediction Tool

<div align="center">
  <a href="README_EN.md">English</a> | <a href="README.md">中文</a>
</div>

## Overview

AI-Kline is a Python-based A-share stock analysis tool that combines traditional technical analysis with artificial intelligence prediction. It provides comprehensive stock analysis and forecasting using candlestick charts, technical indicators, financial data, and news information.

### Features

- **Data Acquisition**: Real-time quotes, historical trading data, financial data and news via AkShare and Tencent APIs
- **Technical Analysis**: Multiple technical indicators including MA, MACD, KDJ, RSI, Bollinger Bands
- **Visualization**: Candlestick charts and technical indicator visualizations
- **AI Analysis**: DeepSeek AI analyzes stock data and predicts future trends and probability of rise
- **Web Interface**: Clean and intuitive web interface for stock code input and analysis results

### Advantages

- **Extremely Low Hardware Requirements**: Runs smoothly on just 1 CPU core and 512MB RAM, perfect for personal servers or low-spec cloud instances
- **Minimal Token Consumption**: Each analysis consumes only a few thousand tokens, extremely low cost (<$0.001 per analysis)
- **Simple Deployment**: No GPU or Docker required, one-click startup

## Tech Stack

- **Backend**: Flask Web Framework
- **Data Sources**: AkShare, Tencent Quote API
- **AI Analysis**: DeepSeek API (grok-2-vision)
- **Visualization**: Matplotlib, ECharts

## Project Structure

```
STOCK_AI/
├── stock_app.py              # Flask main application
├── requirements.txt          # Dependencies
├── .env.example              # Environment template
├── modules/
│   ├── data_fetcher.py       # Data fetching module
│   ├── technical_analyzer.py # Technical analysis module
│   ├── visualizer.py         # Visualization module
│   └── ai_analyzer.py        # AI analysis module
├── templates/
│   └── index.html            # Frontend page
└── static/                   # Static resources
```

## Deployment Guide

### Requirements

- Python 3.8+
- Linux server (CentOS/Ubuntu)
- **Hardware**: 1 CPU core, 512MB RAM

### Installation Steps

1. **Clone the repository**
```bash
git clone https://github.com/guchao1990/stock-ai.git
cd stock-ai
```

2. **Install dependencies**
```bash
pip install -r requirements.txt
```

3. **Configure environment variables**
```bash
cp .env.example .env
# Edit .env and add your API key
vi .env
```

`.env` file content:
```
# DeepSeek API Configuration
API_KEY=your_api_key_here
BASE_URL=https://api.deepseek.com/v1
MODEL_NAME=deepseek-chat
```

4. **Start the service**
```bash
# Direct run
python stock_app.py

# Or run with supervisor (background)
supervisord -c supervisor.conf
```

5. **Access the application**

Navigate to `http://your-server-ip:5000`

### Nginx Reverse Proxy (Optional)

```nginx
server {
    listen 80;
    server_name your_domain.com;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

## Usage

1. Enter a stock code (e.g., `000001` for Ping An Bank)
2. Select analysis period (1 year / 6 months / 3 months / 1 month)
3. Click "Start Analysis"
4. View results:
   - Stock basic info (market cap, PE ratio, PB ratio, turnover rate)
   - Candlestick and technical charts
   - AI analysis results and probability of rise prediction

## Screenshots

![Image #1](https://minimax-algeng-chat-tts.oss-cn-wulanchabu.aliyuncs.com/ccv2%2F2026-05-07%2FMiniMax-M2.7%2F2031917385446859654%2F425feeec7fb0156d1cc549cd0071c66a929708dccb9f839f8ea0d6cd0ffd653d..jpeg?Expires=1778229251&OSSAccessKeyId=LTAI5tGLnRTkBjLuYPjNcKQ8&Signature=hJU60BikdUAoIGzaChWuTiKSG7k%3D)

![Image #2](https://minimax-algeng-chat-tts.oss-cn-wulanchabu.aliyuncs.com/ccv2%2F2026-05-07%2FMiniMax-M2.7%2F2031917385446859654%2F6e4aba51c2d064fec227dbdbb9f3eef35f8f1d3227bf227499d224ffd15ab285..jpeg?Expires=1778229251&OSSAccessKeyId=LTAI5tGLnRTkBjLuYPjNcKQ8&Signature=POX0xwEgcR5vj2hB3y1MH29Wpj4%3D)

![Image #3](https://minimax-algeng-chat-tts.oss-cn-wulanchabu.aliyuncs.com/ccv2%2F2026-05-07%2FMiniMax-M2.7%2F2031917385446859654%2F13265322478e2c04f5762606e8e45aba5cc4610731d3bbf1cd7d51f6591e1a37..jpeg?Expires=1778229252&OSSAccessKeyId=LTAI5tGLnRTkBjLuYPjNcKQ8&Signature=Z%2BkYRaJFY0P%2BIOdXLjxTNExibkI%3D)

## Disclaimer

- This tool is for educational and research purposes only, not investment advice
- AI analysis results are based on historical data and cannot guarantee accuracy of future trends
- Invest at your own risk

## License

MIT License
