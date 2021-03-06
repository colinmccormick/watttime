# Copyright wattTime 2013
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
# Authors: Sunil Abraham, Eric Stansifer, Sam Marcellus, Anna Schneider


import dateutil.parser
import requests
import StringIO
import urllib2
import zipfile
import datetime
import pytz
import pandas

from windfriendly.models import BPA, NE, CAISO, MeterReading, User, MARGINAL_FUELS, FORECAST_CODES

import xml.etree.ElementTree as ET

from django.core.exceptions import ObjectDoesNotExist

class UtilityParser():
    """Base class for utility/balancing authority data scrapers and parsers"""
    #### interface: implement these in derived classes

    def __init__(self):
        self.MODEL = None
        
    def update(self):
        """Scrape and store latest data"""
        pass
    
    def datapoint_to_db(self, dp):
        """Store data in the database and return success code"""
        return False
        
    def scrape(self, **kwargs):
        """Get data from web and return a file buffer or StringIO"""
        return None
        
    def parse(self, streams):
        """Parse list of data streams and return a time-sorted list of dicts,
            datapoint[k]=v
        """
        return [{}]
    
    #### helper functions
    
    def today(self, tz):
        now = datetime.datetime.today()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)
        return tz.localize(today)

    def tomorrow(self, tz):
        return self.today(tz) + datetime.timedelta(1)

