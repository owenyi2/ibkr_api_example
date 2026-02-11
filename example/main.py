import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv("data.log", sep = "\t", header = None)
df = pd.pivot(df, index = 0, columns =  1, values = 2).rename_axis(index=None, columns=None)
index = df.index.str.replace(r"\s[A-Z]{3,4}\s", " ", regex=True)
df.index = pd.to_datetime(index, format = "%Y-%m-%d %H:%M:%S %z")

hkex_data = pd.read_csv("Equities_3690.csv")
hkex_data["Time"] = pd.to_datetime(
    hkex_data["Time"],
    format="%Y/%m/%d %H:%M"
    ).dt.tz_localize("Asia/Hong_Kong")
hkex_data.set_index("Time", inplace = True)

fig, ax = plt.subplots()

ax.set_title("Meituan Share Price (3690.HK)")
df[["DELAYED_ASK", "DELAYED_BID"]].ffill().plot(ax = ax)
df["DELAYED_LAST"].plot(ax = ax, style = "x", linestyle="None")
hkex_data["2026-02-11 10:00:00":]["Last Traded Price"].shift(freq=pd.Timedelta(minutes=16)).plot(ax = ax)

# even though I should be getting 15 minute delayed data, it seems like the delay is more like 16 minutes

plt.show()
