import re
import datetime

from fiftystates.backend import db
from fiftystates.site.geo.models import District
from fiftystates.utils import keywordize

from django.http import HttpResponse

import pymongo

from piston.utils import rc
from piston.handler import BaseHandler, HandlerMetaClass

import pysolr
from jellyfish import levenshtein_distance

try:
    import json
except ImportError:
    import simplejson as json


_chamber_aliases = {
    'assembly': 'lower',
    'house': 'lower',
    'senate': 'upper',
    }

solr = pysolr.Solr("http://localhost:8983/solr/")


class FiftyStateHandlerMetaClass(HandlerMetaClass):
    """
    Returns 404 if Handler result is None.
    """
    def __new__(cls, name, bases, attrs):
        new_cls = super(FiftyStateHandlerMetaClass, cls).__new__(
            cls, name, bases, attrs)

        if hasattr(new_cls, 'read'):
            old_read = new_cls.read

            def new_read(*args, **kwargs):
                obj = old_read(*args, **kwargs)
                if isinstance(obj, HttpResponse):
                    return obj

                if obj is None:
                    return rc.NOT_FOUND

                return obj

            new_cls.read = new_read

        return new_cls


class FiftyStateHandler(BaseHandler):
    """
    Base handler for the Fifty State API.
    """
    __metaclass__ = FiftyStateHandlerMetaClass
    allowed_methods = ('GET',)


class MetadataHandler(FiftyStateHandler):
    def read(self, request, state):
        """
        Get metadata about a state legislature.
        """
        return db.metadata.find_one({'_id': state.lower()})


class BillHandler(FiftyStateHandler):
    def read(self, request, state, session, bill_id, chamber=None):
        query = {'state': state.lower(), 'session': session,
                 'bill_id': bill_id}
        if chamber:
            query['chamber'] = chamber.lower()
        return db.bills.find_one(query)


class BillSearchHandler(FiftyStateHandler):
    def read(self, request):
        _filter = {}

        for key in ('state', 'chamber'):
            try:
                _filter[key] = request.GET[key]
            except KeyError:
                pass

        # process search_window
        search_window = request.GET.get('search_window', '').lower()
        if search_window:
            if search_window == 'session':
                _filter['current_session'] = 'true'
            elif search_window == 'term':
                _filter['current_term'] = 'true'
            elif search_window.startswith('session:'):
                _filter['session'] = '"%s"' % search_window.split(
                    'session:')[1]
            elif search_window.startswith('term:'):
                _filter['term'] = '"%s"' % search_window.split('term:')[1]
            elif search_window == 'all':
                pass
            else:
                resp = rc.BAD_REQUEST
                resp.write(": invalid search_window. Valid choices are "
                           "'term', 'session' or 'all'")
                return resp

        # process updated_since
        since = request.GET.get('updated_since')
        if since:
            try:
                since = datetime.datetime.strptime(since, "%Y-%m-%d %H:%M")
            except ValueError:
                try:
                    since = datetime.datetime.strptime(since, "%Y-%m-%d")
                except ValueError:
                    resp = rc.BAD_REQUEST
                    resp.write(": invalid updated_since parameter."
                    " Please supply a date in YYYY-MM-DD format.")
                    return resp

            _filter['updated_at_dt'] = "[%sZ TO *]" % since.isoformat()

        fq = " ".join(["+%s:%s" % (key, value)
                       for (key, value) in _filter.items()])

        results = solr.search(request.GET.get('q', ''), fq=fq, rows=100)
        return list(results)


class LegislatorHandler(FiftyStateHandler):
    def read(self, request, id):
        return db.legislators.find_one({'_all_ids': id})


class LegislatorSearchHandler(FiftyStateHandler):
    def read(self, request):
        legislator_fields = {'sources': 0, 'roles': 0}

        _filter = _build_mongo_filter(request, ('state', 'first_name',
                                               'last_name'))
        elemMatch = _build_mongo_filter(request, ('chamber', 'term',
                                                  'district', 'party'))
        _filter['roles'] = {'$elemMatch': elemMatch}

        active = request.GET.get('active')
        if not active and 'term' not in request.GET:
            # Default to only searching active legislators if no term
            # is supplied
            _filter['active'] = True
        elif active:
            _filter['active'] = (active.lower() == 'true')

        return list(db.legislators.find(_filter, legislator_fields))


class LegislatorGeoHandler(FiftyStateHandler):
    def read(self, request):
        try:
            districts = District.lat_long(request.GET['lat'],
                                          request.GET['long'])

            filters = []
            for d in districts:
                filters.append({'state': d.state_abbrev,
                                'roles': {'$elemMatch': {
                                    'district': d.name,
                                    'chamber': d.chamber}}})

            if not filters:
                return []

            return list(db.legislators.find({'$or': filters}))
        except KeyError:
            resp = rc.BAD_REQUEST
            resp.write(": Need lat and long parameters")
            return resp


