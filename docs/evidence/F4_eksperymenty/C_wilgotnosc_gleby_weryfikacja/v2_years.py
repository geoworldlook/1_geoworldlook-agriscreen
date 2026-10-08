import sys; sys.dont_write_bytecode=True
exec(open("v1_events.py").read().split("def sc(")[0])
J["obs_ev"]=J.obs<=-1; J["L2w"]=J.L2_op<=-1; J["RZw"]=J.RZ_op<=-1
S=J[J.index.month.isin(range(4,11))]
g=S.groupby(S.index.year)[["obs_ev","L2w","RZw"]].sum()
g["L2_hit"]=(S.obs_ev&S.L2w).groupby(S.index.year).sum(); g["RZ_hit"]=(S.obs_ev&S.RZw).groupby(S.index.year).sum()
print("IV-X dekads per year (op base): observed events, warnings, hits"); print(g.to_string())
for y in ("2019","2020","2022"):
    print(f"\n{y} VI-X dekadal z"); print(J.loc[f"{y}-06":f"{y}-10",["obs","RZ_op","L2_op"]].round(2).T.to_string())
