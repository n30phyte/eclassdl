import getpass
import json
import os
import re
import urllib.parse
import shutil
from random import randint
from time import sleep

import requests
import requests.utils
from lxml import html
from pathvalidate import sanitize_filename


# "\<div\sclass\=\"resourceworkaround\"\>Click\s\<a\shref=\"(.*)\"\sonclick\=\"this\.target=\'\_blank\'\"\>"gm

PATH = os.getcwd()
CACHE = "cache"
OUTPUT_FOLDER = "classes"
COOKIES_FILE = os.path.join(PATH, "cookies.json")

UALBERTA_APPS_URL = "https://apps.ualberta.ca"
ECLASS_BASE_URL = "https://eclass.srv.ualberta.ca"

EXTENSIONS = ["pdf", "txt", "sql", "doc"]
MIME_TYPES = ["application", "image", "text"]

# https://stackoverflow.com/questions/3173320/text-progress-bar-in-the-console
# Print iterations progress
def printProgressBar(
    iteration,
    total,
    prefix="",
    suffix="",
    decimals=1,
    length=100,
    fill="█",
    printEnd="\r",
):
    """
    Call in a loop to create terminal progress bar
    @params:
        iteration   - Required  : current iteration (Int)
        total       - Required  : total iterations (Int)
        prefix      - Optional  : prefix string (Str)
        suffix      - Optional  : suffix string (Str)
        decimals    - Optional  : positive number of decimals in percent complete (Int)
        length      - Optional  : character length of bar (Int)
        fill        - Optional  : bar fill character (Str)
        printEnd    - Optional  : end character (e.g. "\r", "\r\n") (Str)
    """
    percent = ("{0:." + str(decimals) + "f}").format(100 * (iteration / float(total)))
    filledLength = int(length * iteration // total)
    bar = fill * filledLength + "-" * (length - filledLength)
    print(f"\r{prefix} |{bar}| {percent}% {suffix}", end=printEnd)
    # Print New Line on Complete
    if iteration == total:
        print()


class eClass:
    progress = 0

    def __init__(self):
        print("Checking cookies")

        self.session = requests.Session()

        self.try_login()

        response = self.session.get(ECLASS_BASE_URL + "/my")

        if response.url != ECLASS_BASE_URL + "/my/":
            print("Login failed.")
            exit(-1)

        print("Logged in to eclass.")

    def get_courses(self):
        homepage = self.session.get(ECLASS_BASE_URL + "/my")
        page_tree = html.fromstring(homepage.content)
        course_elems = page_tree.xpath(r'//div[contains(@class, "currentcourse")]')

        courses = {}

        for element in course_elems:
            course = element.xpath(r".//a")[0]
            courses[course.attrib["title"]] = course.attrib["href"]

        return courses

    def try_login(self):
        if os.path.isfile(COOKIES_FILE):
            with open(COOKIES_FILE) as cookies:
                self.cookies = requests.utils.cookiejar_from_dict(json.load(cookies))
                self.session.cookies.update(self.cookies)
                self.session.cookies.clear_expired_cookies()

        try:
            response = self.session.get(ECLASS_BASE_URL + "/my")
        except:
            self.session.cookies.clear()
            response = self.session.get(ECLASS_BASE_URL + "/my")

        if "login.ualberta.ca" in response.url:
            # Cookies out of date or nonexistent
            print("Need to log in. Please input your username and password.")
            username = input("Username: ")
            password = getpass.getpass("Password: ")

            # Grab hidden input
            login_tree = html.fromstring(response.content)

            hidden_elements = login_tree.xpath(r'//form//input[@type="hidden"]')
            payload = {
                item.attrib["name"]: item.attrib["value"] for item in hidden_elements
            }

            payload["username"] = username
            payload["password"] = password

            saml_redirect = self.session.post(response.url, data=payload)

            redirect_tree = html.fromstring(saml_redirect.content)

            redirect_target = redirect_tree.xpath(r"//form//@action")
            redirect_elements = redirect_tree.xpath(r'//form//input[@type="hidden"]')
            redirect_payload = {
                item.attrib["name"]: item.attrib["value"] for item in redirect_elements
            }

            self.session.post(redirect_target[0], data=redirect_payload)

            with open(COOKIES_FILE, "w") as cookies:
                json.dump(
                    requests.utils.dict_from_cookiejar(self.session.cookies), cookies
                )

    def get_course_content(self, url):
        course_page = self.session.get(url)

        page_tree = html.fromstring(course_page.content)

        main_area = page_tree.xpath(r'//section[@id="region-main"]')

        links = set()

        for link in main_area[0].xpath(r".//a"):
            try:
                links.add(link.attrib["href"])
            except:
                None

        sub_links = set()

        for link in links:
            if re.search(r"mod/assign", link, re.IGNORECASE):
                sub_links.update(self.get_course_content(link))

        links.update(sub_links)

        pre_cleaned_links = [
            link
            for link in links
            if re.search(
                r"mod/resource|mod_label|introattachment|\.{}".format(
                    "|\.".join(EXTENSIONS)
                ),
                link,
                re.IGNORECASE,
            )
        ]

        cleaned_links = [
            link
            for link in pre_cleaned_links
            if not re.search(
                r"assignfeedback|assignsubmission",
                link,
                re.IGNORECASE,
            )
        ]

        return cleaned_links

    def download_course_content(self, course_name, links):
        name = "".join(course_name.split()[:2])
        download_dir = os.path.join(PATH, OUTPUT_FOLDER, name)
        cache_dir = os.path.join(download_dir, CACHE)
        if not os.path.exists(download_dir):
            os.makedirs(download_dir)
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        count = 0
        oldcount = 0
        maxcount = len(links)
        for item in links:
            printProgressBar(count, maxcount, prefix="Progress:", suffix="", length=50)
            oldcount = count
            count += 1

            download_redirect = False

            file_header = self.session.head(item, allow_redirects=True)
            if re.search(
                r"{}".format("|".join(MIME_TYPES)),
                file_header.headers.get("content-type"),
            ):
                filename = urllib.parse.unquote(file_header.url.split("/")[-1])
                filename = re.sub(r"\?time=\d*", "", filename)
                filename = re.sub(r"forcedownload=\d", "", filename)
                filename = sanitize_filename(filename)

                file_path = os.path.join(download_dir, filename)
                if re.search(
                    r"view\.php\?",
                    file_header.url,
                ):
                    download_redirect = True
                    file_path = os.path.join(cache_dir, filename)

                printProgressBar(
                    oldcount,
                    maxcount,
                    prefix="Progress:",
                    suffix="{:10.10}".format(filename),
                    length=50,
                )

                with self.session.get(file_header.url, stream=True) as r:
                    with open(file_path, "wb") as new_file:
                        for chunk in r.iter_content(chunk_size=8192):
                            new_file.write(chunk)

                if download_redirect:
                    find_file = re.compile(
                        '\<div\sclass\="resourceworkaround"\>Click\s\<a\shref="(.*)"\sonclick\="this\.target=\'\_blank\'"\>'
                    )
                    cache_path = file_path
                    with open(cache_path, "r", encoding="utf-8") as cache_read:
                        for line in cache_read:
                            found = find_file.search(line)
                            if found:
                                new_link = found.group(1)

                                file_header = self.session.head(
                                    new_link, allow_redirects=True
                                )
                                if re.search(
                                    r"{}".format("|".join(MIME_TYPES)),
                                    file_header.headers.get("content-type"),
                                ):
                                    filename = urllib.parse.unquote(
                                        file_header.url.split("/")[-1]
                                    )
                                    filename = re.sub(r"\?time=\d*", "", filename)
                                    filename = sanitize_filename(filename)

                                    file_path = os.path.join(download_dir, filename)

                                    printProgressBar(
                                        oldcount + 0.5,
                                        maxcount,
                                        prefix="Progress:",
                                        suffix="{:10.10}".format(filename),
                                        length=50,
                                    )

                                    with self.session.get(
                                        file_header.url, stream=True
                                    ) as r:
                                        with open(file_path, "wb") as new_file:
                                            for chunk in r.iter_content(
                                                chunk_size=8192
                                            ):
                                                new_file.write(chunk)

                sleep(randint(1, 2))
        printProgressBar(
            count,
            maxcount,
            prefix="Progress:",
            suffix="{:10.10}".format("Done!"),
            length=50,
        )

    def clean_cache(self, course_name):
        links = set()
        name = "".join(course_name.split()[:2])
        cache_dir = os.path.join(PATH, OUTPUT_FOLDER, name, CACHE)
        try:
            shutil.rmtree(cache_dir)
        except OSError as e:
            print("Error: %s : %s" % (cache_dir, e.strerror))


def main():
    eclass = eClass()

    print("Please pick a class from the following: ")

    course_list = eclass.get_courses()
    key_list = list(course_list)
    toDownload = []
    getInput = True
    while getInput:
        count = 1
        for course in key_list:
            print("{0} : {1}".format(count, course))
            count += 1
        print()
        print("all : Downloads all classes")
        print("exit : Quits the program")
        print("Multiple classes can be selected with spaces `1 3 5`")
        targets = input(f"Class numbers (1-{len(course_list)}): ")
        targets = targets.split(" ")
        if targets[0].lower() == "exit":
            exit(0)
        elif targets[0].lower() == "all":
            toDownload = list(range(0, len(course_list)))
            getInput = False
        else:
            getInput = False
            for target in targets:
                if target.isdigit() and int(target) in range(1, len(course_list) + 1):
                    toDownload.append(int(target) - 1)
                else:
                    print("{0} is invalid!".format(target))
                    getInput = True

    for index in toDownload:
        course = key_list[index]
        print("Downloading: {0}".format(course))
        course_url = course_list[course]
        links = eclass.get_course_content(course_url)
        eclass.download_course_content(course, links)
        eclass.clean_cache(course)
    print("Done!")
    input("Press Enter to Exit")


if __name__ == "__main__":
    main()
