from typing import Dict, Iterator, List, Set, Tuple
from datetime import datetime
from operator import itemgetter
import pytz
from flask import Flask, render_template
from google.cloud import datastore

datastore_client = datastore.Client("badminton-group", "groups")
app = Flask(__name__)


def fetch_groups(limit: int = None) -> Iterator:
    query = datastore_client.query(kind="group")
    query.order = ["-start_time"]
    return query.fetch(limit=limit)


def process_groups(groups: Iterator) -> Iterator[Dict]:
    clean_groups = get_clean_data(
        groups,
        {
            ("location", str),
            ("start_time", datetime),
            ("end_time", datetime),
            ("single_limit", int),
            ("double_limit", int),
            ("single_players", list),
            ("double_players", list),
        },
    )
    for group in clean_groups:
        start_time_local: datetime = group["start_time"].astimezone(
            pytz.timezone("US/Pacific")
        )
        end_time_local: datetime = group["end_time"].astimezone(
            pytz.timezone("US/Pacific")
        )
        single_players, single_waitlist = process_players(
            group["single_players"], group["single_limit"]
        )
        double_players, double_waitlist = process_players(
            group["double_players"], group["double_limit"]
        )
        yield {
            "location": group["location"],
            "date": start_time_local.strftime("%a %b %-d"),
            "start_time": start_time_local.strftime("%-I:%M %p"),
            "end_time": end_time_local.strftime("%-I:%M %p"),
            "single_limit": group["single_limit"],
            "double_limit": group["double_limit"],
            "single_players": single_players,
            "single_waitlist": single_waitlist,
            "double_players": double_players,
            "double_waitlist": double_waitlist,
        }


def process_players(players: List, limit: int) -> Tuple[List, List]:
    clean_players = get_clean_data(players, {("name", str), ("signup_time", datetime)})
    sorted_players = sorted(clean_players, key=itemgetter("signup_time"))
    if len(sorted_players) <= limit:
        return sorted_players, []
    else:
        return sorted_players[:limit], sorted_players[limit:]


def get_clean_data(
    data: List[Dict], required_field_and_type: Set[Tuple[str, str]]
) -> Iterator[Dict]:
    for item in data:
        if all(
            field in item and isinstance(item[field], type)
            for field, type in required_field_and_type
        ):
            yield item


@app.route("/")
def root():
    groups = fetch_groups(10)
    processed_groups = process_groups(groups)
    return render_template("index.html", groups=processed_groups)


if __name__ == "__main__":
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.

    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)