class CommitteeHandler(FiftyStateHandler):
    def read(self, request, id):
        return db.committees.find_one({'_all_ids': id})


class CommitteeSearchHandler(FiftyStateHandler):
    def read(self, request):
        committee_fields = {'members': 0, 'sources': 0}

        _filter = _build_mongo_filter(request, ('committee', 'subcommittee',
                                                'chamber', 'state'))
        return list(db.committees.find(_filter, committee_fields))


class StatsHandler(FiftyStateHandler):
    def read(self, request):
        counts = {}

        # db.counts contains the output of a m/r run that generates
        # per-state counts of bills and bill sub-objects
        for count in db.counts.find():
            val = count['value']
            state = count['_id']

            if state == 'total':
                val['legislators'] = db.legislators.count()
                val['documents'] = db.documents.files.count()
            else:
                val['legislators'] = db.legislators.find(
                    {'roles.state': state}).count()
                val['documents'] = db.documents.files.find(
                    {'metadata.bill.state': state}).count()

            counts[state] = val

        stats = db.command('dbStats')
        stats['counts'] = counts

        return stats


class EventsHandler(FiftyStateHandler):
    def read(self, request, id=None, events=[]):
        if events:
            return events

        if id:
            return db.events.find_one({'_id': id})

        spec = {}

        for key in ('state', 'type'):
            value = request.GET.get(key)
            if not value:
                continue

            split = value.split(',')

            if len(split) == 1:
                spec[key] = value
            else:
                spec[key] = {'$in': split}

        return list(db.events.find(spec).sort(
            'when', pymongo.DESCENDING).limit(20))


class ReconciliationHandler(BaseHandler):
    """
    An endpoint compatible with the Google Refine 2.0 reconciliation API.

    Given a query containing a legislator name along with some optional
    filtering properties ("state", "chamber"), this handler will return
    a list of possible matching legislators.

    See http://code.google.com/p/google-refine/wiki/ReconciliationServiceApi
    for the API specification.
    """
    allowed_methods = ('GET', 'POST')

    metadata = {
        "name": "Open State Reconciliation Service",
        "view": {
            "url": "http://localhost:8000/api/v1/legislators/preview/{{id}}/",
            },
        "preview": {
            "url": "http://localhost:8000/api/v1/legislators/preview/{{id}}/",
            "width": 430,
            "height": 300
            },
        "defaultTypes": [
            {"id": "/openstates/legislator",
             "name": "Legislator"}],
        }

    def read(self, request):
        return self.reconcile(request)

    def create(self, request):
        return self.reconcile(request)

    def reconcile(self, request):
        query = request.GET.get('query') or request.POST.get('query')

        if query:
            # If the query doesn't start with a '{' then it's a simple
            # string that should be used as the query w/ no extra params
            if not query.startswith("{"):
                query = '{"query": "%s"}' % query
            query = json.loads(query)

            return {"result": self.results(query)}

        # Batch query mode
        queries = request.GET.get('queries') or request.POST.get('queries')

        if queries:
            queries = json.loads(queries)
            ret = {}
            for key, value in queries.items():
                ret[key] = {'result': self.results(value)}

            return ret

        # If no queries, return metadata
        return self.metadata

    def results(self, query):
        # Look for the query to be a substring of a legislator name
        # (case-insensitive)
        pattern = re.compile(".*%s.*" % query['query'],
                             re.IGNORECASE)

        spec = {'full_name': pattern}

        for prop in query.get('properties', []):
            # Allow filtering by state or chamber for now
            if prop['pid'] in ('state', 'chamber'):
                spec[prop['pid']] = prop['v']

        legislators = db.legislators.find(spec)

        results = []
        for leg in legislators:
            if legislators.count() == 1:
                match = True
                score = 100
            else:
                match = False
                if leg['last_name'] == query['query']:
                    score = 90
                else:
                    distance = levenshtein_distance(leg['full_name'].lower(),
                                                    query['query'].lower())
                    score = 100.0 / (1 + distance)

            # Note: There's a bug in Refine that causes reconciliation
            # scores to be overwritten if the same legislator is returned
            # for multiple queries. see:
            # http://code.google.com/p/google-refine/issues/detail?id=185

            results.append({"id": leg['_id'],
                            "name": leg['full_name'],
                            "score": score,
                            "match": match,
                            "type": [
                                {"id": "/openstates/legislator",
                                 "name": "Legislator"}]})

        return sorted(results, cmp=lambda l, r: cmp(r['score'], l['score']))
