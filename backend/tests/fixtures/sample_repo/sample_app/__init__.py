"""Sample app used as a parser fixture. Never executed."""

from sample_app.service import create_user

from . import models as m
from .settings import DEBUG

__all__ = ["create_user"]
