import random
from shapely.geometry import shape, Polygon, Point
from h3 import h3
from Fleet_sim.location import Location


class Zone:
    def __init__(self, id, hexagon, demand):
        self.id = id
        self.polygon = shape(
            {"type": "Polygon", "coordinates": [h3.h3_to_geo_boundary(hexagon, geo_json=True)], "properties": ""})
        self.centre = Location(self.polygon.centroid.x, self.polygon.centroid.y)
        self.hexagon = hexagon
        self.list_of_vehicles = []
        self.demand = demand

    def update(self, vehicles):
        self.list_of_vehicles = [vehicle for vehicle in vehicles
                                 if vehicle.position == self.id and vehicle.mode == 'idle']