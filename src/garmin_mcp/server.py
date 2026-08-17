"""Local MCP server exposing read-only Garmin Connect data to Claude Desktop.

Runs over stdio, so stdout MUST stay reserved for the MCP JSON-RPC stream --
all logging here goes to stderr, and no tool ever prints to stdout.

Auth is deliberately non-interactive: this process only ever loads/refreshes
a cached OAuth token (see garmin_mcp.auth). It never prompts for an MFA code,
since blocking on stdin here would hang the tool call and could corrupt the
stdio protocol stream. If no valid cached session exists, tools fail fast
with an instruction to run scripts/setup_auth.py from a terminal.
"""

from __future__ import annotations

import logging
import sys
from datetime import date
from typing import Any

from garminconnect import (
    Garmin,
    GarminConnectAuthenticationError,
    GarminConnectConnectionError,
    GarminConnectTooManyRequestsError,
)
from mcp.server import MCPServer

from garmin_mcp import auth

logging.basicConfig(
    level=logging.WARNING,
    stream=sys.stderr,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logging.getLogger("garmin_mcp").setLevel(logging.INFO)
logger = logging.getLogger("garmin_mcp")

mcp = MCPServer("garmin")

_client: Garmin | None = None

_REAUTH_HINT = (
    "Run `uv run python scripts/setup_auth.py` in the garmin_mcp project "
    "directory to (re-)authenticate, then retry."
)


def _today() -> str:
    return date.today().isoformat()


def _get_client() -> Garmin:
    global _client
    if _client is not None:
        return _client

    email = auth.load_email()
    if not email:
        raise RuntimeError(f"Garmin account not configured yet. {_REAUTH_HINT}")
    password = auth.get_password(email)

    client = Garmin(email=email, password=password)
    try:
        mfa_status, _legacy_token = client.login(tokenstore=auth.tokenstore_path())
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as exc:
        raise RuntimeError(
            f"Garmin login failed ({exc}). The cached session may have expired. "
            f"{_REAUTH_HINT}"
        ) from exc

    if mfa_status:
        raise RuntimeError(
            "Garmin requires a fresh login with a multi-factor authentication "
            f"code, which this server can't provide interactively. {_REAUTH_HINT}"
        )

    logger.info("Authenticated to Garmin Connect as %s", email)
    _client = client
    return client


def _call(fn_name: str, *args: Any, **kwargs: Any) -> Any:
    """Call a read method on the authenticated client, translating errors
    into clear, tool-friendly messages."""
    client = _get_client()
    fn = getattr(client, fn_name)
    try:
        return fn(*args, **kwargs)
    except GarminConnectTooManyRequestsError as exc:
        raise RuntimeError(
            "Garmin Connect rate-limited this request. Wait a bit and try again."
        ) from exc
    except (GarminConnectAuthenticationError, GarminConnectConnectionError) as exc:
        global _client
        _client = None  # force a fresh login attempt next call
        raise RuntimeError(f"Garmin session error ({exc}). {_REAUTH_HINT}") from exc


# --- Tools -------------------------------------------------------------


@mcp.tool()
def list_activities(
    limit: int = 20, start: int = 0, activity_type: str | None = None
) -> Any:
    """List recent Garmin activities, most recent first.

    Args:
        limit: Maximum number of activities to return.
        start: Number of most-recent activities to skip (for pagination).
        activity_type: Optional Garmin activity type filter, e.g. "running",
            "cycling", "swimming". Leave unset to include all types.
    """
    return _call("get_activities", start, limit, activity_type)


@mcp.tool()
def get_activity(activity_id: str) -> Any:
    """Get full detail for a single activity: summary plus per-metric time
    series (pace/HR/power/elevation, GPS-derived stats, etc.).

    Args:
        activity_id: The Garmin activity ID, as returned by list_activities.
    """
    return {
        "summary": _call("get_activity", activity_id),
        "details": _call("get_activity_details", activity_id),
    }


@mcp.tool()
def get_activity_splits(activity_id: str) -> Any:
    """Get lap/split data for a single activity.

    Args:
        activity_id: The Garmin activity ID, as returned by list_activities.
    """
    return _call("get_activity_splits", activity_id)


@mcp.tool()
def get_heart_rate(date_str: str | None = None) -> Any:
    """Get a day's heart rate data: resting HR and an intraday HR timeline.

    Args:
        date_str: Date as YYYY-MM-DD. Defaults to today.
    """
    return _call("get_heart_rates", date_str or _today())


@mcp.tool()
def get_daily_stats(date_str: str | None = None) -> Any:
    """Get a day's overall stats summary: steps, calories, resting HR,
    distance, floors climbed, intensity minutes, etc.

    Args:
        date_str: Date as YYYY-MM-DD. Defaults to today.
    """
    return _call("get_user_summary", date_str or _today())


@mcp.tool()
def get_sleep(date_str: str | None = None) -> Any:
    """Get sleep data for the night ending on the given date: sleep stages,
    duration, sleep score, and related metrics.

    Args:
        date_str: Date as YYYY-MM-DD. Defaults to today.
    """
    return _call("get_sleep_data", date_str or _today())


@mcp.tool()
def get_hrv(date_str: str | None = None) -> Any:
    """Get heart rate variability (HRV) data for the given date.

    Args:
        date_str: Date as YYYY-MM-DD. Defaults to today.
    """
    return _call("get_hrv_data", date_str or _today())


@mcp.tool()
def get_body_battery(start_date: str | None = None, end_date: str | None = None) -> Any:
    """Get Body Battery (energy reserve) data over a date range.

    Args:
        start_date: Start date as YYYY-MM-DD. Defaults to today.
        end_date: End date as YYYY-MM-DD. Defaults to start_date.
    """
    start = start_date or _today()
    return _call("get_body_battery", start, end_date or start)


@mcp.tool()
def get_stress(date_str: str | None = None) -> Any:
    """Get all-day stress level data for the given date.

    Args:
        date_str: Date as YYYY-MM-DD. Defaults to today.
    """
    return _call("get_all_day_stress", date_str or _today())


@mcp.tool()
def get_training_readiness(date_str: str | None = None) -> Any:
    """Get Garmin's Training Readiness score and contributing factors for
    the given date.

    Args:
        date_str: Date as YYYY-MM-DD. Defaults to today.
    """
    return _call("get_training_readiness", date_str or _today())


# --- Profile & physiology -----------------------------------------------


@mcp.tool()
def get_profile() -> Any:
    """Get the athlete's profile: identity/unit preferences, personal
    settings (including max HR, resting HR, weight, height, VO2max),
    configured heart rate zones per sport, and configured power zones per
    sport.
    """
    return {
        "user_profile": _call("get_user_profile"),
        "settings": _call("get_userprofile_settings"),
        "heart_rate_zones": _call("get_heart_rate_zones"),
        "power_zones": _call("get_power_zones"),
    }


@mcp.tool()
def get_lactate_threshold(
    latest: bool = True,
    start_date: str | None = None,
    end_date: str | None = None,
    aggregation: str = "daily",
) -> Any:
    """Get running lactate threshold data (heart rate, power, and speed).

    Args:
        latest: If True, return the latest lactate threshold info. If
            False, query a range instead (requires start_date).
        start_date: Start date as YYYY-MM-DD. Required if latest is False;
            ignored if latest is True.
        end_date: End date as YYYY-MM-DD. Defaults to today. Ignored if
            latest is True.
        aggregation: One of "daily", "weekly", "monthly", "yearly".
    """
    return _call(
        "get_lactate_threshold",
        latest=latest,
        start_date=start_date,
        end_date=end_date,
        aggregation=aggregation,
    )


@mcp.tool()
def get_cycling_ftp() -> Any:
    """Get the athlete's latest cycling Functional Threshold Power (FTP)."""
    return _call("get_cycling_ftp")


@mcp.tool()
def get_ftp_history(
    start_date: str, end_date: str, sport: str = "CYCLING", aggregation: str = "daily"
) -> Any:
    """Get historic Functional Threshold Power for a sport over a date range.

    Args:
        start_date: First date in the range, as YYYY-MM-DD.
        end_date: Last date in the range, as YYYY-MM-DD.
        sport: Garmin sport key, e.g. "RUNNING", "CYCLING".
        aggregation: One of "daily", "weekly", "monthly", "yearly".
    """
    return _call(
        "get_functional_threshold_power_range",
        start_date,
        end_date,
        sport=sport,
        aggregation=aggregation,
    )


@mcp.tool()
def get_max_metrics(start_date: str | None = None, end_date: str | None = None) -> Any:
    """Get max-metric data (e.g. VO2max) over a date range.

    Args:
        start_date: Start date as YYYY-MM-DD. Defaults to today.
        end_date: End date as YYYY-MM-DD. Defaults to start_date.
    """
    start = start_date or _today()
    return _call("get_max_metrics_range", start, end_date or start)


@mcp.tool()
def get_resting_heart_rate(
    start_date: str | None = None, end_date: str | None = None
) -> Any:
    """Get the daily resting heart rate trend over a date range.

    Args:
        start_date: Start date as YYYY-MM-DD. Defaults to today.
        end_date: End date as YYYY-MM-DD. Defaults to start_date.
    """
    start = start_date or _today()
    return _call("get_rhr_daily", start, end_date or start)


@mcp.tool()
def get_fitness_age(date_str: str | None = None) -> Any:
    """Get the athlete's Garmin Fitness Age for the given date.

    Args:
        date_str: Date as YYYY-MM-DD. Defaults to today.
    """
    return _call("get_fitnessage_data", date_str or _today())


@mcp.tool()
def get_personal_records() -> Any:
    """Get the athlete's personal records."""
    return _call("get_personal_record")


# --- Training plans, workouts & schedule ---------------------------------


@mcp.tool()
def list_workouts(limit: int = 100, start: int = 0) -> Any:
    """List the athlete's saved workouts (templates), most recent first.

    Args:
        limit: Maximum number of workouts to return.
        start: Number of most-recent workouts to skip (for pagination).
    """
    return _call("get_workouts", start, limit)


@mcp.tool()
def get_workout(workout_id: str) -> Any:
    """Get the full structure of one workout: segments, targets, intervals.

    Args:
        workout_id: The workout ID, as returned by list_workouts or
            get_scheduled_workout.
    """
    return _call("get_workout_by_id", workout_id)


@mcp.tool()
def get_scheduled_workouts(year: int, month: int) -> Any:
    """Get the calendar of workouts scheduled for a given month. This is
    the primary way to find out what's coming up next in training.

    Args:
        year: Four-digit year, e.g. 2026.
        month: Month number, 1-12.
    """
    return _call("get_scheduled_workouts", year, month)


@mcp.tool()
def get_scheduled_workout(scheduled_workout_id: str) -> Any:
    """Get detail for one scheduled workout instance.

    Args:
        scheduled_workout_id: The scheduled-workout ID, as returned by
            get_scheduled_workouts.
    """
    return _call("get_scheduled_workout_by_id", scheduled_workout_id)


@mcp.tool()
def list_training_plans() -> Any:
    """List training plans."""
    return _call("get_training_plans")


@mcp.tool()
def get_training_plan(plan_id: str) -> Any:
    """Get details for a specific training plan.

    Args:
        plan_id: The training plan ID, as returned by list_training_plans.
    """
    return _call("get_training_plan_by_id", plan_id)


@mcp.tool()
def get_adaptive_training_plan(plan_id: str) -> Any:
    """Get details for a specific adaptive training plan.

    Args:
        plan_id: The adaptive training plan ID, as returned by
            list_training_plans.
    """
    return _call("get_adaptive_training_plan_by_id", plan_id)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
