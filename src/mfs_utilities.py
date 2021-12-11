from datetime import date, timedelta, datetime, timezone, tzinfo
import undetected_chromedriver.v2 as uc
from selenium import webdriver
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.common.by import By
from selenium.common.exceptions import TimeoutException
from bs4 import BeautifulSoup
from more_itertools import windowed
from dateutil.tz import gettz
import pandas as pd
from pymap3d.vincenty import track2
import folium
from matplotlib import cm
from matplotlib.colors import Normalize, to_hex
from time import time as now
import warnings

# Parse HTML source into a dataframe
def page_to_dataframe(page_source, flight, startdate, airportdf):
    origin, destination = flight
    soup = BeautifulSoup(page_source, "lxml")
    results = soup.find_all("div", attrs={"class": "resultInner"})
    resultDicts = []
    for result in results:
        container = result.find_all(class_="container")
        times = []
        stops = []
        legs = []

        for f, flight in enumerate(container):
            time_pairs = flight.find_all("span", attrs={"class": "time-pair"})

            # Loop over Depart and Arrive times
            for p, pair in enumerate(time_pairs):
                dayOffset = 0

                # Find superscripts
                sups = pair.find("sup")
                if sups:
                    sups = sups.getText().strip()
                    if sups[0] in ["+", "-"]:
                        if sups[0] == "+":
                            dayOffset = int(sups)
                    else:
                        raise ValueError("Unknown superscript found: %s" % sups)

                # Compute time
                if p % 2 == 0:
                    time = pair.find(
                        "span", attrs={"class": "depart-time base-time"}
                    ).getText()
                else:
                    time = pair.find(
                        "span", attrs={"class": "arrival-time base-time"}
                    ).getText()
                meridiem = (
                    pair.find("span", attrs={"class": "time-meridiem meridiem"})
                    .getText()
                    .lower()
                )
                time = (
                    datetime(
                        year=startdate.year,
                        month=startdate.month,
                        day=startdate.day,
                        hour=int(time.split(":")[0]),
                        minute=int(time.split(":")[1]),
                        tzinfo=gettz(
                            airportdf.loc[origin if p % 2 == 0 else destination][
                                "Timezone"
                            ]
                        ),
                    )
                    + timedelta(days=dayOffset)
                )
                if meridiem[0] == "p":
                    time += timedelta(hours=12)
                times.append(time)

            # Find stops
            stop = flight.find(class_="stops-text").getText().strip()
            if stop == "nonstop":
                if f == 0:
                    legs.append([(origin, destination)])
                else:
                    legs.append([(destination, origin)])
            else:
                layovers = flight.find_all(class_="js-layover")
                layovers = list(map(lambda x: x.getText().strip(), layovers))
                stop = layovers
                legs1 = [origin if f == 0 else destination]
                for s in stop:
                    if "-" in s:
                        parts = s.split("-")
                        if len(parts) != 2:
                            raise ValueError("parse error 1")
                        legs1.extend([parts[0], 0, parts[1]])
                    else:
                        legs1.append(s)
                legs1.append(destination if f == 0 else origin)
                legs2 = []
                for legpair in windowed(legs1, 2):
                    if 0 not in legpair:
                        legs2.append(legpair)
                legs.append(legs2)
            stops.append(stop)
        
        # Find price
        priceString = (
            result.find("span", attrs={"class": "price-text"})
            .getText()
            .strip()
            .strip("$")
            .replace(",", "")
        )
        validPrice = priceString.isdigit()
        if validPrice:
            price = int(priceString)
            distance = 0

            airportsInDf = True
            for leg in legs:
                for l in leg:
                    if l[0] in airportdf and l[1] in airportdf:
                        distance += airportdf.loc[l[0]][l[1]]
                    else:
                        airportsInDf = False
                        break
                else:
                    continue
                break
            if airportsInDf:
                resultDict = dict(
                    depart_time_1=times[0],
                    arrive_time_1=times[1],
                    depart_time_2=times[2],
                    arrive_time_2=times[3],
                    price=price,
                    stops_1=stops[0],
                    stops_2=stops[1],
                    origin=origin,
                    destination=destination,
                    legs_1=tuple(legs[0]),
                    legs_2=tuple(legs[1]),
                    distance_mi=distance,
                )
                resultDicts.append(resultDict)
            else:
                warnings.warn("Airport not in database", RuntimeWarning)
        else:
            warnings.warn('Failed to parse price: "%s"' % priceString, RuntimeWarning)
    return pd.DataFrame(resultDicts) if resultDicts else None