class CAISOParser(UtilityParser):
    def __init__(self):
        self.MODEL = CAISO
        self.CAISO_BASE_URL = 'http://oasis.caiso.com/mrtu-oasis/SingleZip'
        self.BASE_PAYLOAD = {'resultformat': '6'}
        self.TOTAL_CODE = 'SLD_FCST'
        self.CLEAN_CODE = 'SLD_REN_FCST'
        self.ACTUAL_CODE = 'ACTUAL'
        self.FRCST_CODE = 'DAM'
        self.HRAHEAD_CODE = 'HASP'
        self.DATE_FRMT = '%Y%m%d'
        self.TZ = pytz.timezone('US/Pacific')
        
    def update(self):
        # figure out dates to pull for
        dates_to_update = {self.ACTUAL_CODE : self.today(self.TZ),
                           self.FRCST_CODE : self.tomorrow(self.TZ),
                           self.HRAHEAD_CODE : self.today(self.TZ),
                          }
                          
        # return data
        to_return = {}
        
        # update each forecast type
        for forecast_code in [self.ACTUAL_CODE, self.FRCST_CODE]:
            # scrape and parse data
            streams = self.scrape_all(forecast_code,
                                      dates_to_update[forecast_code],
                                      dates_to_update[forecast_code])
            datapoints = self.parse(streams)
            
            # save to db
            old_latest_date = self.MODEL.latest_date(forecast_code)
            n_stored_points = 0
            for dp in datapoints:
                success = self.datapoint_to_db(dp)
                if success:
                    n_stored_points += 1
            new_latest_date = self.MODEL.latest_date(forecast_code)

            # log
            to_return[forecast_code] = {'prior_latest_date' : str(old_latest_date),
                                        'update_rows' : n_stored_points,
                                        'latest_date' : str(new_latest_date),
                                        }
        
        # return
        return to_return

    def _date_gen(self, start_date, end_date):
        if start_date == end_date:
            yield start_date
        while start_date < end_date:
            yield start_date
            start_date = start_date + datetime.timedelta(1)

    def scrape_all(self, forecast_type, start_date, end_date):
        """ Gets all data for this forecast type
                for dates between start and end (inclusive).
            Returns a dictionary with 
            streams[(energy_type, forecast_type, date)] = stream
        """
        streams = {}
        for energy_type in [self.TOTAL_CODE, self.CLEAN_CODE]:
            for date in self._date_gen(start_date, end_date):
                stream = self.scrape(energy_type, forecast_type, date, date)
                streams[(energy_type, forecast_type, date)] = stream
        return streams
                                   
    def scrape(self, energy_type, forecast_type, start_date, end_date):
        """ Queries the CAISO API and returns a ZipExtFile
            (file-like, supports read()) containing the requested data
        """
        # set up get request
        payload = {'queryname': energy_type,
                   'market_run_id': forecast_type,
                   'startdate': start_date.strftime(self.DATE_FRMT),
                   'enddate': end_date.strftime(self.DATE_FRMT),
                  }
        payload.update(self.BASE_PAYLOAD)
 
        # try get
        try: 
            r = requests.get(self.CAISO_BASE_URL, params=payload) # have request
        except requests.exceptions.RequestException, e:
            raise Exception('unable to get CAISO data' + str(e))
            
        # read data from zip
        z = zipfile.ZipFile(StringIO.StringIO(r.content)) # have zipfile
        f = z.read(z.namelist()[0]) # have csv
        z.close()
        
        # return file-like object
        stream = StringIO.StringIO(f)
        return stream
                        
    def _is_energy_header(self, key):
        # energy columns have header HEXX
        if key[:2] == 'HE':
            if self._header_to_hour(key) < 24:
                return True
        return False
        
    def _header_to_hour(self, key):
        # 0 to 24
        return int(key[2:])-1
        
    def _extract_values(self, energy_type, forecast_type, vals, total_index=None):
        # set up storage
        data_dict = {}
        
        # get any interesting info for this energy and forecast type
        data_dict['forecast_type'] = forecast_type
        if energy_type == self.TOTAL_CODE:
            if total_index is not None:
                data_dict['load'] = vals[total_index]
            else:
                data_dict['load'] = sum(vals)
        elif energy_type == self.CLEAN_CODE:
            data_dict['solar'] = vals[0] + vals[2]
            data_dict['wind'] = vals[1] + vals[3]
        else:
            raise ValueError("bad energy type %s" % energy_type)
            
        # return
        return data_dict

    def parse(self, streams):
        # set up storage
        # datapoints[timestamp] = datapoint
        datapoints = {}
        
        # parse all streams
        for streamkey, stream in streams.iteritems():
            
            # unpack streamkey
            energy_type, forecast_type, date = streamkey
            
            # load stream into dataframe
            # TODO: check for non-csv content here! and return without updating if error
            df = pandas.read_csv(stream, lineterminator='\n')
            
            # if total, get row number to use
            if energy_type == self.TOTAL_CODE:
                try:
                    tac_col = df['TAC_AREA_NAME']
                except KeyError:
                    raise KeyError('no tac found for %s %s' % (energy_type, forecast_type))
                total_index = tac_col.index[tac_col == 'CA ISO-TAC']
            else:
                total_index = None
            
            # parse dataframe columns
            for header, vals in df.iteritems():
                if self._is_energy_header(header):
                    
                    # set up storage for hourly energy data
                    hour = self._header_to_hour(header)
                    timestamp = date.replace(hour=hour)
                    if timestamp not in datapoints:
                        datapoints[timestamp] = {'timestamp' : timestamp}
                        
                    # extract and store the data
                    data_dict = self._extract_values(energy_type, 
                                                     forecast_type, 
                                                     vals,
                                                     total_index)
                    datapoints[timestamp].update(data_dict)
                        
        # convert to list and return
        datapoints_list = datapoints.values()
        sorted_dps = sorted(datapoints_list, key=lambda x: x['timestamp'])
        return sorted_dps
        
    def datapoint_to_db(self, dp):
        """Store data in the CAISO database and return success code"""
        if self._is_datapoint_to_store(dp):
            row = self.MODEL()
            row.load = dp['load']  
            row.wind = dp['wind']
            row.solar = dp['solar']
            row.forecast_code = FORECAST_CODES[dp['forecast_type']]
            row.date = dp['timestamp']
            row.date_extracted = pytz.utc.localize(datetime.datetime.now())
            row.save()
            return True
        else:
            return False
            
    def _is_datapoint_to_store(self, dp):
        """Returns bool for whether or not to store this data point in db"""
        # reject if invalid data
        if not dp['load'] > 0:
            return False
            
        if dp['forecast_type'] == self.ACTUAL_CODE:
            # only store past data for actual
            latest = self.MODEL.latest_date(self.ACTUAL_CODE)
            if latest:
                if dp['timestamp'] > latest:
                    return True # this is new data
                else:
                    return False # this is old data
            else:
                return True # no existing data
                
        else:
            # any time is ok for forecasts
            return True
            

