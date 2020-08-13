import random
import pandas as pd
import simpy
import logging
from Fleet_sim.trip import Trip

lg = logging.getLogger(__name__)
lg.setLevel(logging.INFO)

formatter = logging.Formatter('%(name)s:%(message)s')

file_handler = logging.FileHandler('report.log')
file_handler.setFormatter(formatter)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
stream_handler.setLevel(logging.ERROR)

lg.addHandler(file_handler)
lg.addHandler(stream_handler)


# This function give us the available vehicles for a trip
def available_vehicle(vehicles, trip, SOC_treshold=20, max_distance=10):
    available_vehicles = list()
    for vehicle in vehicles:
        distance_to_pickup = vehicle.location.distance(trip.origin)
        distance_to_dropoff = vehicle.location.distance(trip.destination)
        charge_consumption = (distance_to_pickup + distance_to_dropoff) * \
                             vehicle.fuel_consumption * 100.0 / vehicle.battery_capacity
        # Add idle vehicles that have enough energy to respond the trip into available vehicles and are not far away too much
        if distance_to_pickup <= max_distance:
            if charge_consumption + SOC_treshold <= vehicle.charge_state and vehicle.mode in ['idle', 'parking', 'ertp']:
                available_vehicles.append(vehicle)
    return available_vehicles


