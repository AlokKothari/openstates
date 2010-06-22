from __future__ import with_statement
import os

try:
    import json
except ImportError:
    import simplejson as json

from fiftystates.scrape import Scraper, FiftystatesObject, JSONDateEncoder


class LegislatorScraper(Scraper):
    def scrape(self, chamber, year):
        """
        Grab all the legislators who served in a given year. Must be
        overridden by subclasses.

        Should raise a :class:`NoDataForYear` exception if the year is invalid.
        """
        raise NotImplementedError('LegislatorScrapers must define a '
                                  'scrape method')

    def save_person(self, person):
        """
        Save a scraped :class:`pyutils.legislation.Person` object. Only
        call after all data for the given person has been collected.

        Should be used for non-legislator people (e.g. Governor, Lt. Gov).
        To add :class:`pyutils.legislation.Legislator` objects call
        :meth:`pyutils.legislation.save_legislator`.
        """
        self.log("save_person: %s" % person['full_name'])

        person['state'] = self.state

        role = person['roles'][0]
        filename = "%s_%s.json" % (role['session'],
                                   person['full_name'])
        filename = filename.encode('ascii', 'replace')

        with open(os.path.join(self.output_dir, "legislators", filename),
                  'w') as f:
            json.dump(person, f, cls=JSONDateEncoder)

    def save_legislator(self, legislator):
        """
        Save a scraped :class:`pyutils.legislation.Legislator` object.
        Only call after all data for the given legislator has been collected.
        """
        self.log("save_legislator: %s" % legislator['full_name'])

        role = legislator['roles'][0]
        legislator['state'] = self.state

        if self.use_mongo:
            from fiftystates.backend import db
            db["%s.legislators.scraped" % self.state].save(legislator)
        else:
            filename = "%s_%s_%s_%s.json" % (role['session'],
                                             role['chamber'],
                                             role['district'],
                                             legislator['full_name'])
            filename = filename.encode('ascii', 'replace')
            with open(os.path.join(self.output_dir, "legislators", filename),
                      'w') as f:
                json.dump(legislator, f, cls=JSONDateEncoder)


class Person(FiftystatesObject):
    def __init__(self, full_name, **kwargs):
        """
        Create a Person.

        Note: the :class:`pyutils.legislation.Legislator` class should
        be used when dealing with state legislators.

        :param full_name: the person's full name
        """
        super(Person, self).__init__('person', **kwargs)
        self['full_name'] = full_name
        self['roles'] = []

    def add_role(self, role, session, start_date=None, end_date=None,
                 **kwargs):
        """
        If ``start_date`` or ``end_date`` are ``None``, they will default
        to the start/end date of the given legislative session.

        Examples:

        leg.add_role('member', session='2009', chamber='upper',
                     party='Republican', district='10th')
        """
        self['roles'].append(dict(role=role, session=session,
                                  start_date=start_date,
                                  end_date=end_date, **kwargs))


class Legislator(Person):
    def __init__(self, session, chamber, district, full_name,
                 first_name='', last_name='', middle_name='',
                 party='', **kwargs):
        """
        Create a Legislator.

        :param session: the session in which this legislator served
        :param chamber: the chamber in which this legislator served,
          'upper' or 'lower'
        :param district: the district this legislator is representing, as given
          by the state, e.g. 'District 2', '7th', 'District C'.
        :param full_name: the full name of this legislator
        :param first_name: the first name of this legislator (if specified)
        :param last_name: the last name of this legislator (if specified)
        :param middle_name: a middle name or initial of this legislator
          (if specified)
        :param party: the party this legislator belongs to (if specified)

        Note: please only provide the first_name, middle_name and last_name
        parameters if they are listed on the state's web site; do not
        try to split the legislator's full name into components yourself.

        Any additional keyword arguments will be associated with this
        Legislator and stored in the database.
        """
        super(Legislator, self).__init__(full_name, **kwargs)
        #self['type'] = 'legislator'
        self.add_role('member', session, chamber=chamber, district=district,
                      party=party)
        self['first_name'] = first_name
        self['last_name'] = last_name
        self['middle_name'] = middle_name
