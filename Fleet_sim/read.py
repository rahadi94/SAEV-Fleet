import pandas as pd

from Fleet_sim.Zone import Zone

demand_table = pd.read_csv('demand_table.csv')

z = 0
zones = list()
for hex in demand_table['h3_hexagon_id_start'].values:
    z += 1
    demand = (demand_table[demand_table['h3_hexagon_id_start'] == hex]
                  .drop('h3_hexagon_id_start', axis=1))/1440 + 0.001
    zone = Zone(z, hex, demand)
    zones.append(zone)