class Model:

    def __init__(self, env, vehicles, charging_stations, zones, parkings, simulation_time=500):
        self.parkings = parkings
        self.zones = zones
        self.charging_stations = charging_stations
        self.vehicles = vehicles
        self.waiting_list = []
        self.simulation_time = simulation_time
        self.env = env
        self.trip_end = env.event()
        self.trip_start = env.event()
        self.charging_start = env.event()
        self.charging_end = env.event()
        self.charging_interrupt = env.event()
        self.relocation_start = env.event()
        self.relocation_end = env.event()

    def park(self, vehicle, parking):
        if self.env.now > 5:
            vehicle.send_parking(parking)
            yield self.env.timeout(vehicle.time_to_parking)
        vehicle.parking(parking)
        yield vehicle.parking_stop

    def parking_task(self, vehicle):
        if vehicle.charge_state >= 40 and vehicle.mode == 'idle':
            # Finding the closest parking
            distances_to_PKs = [vehicle.location.distance(PK.location) for PK in self.parkings]
            parking = [x for x in self.parkings
                       if x.location.distance(vehicle.location) == min(distances_to_PKs)][0]
            with parking.capacity.request() as req:
                yield req
                yield self.env.process(self.park(vehicle, parking))

    def relocate(self, vehicle, target_zone):
        vehicle.relocate(target_zone)
        yield self.env.timeout(vehicle.time_to_relocate)
        vehicle.finsih_relocating(target_zone)

    def relocate_task(self, vehicle):
        for zone in self.zones:
            zone.update(self.vehicles)
        if vehicle.charge_state >= 60 and vehicle.mode in ['idle', 'parking'] and len(
                vehicle.position.list_of_vehicles) > 1:
            target_zones = [z for z in self.zones if len(z.list_of_vehicles) == 0 and
                            z.demand[str(int(self.env.now / 10))].values > vehicle.position.demand[
                                str(int(self.env.now / 10))].values]
            if len(target_zones) > 1:
                target_demands = [target.demand[str(int(self.env.now / 10))].values for target in target_zones]
                target_zone = [z for z in target_zones
                               if z.demand[str(int(self.env.now / 10))].values == max(target_demands)][0]
                self.env.process(self.relocate(vehicle, target_zone))

    def start_charge(self, charging_station, vehicle):
        vehicle.send_charge(charging_station)
        yield self.env.timeout(vehicle.time_to_CS)
        vehicle.t_start_charging = self.env.now
        vehicle.charging(charging_station)
        self.charging_start.succeed()
        self.charging_start = self.env.event()

    def finish_charge(self, charging_station, vehicle):

        try:
            yield self.env.timeout(vehicle.charge_duration)
            vehicle.finish_charging(charging_station)
            self.charging_end.succeed()
            self.charging_end = self.env.event()
        except simpy.Interrupt:
            vehicle.charge_state += (charging_station.power * (
                    self.env.now - vehicle.t_start_charging) * 100) / vehicle.battery_capacity
            vehicle.mode = 'idle'
            vehicle.count_seconds['charging'] += self.env.now - vehicle.t_start_charging
            self.charging_interrupt.succeed()
            self.charging_interrupt = self.env.event()
            vehicle.costs['charging'] += (vehicle.charging_threshold - vehicle.charge_state) * vehicle.charging_cost
            print(f'Warning!!!Charging state of vehicle {vehicle.id} is {vehicle.charge_state} at {self.env.now} ')

    # Checking charge status for vehicles and send them to charge if necessary
    def charge_task(self, vehicle):
        if vehicle.charge_state <= 40 and vehicle.mode == 'idle':
            # Finding the closest charging station
            distances_to_CSs = [vehicle.location.distance(CS.location) for CS in self.charging_stations]
            charging_station = [x for x in self.charging_stations
                                if x.location.distance(vehicle.location) == min(distances_to_CSs)][0]
            with charging_station.plugs.request() as req:
                yield req
                yield self.env.process(self.start_charge(charging_station, vehicle))
                charging = self.env.process(self.finish_charge(charging_station, vehicle))
                yield charging | self.env.timeout(10)
                if not charging.triggered:
                    charging.interrupt()
                    print(f'Vehicle {vehicle.id} stop charging at {self.env.now}')

    def take_trip(self, trip, vehicle):
        vehicle.send(trip)
        trip.mode = 'assigned'
        yield self.env.timeout(vehicle.time_to_pickup)
        vehicle.pick_up(trip)
        trip.mode = 'in vehicle'
        yield self.env.timeout(trip.duration)
        vehicle.drop_off(trip)
        self.trip_end.succeed()
        self.trip_end = self.env.event()
        self.vehicle_id = vehicle.id
        trip.mode = 'finished'

    def trip_task(self, trip):
        available_vehicles = available_vehicle(self.vehicles, trip)
        distances = [vehicle.location.distance(trip.origin) for vehicle in available_vehicles]
        # If there is no available vehicle, add the trip to the waiting list
        if len(available_vehicles) == 0:
            #trip.mode = 'missed'
            return
        # Assigning the closest available vehicle to the trip
        print(f'There is/are {len(available_vehicles)} available vehicle(s) for trip {trip.id}')
        vehicle = [x for x in available_vehicles
                   if x.location.distance(trip.origin) == min(distances)][0]
        if vehicle.mode == 'parking':
            vehicle.parking_stop.succeed()
            vehicle.parking_stop = self.env.event()
        self.env.process(self.take_trip(trip, vehicle))

    def trip_generation(self, zone):
        j = 0
        # Trips are being generated randomly and cannot be rejected
        while True:
            j += 1
            trip = Trip(self.env, [zone.id, j], zone)
            yield self.env.timeout(trip.interarrival)
            self.trip_start.succeed()
            self.trip_start = self.env.event()
            trip.info['arrival_time'] = self.env.now
            self.waiting_list.append(trip)
            print(f'Trip {trip.id} is received at {self.env.now}')
            trip.start_time = self.env.now

    def missed_trip(self):
        while True:
            for trip in self.waiting_list:
                if trip.mode == 'unassigned' and self.env.now > (trip.start_time + 10):
                    trip.mode = 'missed'
                    print (f'trip {trip.id} is missed at {self.env.now}')
            yield self.env.timeout(1)

    def run(self):
        while True:
            # All vehicles start from parking
            if self.env.now == 0:
                for vehicle in self.vehicles:
                    self.env.process(self.parking_task(vehicle))

            event_trip_start = self.trip_start
            event_trip_end = self.trip_end
            event_charging_end = self.charging_end
            event_charging_interuppt = self.charging_interrupt
            events = yield event_trip_start | event_trip_end | event_charging_end | event_charging_interuppt
            if event_trip_start in events:
                for trip in self.waiting_list:
                    if trip.mode == 'unassigned':
                        self.trip_task(trip)
                        yield self.env.timeout(0)
            if event_trip_end in events:
                print(f'A vehicle get idle at {self.env.now}')
                vehicle = [v for v in self.vehicles if v.id == self.vehicle_id][0]
                self.env.process(self.charge_task(vehicle))
                yield self.env.timeout(0.1)
                self.relocate_task(vehicle)
                for trip in self.waiting_list:
                    if trip.mode == 'unassigned':
                        self.trip_task(trip)
                        yield self.env.timeout(0)
                self.env.process(self.parking_task(vehicle))
                yield self.env.timeout(0.1)

            if event_charging_end in events:
                print(f'A vehicle get charged at {self.env.now}')
                vehicle = [v for v in self.vehicles if v.id == self.vehicle_id][0]
                self.relocate_task(vehicle)
                for trip in self.waiting_list:
                    if trip.mode == 'unassigned':
                        self.trip_task(trip)
                        yield self.env.timeout(0)

            if event_charging_interuppt in events:
                print(f'Charging get interrupted at {self.env.now}')
                for trip in self.waiting_list:
                    if trip.mode == 'unassigned':
                        self.trip_task(trip)
                        yield self.env.timeout(0)

    def obs_Ve(self, vehicle):
        self.t = []
        while True:
            t_now = self.env.now
            self.t.append(t_now)
            vehicle.info['SOC'].append(vehicle.charge_state)
            vehicle.info['location'].append([vehicle.location.lat, vehicle.location.long])
            vehicle.info['position'].append(vehicle.position)
            vehicle.info['mode'].append(vehicle.mode)
            yield self.env.timeout(1)

    def obs_CS(self, charging_station):
        while True:
            charging_station.queue.append(charging_station.plugs.count)
            yield self.env.timeout(1)

    def obs_PK(self, parking):
        while True:
            parking.queue.append(parking.capacity.count)
            yield self.env.timeout(1)

    def save_results(self):
        trips_info = []
        for i in self.waiting_list:
            trips_info.append(i.info)
        results = pd.DataFrame(trips_info)
        with pd.ExcelWriter("results.xlsx") as writer:
            results.to_excel(writer, sheet_name='Trips')
            for j in self.vehicles:
                pd.DataFrame([j.info["SOC"], j.info["location"], j.info["position"], j.info["mode"]]) \
                    .to_excel(writer, sheet_name='Vehicle_%s' % j.id)

            for c in self.charging_stations:
                pd.DataFrame([c.queue]).to_excel(writer, sheet_name='CS_%s' % c.id)

            for p in self.parkings:
                pd.DataFrame([p.queue]).to_excel(writer, sheet_name='PK_%s' % p.id)
