from django.shortcuts import render

# Create your views here.
# reporting_and_analytics/views.py

import json
import logging
import datetime
import uuid
from .analysis_report import generate_task_report_summary

from rest_framework import generics, filters, status
from rest_framework.generics import RetrieveAPIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import transaction, IntegrityError
from django.db.models import Q # For complex queries

from .models import TaskAnalysisReport, TaskSummaryReport,TaskReport,Task,TaskSummaryReportNew
from .serializers import TaskAnalysisReportSerializer,TaskSummaryReportSerializer,TaskSummaryReportNewSerializer
from django_filters.rest_framework import DjangoFilterBackend
import django_filters
# Removed: from .utils.redis_tracker import add_processed_task_report_run_id


logger = logging.getLogger(__name__)

# --- DRF View for Task Analysis Report Ingestion (POST) and Consumption (GET) ---

class TaskAnalysisReportListCreateAPIView(generics.ListCreateAPIView):
    """
    API endpoint to ingest (POST) a batch of TaskAnalysisReport instances
    and to retrieve (GET) a list of TaskAnalysisReport instances.
    """
    queryset = TaskAnalysisReport.objects.all().select_related('task')
    serializer_class = TaskAnalysisReportSerializer
    filter_backends = [filters.OrderingFilter]
    
    ordering_fields = [
        'report_start_datetime', 'report_end_datetime', 'total_task_runtime_seconds',
        'runs_initiated', 'runs_completed', 'runs_failed_exception', 'runs_incomplete',
        'downloaded_file_count', 'saved_file_count', 'overall_task_status'
    ]
    ordering = ['-report_start_datetime']
    permission_classes = [AllowAny]
    def get_queryset(self):
        """
        Filters the queryset for GET requests based on query parameters.
        """
        queryset = super().get_queryset()
        
        run_id = self.request.query_params.get('run_id')
        task_uuid = self.request.query_params.get('task_uuid')
        job_uuid = self.request.query_params.get('job_uuid')
        overall_status = self.request.query_params.get('overall_task_status')
        
        start_datetime_ms = self.request.query_params.get('report_start_datetime_gte_ms')
        end_datetime_ms = self.request.query_params.get('report_end_datetime_lte_ms')

        if run_id:
            queryset = queryset.filter(run_id=run_id)
        
        if task_uuid:
            try:
                uuid.UUID(task_uuid) # Validate UUID format
                queryset = queryset.filter(task__uuid=task_uuid)
            except ValueError:
                queryset = queryset.none()
                logger.warning(f"Invalid task_uuid provided: {task_uuid}")

        if job_uuid:
            try:
                uuid.UUID(job_uuid) # Validate UUID format
                queryset = queryset.filter(task__job_uuid=job_uuid)
            except ValueError:
                queryset = queryset.none()
                logger.warning(f"Invalid job_uuid provided: {job_uuid}")

        if overall_status:
            queryset = queryset.filter(overall_task_status__iexact=overall_status)

        if start_datetime_ms:
            try:
                start_dt = datetime.datetime.fromtimestamp(int(start_datetime_ms) / 1000, tz=datetime.timezone.utc)
                queryset = queryset.filter(report_start_datetime__gte=start_dt)
            except (ValueError, TypeError):
                logger.warning(f"Invalid report_start_datetime_gte_ms: {start_datetime_ms}")

        if end_datetime_ms:
            try:
                end_dt = datetime.datetime.fromtimestamp(int(end_datetime_ms) / 1000, tz=datetime.timezone.utc)
                queryset = queryset.filter(report_end_datetime__lte=end_dt)
            except (ValueError, TypeError):
                logger.warning(f"Invalid report_end_datetime_lte_ms: {end_datetime_ms}")

        return queryset

    def create(self, request, *args, **kwargs):
        payload = request.data
        reports = payload.get("data", [])
        

        if not isinstance(reports, list):
            return Response(
                {"detail": "Expected a list under 'data' key."},
                status=status.HTTP_400_BAD_REQUEST
            )

        created_reports = []
        print(reports)
        for report_data in reports:
            try:
                run_id = report_data.get('run_id')
                task_uuid = report_data.get('task_uuid')  # Expecting this as input
                service = report_data.get('service')
                end_point = report_data.get('end_point')
                data_point = report_data.get('data_point')
                full_report = report_data
                start_ts = report_data.get('report_start_datetime')
                end_ts = report_data.get('report_end_datetime')

                report_start_datetime = datetime.datetime.fromtimestamp(start_ts / 1000, tz=datetime.timezone.utc) if isinstance(start_ts, (int, float)) else None
                report_end_datetime = datetime.datetime.fromtimestamp(end_ts / 1000, tz=datetime.timezone.utc) if isinstance(end_ts, (int, float)) else None

                # Ensure task_uuid is a UUID object
                if isinstance(task_uuid, str):
                    task_uuid = uuid.UUID(task_uuid)

                task, created = Task.objects.get_or_create(
                    uuid=task_uuid,
                    defaults={
                        "name": f"AutoCreated-{task_uuid.hex[:8]}",   # or just "Unnamed Task"
                        "task_type": "unknown",                        # or any safe default
                        "interact": False,
                    }
                )

                if created:
                    logger.info(f"Created new Task with uuid={task_uuid}")
                else:
                    logger.debug(f"Found existing Task with uuid={task_uuid}")

                # Optional duplicate check
                existing = TaskReport.objects.filter(
                    report_start_datetime=report_start_datetime,
                    report_end_datetime=report_end_datetime,
                    run_id=run_id,
                    task=task,
                    data_point=data_point
                ).first()

                if existing:
                    logger.warning(f"Duplicate report: run_id={run_id}")
                    continue  # skip this report

                report = TaskReport.objects.create(
                    task=task,
                    run_id=run_id,
                    service=service,
                    end_point=end_point,
                    data_point=data_point,
                    report_start_datetime=report_start_datetime,
                    report_end_datetime=report_end_datetime,
                    full_report=full_report,
                )
                created_reports.append(str(report.id))

            except Exception as e:
                logger.exception(f"Failed to process report: {e}")
                continue  # Skip this item but don't crash the entire batch

        if created_reports:
            return Response(
                {"message": f"{len(created_reports)} reports created.", "report_ids": created_reports},
                status=status.HTTP_201_CREATED
            )
        else:
            return Response(
                {"detail": "No new reports were created."},
                status=status.HTTP_400_BAD_REQUEST
            )


        



        
