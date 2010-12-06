from fiftystates.scrape import NoDataForPeriod
from fiftystates.scrape.committees import CommitteeScraper, Committee
from lxml import etree, html
from fiftystates.scrape.az import utils
from scrapelib import HTTPError
import re, datetime

base_url = 'http://www.azleg.gov/'

class AZCommitteeScraper(CommitteeScraper):
    state = 'az'
    parties = {
        'R': 'Republican',
        'D': 'Democrat',
        'L': 'Libertarian',
        'I': 'Independant',
        'G': 'Green Party'
    }
    def get_party(self, abbr):
        return self.parties[abbr]
        
    def get_session_for_term(self, term):
        return self.metadata['terms'][-1]['sessions'][-1]
        
    def get_session_id(self, session):
        return self.metadata['session_details'][session]['session_id']
        
    def scrape(self, chamber, term):
        session = self.get_session_for_term(term)
        try:
            session_id = self.get_session_id(session)
        except KeyError:
            raise NoDataForPeriod
        
        # not getting the floor committees maybe try it during the new session
        # for committee_type in ('S', 'F'):
        #     self.scrape_index(chamber, session, session_id, committee_type)
        
        url = base_url + 'xml/committees.asp?session=%s' % session_id
        
        with self.urlopen(url) as page:
            root = etree.fromstring(page, etree.XMLParser(recover=True))
            
            body = '//body[@Body="%s"]/committee' % {'upper': 'S',
                                                     'lower': 'H'}[chamber]
            for com in root.xpath(body):
                c_id, name, short_name, sub = com.values()
                print sub
                if sub == '1':
                    print sub
                    parent = name.split('Subcommittee')[0].strip()
                    name = name[name.index('Subcommittee'):]
                    
                    c = Committee(chamber, committee=parent, short_name=short_name, 
                              sub_committee=name, session=session,
                              az_committee_id=c_id)
                else:
                    c = Committee(chamber, name, short_name=short_name, 
                                  session=session, az_committee_id=c_id)
                                  
                c.add_source(url)
                #for some reason they don't always have any info on the committees'
                try:
                    self.scrape_com_info(session, session_id, c_id, c)
                except HTTPError:
                    pass
                
                self.save_committee(c)
            
    def scrape_com_info(self, session, session_id, committee_id, committee):
        url = base_url + 'CommitteeInfo.asp?Committee_ID=%s&Session_ID=%s'
        
        with self.urlopen(url % (committee_id, session_id)) as page:
            committee.add_source(url)
            root = html.fromstring(page)
            p = '//table/tr/td[1]/a/ancestor::tr[1]'
            rows = root.xpath(p)
            #need to skip the first row cause its a link to the home page
            for row in rows[1:]:
                name = row[0].text_content().strip()
                role = row[1].text_content().strip()
                committee.add_member(name, role)
                
    def scrape_index(self, chamber, session, session_id, committee_type):
        url = base_url + 'xml/committees.asp?session=%s&type=%s'
        
        with self.urlopen(url % (session_id, committee_type)) as page:
            root = etree.fromstring(page, etree.XMLParser(recover=True))
            
            body = '//body[@Body="%s"]/committee' % {'upper': 'S',
                                                     'lower': 'H'}[chamber]
            # TODO need to and make sure to add sub committees
            for com in root.xpath(body):
                c_id, name, short_name, sub = com.values()
                c = Committee(chamber, name, short_name=short_name, 
                              session=session, az_committee_id=c_id)
                c.add_source(url)
                self.scrape_com_info(session, session_id, c_id, c)
                self.save_committee(c)
