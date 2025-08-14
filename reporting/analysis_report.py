import json
from datetime import timedelta
from typing import Any, Dict, List, Set


def seconds_to_hms(seconds: float) -> str:
    try:
        return str(timedelta(seconds=int(round(float(seconds)))))
    except Exception:
        return "0:00:00"


def extract_event_types(events: List[Dict[str, Any]]) -> List[str]:
    uniq = []
    for ev in events or []:
        t = ev.get("type", "unknown")
        if t not in uniq:
            uniq.append(t)
    return uniq


def add_to_set(lst: List[Dict[str, Any]], field: str, acc: Set[str]):
    for item in lst or []:
        val = item.get(field)
        if val:
            acc.add(str(val))


def safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(v)
    except Exception:
        return default


def try_get(d: Dict[str, Any], key: str, default: Any = 0):
    v = d.get(key, default)
    return v if v is not None else default


def aggregate_page_loads_overall(agg: Dict[str, Any], page_load_details: Dict[str, Any]) -> None:
    for url, details in (page_load_details or {}).items():
        url_agg = agg.setdefault(url, {
            "start_attempts": 0,
            "success_page_load": 0,
            "total_page_load_time": 0.0,
            "refresh_success": 0,
            "refresh_failed": 0,
            "load_failed": 0,
        })
        url_agg["start_attempts"] += try_get(details, "start_attempts", 0)
        url_agg["success_page_load"] += try_get(details, "success_page_load", 0)
        url_agg["total_page_load_time"] += safe_float(try_get(details, "total_page_load_time", 0.0))
        url_agg["refresh_success"] += try_get(details, "refresh_success", 0)
        url_agg["refresh_failed"] += try_get(details, "refresh_failed", 0)
        url_agg["load_failed"] += try_get(details, "load_failed", 0)


def summarize_page_load_details(page_load_details: Dict[str, Any]) -> Dict[str, Any]:
    summary = {}
    for url, details in (page_load_details or {}).items():
        summary[url] = {
            "start_attempts": try_get(details, "start_attempts", 0),
            "success_page_load": try_get(details, "success_page_load", 0),
            "total_page_load_time": safe_float(try_get(details, "total_page_load_time", 0.0)),
            "refresh_success": try_get(details, "refresh_success", 0),
            "refresh_failed": try_get(details, "refresh_failed", 0),
            "load_failed": try_get(details, "load_failed", 0),
        }
    return summary


def init_main_report() -> Dict[str, Any]:
    return {
        "total_login_attempts": 0,
        "total_successful_logins": 0,
        "total_failed_logins": 0,
        "total_attempts_failed": 0,
        "total_login_time_seconds": 0.0,
        "total_critical_events_count": 0,
        "total_reports_count": 0,
        "final_logins_count": 0,
        "login_exceptions_count_total": 0,
        "page_detection_exceptions_count_total": 0,
        "locate_element_exceptions_count_total": 0,
        "total_2fa_attempts": 0,
        "total_2fa_successes": 0,
        "total_2fa_failures": 0,
        "total_2fa_time_seconds": 0.0
    }


