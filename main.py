import os
from typing import Dict, Iterator, List, Optional, Set, Tuple
from datetime import datetime
from operator import itemgetter
import pytz
from flask import Flask, render_template, request
from wtforms import Form, StringField, SubmitField, RadioField, validators
from google.cloud import datastore


datastore_client = datastore.Client("badminton-group", "groups")
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(32)


class EditForm(Form):
    player_type = RadioField(
        validators=[validators.DataRequired()],
        choices=[("double", "Double"), ("single", "Single")],
        default="double",
    )
    player_name = StringField(validators=[validators.DataRequired()])
    add_submit = SubmitField("Add")
    remove_submit = SubmitField("Remove")


def fetch_groups(limit: int = None) -> Iterator:
    query = datastore_client.query(kind="group")
    query.order = ["-start_time"]
    return query.fetch(limit=limit)


def fetch_group(
    group_id: str, transaction: datastore.Transaction = None
) -> Optional[datastore.Entity]:
    key = datastore_client.key("group", int(group_id))
    group_entity = datastore_client.get(key, transaction=transaction)
    if not group_entity:
        print(f"Cannot find group eneity with key {key}")
    return group_entity


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
            "id": group.id,
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
    data: Iterator, required_field_and_type: Set[Tuple[str, str]]
) -> Iterator[Dict]:
    for item in data:
        if all(
            field in item and isinstance(item[field], type)
            for field, type in required_field_and_type
        ):
            yield item


def get_player_list_name_by_type(player_type: str) -> str:
    if player_type == "double":
        return "double_players"
    elif player_type == "single":
        return "single_players"


def process_add(group_id: str, player_type: str, player_name: str) -> None:
    with datastore_client.transaction() as transaction:
        group_entity = fetch_group(group_id, transaction=transaction)
        if not group_entity:
            return
        player_list_name = get_player_list_name_by_type(player_type)
        if player_name in {x["name"] for x in group_entity[player_list_name]}:
            print("Player with the same name already exist!")
        else:
            group_entity[player_list_name].append(
                {"name": player_name, "signup_time": datetime.utcnow()}
            )
            datastore_client.put(group_entity)


def process_remove(group_id: str, player_type: str, player_name: str):
    with datastore_client.transaction() as transaction:
        group_entity = fetch_group(group_id, transaction=transaction)
        if not group_entity:
            return
        player_list_name = get_player_list_name_by_type(player_type)
        new_players = [
            x for x in group_entity[player_list_name] if x["name"] != player_name
        ]
        if new_players == group_entity[player_list_name]:
            print("Cannot find player with that name")
        else:
            group_entity[player_list_name] = new_players
            datastore_client.put(group_entity)


@app.route("/", methods=["GET"])
def root():
    groups = fetch_groups(10)
    processed_groups = list(process_groups(groups))
    edit_form = EditForm()
    return render_template("index.html", groups=processed_groups, edit_form=edit_form)


@app.route("/", methods=["POST"])
def root_post():
    if all(x in request.form for x in ["group_id", "player_type", "player_name"]):
        if "add_submit" in request.form:
            process_add(
                request.form["group_id"],
                request.form["player_type"],
                request.form["player_name"],
            )
        elif "remove_submit" in request.form:
            process_remove(
                request.form["group_id"],
                request.form["player_type"],
                request.form["player_name"],
            )
    return root()


if __name__ == "__main__":
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.

    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    app.run(host="127.0.0.1", port=8080, debug=True)
