from fiftystates.scrape import ScrapeError, NoDataForPeriod
from fiftystates.scrape.votes import Vote
from fiftystates.scrape.bills import BillScraper, Bill
from fiftystates.scrape.hi.utils import BASE_URL, year_from_session

import lxml.html
import re
import datetime as dt

def versions_page_url(type, bill_number):
    return BASE_URL + '/session2009/getstatus.asp?query=' \
                         + type + bill_number + '&showtext=on&currpage=1'

def bills_url(chamber):
    if chamber == "upper":
            return (BASE_URL + "/session2009/lists/RptIntroSB.aspx", "HB")
    else:
            return (BASE_URL + "/session2009/lists/RptIntroSB.aspx", "SB")

def bill_url(link):
    return BASE_URL + "/session2009/lists/" + link

def bill_version_url(link):
    return "http://www.capitol.hawaii.gov/session2009/Bills/" + link


class HIBillScraper(BillScraper):
    state = 'hi'

    def scrape_votes(self, vote_text, vote_url, house, date, bill):
        votes_parts = vote_text.split(";")
        voters = []

        motion_text, sep, after = vote_text.partition(" The votes were as follows:")

        for vp in votes_parts:
            before, sep, after = vp.partition("(s)")
            voters_list = after.split(", ")
            voters_list[0] = voters_list[0].lstrip(" ")
            voters_list[-1] = voters_list[-1].rstrip(". ")
            voters.append(voters_list)

        #Ayes, Ayes with reservations, Noes, Excused

        vote_counts = [0, 0, 0, 0]

        for i, t in enumerate(votes_parts):
            match = re.search("[0-9]+", t)
            if (match != None):
                vote_counts[i] = int(match.group(0))

        if(house == 'H'):
            vote_house = "lower"
        else:
            vote_house = "upper"

        vote = Vote(vote_house, date, motion_text, True, \
                vote_counts[0], vote_counts[2], vote_counts[1] + vote_counts[3])
        vote.add_source(vote_url)

        for yes_voter in voters[0]:
            vote.yes(yes_voter)
        for no_voter in voters[2]:
            vote.no(no_voter)
        for other_voter in voters[1]:
            vote.other(other_voter)
        for other_voter in voters[2]:
            vote.other(other_voter)

        bill.add_vote(vote)

    def scrape(self, chamber, session):
        year = year_from_session(session)
        session = "%s-%d" % (year, int(year) + 1)

        if year >= 2009:
            self.scrape_session_2009(chamber, session)
        else:
            self.scrape_session_old(chamber, session)

    def scrape_session_2009(self, chamber, session):
        url, type = bills_url(chamber)

        with self.urlopen(url) as page_html:
            page = lxml.html.fromstring(page_html)
            for element, attribute, link, pos in page.iterlinks():
                if re.search("billtype=" + type + "&billnumber=[0-9]+", link) != None:
                    bill_page_url = bill_url(link)
                    with self.urlopen(bill_page_url) as bill_page_str:
                        bill_page = lxml.html.fromstring(bill_page_str)
                        splitted_link = link.split("=")
                        bill_number = splitted_link[-1]
                        bill_id = bill_page.cssselect('a[class="headerlink"]')
                        bill_id = bill_id[0]
                        bill_id = bill_id.text_content()
                        bill_title = bill_page.cssselect('td[style="color:Black"]')
                        bill_title = bill_title[0]
                        bill_title = bill_title.text_content()
                        bill = Bill(session, chamber, bill_id, bill_title)
                        bill.add_source(bill_page_url)

                        actions_table_list = bill_page.cssselect('table[rules="all"]')
                        actions_table = actions_table_list[0]
                        action_elements = actions_table.cssselect('tr')
                        # first element is not an action element
                        action_elements.pop(0)

                        for ae in action_elements:
                            action_element_parts = ae.cssselect('td')

                            action_date = action_element_parts[0]
                            actor_house = action_element_parts[1]
                            action_text = action_element_parts[2]

                            # look for acting comittees
                            match = re.search("(committee\(s\)|committee) on ([A-Z]{3}(/|-)[A-Z]{3}|[A-Z]{3})", action_text.text_content())

                            if(match != None):
                                actor = match.group(0)
                            elif(actor_house == 'H'):
                                actor = "lower"
                            elif (actor_house == 'S'):
                                actor = "upper"
                            else:
                                actor = chamber

                            action_date = dt.datetime.strptime(action_date.text_content(), '%m/%d/%Y')

                            if (re.search("The votes were as follows", action_text.text_content()) != None):
                                self.scrape_votes(action_text.text_content(), bill_page_url, actor_house, action_date, bill)

                            bill.add_action(actor, action_text, action_date)

                        with self.urlopen(versions_page_url(type, bill_number)) as versions_page_html:
                            versions_page = lxml.html.fromstring(versions_page_html)
                            versions_elements = versions_page.cssselect('span[class="searchtitle"]')
                            for ve in versions_elements:
                                element_text = ve.text_content()
                                version_name = element_text.rstrip("_.HTM")
                                bill.add_version(version_name, bill_version_url(element_text))

    def scrape_session_old(self, chamber, session):
        pass
