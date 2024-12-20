import pandas as pd
import numpy as np
from prophet import Prophet
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
# from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
# from sklearn.model_selection import train_test_split
from sklearn.preprocessing import LabelEncoder, StandardScaler
from xgboost import XGBClassifier


def calculate_rsiW(data, ticker, target, window):
    """
    Calculate the Relative Strength Index (RSI).
    
    Parameters:
        data (DataFrame): Stock data with target prices.
        window (int): Lookback period for RSI.
        
    Returns:
        Series: RSI values.
    """
    delta = data[target+"_"+ticker].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    
    avg_gain = pd.Series(gain).rolling(window=window).mean()
    avg_loss = pd.Series(loss).rolling(window=window).mean()
    
    rs = avg_gain / avg_loss
    
    return 100 - (100 / (1 + rs))

def calculate_rsiL(data, target, window):
    """
    Calculate the Relative Strength Index (RSI).
    
    Parameters:
        data (DataFrame): Stock data with target prices.
        window (int): Lookback period for RSI.
        
    Returns:
        Series: RSI values.
    """
    delta = data[target].diff()
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    
    avg_gain = pd.Series(gain).rolling(window=window).mean()
    avg_loss = pd.Series(loss).rolling(window=window).mean()
    
    rs = avg_gain / avg_loss
    
    return 100 - (100 / (1 + rs))

def calculate_vwapW(data, ticker, target):
    cumulative_volume = data["Volume_"+ticker].cumsum()
    cumulative_price_volume = (data[target+"_"+ticker] * data["Volume_"+ticker]).cumsum()
    return cumulative_price_volume / cumulative_volume

def calculate_vwapL(data, target):
    cumulative_volume = data['Volume'].cumsum()
    cumulative_price_volume = (data[target] * data['Volume']).cumsum()
    return cumulative_price_volume / cumulative_volume

def calculate_technical_indicators(data, ticker, target):
    """
    Calculate technical indicators for the dataset.
    """
    data['RSI'] = calculate_rsiW(data, ticker, target, window=14)
    data['MA20'] = data[target+"_"+ticker].rolling(window=20).mean()
    data['MA50'] = data[target+"_"+ticker].rolling(window=50).mean()
    data['Bollinger_Upper'] = data['MA20'] + 2 * data[target+"_"+ticker].rolling(window=20).std()
    data['Bollinger_Lower'] = data['MA20'] - 2 * data[target+"_"+ticker].rolling(window=20).std()
    data['VWAP'] = calculate_vwapW(data, ticker, target)
    return data


