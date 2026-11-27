from urllib.parse import urlparse
from wtforms import BooleanField, PasswordField, StringField, SubmitField
from flask_wtf import FlaskForm
from wtforms import BooleanField, StringField, SubmitField
from wtforms.validators import DataRequired, Length, Optional, ValidationError


def valid_http_url(value):
    try:
        parsed = urlparse(value)
    except ValueError:
        return False
    return parsed.scheme in ("http", "https") and bool(parsed.netloc)


def http_url(form, field):
    if not valid_http_url((field.data or "").strip()):
        raise ValidationError("Enter a valid http:// or https:// link.")



class CafeForm(FlaskForm):
    name = StringField("Name", validators=[DataRequired(), Length(max=120)])
    location = StringField("Location", validators=[DataRequired(), Length(max=120)])
    seats = StringField("Seats", validators=[DataRequired(), Length(max=80)])
    coffee_price = StringField("Coffee price", validators=[Optional(), Length(max=30)])
    map_url = StringField("Map link", validators=[DataRequired(), Length(max=500), http_url])
    img_url = StringField("Image link", validators=[DataRequired(), Length(max=500), http_url])
    has_wifi = BooleanField("Wi-Fi")
    has_sockets = BooleanField("Power sockets")
    has_toilet = BooleanField("Toilet")
    can_take_calls = BooleanField("Can take calls")
    submit = SubmitField("Save cafe")


class LoginForm(FlaskForm):
    password = PasswordField("Admin password", validators=[DataRequired()])
    submit = SubmitField("Log in")