class TaskSummaryReportFilter(django_filters.FilterSet):

    # Filter by the UUID of the associated Task
    task_uuid = django_filters.UUIDFilter(field_name='task__uuid')
    
    # Filter by task name (case-insensitive contains). Useful if tasks have names.
    task_name = django_filters.CharFilter(field_name='task__name', lookup_expr='icontains')

    # Filters for various status fields, allowing exact (case-insensitive) matches
    latest_overall_task_status = django_filters.CharFilter(lookup_expr='iexact')
    latest_overall_bot_login_status = django_filters.CharFilter(lookup_expr='iexact')
    
    # Filter by the boolean 'has_next_page_info' field
    has_next_page_info = django_filters.BooleanFilter()

    # Date range filters for when the summary report was last updated.
    # Use `updated_at_gte` (greater than or equal to) and `updated_at_lte` (less than or equal to).
    updated_at_gte = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='gte')
    updated_at_lte = django_filters.DateTimeFilter(field_name='updated_at', lookup_expr='lte')

    class Meta:
        model = TaskSummaryReport
        fields = [
            'task_uuid', 'task_name', 'latest_overall_task_status',
            'latest_overall_bot_login_status', 'has_next_page_info',
            'updated_at_gte', 'updated_at_lte',
        ]
class TaskSummaryReportListView(generics.ListAPIView):
    """
    API endpoint to retrieve a list of TaskSummaryReport instances.
    
    Supports:
    - Filtering by `task_uuid`, `task_name`, various `latest_overall_status` fields,
      `has_next_page_info`, and `updated_at` date ranges.
    - Ordering by fields like `total_runs_completed`, `updated_at`, etc.
    """
    # Define the queryset: retrieves all TaskSummaryReport objects.
    # `.select_related('task')` is crucial for performance to avoid N+1 queries 
    # when the serializer accesses related Task details.
    queryset = TaskSummaryReport.objects.all().select_related('task')
    
    # Specify the serializer responsible for converting model instances to JSON.
    serializer_class = TaskSummaryReportSerializer
    
    # Set the permission policy. `AllowAny` means the endpoint is publicly accessible.
    # For production, you'll likely want `IsAuthenticated` or more specific permissions.
    permission_classes = [AllowAny]
    
    # Configure DRF's filter backends:
    # - `DjangoFilterBackend`: Enables filtering based on the `TaskSummaryReportFilter`.
    # - `filters.OrderingFilter`: Allows clients to sort results using the 'ordering' query parameter.
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    
    # Link this view to the custom filterset defined above.
    filterset_class = TaskSummaryReportFilter
    
    # Define the fields that can be used for ordering results via the 'ordering' query parameter.
    ordering_fields = [
        'total_runs_completed', 'total_runs_failed_exception',
        'cumulative_total_runtime_seconds', 'average_runtime_seconds_per_run',
        'updated_at', 'latest_report_end_datetime',
    ]
    
    # Set the default ordering for the list. Summaries will be returned with
    # the most recently updated ones first by default.
    ordering = ['-updated_at']