def backtest_strategy(data, ticker, initial_capital, strategy, target, **kwargs):
    """
    Backtest various trading strategies.

    Parameters:
        data (DataFrame): Stock data with required columns.
        ticker: Stock ticker
        initial_capital (float): initial investment / starting capital
        strategy (str): The strategy name ('RSI', 'VWAP', 'Bollinger', etc.).
        target (str): column to predict (usually Adj Close)
        **kwargs: Additional parameters for strategy customization.

    Returns:
        DataFrame: Data with strategy signals and portfolio value.
        model: forcasting model, if available
    """
    data_raw = data.copy()
    data = data.copy()  # Prevent modifying the original DataFrame

    og_min_date = min(data_raw['Date'])

    model = None

    # Calculate indicators based on the strategy
    if strategy == "Hold":
        data['Signal'] = 1

    elif strategy == "SMA":   
        short_window = kwargs.get('short_window')
        long_window = kwargs.get('long_window')
    
        # Calculate moving averages
        data['SMA_Short'] = data[target+"_"+ticker].rolling(window=short_window).mean()
        data['SMA_Long'] = data[target+"_"+ticker].rolling(window=long_window).mean()
        
        # Generate signals: 1 = Buy, -1 = Sell, 0 = Hold
        data['Signal'] = 0
        data.loc[data['SMA_Short'] > data['SMA_Long'], 'Signal'] = 1
        data.loc[data['SMA_Short'] <= data['SMA_Long'], 'Signal'] = -1

    elif strategy == 'RSI':
        rsi_window = kwargs.get('rsi_window')
        oversold = kwargs.get('oversold')
        overbought = kwargs.get('overbought')
        data['RSI'] = calculate_rsiW(data, ticker, target, rsi_window)
        data['Signal'] = 0
        # data.loc[data['RSI'] < kwargs.get('oversold', oversold), 'Signal'] = 1 # are these right? fix below
        # data.loc[data['RSI'] > kwargs.get('overbought', overbought), 'Signal'] = -1
        data.loc[data['RSI'] < oversold, 'Signal'] = 1
        data.loc[data['RSI'] > overbought, 'Signal'] = -1

    elif strategy == 'VWAP':
        data['VWAP'] = calculate_vwapW(data, ticker, target)
        data['Signal'] = 0
        data.loc[data[target+"_"+ticker] < data['VWAP'], 'Signal'] = 1  # Buy below VWAP
        data.loc[data[target+"_"+ticker] > data['VWAP'], 'Signal'] = -1  # Sell above VWAP

    elif strategy == 'Bollinger':
        window = kwargs.get('bollinger_window', 20)
        num_std = kwargs.get('num_std', 2)
        data['Moving_Avg'] = data[target+"_"+ticker].rolling(window=window).mean()
        data['Std_Dev'] = data[target+"_"+ticker].rolling(window=window).std()
        data['Upper_Band'] = data['Moving_Avg'] + (data['Std_Dev'] * num_std)
        data['Lower_Band'] = data['Moving_Avg'] - (data['Std_Dev'] * num_std)
        data['Signal'] = 0
        data.loc[data[target+"_"+ticker] < data['Lower_Band'], 'Signal'] = 1  # Buy
        data.loc[data[target+"_"+ticker] > data['Upper_Band'], 'Signal'] = -1  # Sell
 
    elif strategy == 'Breakout':
        breakout_window = kwargs.get('breakout_window')
        data['High_Max'] = data['spy_High'].rolling(window=breakout_window).max().shift(1)
        data['Low_Min'] = data['spy_Low'].rolling(window=breakout_window).min().shift(1)
        data['Signal'] = 0
        data.loc[data[target+"_"+ticker] > data['High_Max'], 'Signal'] = 1  # Breakout above
        data.loc[data[target+"_"+ticker] < data['Low_Min'], 'Signal'] = -1  # Breakout below

    elif strategy == 'Prophet':
        initial_training_period = kwargs.get('initial_training_period')

        data_simp = data[['Date',target+"_"+ticker]]
        data_simp = data_simp.rename(columns={'Date': 'ds',target+"_"+ticker:'y'})
          
        # Prepare columns
        data['Signal'] = 0
        
        for i in range(initial_training_period, len(data)):
            data_simp_cut = data_simp.iloc[:i]

            # Initialize and fit Prophet
            model = Prophet(daily_seasonality=True, yearly_seasonality=True)
            model.fit(data_simp_cut)

            future = model.make_future_dataframe(periods=1, include_history=False)
            forecast = model.predict(future)

            predicted_price = forecast['yhat'].iloc[0]
            current_price = data.loc[data.index[i - 1], target+"_"+ticker]

            data.loc[data.index[i], 'Signal'] = 1 if predicted_price > current_price else -1

    elif strategy == "Logit":
        initial_training_period = kwargs.get('initial_training_period')
        retrain_interval = kwargs.get('retrain_interval')
        selected_features = kwargs.get('selected_features')
        max_iter = kwargs.get('max_iter')

        data = calculate_technical_indicators(data, ticker, target)

         # Define target variable: price direction (1 = up, -1 = down, 0 = stable)
        data['Target'] = np.sign(data[target+"_"+ticker].shift(-1) - data[target+"_"+ticker])
        
        # Drop rows with missing values due to rolling calculations
        data = data.dropna()
        
        # Define features and target
        X = data[selected_features]
        y = data['Target']
        
        model = LogisticRegression(max_iter=max_iter)
        scaler = StandardScaler()

        # Prepare columns
        data['Signal'] = 1

        for i in range(initial_training_period, len(data), retrain_interval):
            # Train only on past data up to the current point
            X_train = X.iloc[:i]
            y_train = y.iloc[:i]

            # Fit the scaler on the training data
            scaler.fit(X_train)

            # Scale training data and fit model
            X_train_scaled = scaler.transform(X_train)

            model.fit(X_train_scaled, y_train)

            # Predict for the next retrain_interval days
            prediction_end = min(i + retrain_interval, len(data))
            X_test = X.iloc[i:prediction_end]

            # Scale test data using already fitted scaler
            X_test_scaled = scaler.transform(X_test)

            data.loc[data.index[i:prediction_end], 'Signal'] = model.predict(X_test_scaled)

    elif strategy =="RandomForest":
        initial_training_period = kwargs.get('initial_training_period')
        retrain_interval = kwargs.get('retrain_interval')
        selected_features = kwargs.get('selected_features')

        data = calculate_technical_indicators(data, ticker, target)
    
        # Define target variable: price direction (1 = up, -1 = down, 0 = stable)
        data['Target'] = np.sign(data[target+"_"+ticker].shift(-1) - data[target+"_"+ticker])
        
        # Drop rows with missing values due to rolling calculations
        data = data.dropna()
        
        # Define features and target
        X = data[selected_features]
        y = data['Target']

        # model_params = model_params or {'n_estimators': 100, 'random_state': 42} # add option for model_params?
        model_params =  {'n_estimators': 100, 'random_state': 42}                  # add option for model_params?
        model = RandomForestClassifier(**model_params)                             # add option for model_params?
        
        # Prepare columns
        data['Signal'] = 1

        for i in range(initial_training_period, len(data), retrain_interval):
            # Train only on past data up to the current point
            X_train = X.iloc[:i]
            y_train = y.iloc[:i]

            # Train the model
            model.fit(X_train, y_train)

            # Predict for the next retrain_interval days
            prediction_end = min(i + retrain_interval, len(data))
            
            X_test = X.iloc[i:prediction_end]
            data.loc[data.index[i:prediction_end], 'Signal'] = model.predict(X_test)

    elif strategy == "XGBoost":
        initial_training_period = kwargs.get('initial_training_period')
        retrain_interval = kwargs.get('retrain_interval')
        selected_features = kwargs.get('selected_features')

        data = calculate_technical_indicators(data, ticker, target)
    
        # Define target variable: price direction (1 = up, -1 = down, 0 = stable)
        data['Target'] = np.sign(data[target+"_"+ticker].shift(-1) - data[target+"_"+ticker])
        
        # Drop rows with missing values due to rolling calculations
        data = data.dropna()
        
        # Define features and target
        X = data[selected_features]
        y = data['Target']
        
        # model_params = model_params or {'eval_metric': 'logloss', 'random_state': 42}  # add option for model_params?
        model_params = {'eval_metric': 'logloss', 'random_state': 42}                    # add option for model_params?
        model = XGBClassifier(**model_params)                                            # add option for model_params?
        le = LabelEncoder()
        
        # Prepare columns
        data['Signal'] = 1

        for i in range(initial_training_period, len(data), retrain_interval):
            # Train only on past data up to the current point
            train_data = data.iloc[:i]
            X_train = train_data[selected_features]
            y_train = le.fit_transform( train_data['Target'] )

            # Train the model
            model.fit(X_train, y_train)

            # Predict for the next retrain_interval days
            prediction_end = min(i + retrain_interval, len(data))
            test_data = data.iloc[i:prediction_end]
            X_test = test_data[selected_features]
            data.loc[data.index[i:prediction_end], 'Signal'] = le.inverse_transform(model.predict(X_test))
    
    elif strategy == 'Perfection':
        data['Signal'] = 1
        data.loc[data['spy_next_day_change_type']=="increase", 'Signal'] = 1
        data.loc[data['spy_next_day_change_type']=="decrease", 'Signal'] = -1

    else:
        raise ValueError(f"Strategy '{strategy}' is not implemented.")

    # Stack on older data where had a training period, assume held stock during that time
    if min(data['Date']) != og_min_date:
        data_training_period = data_raw.loc[data_raw['Date']<min(data['Date'])].reset_index(drop=True)
        data_training_period['Signal']=1
        data = pd.concat([data_training_period,data])

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
    
    data['Daily_Return'] = data[target+"_"+ticker].pct_change()
    data['Strategy_Return'] = data['signal_adj'].shift(1) * data['Daily_Return']
    data['Portfolio_Value'] = (1 + data['Strategy_Return']).cumprod() * initial_capital

    return data, model