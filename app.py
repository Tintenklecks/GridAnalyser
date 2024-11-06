import streamlit as st
from pycoingecko import CoinGeckoAPI
import pandas as pd
from datetime import datetime, timedelta

if "all_coins" not in st.session_state:
    st.session_state.all_coins = []


def get_top_coins(limit=100):
    if len(st.session_state.all_coins) == 0:
        cg = CoinGeckoAPI()
        coins = cg.get_coins_markets(
            vs_currency='usd', order='market_cap_desc', per_page=limit, page=1)
        st.session_state.all_coins.extend(coins)

    return st.session_state.all_coins


if "last_coin_id" not in st.session_state:
    st.session_state.last_coin_id = ""
    st.session_state.last_from_timestamp = 0
    st.session_state.last_to_timestamp = 0
    st.session_state.last_dataframe = None


def get_historical_prices(coin_id, vs_currency, from_timestamp, to_timestamp):

    if coin_id == "":
        return st.session_state.last_dataframe

    if st.session_state.last_coin_id != coin_id or st.session_state.last_from_timestamp != from_timestamp or st.session_state.last_to_timestamp != to_timestamp:
        cg = CoinGeckoAPI()
        data = cg.get_coin_market_chart_range_by_id(
            id=coin_id,
            vs_currency=vs_currency,
            from_timestamp=from_timestamp,
            to_timestamp=to_timestamp
        )
        prices = data['prices']
        df = pd.DataFrame(prices, columns=['timestamp', 'price'])
        df['datetime'] = pd.to_datetime(df['timestamp'], unit='ms')
        st.session_state.last_coin_id = coin_id
        st.session_state.last_from_timestamp = from_timestamp
        st.session_state.last_to_timestamp = to_timestamp
        st.session_state.last_dataframe = df

    return st.session_state.last_dataframe


def grid_bot(coin_prices_df, lower_limit, upper_limit, num_grids, investment_usd):
    # Initialize variables
    cash_balance = investment_usd
    coin_balance = 0.0
    positions = []  # List of open positions
    buy_sell_positions = []  # List of all buy/sell actions
    transaction_number = 0  # Initialize transaction number

    # For tracking cash balance over time
    cash_balances = [cash_balance]

    # Extract coin prices and timestamps
    coin_prices = coin_prices_df['price'].tolist()
    timestamps = coin_prices_df['datetime'].tolist()

    # Define grid levels
    grid_size = (upper_limit - lower_limit) / num_grids
    grid_levels = [lower_limit + i * grid_size for i in range(num_grids + 1)]
    grid_levels = sorted(grid_levels)

    # Calculate amount per order
    amount_per_order = investment_usd / num_grids

    # Simulate trading over coin prices
    for t in range(1, len(coin_prices)):
        p_prev = coin_prices[t - 1]
        p_curr = coin_prices[t]

        if p_prev == p_curr:
            continue  # No price change

        # Price decreased
        if p_prev > p_curr:
            # Price crossed downwards from p_prev to p_curr
            crossed_grids = [level for level in grid_levels if p_curr <=
                             level < p_prev and lower_limit <= level <= upper_limit]
            for grid_level in crossed_grids:
                if cash_balance >= amount_per_order:
                    # Increment transaction number
                    transaction_number += 1

                    coin_amount = amount_per_order / grid_level
                    cash_balance -= amount_per_order
                    coin_balance += coin_amount
                    buy_action = {
                        'datetime': timestamps[t],
                        'transaction_number': transaction_number,
                        'action': 'buy',
                        'price': grid_level,
                        'amount': coin_amount,
                        'gain': None
                    }
                    buy_sell_positions.append(buy_action)
                    # Place a sell order at the grid level above
                    sell_price = grid_level + grid_size
                    if lower_limit <= sell_price <= upper_limit:
                        position = {
                            'transaction_number': transaction_number,
                            'buy_price': grid_level,
                            'sell_price': sell_price,
                            'amount': coin_amount,
                            'buy_datetime': timestamps[t],
                        }
                        positions.append(position)
                else:
                    pass  # Insufficient cash

        # Price increased
        elif p_prev < p_curr:
            # Price crossed upwards from p_prev to p_curr
            crossed_grids = [level for level in grid_levels if p_prev <
                             level <= p_curr and lower_limit <= level <= upper_limit]
            for grid_level in crossed_grids:
                # Check if we have any positions to sell at the grid below
                positions_to_remove = []
                for position in positions:
                    if position['sell_price'] == grid_level:
                        coin_amount = position['amount']
                        cash_balance += coin_amount * grid_level
                        coin_balance -= coin_amount
                        gain = (grid_level -
                                position['buy_price']) * coin_amount
                        # Assign transaction_number from the position
                        txn_number = position['transaction_number']
                        sell_action = {
                            'datetime': timestamps[t],
                            'transaction_number': txn_number,
                            'action': 'sell',
                            'price': grid_level,
                            'amount': coin_amount,
                            'gain': gain
                        }
                        buy_sell_positions.append(sell_action)
                        positions_to_remove.append(position)
                for position in positions_to_remove:
                    positions.remove(position)

        # Append current cash balance to the list
        cash_balances.append(cash_balance)

    # Create DataFrame of transactions
    transactions_df = pd.DataFrame(buy_sell_positions)

    # Calculate total profit
    total_profit = transactions_df['gain'].sum(skipna=True)

    # Calculate maximum invested amount
    min_cash_balance = min(cash_balances)
    max_invested_amount = investment_usd - min_cash_balance

    return transactions_df, total_profit, grid_size, max_invested_amount


