import time
from Queue import Queue
from threading import Thread
import msgpack
from xbos import get_client
from xbos.services.hod import HodClient
from xbos.devices.thermostat import Thermostat
from xbos.devices.light import Light

c = get_client()
hod = HodClient("ciee/hod",c)

lighting_query = """SELECT ?equipment ?uri WHERE {
?equipment rdf:type/rdfs:subClassOf* brick:Lighting_System .
?equipment bf:uri ?uri .
} LIMIT 500;"""

tstat_query = """SELECT ?equipment ?uri WHERE {
?equipment rdf:type/rdfs:subClassOf* brick:Thermostat .
?equipment bf:uri ?uri .
} LIMIT 500;"""

def light_strategy(self):
    self.old_brightness = self.brightness
    print "old", self.old_brightness
    new_brightness = 25
    print "change to", new_brightness
    #self.write({'brightness': new_brightness})

def light_reset(self):
    print "reset to", self.old_brightness
    #self.write({'brightness': self.old_brightness})


results = hod.do_query(lighting_query)
lights = []
if results["Count"] > 0:
    for row in results["Rows"]:
        l = Light(c, row["?uri"])
        lights.append(l)

def tstat_strategy(self):
    print self._state
    self.old_hsp = self.heating_setpoint
    self.old_csp = self.cooling_setpoint
    print "old",self.old_hsp,self.old_csp
    new_hsp = self.old_hsp-2
    new_csp = self.old_csp+2
    print "change to", new_hsp,new_csp
    self.write({
        'heating_setpoint': new_hsp,
        'cooling_setpoint': new_csp,
        'override': True
    })
    print "done writing"

def tstat_reset(self):
    print "reset to",self.old_hsp,self.old_csp
    self.write({
        'heating_setpoint': self.old_hsp,
        'cooling_setpoint': self.old_csp,
        'override': True
    })

results = hod.do_query(tstat_query)
tstats = []
if results["Count"] > 0:
    for row in results["Rows"]:
        t = Thermostat(c, row["?uri"])
        tstats.append(t)

dr_ponum = (2,0,0,1)
dr_queue = Queue()

def on_dr_event(bw_message):
    dr_queue.put(bw_message)

def do_dr_event(bw_message):
    for po in bw_message.payload_objects:
        if po.type_dotted == dr_ponum:
            event = msgpack.unpackb(po.content)
            duration = int(event["duration"])
            print "GOT DR EVENT for",duration,"seconds"
    for tstat in tstats:
        tstat_strategy(tstat)
    for light in lights:
        light_strategy(light)
    print "sleeping"
    time.sleep(duration)
    print "resetting"
    for tstat in tstats:
        tstat_reset(tstat)
    for light in lights:
        light_reset(light)

def dr_handler():
    while True:
        item = dr_queue.get()
        do_dr_event(item)
        dr_queue.task_done()

time.sleep(10)
c.subscribe("ciee/demand_response", on_dr_event)
print "Waiting for Demand Response events"

dr_worker = Thread(target=dr_handler)
dr_worker.daemon = True
dr_worker.start()

dr_queue.join()
while True:
    time.sleep(1000)
