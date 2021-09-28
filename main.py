import os
import logging
from flask import send_from_directory
from typing import Dict, Iterable, Iterator, List, Optional, Set, Tuple
from datetime import datetime, date
from operator import itemgetter
import pytz
from flask import Flask, render_template, request, flash
from werkzeug.utils import redirect
from wtforms import (
    Form,
    StringField,
    SubmitField,
    RadioField,
    PasswordField,
    validators,
)
from wtforms.fields.html5 import TimeField, DateField, IntegerField
from google.cloud.datastore import Client, Entity, Transaction


PAGE_LIMIT = 10

logger = logging.getLogger()
datastore_client = Client("badminton-group", "groups")
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(32)


class EditForm(Form):
    player_type = RadioField(
        validators=[validators.DataRequired()],
        choices=[("double", "Double"), ("single", "Single")],
        default="double",
    )
    player_name = StringField("Name", validators=[validators.DataRequired()])
    player_pin = PasswordField("PIN", validators=[validators.DataRequired()])
    add_submit = SubmitField("Add")
    remove_submit = SubmitField("Remove")


class GroupForm(Form):
    location = StringField(validators=[validators.DataRequired()])
    date = DateField(validators=[validators.DataRequired()], default=date.today)
    start_time = TimeField(
        validators=[validators.DataRequired()],
        format="%H:%M",
        default=datetime(2019, 1, 1, hour=20, minute=00),
    )
    end_time = TimeField(
        validators=[validators.DataRequired()],
        format="%H:%M",
        default=datetime(2019, 1, 1, hour=22, minute=00),
    )
    single_limit = IntegerField(validators=[validators.DataRequired()], default=8)
    double_limit = IntegerField(validators=[validators.DataRequired()], default=12)
    create_submit = SubmitField("Create")


def fetch_groups(limit: int = None) -> List[Entity]:
    query = datastore_client.query(kind="group")
    query.order = ["-start_time"]
    try:
        return list(query.fetch(limit=limit))
    except Exception as e:
        logger.error(e, exc_info=True)
        return []


def fetch_group(group_id: str, transaction: Transaction = None) -> Optional[Entity]:
    key = datastore_client.key("group", int(group_id))
    try:
        group_entity = datastore_client.get(key, transaction=transaction)
        return group_entity
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


def process_create_group(data: dict) -> Optional[str]:
    new_group = Entity(datastore_client.key("group"))
    local = pytz.timezone("US/Pacific")
    start_time = local.localize(
        datetime.strptime(data["date"] + " " + data["start_time"], "%Y-%m-%d %H:%M")
    )
    end_time = local.localize(
        datetime.strptime(data["date"] + " " + data["end_time"], "%Y-%m-%d %H:%M")
    )
    new_group.update(
        {
            "location": data["location"],
            "start_time": start_time,
            "end_time": end_time,
            "single_limit": int(data["single_limit"]),
            "double_limit": int(data["double_limit"]),
            "single_players": [],
            "double_players": [],
        }
    )
    try:
        datastore_client.put(new_group)
        return str(new_group.id)
    except Exception as e:
        logger.error(e, exc_info=True)
        return None


def process_groups(groups: Iterable) -> Iterator[Dict]:
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


def process_players(players: Iterable, limit: int) -> Tuple[List, List]:
    clean_players = get_clean_data(
        players, {("name", str), ("pin", str), ("signup_time", datetime)}
    )
    sorted_players = sorted(clean_players, key=itemgetter("signup_time"))
    if len(sorted_players) <= limit:
        return sorted_players, []
    else:
        return sorted_players[:limit], sorted_players[limit:]


def get_clean_data(
    data: Iterable, required_field_and_type: Set[Tuple[str, type]]
) -> Iterator[Entity]:
    for item in data:
        if all(
            field_name in item and isinstance(item[field_name], type_name)
            for field_name, type_name in required_field_and_type
        ):
            yield item


