"""HTML page routes.

Pages render a shell; the data is fetched by the frontend from the JSON API. This keeps
one source of truth for every resource and means the pages exercise the same endpoints an
external client would.
"""

from __future__ import annotations

from flask import Blueprint, redirect, render_template, url_for

from middleware.auth_middleware import optional_context, page_login_required

bp = Blueprint("pages", __name__)


def _redirect_if_signed_in():
    return redirect(url_for("pages.dashboard_page")) if optional_context() else None


@bp.get("/")
def index():
    if optional_context():
        return redirect(url_for("pages.dashboard_page"))
    return redirect(url_for("pages.login_page"))


@bp.get("/login")
def login_page():
    return _redirect_if_signed_in() or render_template("login.html", mode="login")


@bp.get("/register")
def register_page():
    return _redirect_if_signed_in() or render_template("login.html", mode="register")


@bp.get("/dashboard")
@page_login_required
def dashboard_page():
    return render_template("dashboard.html")


@bp.get("/projects")
@page_login_required
def projects_page():
    return render_template("projects.html")


@bp.get("/projects/<int:project_id>")
@page_login_required
def project_detail_page(project_id: int):
    return render_template("project_detail.html", project_id=project_id)


@bp.get("/incidents")
@page_login_required
def incidents_page():
    return render_template("incidents.html")


@bp.get("/incidents/<int:incident_id>")
@page_login_required
def incident_detail_page(incident_id: int):
    return render_template("incident_detail.html", incident_id=incident_id)