class BPAParser(UtilityParser):
    def __init__(self, url = None):
        self.MODEL = BPA
        self.BPA_LOAD_URL = url or 'http://transmission.bpa.gov/business/operations/wind/baltwg.txt'
        #If we're pulling historical data, ignore latest
        if url is None:
            self.update_latest = True
        else:
            self.update_latest = False
        self.BPA_LOAD_NCOLS = 5
        self.BPA_LOAD_SKIP_LINES = 7

        self.BPA_OVERSUPPLY_URL = 'http://transmission.bpa.gov/business/operations/wind/twndbspt.txt'
        self.BPA_OVERSUPPLY_NCOLS = 4
        self.BPA_OVERSUPPLY_SKIP_LINES = 11

    def getData(self, url):
        # Make request for data
        try:
            data = requests.get(url).text
        except requests.exceptions.RequestException:
            data = urllib2.urlopen(url).read()
            #raise Exception('unable to get BPA data' + str(e))
        return data

    def parseDate(self, datestring):
        tzd = {
            'PST': -28800,
            'PDT': -25200,
        }
        tz = pytz.timezone('US/Pacific')
        dt = dateutil.parser.parse(datestring, tzinfos=tzd)
        if dt.tzinfo == None:
            dt = dt.replace(tzinfo = tz)
        dt = dt.astimezone(pytz.UTC)
        return dt

    def parseLoadRow(self, row):
        fields = row.split('\t')
        res = {'date': self.parseDate(fields[0])}
        if len(fields) == 5:
            try:
                [total, wind, hydro, thermal]  = [int(x) for x in fields[1:]]
            except:
                return res
            res.update({'wind': wind, 'hydro': hydro, 'thermal': thermal,
                        'total': total})
            return res
        else:
            return res

    def parseOversupplyRow(self, row):
        fields = row.split('\t')
        res = {'date': self.parseDate(fields[0])}
        if len(fields) == 4:
            [basepoint, wind, oversupply] = [int(x) for x in fields[1:]]
            res.update({'basepoint': basepoint, 'wind': wind,
                        'oversupply': oversupply})
            return res
        else:
            return res

    def rowIsAfterDate(self, row, date):
        row_date = row['date']
        return row_date > date

    def rowHasAllCols(self, row, ncols):
        return len(row) == ncols

    def isGoodRow(self, row, ncols, date=None):
        if date:
            return (self.rowHasAllCols(row, ncols) and self.rowIsAfterDate(row, date))
        else:
            return self.rowHasAllCols(row, ncols)

    def parse(self, url, parse_row_fn, skip_lines, ncols, latest_date=None):
        data = self.getData(url)
        # First skip_lines lines are boilerplate text, last line is blank
        rows = data.split('\r\n')[skip_lines:-1]
        parsed_rows = [parse_row_fn(row) for row in rows]
        res = filter(lambda x: self.isGoodRow(x, ncols, latest_date), parsed_rows)
        return res

    def parseBPALoad(self, latest_date=None):
        return self.parse(self.BPA_LOAD_URL, self.parseLoadRow,
                     self.BPA_LOAD_SKIP_LINES, self.BPA_LOAD_NCOLS,
                     latest_date)

    def parseBPAOversupply(self, latest_date=None):
        return self.parse(self.BPA_OVERSUPPLY_URL, self.parseOversupplyRow,
                     self.BPA_OVERSUPPLY_SKIP_LINES, self.BPA_OVERSUPPLY_NCOLS,
                     latest_date)

    def zipTables(self, table_a, table_b):
        max_index = reduce(min, map(len, [table_a, table_b]))
        res = []
        for i in xrange(max_index):
            res.append(dict(table_a[i].items() + table_b[i].items()))
        return res

    def getBPA(self, latest_date=None):
        parsed_load = self.parseBPALoad(latest_date)
        return parsed_load

    def writeBPA(self, row):
        b = BPA()
        b.date = row['date']
        b.load = row['total']
        b.wind = row['wind']
        b.hydro = row['hydro']
        b.thermal = row['thermal']
        b.save()

    def update(self):
        latest_date = self.MODEL.latest_date() if self.update_latest else None
        update = self.getBPA(latest_date)
        for row in update:
            self.writeBPA(row)
        return {
          'prior_latest_date' : str(latest_date),
          'update_rows' : len(update),
          'latest_date' : str(self.MODEL.latest_date())
        }


