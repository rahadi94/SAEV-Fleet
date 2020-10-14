from geopy.distance import geodesic
import random
from shapely.geometry import Point, shape
from h3 import h3


'''def find_zone(loc, zones):
    hexagon = h3.geo_to_h3(loc.lat, loc.long, 7)
    position = [x for x in zones
                if x.hexagon == hexagon][0]
    return position'''


def find_zone(loc, zones):
    distances_to_centers = [loc.distance(zone.centre) for zone in zones]
    position = [x for x in zones
                if x.centre.distance(loc) == min(distances_to_centers)][0]
    return position


class Location:

    def __init__(self, lat, long):
        self.long = long
        self.lat = lat

    def distance(self, loc):
        origin = [self.lat, self.long]
        destination = [loc.lat, loc.long]
        return geodesic(origin, destination).kilometers


def generate_random(hex):
    polygon = shape(
        {"type": "Polygon", "coordinates": [h3.h3_to_geo_boundary(hex, geo_json=True)], "properties": ""})
    minx, miny, maxx, maxy = polygon.bounds
    c = True
    while c:
        pnt = Point(random.uniform(minx, maxx), random.uniform(miny, maxy))
        if polygon.contains(pnt):
            c = False

        return Location(pnt.x, pnt.y)

    """import googlemaps
    API_key = 'AIzaSyCxGGUs - xbyFZFsiDDSKNP7QIjGr - Is1DA'
    gmaps = googlemaps.Client(key=API_key)
    result = gmaps.distance_matrix(origins, destination, mode='walking')["rows"][0]["elements"][0]["distance"]["value"]"""
