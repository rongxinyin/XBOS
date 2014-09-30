from smap.archiver.client import SmapClient
import time
import pandas as pd
#pd.options.display.mpl_style = 'default'

client = SmapClient('http://ciee.cal-sdb.org:8079')
# timestamps
end = int(time.time())
start = end - 60*60*24*30 # last month
print start, end

def get_demand():
    # get energy data for same timeframe
    res = client.query('select uuid where Metadata/System = "Monitoring" and Properties/UnitofMeasure = "kW"')
    uuids = [x['uuid'] for x in res]
    data = dict(zip(uuids,client.data_uuid(uuids, start, end, cache=False)))

    # create dataframe, use time as index
    demand = pd.DataFrame(data.values()[0])
    demand[0] = pd.to_datetime(demand[0], unit='ms')
    demand.index = demand[0]
    del demand[0]
    return demand

def get_hvacstates():
    # get all hvac_state timeseries
    res = client.query('select uuid where Metadata/System = "HVAC" and Path like "%hvac_state"')
    uuids = [x['uuid'] for x in res]
    data = dict(zip(uuids,client.data_uuid(uuids, start, end, cache=False)))

    ret = {}

    for uuid in data.iterkeys():
        hvac = pd.DataFrame(data[uuid])
        hvac[0] = pd.to_datetime(hvac[0], unit='ms')
        hvac.index = hvac[0]
        del hvac[0]
        zone = client.query("select Metadata/HVACZone where uuid = '{0}'".format(uuid))[0]['Metadata']['HVACZone']
        ret[zone] = hvac
    return ret

def group_contiguous(df, key, value):
    """
    condition: df[key] == value
    We need to create discrete groups based on a condition that exists for a contiguous region. In our case, we
    want to identify sections of indices of our dataframe [df] where the condition is met and the indexes are
    sequential

    Returns a list of tuples (before, start, end, after, condition):
    before: index before group
    start: first index where [condition] holds
    end: last index where [condition] holds
    after: index after group
    condition: is [condition] T/F?
    """
    # transitions is a list of indexes into [df] indicating the location before
    # [df] jumps from condition=True to condition=False (or vice-versa)
    conditions = pd.np.diff(df[key] == value)
    transitions = conditions.nonzero()[0]
    # pairs of indexes indicating the start/end of a group
    pairs = zip(transitions[:-1], transitions[1:])
    ret = []
    for start,end in pairs:
        ret.append((start,start+1,end,end+1,df.iloc[start+1][key] == value))
    return ret

def resample_and_merge():
    """
    Resamples every 5 seconds and merges the demand data with the zone data. Yields one dataframe
    for each zone
    """
    demand = get_demand()
    demand_rs = demand.resample('5S',pd.np.max,closed='left')
    hvacs = get_hvacstates()
    for zone,hvac in hvacs.iteritems():
        # resample every minute
        hvac_rs = hvac.resample('5S',pd.np.max,closed='left')
        # join on the timestamps to filter out missing data
        merge = hvac_rs.merge(demand_rs, left_index=True, right_index=True)
        merge.columns = ['state','demand']
        yield zone, merge

def resample_and_merge_cumulative():
    """
    Adds the HVAC states together, does 5second resampling and returns a single dataframe
    """
    demand = get_demand()
    demand_rs = demand.resample('5S',pd.np.max,closed='left')
    cumulative = demand_rs.copy()
    cumulative[1] = 0
    cumulative[1] = cumulative[1].fillna(0)
    hvacs = get_hvacstates()
    for zone,hvac in hvacs.iteritems():
        # resample every minute
        hvac_rs = hvac.resample('5S',pd.np.max,closed='left')
        # join on the timestamps to filter out missing data
        merge = hvac_rs.merge(demand_rs, left_index=True, right_index=True)
        merge.columns = ['state','demand']
        cumulative[1] += hvac_rs[1].fillna(0)
    merge['state'] = cumulative
    return merge

def plot_zones():
    for zone, merge in resample_and_merge():
        merge.plot(figsize=(30,10)).get_figure().savefig('{0}.png'.format(zone))

def plot_cumulative():
    merge = resample_and_merge_cumulative()
    merge.plot(figsize=(30,10)).get_figure().savefig('cumulative.png')

if __name__ == '__main__':
    #for zone, merge in resample_and_merge():
    #    merge = merge.dropna(how='any')
    #    idxs = group_contiguous(merge, 'state', 4)
    #    for idx in idxs:
    #        mean_demand = merge.iloc[idx[1]:idx[2]]['demand'].mean()
    #        before_demand = merge.iloc[idx[0]]['demand']
    #        after_demand = merge.iloc[idx[3]]['demand']
    #        print 'Mean during: {0}, Before: {1}, After: {2}, Samples: {3}'.format(mean_demand, before_demand, after_demand, idx[2]-idx[1])
    merge = resample_and_merge_cumulative()
    merge = merge.dropna(how='any')
    idxs = group_contiguous(merge, 'state', 0)
    for idx in idxs:
        mean_demand = merge.iloc[idx[1]:idx[2]]['demand'].mean()
        before_demand = merge.iloc[idx[0]]['demand']
        after_demand = merge.iloc[idx[3]]['demand']
        print 'State: {0}, Mean during: {1}, Before: {2}, After: {3}, Samples: {4}'.format(idx[4], mean_demand, before_demand, after_demand, idx[2]-idx[1])
    plot_cumulative()
