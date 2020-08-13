import random
from Fleet_sim.location import Location, generate_random
import numpy as np
from Fleet_sim.vehicle import Vehicle


class Trip:

    def __init__(self, env, id, zone):
        self.env = env
        self.id = id
        self.zone = zone
        np.random.seed(0)

        # We generate origin and destination of trips randomly
        time = self.env.now
        self.origin = generate_random(zone.hexagon)
        self.destination = Location(random.uniform(13.00, 13.80), random.uniform(52.00, 52.80))
        for i in range(0, 24):
            if i*60 <= time <= (i+1)*60:
                arrival_rate = zone.demand[str(i)].values
        # We generate time-varying trips (i.e. trips are being generated exponentially, in which
        # arrival-rate is a gaussian function of time during the day)

        self.interarrival = random.expovariate(arrival_rate)
        self.start_time = None

        distance = self.origin.distance(self.destination)
        self.duration = distance / Vehicle.speed
        self.end_time = self.interarrival + self.duration

        self.mode = 'unassigned'
        self.info = dict()
        self.info['id'] = self.id
        self.info['origin'] = [self.origin.lat, self.origin.long]
        self.info['destination'] = [self.destination.lat, self.destination.long]
        self.info['arrival_time'] = None
        self.info['pickup_time'] = None
        self.info['waiting_time'] = None

    """
    Allowed modes are:
    unassigned - no vehicle is assigned to it
    assigned - a vehicle is assigned and sent
    in vehicle - it is being served
    finished - it is finished   """
