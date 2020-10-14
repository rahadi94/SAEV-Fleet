from Fleet_sim.charging_station import ChargingStation
from Fleet_sim.location import Location
import pandas as pd
from Fleet_sim.model import Model
import simpy
import random

from Fleet_sim.parking import Parking
from Fleet_sim.read import zones
from Fleet_sim.vehicle import Vehicle

for iteration in range(1):
    print(f'iteration:{iteration}')
    env = simpy.Environment()

    # Initialize Vehicles


    def generate_location():
        return Location(random.uniform(13.80, 13.08), random.uniform(52.20, 52.70))


    vehicles_data = []
    for i in range(300):
        vehicle_data = dict(id=i, env=env, initial_location=generate_location(), capacity=50,
                            charge_state=random.randint(70, 75),
                            mode='idle')
        vehicles_data.append(vehicle_data)

    vehicles = list()

    for data in vehicles_data:
        vehicle = Vehicle(
            data['id'],
            data['env'],
            data['initial_location'],
            data['capacity'],
            data['charge_state'],
            data['mode']
        )
        vehicles.append(vehicle)
    # Initializing charging stations

    CSs_data = []
    CSs_optimum = [z for z in zones if z.id in [3, 11, 15, 18, 27, 36, 40, 42, 45, 52, 59, 65, 73, 74, 86, 88]]
    c = [4, 3, 6, 5, 4, 3, 3, 4, 4, 5, 4, 5, 3, 5, 8, 4]
    CSs_zones = []
    for s in range(len(c)):
        CSs_zones.append(dict(base=CSs_optimum[s], Number_of_chargers=c[s]))
    for zone in CSs_zones:
        CS_data = dict(id=zone['base'].id, env=env, location=zone['base'].centre, power=11 / 60,
                       Number_of_chargers=zone['Number_of_chargers'])
        CSs_data.append(CS_data)
    '''CSs_data = []
    for i in zones:
        CS_data = dict(id=i.id, env=env, location=i.centre, power=11 / 60, Number_of_chargers=500)
        CSs_data.append(CS_data)'''

    # Initialize Charging Stations
    charging_stations = list()

    for data in CSs_data:
        charging_station = (ChargingStation(
            data['id'],
            data['env'],
            data['location'],
            data['power'],
            data['Number_of_chargers']

        ))
        charging_stations.append(charging_station)

    PKs_data = []
    for i in range(100):
        PK_data = dict(id=i, env=env, location=generate_location(), Number_of_parkings=40)
        PKs_data.append(PK_data)

    # Initialize Charging Stations
    parkings = list()

    for data in PKs_data:
        parking = (Parking(
            data['id'],
            data['env'],
            data['location'],
            data['Number_of_parkings']

        ))
        parkings.append(parking)

    # Run simulation
    sim = Model(env, vehicles=vehicles, charging_stations=charging_stations, zones=zones, parkings=parkings,
                simulation_time=1440 * 0.1)
    for zone in zones:
        env.process(sim.trip_generation(zone=zone))
    for vehicle in vehicles:
        env.process(sim.run(vehicle))

    env.process(sim.hourly_charging())
    env.process(sim.charging_interruption())

    for vehicle in vehicles:
        env.process(sim.obs_Ve(vehicle=vehicle))

    for charging_station in charging_stations:
        env.process(sim.obs_CS(charging_station=charging_station))

    """for parking in parkings:
        env.process(sim.obs_PK(parking))"""

    env.process(sim.missed_trip())

    env.run(until=sim.simulation_time)

    pd_ve = pd.DataFrame()
    for vehicle in vehicles:
        pd_ve = pd_ve.append(pd.DataFrame(vehicle.count_seconds.values()).transpose())
    pd_ve.to_csv('vehicles.csv')
    sim.save_results(iteration)
"""
Extension and debugs:
. Critical:
    . When a trip is consider as unserved
. Define a function calculating the waiting time for each request.
. Should vehicles wait for travelers?
. Use driving distances between two points (i.g. Google Map)
. Consider a waiting time tolerance for each trip after which the trip is missed
. Count missed trips
. Consider public and owned CSs
. Calculate charging cost and revenue 
. We can consider different size of vehicles
. We can consider different trips (pooling, multi-destination)
. V2G connection 
. We should measure waiting time, impact on the grid and REG utilization (First, we need to add REG to the model)
. In this scenario we just assign idle vehicles to trips. In further, we could consider active vehicles too, because 
    maybe one of these active vehicles would be the best choice.
"""