class TaskSummaryReportDetailViewNew(generics.RetrieveAPIView):



    """
    API endpoint to retrieve a single TaskSummaryReport instance.
    The lookup is performed using the associated Task's UUID.
    """
    # Define the queryset, again using select_related for efficient retrieval.
    queryset = TaskSummaryReportNew.objects.all().select_related('task')
    
    # Specify the serializer for a single instance.
    serializer_class = TaskSummaryReportNewSerializer
    
    # Set the permission policy. As with the list view, consider `IsAuthenticated` for production.
    permission_classes = [AllowAny]
    
    # Crucially, this tells DRF to use the `task__uuid` field (the UUID of the related Task)
    # for looking up the TaskSummaryReport object. This means your URL pattern will use this.
    lookup_field = 'task__uuid'
    
    # This specifies the name of the URL keyword argument that will hold the UUID.
    # For example, if your URL is `task-summaries/<uuid:task_uuid>/`, then `task_uuid` is the kwarg.
    lookup_url_kwarg = 'task_uuid'

import json
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponseBadRequest
from django.db import transaction


@csrf_exempt
def update_task_summaries(request):
    if request.method != "POST":
        return HttpResponseBadRequest("Only POST method allowed")

    try:
        data = json.loads(request.body)
        print("Received payload:", data)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    task_uuid = data.get("task_uuid")
    status = data.get("status")
    
    # Handle single string or list of issues
    issues = data.get("issues") or [data.get("issue")]

    if not task_uuid or not status:
        return JsonResponse({"error": "Missing task_uuid or status"}, status=400)

    if status.lower() == "pending":
        return JsonResponse({
            "message": "Status is pending, no changes made.",
            "status": "200"
        })

    try:
        summary = TaskSummaryReportNew.objects.get(task=task_uuid)
    except TaskSummaryReportNew.DoesNotExist:
        return JsonResponse({"error": f"No TaskSummaryReportNew found for uuid {task_uuid}"}, status=404)

    updated = False
    for issue_item in issues:
        # Normalize issue name
        if isinstance(issue_item, dict):
            issue_name = issue_item.get("issue_name", "").lower()
        else:
            issue_name = str(issue_item or "").lower()

        if issue_name == "incorrect password":
            original_len = len(summary.critical_events_summary or [])
            summary.critical_events_summary = [
                event for event in (summary.critical_events_summary or [])
                if str(event).lower() != "incorrect_password"
            ]
            if len(summary.critical_events_summary) != original_len:
                updated = True

        elif issue_name == "storage house down":
            if getattr(summary, "storage_upload_failed", True):
                summary.storage_upload_failed = False
                updated = True

        elif issue_name == "login attempts failed":
            if getattr(summary, "total_attempt_failed", 0) != 0:
                summary.total_attempt_failed = 0
                updated = True

    if updated:
        summary.save()

    return JsonResponse({
        "message": "TaskSummary updated based on issues.",
        "status": "200"
    })