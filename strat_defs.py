import pandas as pd
import numpy as np

def calculate_rsi(data, window):
    """
    Calculate the Relative Strength Index (RSI).
    
    Parameters:
        data (DataFrame): Stock data with 'Close' prices.
        window (int): Lookback period for RSI.
        
    Returns:
        Series: RSI values.
    """
    delta = data['Close'].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    
    avg_gain = pd.Series(gain).rolling(window=window).mean()
    avg_loss = pd.Series(loss).rolling(window=window).mean()
    
    rs = avg_gain / avg_loss
    
    return 100 - (100 / (1 + rs))

def calculate_vwap(data):
    cumulative_volume = data['Volume'].cumsum()
    cumulative_price_volume = (data['Close'] * data['Volume']).cumsum()
    return cumulative_price_volume / cumulative_volume

def backtest_strategy(data, initial_capital, strategy, **kwargs):
    """
    Backtest various trading strategies.

    Parameters:
        data (DataFrame): Stock data with required columns.
        strategy (str): The strategy name ('RSI', 'VWAP', 'Bollinger', etc.).
        initial_capital (float): initial investment / starting capital
        **kwargs: Additional parameters for strategy customization.

    Returns:
        DataFrame: Data with strategy signals and portfolio value.
        float: Total profit/loss.
    """
    data = data.copy()  # Prevent modifying the original DataFrame

    # Calculate indicators based on the strategy
    if strategy == "Hold":
        # Calculate daily returns
        data['Daily_Return'] = data['Close'].pct_change()
        
        # Calculate portfolio value
        data['Portfolio_Value'] = (1 + data['Daily_Return']).cumprod() * initial_capital
        return data

    elif strategy == "SMA":   
        short_window = kwargs.get('short_window')
        long_window = kwargs.get('long_window')
     
        data = data.set_index('Date')
    
        # Calculate moving averages
        data['SMA_Short'] = data['Close'].rolling(window=short_window).mean()
        data['SMA_Long'] = data['Close'].rolling(window=long_window).mean()
        
        # Generate signals: 1 = Buy, -1 = Sell, 0 = Hold
        data['Signal'] = 0
        data.loc[data['SMA_Long'] > data['SMA_Long'], 'Signal'] = 1
        data.loc[data['SMA_Short'] <= data['SMA_Long'], 'Signal'] = -1
        
        # Calculate daily returns
        data['Daily_Return'] = data['Close'].pct_change()
        
        # Calculate portfolio value
        data['pv_hold'] = (1 + data['Daily_Return']).cumprod() * initial_capital
        
        pv_strat_sma = [initial_capital]
        prev = initial_capital
        for i in range(1,data.shape[0]):
            if data['Signal'][i] == -1:
                val=prev
                pv_strat_sma.append(val)
            else:
                val = prev * (1+data['Daily_Return'][i])
                pv_strat_sma.append(val)
                prev=val
        
        data['Portfolio_Value'] = pv_strat_sma
        data = data.reset_index()
        return data
    
    elif strategy == 'RSI':
        rsi_window = kwargs.get('rsi_window')
        oversold = kwargs.get('oversold')
        overbought = kwargs.get('overbought')
        data['RSI'] = calculate_rsi(data, rsi_window)
        data['Signal'] = 0
        data.loc[data['RSI'] < kwargs.get('oversold', oversold), 'Signal'] = 1
        data.loc[data['RSI'] > kwargs.get('overbought', overbought), 'Signal'] = -1

    elif strategy == 'VWAP':
        data['VWAP'] = calculate_vwap(data)
        data['Signal'] = 0
        data.loc[data['Close'] < data['VWAP'], 'Signal'] = 1  # Buy below VWAP
        data.loc[data['Close'] > data['VWAP'], 'Signal'] = -1  # Sell above VWAP

    elif strategy == 'Bollinger':
        window = kwargs.get('bollinger_window', 20)
        num_std = kwargs.get('num_std', 2)
        data['Moving_Avg'] = data['Close'].rolling(window=window).mean()
        data['Std_Dev'] = data['Close'].rolling(window=window).std()
        data['Upper_Band'] = data['Moving_Avg'] + (data['Std_Dev'] * num_std)
        data['Lower_Band'] = data['Moving_Avg'] - (data['Std_Dev'] * num_std)
        data['Signal'] = 0
        data.loc[data['Close'] < data['Lower_Band'], 'Signal'] = 1  # Buy
        data.loc[data['Close'] > data['Upper_Band'], 'Signal'] = -1  # Sell

    elif strategy == 'Breakout':
        breakout_window = kwargs.get('breakout_window')
        data['High_Max'] = data['High'].rolling(window=breakout_window).max().shift(1)
        data['Low_Min'] = data['Low'].rolling(window=breakout_window).min().shift(1)
        data['Signal'] = 0
        data.loc[data['Close'] > data['High_Max'], 'Signal'] = 1  # Breakout above
        data.loc[data['Close'] < data['Low_Min'], 'Signal'] = -1  # Breakout below

    elif strategy == 'Perfection':
        data['Signal'] = 0
        data.loc[data['spy_next_day_change_type']=="increase", 'Signal'] = 1 
        # data.loc[data['spy_next_day_change_type']=="decrease", 'Signal'] = -1  
    # More strategies can be added similarly...

    else:
        raise ValueError(f"Strategy '{strategy}' is not implemented.")

    # Backtest logic: Calculate portfolio value
    signal_adj = []
    prev = 1
    for i in data['Signal']:
        if i==1:
            signal_adj.append(1)
            prev=1
        elif i==-1:
            signal_adj.append(0)
            prev=0
        else:
            signal_adj.append(prev)
            
    data['signal_adj'] = signal_adj

    data['Daily_Return'] = data['Close'].pct_change()
    data['Strategy_Return'] = data['signal_adj'].shift(1) * data['Daily_Return']
    data['Portfolio_Value'] = (1 + data['Strategy_Return']).cumprod() * initial_capital

    return data

# ML defs
def calculate_technical_indicators(data):
    """
    Calculate technical indicators for the dataset.
    """
    data['RSI'] = calculate_rsi(data, window=14)
    data['MA20'] = data['Close'].rolling(window=20).mean()
    data['MA50'] = data['Close'].rolling(window=50).mean()
    data['Bollinger_Upper'] = data['MA20'] + 2 * data['Close'].rolling(window=20).std()
    data['Bollinger_Lower'] = data['MA20'] - 2 * data['Close'].rolling(window=20).std()
    data['VWAP'] = calculate_vwap(data)
    return data

def preprocess_data(data):
    """
    Prepare data for machine learning.
    """
    # Add technical indicators
    data = calculate_technical_indicators(data)
    
    # Define target variable: price direction (1 = up, -1 = down, 0 = stable)
    data['Target'] = np.sign(data['Close'].shift(-1) - data['Close'])
    
    # Drop rows with missing values due to rolling calculations
    data = data.dropna()
    
    # Define features and target
    X = data[['RSI', 'MA20', 'MA50', 'Bollinger_Upper', 'Bollinger_Lower', 'VWAP']]
    y = data['Target']
    
    return X, y