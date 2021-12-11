# multi-flight-search
Determine the best meetup city based on total flight distance and price.

## Description
This project combines airport metadata with flight prices from Kayak to analyze the price-distance tradeoff associated with multiple parties meeting at a single location on a certain date.  The closest airports are computed based on the metadata, and prices are scraped using 
[undetected-chromedriver](https://github.com/ultrafunkamsterdam/undetected-chromedriver) to create a scatter plot of price vs distance, and also a map displaying all unique flight paths.

## Notebook
View the notebook on [nbviewer here](https://nbviewer.org/github/tjburrows/multi-flight-search/blob/main/multi_flight_search.ipynb)

## How To
First run [create_dataset.ipynb](https://nbviewer.org/github/tjburrows/multi-flight-search/blob/main/create_dataset.ipynb) to merge data into a dataframe.  Then, run [multi_flight_search.ipynb](https://nbviewer.org/github/tjburrows/multi-flight-search/blob/main/multi_flight_search.ipynb) to run analysis.

## Dependencies
This project requires numerous packages: 
- `numpy`
- `pandas`
- `pymap3d`
- `undetected_chromedriver`
- `selenium`
- `BeautifulSoup`
- `more_itertools`
- `folium`
- `matplotlib`
