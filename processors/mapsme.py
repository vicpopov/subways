import json
from subway_structure import distance


OSM_TYPES = {'n': (0, 'node'), 'w': (2, 'way'), 'r': (3, 'relation')}
SPEED_TO_ENTRANCE = 3  # km/h
SPEED_ON_TRANSFER = 3.5
SPEED_ON_LINE = 40
DEFAULT_INTERVAL = 2.5  # minutes


def process(cities, transfers, cache_name):
    def uid(elid, typ=None):
        t = elid[0]
        osm_id = int(elid[1:])
        if not typ:
            osm_id = osm_id << 2 + OSM_TYPES[t][0]
        elif typ != t:
            raise Exception('Got {}, expected {}'.format(elid, typ))
        return osm_id << 1

    def format_colour(c):
        return c[1:] if c else None

    def find_exits_for_platform(center, nodes):
        exits = []
        min_distance = None
        for n in nodes:
            d = distance(center, (n['lon'], n['lat']))
            if not min_distance:
                min_distance = d * 2 / 3
            elif d < min_distance:
                continue
            too_close = False
            for e in exits:
                d = distance((e['lon'], e['lat']), (n['lon'], n['lat']))
                if d < min_distance:
                    too_close = True
                    break
            if not too_close:
                exits.append(n)
        return exits

    cache = {}
    if cache_name:
        with open(cache_name, 'r', encoding='utf-8') as f:
            cache = json.load(f)

    stops = {}  # el_id -> station data
    networks = []

    good_cities = set([c.name for c in cities])
    for city_name, data in cache.items():
        if city_name in good_cities:
            continue
        # TODO: get a network, stops and transfers from cache

    platform_nodes = {}
    for city in cities:
        network = {'network': city.name, 'routes': [], 'agency_id': city.id}
        for route in city:
            routes = {
                'type': route.mode,
                'ref': route.ref,
                'name': route.name,
                'colour': format_colour(route.colour),
                'route_id': uid(route.id, 'r'),
                'itineraries': []
            }
            if route.infill:
                routes['casing'] = routes['colour']
                routes['colour'] = format_colour(route.infill)
            for i, variant in enumerate(route):
                itin = []
                for stop in variant:
                    stops[stop.stoparea.id] = stop.stoparea
                    itin.append([uid(stop.stoparea.id), round(stop.distance*3.6/SPEED_ON_LINE)])
                    # Make exits from platform nodes, if we don't have proper exits
                    if len(stop.stoparea.entrances) + len(stop.stoparea.exits) == 0:
                        for pl in stop.stoparea.platforms:
                            pl_el = city.elements[pl]
                            if pl_el['type'] == 'node':
                                pl_nodes = [pl_el]
                            elif pl_el['type'] == 'way':
                                pl_nodes = [city.elements['n{}'.format(n)]
                                            for n in pl_el['nodes']]
                            else:
                                pl_nodes = []
                                for m in pl_el['members']:
                                    if m['type'] == 'way':
                                        pl_nodes.extend(
                                            [city.elements['n{}'.format(n)]
                                             for n in city.elements['{}{}'.format(
                                                 m['type'][0], m['ref'])]['nodes']])
                            platform_nodes[pl] = find_exits_for_platform(
                                stop.stoparea.centers[pl], pl_nodes)

                routes['itineraries'].append({
                    'stops': itin,
                    'interval': round((variant.interval or DEFAULT_INTERVAL) * 60)
                })
            network['routes'].append(routes)
        networks.append(network)

    m_stops = []
    for stop in stops.values():
        st = {
            'name': stop.name,
            'int_name': stop.int_name,
            'lat': stop.center[1],
            'lon': stop.center[0],
            'osm_type': OSM_TYPES[stop.station.id[0]][1],
            'osm_id': int(stop.station.id[1:]),
            'id': uid(stop.id),
            'entrances': [],
            'exits': [],
        }
        for e_l, k in ((stop.entrances, 'entrances'), (stop.exits, 'exits')):
            for e in e_l:
                if e[0] == 'n':
                    st[k].append({
                        'osm_type': 'node',
                        'osm_id': int(e[1:]),
                        'lon': stop.centers[e][0],
                        'lat': stop.centers[e][1],
                        'distance': 60 + round(distance(
                            stop.centers[e], stop.center)*3.6/SPEED_TO_ENTRANCE)
                    })
        if len(stop.entrances) + len(stop.exits) == 0:
            if stop.platforms:
                for pl in stop.platforms:
                    for n in platform_nodes[pl]:
                        for k in ('entrances', 'exits'):
                            st[k].append({
                                'osm_type': n['type'],
                                'osm_id': n['id'],
                                'lon': n['lon'],
                                'lat': n['lat'],
                                'distance': 60 + round(distance(
                                    (n['lon'], n['lat']), stop.center)*3.6/SPEED_TO_ENTRANCE)
                            })
            else:
                for k in ('entrances', 'exits'):
                    st[k].append({
                        'osm_type': OSM_TYPES[stop.station.id[0]][1],
                        'osm_id': int(stop.station.id[1:]),
                        'lon': stop.centers[stop.id][0],
                        'lat': stop.centers[stop.id][1],
                        'distance': 60
                    })

        m_stops.append(st)

    c_transfers = []
    for t_set in transfers:
        t = list(t_set)
        for t_first in range(len(t) - 1):
            for t_second in range(t_first + 1, len(t)):
                if t[t_first].id in stops and t[t_second].id in stops:
                    c_transfers.append([
                        uid(t[t_first].id),
                        uid(t[t_second].id),
                        30 + round(distance(t[t_first].center,
                                            t[t_second].center)*3.6/SPEED_ON_TRANSFER)
                    ])

    if cache_name:
        with open(cache_name, 'w', encoding='utf-8') as f:
            json.dump(cache, f)

    result = {
        'stops': m_stops,
        'transfers': c_transfers,
        'networks': networks
    }
    return result