# Use undetected chromedriver to get Kayak webpage
def get_url(url, driver, timeout, count=0):
    try:
        driver.get(url)
        
        # Wait for exactly 15 results on page
        elem = WebDriverWait(driver, timeout).until(
            lambda x: len(x.find_elements(By.XPATH, "//div[@class='resultInner']"))
            == 15
        )
        return driver.page_source
    except TimeoutException as ex:
        retries = 5
        if count < retries:
            timeout *= 2
            print("Retrying with %ds timeout..." % timeout)
            return get_url(url, driver, timeout, count + 1)
        else:
            raise ValueError("get failed after 5 retries")

# Loop over flights requested and scrape data to produce a dataframe
def kayak_scraper(flightList, startdate, days, airportdf, timeout=20):
    enddate = startdate + timedelta(days)
    str_format = "%Y-%m-%d"
    enddate_str = enddate.strftime(str_format)
    startdate_str = startdate.strftime(str_format)
    driver = uc.Chrome(version_main=95, headless=False)
    results = []
    with driver:
        for f, flight in enumerate(flightList):
            print("Getting %d/%d" % (f + 1, len(flightList)), end=" ")
            origin, destination = flight
            url = (
                "https://www.kayak.com/flights/"
                + origin
                + "-"
                + destination
                + "/"
                + startdate_str
                + "/"
                + enddate_str
                + "?sort=price_a"
            )
            start = now()
            page_source = get_url(url, driver, timeout)
            results.append(page_to_dataframe(page_source, flight, startdate, airportdf))
            end = now()
            print("%.0f sec" % round(end - start))
    driver.quit()
    results = pd.concat(results)
    return results

# Plot flights and color by distance of flight
def flight_plot(resultdf, airportdf, zoom=3):
    # Get destination latitude, longitude
    dests_iata = resultdf["destination"].unique()
    dest_latlon = airportdf.loc[dests_iata][["Latitude", "Longitude"]].mean()
    m = folium.Map(location=dest_latlon, zoom_start=zoom)

    norm = Normalize(
        vmin=resultdf["distance_mi"].min(), vmax=resultdf["distance_mi"].max()
    )
    cmap = lambda x: to_hex(cm.jet(norm(x)))
    resultdfdedup = resultdf.drop_duplicates(subset=["legs_1", "legs_2"])
    for r in range(len(resultdfdedup)):
        fg = folium.FeatureGroup(name="line %d" % r, show=True)
        lineLats = []
        lineLons = []
        for legs2 in [resultdfdedup.iloc[r]["legs_1"], resultdfdedup.iloc[r]["legs_2"]]:
            for legs in legs2:
                srcLat = airportdf.loc[legs[0]]["Latitude"]
                srcLon = airportdf.loc[legs[0]]["Longitude"]
                dstLat = airportdf.loc[legs[1]]["Latitude"]
                dstLon = airportdf.loc[legs[1]]["Longitude"]
                lineLat, lineLon = track2(srcLat, srcLon, dstLat, dstLon, npts=50)
                lineLats.extend(lineLat)
                lineLons.extend(lineLon)
        lineLons = list(map(lambda x: (x % 360) - 360, lineLons))
        folium.Polygon(
            zip(lineLats, lineLons),
            color=cmap(resultdfdedup.iloc[r]["distance_mi"]),
            no_clip=True,
            smoothFactor=1,
        ).add_to(fg)
        fg.add_to(m)
    folium.LayerControl().add_to(m)
    return m
