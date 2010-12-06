#!/usr/bin/env python
import sys
import logging
import argparse

from pymongo.son import SON

import urllib
import urllib2_file
import urllib2

from fiftystates.backend import db, fs
from fiftystates.backend.utils import base_arg_parser


def import_versions(state, solr_url="http://localhost:8983/solr/"):
    for bill in db.bills.find({'state': state}):
        for version in bill['versions']:
            if 'document_id' not in version:
                continue

            doc = fs.get(version['document_id'])

            params = {}
            params['literal.bill_id'] = doc.metadata['bill']['bill_id']
            params['literal.state'] = doc.metadata['bill']['state']
            params['literal.chamber'] = doc.metadata['bill']['chamber']
            params['literal.bill_title'] = (
                doc.metadata['bill']['title'].encode('ascii', 'replace'))
            params['literal.document_name'] = doc.metadata['name']
            params['literal.url'] = doc.metadata['url']
            params['literal.id'] = version['document_id']
            params['commit'] = 'false'

            url = "%supdate/extract?%s" % (solr_url, urllib.urlencode(params))
            req = urllib2.Request(url, {'file': doc})
            urllib2.urlopen(req)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        parents=[base_arg_parser],
        description="Download and store copies of bill versions.")
    parser.add_argument('-u', '--url', type=str, dest='url',
                        default='http://localhost:8983/solr/',
                        help='the solr instance URL')

    args = parser.parse_args()

    verbosity = {0: logging.WARNING,
                 1: logging.INFO}.get(args.verbose, logging.DEBUG)

    logging.basicConfig(level=verbosity,
                        format=("%(asctime)s %(name)s %(levelname)s " +
                                args.state + " %(message)s"),
                        datefmt="%H:%M:%S")

    import_versions(args.state, args.url)
