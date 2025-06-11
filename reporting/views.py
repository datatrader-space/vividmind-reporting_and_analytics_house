from django.shortcuts import render

# Create your views here.
# reporting_and_analytics/views.py

import json
import logging
import datetime
import uuid

from rest_framework import generics, filters, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from django.db import transaction, IntegrityError
from django.db.models import Q # For complex queries

from .models import TaskAnalysisReport, TaskSummaryReport
from .serializers import TaskAnalysisReportSerializer,TaskSummaryReportSerializer
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
        """
        Handles POST requests for batch ingestion of TaskAnalysisReport instances.
        Expects a list of report dictionaries.
        """
        if not isinstance(request.data['data'], list):
            return Response(
                {"detail": "Expected a list of task reports for batch ingestion."},
                status=status.HTTP_400_BAD_REQUEST
            )

        processed_reports_count = 0
        successful_reports_data = []
        errors = []

        with transaction.atomic():
            for index, report_data in enumerate(request.data['data']):
                current_run_id = report_data.get('run_id')
                current_start_datetime = report_data.get('report_start_datetime')
                current_end_datetime = report_data.get('report_end_datetime')

                # Prepare serializer for validation and potential saving
                # partial=True allows for partial updates if an instance is found
                serializer = self.get_serializer(data=report_data, partial=True)

                if serializer.is_valid():
                    try:
                        # Convert datetime fields to proper datetime objects for query if they are timestamps
                        if isinstance(current_start_datetime, (int, float)):
                            current_start_datetime_dt = datetime.datetime.fromtimestamp(current_start_datetime / 1000, tz=datetime.timezone.utc)
                        else:
                            current_start_datetime_dt = current_start_datetime # Assume it's already a datetime object or None

                        if isinstance(current_end_datetime, (int, float)):
                            current_end_datetime_dt = datetime.datetime.fromtimestamp(current_end_datetime / 1000, tz=datetime.timezone.utc)
                        else:
                            current_end_datetime_dt = current_end_datetime # Assume it's already a datetime object or None

                        # Check for existing report by run_id OR by datetime range
                        # Using Q objects for OR logic
                        existing_report = None
                        query = Q()

                        # Only add datetime range to query if both start and end times are provided and valid
                        if current_start_datetime_dt and current_end_datetime_dt:
                            # Check for exact match or overlap
                            query |= Q(
                                report_start_datetime=current_start_datetime_dt,
                                report_end_datetime=current_end_datetime_dt
                            )
                            # You might also want to check for overlaps if reports can span time:
                            # query |= Q(
                            #     report_start_datetime__lte=current_end_datetime_dt,
                            #     report_end_datetime__gte=current_start_datetime_dt
                            # )

                        if (current_start_datetime_dt and current_end_datetime_dt):
                            try:
                                existing_report = TaskAnalysisReport.objects.filter(query).first()
                            except Exception as e:
                                errors.append(f"Entry {index} (run_id: {current_run_id}): Error checking for existing report - {e}")
                                logger.error(f"Error checking for existing report {current_run_id}: {e}", exc_info=True)
                                continue # Skip to next report

                        if existing_report:
                            # Update existing report
                            
                            errors.append(f"Entry {index} (run_id: {current_run_id}): Error Report already exists -")
                            logger.error(f"Error Report already exists", exc_info=True)
                            
                        else:
                            # Create new report
                            report_instance = serializer.save()
                            logger.info(f"Created new TaskAnalysisReport for run_id: {report_instance.run_id}")
                            successful_reports_data.append({
                                "run_id": str(report_instance.run_id),
                                "task_uuid": str(report_instance.task.uuid),
                                "status": "created"
                            })
                        
                        processed_reports_count += 1

                    except IntegrityError as e:
                        errors.append(f"Entry {index} (run_id: {current_run_id}): Database integrity error - {e}")
                        logger.error(f"Integrity error for task report entry {index} (run_id: {current_run_id}): {e}", exc_info=True)
                    except Exception as e:
                        errors.append(f"Entry {index} (run_id: {current_run_id}): An unexpected error occurred - {e}")
                        logger.exception(f"Unexpected error processing task report entry {index} (run_id: {current_run_id}).")
                else:
                    errors.append(f"Entry {index} (run_id: {current_run_id}): Validation failed - {serializer.errors}")
                    logger.warning(f"Validation failed for task report entry {index} (run_id: {current_run_id}): {serializer.errors}")

            if errors:
                transaction.set_rollback(True)
                logger.error(f"Batch ingestion failed due to errors: {errors}")
                return Response(
                    {"message": f"Successfully processed {processed_reports_count} reports with errors.", "details": errors},
                    status=status.HTTP_200_OK
                )

            logger.info(f"Batch ingestion completed. Processed {processed_reports_count} task reports successfully.")
            return Response(
                {"message": f"Successfully processed {processed_reports_count} task reports.", "processed_reports": successful_reports_data},
                status=status.HTTP_201_CREATED
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

class TaskSummaryReportDetailView(generics.RetrieveAPIView):
    """
    API endpoint to retrieve a single TaskSummaryReport instance.
    The lookup is performed using the associated Task's UUID.
    """
    # Define the queryset, again using select_related for efficient retrieval.
    queryset = TaskSummaryReport.objects.all().select_related('task')
    
    # Specify the serializer for a single instance.
    serializer_class = TaskSummaryReportSerializer
    
    # Set the permission policy. As with the list view, consider `IsAuthenticated` for production.
    permission_classes = [AllowAny]
    
    # Crucially, this tells DRF to use the `task__uuid` field (the UUID of the related Task)
    # for looking up the TaskSummaryReport object. This means your URL pattern will use this.
    lookup_field = 'task__uuid'
    
    # This specifies the name of the URL keyword argument that will hold the UUID.
    # For example, if your URL is `task-summaries/<uuid:task_uuid>/`, then `task_uuid` is the kwarg.
    lookup_url_kwarg = 'task_uuid'