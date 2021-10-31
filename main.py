import os
import logging
from flask import send_from_directory
from datetime import datetime, date
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
from wtforms.widgets import TextArea
from wtforms.fields.html5 import TimeField, DateField, IntegerField, DateTimeLocalField
from data_process import (
    fetch_groups,
    process_groups,
    fetch_group,
    process_add,
    process_create_group,
    process_remove,
)

PAGE_LIMIT = 10

logger = logging.getLogger()
app = Flask(__name__)
app.config["SECRET_KEY"] = os.urandom(32)


class EditForm(Form):
    player_type = RadioField(
        "Sign up:",
        validators=[validators.DataRequired()],
        choices=[("double", "Double"), ("single", "Single")],
        default="double",
    )
    player_name = StringField(validators=[validators.DataRequired()])
    player_pin = PasswordField(validators=[validators.DataRequired()])
    add_submit = SubmitField("Add")
    remove_submit = SubmitField("Remove")


class GroupForm(Form):
    location = StringField(validators=[validators.DataRequired()])
    description = StringField(u"Text", widget=TextArea())
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
    retreat_deadline = DateTimeLocalField(
        "Retreat deadline",
        default=datetime.now(),
        format="%Y-%m-%dT%H:%M",
        validators=[validators.DataRequired()],
    )
    pin = StringField(validators=[validators.DataRequired()])
    create_submit = SubmitField("Create")


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
    try:
        processed_groups = list(process_groups(groups))
        group = processed_groups[0]
        edit_form = EditForm()
        if group["single_limit"] == 0:
            group["player_types_disabled"] = True
            group["default_type"] = {"value": "double", "text": "Double"}

        elif group["double_limit"] == 0:
            group["player_types_disabled"] = True
            group["default_type"] = {"value": "single", "text": "Single"}
        else:
            group["player_types_disabled"] = False
            group["default_type"] = {"value": "single", "text": "Single"}

        return render_template("group.html", group=group, edit_form=edit_form)
    except Exception as e:
        logger.error(e, exc_info=True)
        return render_template("404.html"), 404


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