def process_report(report: Dict[str, Any], main_report: Dict[str, Any], detailed_reports: List[Dict[str, Any]],
                   aggregate_page_loads: Dict[str, Any], global_sets: Dict[str, Set[str]]) -> None:
    total_login_attempts = try_get(report, "total_login_attempts", 0)
    successful_logins = try_get(report, "successful_logins", 0)
    failed_logins = try_get(report, "failed_logins", 0)
    total_login_time = safe_float(try_get(report, "total_login_time", 0.0))
    critical_events = report.get("critical_events_summary", []) or []
    attempts_failed_errors = report.get("attempt_failed_errors", []) or []

    main_report["total_login_attempts"] += total_login_attempts
    main_report["total_successful_logins"] += successful_logins
    main_report["total_failed_logins"] += failed_logins
    main_report["total_attempts_failed"] += len(attempts_failed_errors)
    main_report["total_login_time_seconds"] += total_login_time
    main_report["total_critical_events_count"] += len(critical_events)
    main_report["login_exceptions_count_total"] += try_get(report, "login_exceptions_count", 0)
    main_report["page_detection_exceptions_count_total"] += try_get(report, "page_detection_exceptions_count", 0)
    main_report["locate_element_exceptions_count_total"] += try_get(report, "locate_element_exceptions_count", 0)
    main_report["total_2fa_attempts"] += try_get(report, "2fa_attempts", 0)
    main_report["total_2fa_successes"] += try_get(report, "2fa_successes", 0)
    main_report["total_2fa_failures"] += try_get(report, "2fa_failures", 0)
    main_report["total_2fa_time_seconds"] += safe_float(try_get(report, "2fa_total_time", 0.0))
    main_report["total_reports_count"] += 1
    if successful_logins >= 1:
        main_report["final_logins_count"] += 1

    add_to_set(critical_events, "type", global_sets["critical_event_types"])
    add_to_set(attempts_failed_errors, "type", global_sets["attempts_failed_reasons"])

    page_load_details = report.get("page_load_details", {}) or {}
    aggregate_page_loads_overall(aggregate_page_loads, page_load_details)

    detailed_entry = {
        "task": report.get("task_id"),
        "run_id": report.get("run_id"),
        "service": report.get('service'),
        "end_point": report.get('end_point'),
        "total_login_attempts": total_login_attempts,
        "successful_logins": successful_logins,
        "failed_logins": failed_logins,
        "failed_attempts": len(attempts_failed_errors),
        "total_login_time": seconds_to_hms(total_login_time),
        "total_login_time_seconds": total_login_time,
        "critical_event_types": extract_event_types(critical_events),
        "attempts_failed_reason": extract_event_types(attempts_failed_errors),
        "critical_events_summary": critical_events,
        "attempt_failed_errors": attempts_failed_errors,
        "2fa_attempts": try_get(report, "2fa_attempts", 0),
        "2fa_successes": try_get(report, "2fa_successes", 0),
        "2fa_failures": try_get(report, "2fa_failures", 0),
        "2fa_total_time": safe_float(try_get(report, "2fa_total_time", 0.0)),
        "login_exceptions_count": try_get(report, "login_exceptions_count", 0),
        "page_detection_exceptions_count": try_get(report, "page_detection_exceptions_count", 0),
        "locate_element_exceptions_count": try_get(report, "locate_element_exceptions_count", 0),
        "page_load_summary": summarize_page_load_details(page_load_details),
        "page_load_details": page_load_details
    }
    detailed_reports.append(detailed_entry)


def compile_reports(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    main_report = init_main_report()
    detailed_reports: List[Dict[str, Any]] = []
    aggregate_page_loads: Dict[str, Any] = {}
    global_sets = {"critical_event_types": set(), "attempts_failed_reasons": set()}

    for rep in reports:
        if isinstance(rep, dict):
            process_report(rep, main_report, detailed_reports, aggregate_page_loads, global_sets)

    main_report["total_login_time"] = seconds_to_hms(main_report["total_login_time_seconds"])
    main_report["total_2fa_time"] = seconds_to_hms(main_report["total_2fa_time_seconds"])
    main_report["final_logins"] = f"{main_report['final_logins_count']} out of {main_report['total_reports_count']}"
    del main_report["final_logins_count"]

    main_report["unique_critical_event_types"] = sorted(list(global_sets["critical_event_types"]))
    main_report["unique_attempts_failed_reasons"] = sorted(list(global_sets["attempts_failed_reasons"]))

    return {
        "main_report": main_report,
        "aggregate_page_loads": aggregate_page_loads,
        "detailed_reports": detailed_reports
    }


def generate_task_report_summary(reports: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Public function to generate a compiled task report from a list of task report dicts.

    :param reports: List of report dictionaries
    :return: Final report with main_report, aggregate_page_loads, and detailed_reports
    """
    return compile_reports(reports)
