import json
import os
import getpass
import urllib.parse

import requests
import requests.utils
from lxml import html

PATH = os.getcwd()
COOKIES_FILE = os.path.join(PATH, "cookies.json")

UALBERTA_APPS_URL = "https://apps.ualberta.ca"

ECLASS_BASE_URL = "https://eclass.srv.ualberta.ca"


class eClass:

    def __init__(self):
        print("Checking cookies")

        self.session = requests.Session()

        self.try_login()

        response = self.session.get(ECLASS_BASE_URL + "/my")

        if response.url != ECLASS_BASE_URL + "/my" and response.url != ECLASS_BASE_URL + "/my/":
            print("Login failed.")
            exit(-1)

    def get_courses(self):
        homepage = self.session.get(ECLASS_BASE_URL + "/my")
        page_tree = html.fromstring(homepage.content)
        course_elems = page_tree.xpath(r'//div[contains(@class, "currentcourse")]')

        "/html/body/div[3]/div[3]/div/div/section[1]/div/aside/section/div/div/div[2]/div[1]/div/h3/a"
        return course_elems

    def try_login(self):
        if os.path.isfile(COOKIES_FILE):
            with open(COOKIES_FILE) as cookies:
                self.cookies = requests.utils.cookiejar_from_dict(json.load(cookies))
                self.session.cookies.update(self.cookies)

        response = self.session.get(ECLASS_BASE_URL + "/my")

        if "login.ualberta.ca" in response.url:
            # Cookies out of date or nonexistent
            print("Need to log in. Please input your username and password.")
            username = input("Username: ")
            password = getpass.getpass("Password: ")

            # Grab hidden input
            login_tree = html.fromstring(response.content)

            hidden_elements = login_tree.xpath(r'//form//input[@type="hidden"]')
            payload = {item.attrib['name']: item.attrib['value'] for item in hidden_elements}

            payload['username'] = username
            payload['password'] = password

            saml_redirect = self.session.post(response.url, data=payload)

            redirect_tree = html.fromstring(saml_redirect.content)

            redirect_target = redirect_tree.xpath(r'//form//@action')
            redirect_elements = redirect_tree.xpath(r'//form//input[@type="hidden"]')
            redirect_payload = {item.attrib['name']: item.attrib['value'] for item in redirect_elements}

            self.session.post(redirect_target[0], data=redirect_payload)

            with open(COOKIES_FILE, 'w') as cookies:
                json.dump(requests.utils.dict_from_cookiejar(self.session.cookies), cookies)
        pass


if __name__ == "__main__":
    eclass = eClass()

    for course in eclass.get_courses():
        print(course)

