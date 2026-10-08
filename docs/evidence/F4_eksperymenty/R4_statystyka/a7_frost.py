import pandas as pd, numpy as np
from common import era5
e = era5()
sp = e[(e.index.month.isin([3,4,5]))]
fr = sp[sp.t2m_min_c <= -1.0]
print("Spring (III-V) days with ERA5-Land Tmin <= -1 C, after 20 March, by year:")
fr2 = fr[(fr.index.month > 3) | (fr.index.day > 20)]
print(fr2.groupby(fr2.index.year)["t2m_min_c"].agg(["count","min"]).loc[2016:].to_string())
print(fr2.loc["2021":"2022"]["t2m_min_c"].round(1).to_string())