def get_player_list_name_by_type(player_type: str) -> Optional[str]:
    if player_type == "double":
        return "double_players"
    elif player_type == "single":
        return "single_players"
    return None


def process_add(
    group_id: str, player_type: str, player_name: str, player_pin: str
) -> Optional[str]:
    with datastore_client.transaction() as transaction:
        group_entity = fetch_group(group_id, transaction=transaction)
        if not group_entity:
            return f"Can't find group with ID {group_id}"
        player_list_name = get_player_list_name_by_type(player_type)
        if player_name.lower() in {
            x["name"].lower() for x in group_entity[player_list_name]
        }:
            return "Player with the same name already exist"
        else:
            group_entity[player_list_name].append(
                {
                    "name": player_name,
                    "pin": player_pin,
                    "signup_time": datetime.utcnow(),
                }
            )
            try:
                datastore_client.put(group_entity)
            except Exception as e:
                logger.error(e, exc_info=True)
            return None


def process_remove(
    group_id: str, player_type: str, player_name: str, player_pin: str
) -> Optional[str]:
    with datastore_client.transaction() as transaction:
        group_entity = fetch_group(group_id, transaction=transaction)
        if not group_entity:
            return f"Can't find group with ID {group_id}"
        player_list_name = get_player_list_name_by_type(player_type)
        new_players = []
        for player in group_entity[player_list_name]:
            if player["name"].lower() != player_name.lower():
                new_players.append(player)
            elif player["pin"] != player_pin:
                return "Wrong PIN"
        if new_players == group_entity[player_list_name]:
            return "Can't find player with that name"
        else:
            group_entity[player_list_name] = new_players
            try:
                datastore_client.put(group_entity)
            except Exception as e:
                logger.error(e, exc_info=True)
            return None


@app.route("/", methods=["GET"])
def root():
    groups = fetch_groups(PAGE_LIMIT)
    processed_groups = list(process_groups(groups))
    return render_template("index.html", groups=processed_groups)


@app.route("/groups/new", methods=["GET"])
def create_group():
    create_form = GroupForm()
    return render_template("create_group.html", form=create_form)


@app.route("/groups/<string:gid>", methods=["GET"])
def group(gid):
    groups = [fetch_group(gid)]
    processed_groups = list(process_groups(groups))
    edit_form = EditForm()
    return render_template("group.html", group=processed_groups[0], edit_form=edit_form)


@app.route("/groups/<string:gid>", methods=["POST"])
def group_post(gid):
    if all(
        x in request.form
        for x in ["group_id", "player_type", "player_name", "player_pin"]
    ):
        if "add_submit" in request.form:
            error_message = process_add(
                request.form["group_id"],
                request.form["player_type"],
                request.form["player_name"],
                request.form["player_pin"],
            )
            if error_message:
                flash(error_message)
        elif "remove_submit" in request.form:
            error_message = process_remove(
                request.form["group_id"],
                request.form["player_type"],
                request.form["player_name"],
                request.form["player_pin"],
            )
            if error_message:
                flash(error_message)
    return redirect("/groups/" + gid, 302)


@app.route("/groups", methods=["POST"])
def create_group_post():
    gid = process_create_group(request.form)
    return redirect("/groups/" + gid, 302)


@app.route("/favicon.ico")
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "favicon.jpeg",
        mimetype="image/vnd.microsoft.icon",
    )


if __name__ == "__main__":
    # This is used when running locally only. When deploying to Google App
    # Engine, a webserver process such as Gunicorn will serve the app. This
    # can be configured by adding an `entrypoint` to app.yaml.

    # Flask's development server will automatically serve static files in
    # the "static" directory. See:
    # http://flask.pocoo.org/docs/1.0/quickstart/#static-files. Once deployed,
    # App Engine itself will serve those files as configured in app.yaml.
    app.run(host="127.0.0.1", port=5000)