# This was written to imitate the BPA Parser somewhat
class NEParser(UtilityParser):
    def __init__(self, request_method = None):
        self.MODEL = NE
        if request_method is None:
            url = 'http://isoexpress.iso-ne.com/ws/wsclient'
            payload = {'_ns0_requestType':'url', '_ns0_requestUrl':'/genfuelmix/current'}
            def wrapper():
                return requests.post(url, data = payload).json()
            self.request_method = wrapper
        else:
            self.request_method = request_method

    def update(self):
        try:
            json = self.request_method()[0]['data']['GenFuelMixes']['GenFuelMix']

            timestamp = None
            ne = self.MODEL()
            ne.gas = 0
            ne.nuclear = 0
            ne.hydro = 0
            ne.coal = 0
            ne.other_renewable = 0
            ne.other_fossil = 0

            marginal_fuel = len(MARGINAL_FUELS) - 1

            for i in json:
                if timestamp is None:
                    timestamp = i['BeginDate']

                fuel = i['FuelCategory']
                gen = i['GenMw']

                if fuel == 'Natural Gas':
                    ne.gas += gen
                elif fuel == 'Nuclear':
                    ne.nuclear += gen
                elif fuel == 'Hydro':
                    ne.hydro += gen
                elif fuel == 'Coal':
                    ne.coal += gen
                # I don't really know how I should be placing some of these fuels
                elif fuel == 'Oil' or fuel == 'Landfill Gas' or fuel == 'Refuse':
                    ne.other_fossil += gen
                elif fuel == 'Wind' or fuel == 'Wood':
                    ne.other_renewable += gen
                else: # Unrecognized fuel
                    ne.other_fossil += gen

                if i['MarginalFlag'] == 'Y':
                    if fuel in MARGINAL_FUELS:
                        marginal_fuel = min(marginal_fuel, MARGINAL_FUELS.index(fuel))

            ne.marginal_fuel = marginal_fuel

            if timestamp is None:
                ne.date = None # Is this okay? Don't know.
            else:
                ne.date = dateutil.parser.parse(timestamp)

            ne.save()

        except requests.exceptions.RequestException: # failed to get data
            pass
        except KeyError: # malformed json format
            pass
        except IndexError: # malformed json format
            pass
        except ValueError: # failed to parse time
            pass

        return {}

class UserDataParser:
    pass

class GreenButtonParser(UserDataParser):
    def __init__(self, xml_file, uid):
        self.uid = uid
        self.tree = ET.parse(urllib2.urlopen(xml_file))
        #self.ns = '{http://www.w3.org/2005/Atom}'
        self.ns ='{http://naesb.org/espi}'

    def parse(self):
        root = self.tree.getroot()
        for reading in root.iter(self.ns+'IntervalReading'):
            cost = reading.find(self.ns+'cost').text
            value = float(reading.find(self.ns+'value').text)/1000
            start = float(reading.find(self.ns+'timePeriod').find(self.ns+'start').text)
            start = datetime.datetime.fromtimestamp(start, pytz.UTC)
            duration = reading.find(self.ns+'timePeriod').find(self.ns+'duration').text

            yield {'cost':cost, 'value':value, 'start':start, 'duration':duration}
        

    def update(self):
        try:
            user = User.objects.get(pk = self.uid)
        except ObjectDoesNotExist: 
            print 'creating user'
            user = User.objects.create(name='New User')


        counter = 0
        for row in self.parse():
            existing = MeterReading.objects.filter(start = row['start'], userid=user)
            if existing.count() > 0:
                r = existing[0]
                if r.energy != row['value']:
                    r.energy = row['value']
                else:
                    continue
            else:
                r = MeterReading()
                r.userid = user
                r.cost = row['cost']
                r.energy = row['value']
                r.start = row['start']
                r.duration = row['duration']
            r.save()
            counter += 1
        return  {'added_count': counter, 'uid':self.uid}