def main():
    st.title("Crypto Grid Trading Bot Simulator")

    print(f"get top coins start {datetime.now()}")
    # Fetch top 100 coins
    coins = get_top_coins(100)
    print(f"get top coins end  {datetime.now()}")

    coin_options = {coin['name']: coin['id'] for coin in coins}
    coin_name = st.selectbox("Select a cryptocurrency:",
                             list(coin_options.keys()))
    coin_id = coin_options[coin_name]

    # Date selection
    col1, col2 = st.columns(2)
    with col1:
        start_date = st.date_input(
            "Start Date", datetime.now() - timedelta(days=30))
    with col2:
        end_date = st.date_input("End Date", datetime.now())

    if start_date >= end_date:
        st.error("Start date must be before end date.")
        return

    # Fetch historical prices to determine min and max prices
    from_timestamp = int(datetime.combine(
        start_date, datetime.min.time()).timestamp())
    to_timestamp = int(datetime.combine(
        end_date, datetime.max.time()).timestamp())

    print(f"get hist data start {datetime.now()}")

    with st.spinner('Fetching historical data...'):
        coin_prices_df = get_historical_prices(
            coin_id, 'usd', from_timestamp, to_timestamp)
    print(f"get hist data end  {datetime.now()}")

    if coin_prices_df.empty:
        st.error("No price data available for the selected dates.")
        return

    min_price = coin_prices_df['price'].min()
    max_price = coin_prices_df['price'].max()

    st.write(f"Price range for {coin_name} from {start_date} to {end_date}:")
    st.write(f"Minimum Price: ${min_price:,.2f}")
    st.write(f"Maximum Price: ${max_price:,.2f}")

    # Set grid parameters
    num_grids = st.slider("Select number of grids:",
                          min_value=5, max_value=200, value=33)

    lower_limit = st.number_input(
        "Grid Bottom Level (Lower Limit):", value=float(f"{min_price:.2f}"))
    upper_limit = st.number_input(
        "Grid Top Level (Upper Limit):", value=float(f"{max_price:.2f}"))

    if lower_limit >= upper_limit:
        st.error("Lower limit must be less than upper limit.")
        return

    # Calculate grid percentage size immediately
    if num_grids > 0 and upper_limit > lower_limit:
        grid_size = (upper_limit - lower_limit) / num_grids
        mid_price = (lower_limit + upper_limit) / 2
        grid_percentage = (grid_size / mid_price) * 100
        st.write(f"**Grid Percentage Size:** {grid_percentage:.4f}%")

    # Investment amount
    investment_usd = st.select_slider(
        "Select your investment amount (USD):",
        options=range(1000, 50001, 1000),
        value=1000
    )

    # Run simulation button
    if st.button("Run Simulation"):
        print(f"start sim start {datetime.now()}")

        with st.spinner('Running simulation...'):
            transactions_df, total_profit, grid_size, max_invested_amount = grid_bot(
                coin_prices_df,
                lower_limit,
                upper_limit,
                num_grids,
                investment_usd
            )
            print(f"end sim end  {datetime.now()}")

            # Calculate HODL profit
            start_price = coin_prices_df.iloc[0]['price']
            end_price = coin_prices_df.iloc[-1]['price']
            hodl_coin_amount = investment_usd / start_price
            hodl_final_value = hodl_coin_amount * end_price
            hodl_profit = hodl_final_value - investment_usd

            # Calculate gain in percent compared to the complete investment
            gain_percentage = (total_profit / investment_usd) * 100

            # Display results
            st.subheader("Simulation Results")

            st.write(f"**Total Grid Bot Profit:** ${total_profit:,.2f}")
            st.write(
                f"**Total Grid Bot Profit Percentage:** {gain_percentage:.2f}%")
            st.write(
                f"**Maximum Amount Invested in Grid Bot:** ${max_invested_amount:,.2f}")
            st.write(f"**Total HODL Profit:** ${hodl_profit:,.2f}")

            print(f"display results start {datetime.now()}")
            st.write("### Transactions:")
            st.dataframe(transactions_df)
            print(f"display results end  {datetime.now()}")


if __name__ == "__main__":
    main()
