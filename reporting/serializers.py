# reporting_and_analytics/serializers.py

from rest_framework import serializers
from .models import Task, TaskAnalysisReport, JobAnalysisReport, CostUnitConfig,TaskSummaryReportNew
import datetime
import uuid

class TaskSerializerForReport(serializers.ModelSerializer):
    """
    A simple serializer for the Task model, used when nesting Task details
    within the TaskAnalysisReport response.
    """
    class Meta:
        model = Task
        fields = ['uuid', 'job_uuid', 'name', 'task_type', 'interact']
        read_only=True




class TaskAnalysisReportSerializer(serializers.ModelSerializer):
    """
    Serializer for consuming (GET requests) TaskAnalysisReport model instances
    and for ingesting (POST requests) well-formatted task reports.
    """
    # For ingestion, we need task_uuid. Other Task fields are not used for creation/update.
    task_uuid = serializers.UUIDField(write_only=True)

    # For output (GET requests), we represent the associated Task's UUID.
    output_task_uuid = serializers.SerializerMethodField(source='task_uuid')

    class Meta:
        model = TaskAnalysisReport
        fields = [
    "overall_task_status",
    "report_start_datetime",
    "report_end_datetime",
    "total_task_runtime_text",
    "total_task_runtime_seconds",
    "runs_initiated",
    "runs_completed",
    "runs_failed_exception",
    "runs_incomplete",
    "found_next_page_info_count",
    "next_page_info_not_found_count",
    "saved_file_count",
    "downloaded_file_count",
    "failed_download_count",
    "overall_bot_login_status",
    "last_status_of_task",
    "billing_issue_resolution_status",
    "non_fatal_errors_summary",
    "exceptions_summary",
    "specific_exception_reasons",
    "failed_downloads_summary",
    "scraped_data_summary",
    "data_enrichment_summary",
    "task_uuid",
    'output_task_uuid',
    'run_id',
]

        read_only_fields = ['created_at', 'updated_at']

    def get_output_task_uuid(self, obj):
        """Returns the UUID of the associated Task for output."""
        return str(obj.task.uuid) if obj.task else None

    def validate(self, data):
        """
        Custom validation for datetime conversion from timestamps if provided.
        """
        # Convert Unix timestamps (ms) to datetime objects if present
        for field in ['report_start_datetime', 'report_end_datetime']:
            
            if field in data and isinstance(data[field], (int, float)):
                data[field] = datetime.datetime.fromtimestamp(data[field] / 1000, tz=datetime.timezone.utc)
            elif field in data and data[field] is None:
                 # Allow None for these fields if explicitly provided as such
                 pass
            elif field in data and not isinstance(data[field], datetime.datetime):
                # If it's not a timestamp or datetime object, raise error.
                # Assuming `datetime.datetime` is the desired format after conversion or if provided directly.
                raise serializers.ValidationError(f"Invalid format for '{field}'. Expected Unix timestamp (ms) or datetime object.")
        return data

    def create(self, validated_data):
        return self._create_or_update_report(validated_data, is_create=True)

    def update(self, instance, validated_data):
        return self._create_or_update_report(validated_data, instance=instance, is_create=False)

    def _create_or_update_report(self, validated_data, instance=None, is_create=True):
        
        task_uuid_val = validated_data.pop('task_uuid')
        

        # Find or create the associated Task instance using only its UUID
        task_instance, task_created = Task.objects.get_or_create(
            uuid=task_uuid_val,
            
            defaults={} # No other fields are updated/set if Task exists
        )
        if task_created:
            # Log this if desired, but no other fields are set beyond UUID
            pass

        validated_data['task'] = task_instance
     
        if is_create:
            report = TaskAnalysisReport.objects.create(**validated_data)
            return report

        """  else:
            # Update current instance
            for attr, value in validated_data.items():
                # Special handling for JSON fields if merging is desired, otherwise direct update
                if isinstance(value, dict) and isinstance(getattr(instance, attr), dict):
                    current_json = getattr(instance, attr)
                  
                    setattr(instance, attr, {**current_json, **value}) # Merge JSON
                else:
                    setattr(instance, attr, value)
            instance.save()
            report = instance """
        
# reporting_and_analytics/serializers.py

from rest_framework import serializers
from .models import Task, TaskAnalysisReport, TaskSummaryReport
import datetime
import uuid
import pytz

# --- Re-using previous serializers for nested representation ---
# (Include these if they are in the same serializers.py file and are used by TaskSummaryReportSerializer)

class FlexibleDateTimeField(serializers.DateTimeField):
    """
    Handles datetime fields that might come as Unix timestamps (milliseconds) or ISO format strings.
    Converts them to proper datetime objects for internal use.
    """
    def to_internal_value(self, value):
        if isinstance(value, (int, float)):
            try:
                # Assuming timestamp is in milliseconds
                dt_object = datetime.datetime.fromtimestamp(value / 1000, tz=pytz.utc)
                return dt_object
            except (TypeError, ValueError):
                pass # Fallback to default if timestamp conversion fails
        return super().to_internal_value(value)




# --- NEW SERIALIZER: TaskSummaryReportSerializer ---
class TaskSummaryReportSerializer(serializers.ModelSerializer):
    """
    Serializer for the TaskSummaryReport model.
    Designed for read-only access to aggregated task summary data.
    """
    # Nested serializer to include Task details directly in the summary response.
    # 'source='task'' tells DRF to use the 'task' foreign key to get the Task object.
    # 'read_only=True' ensures this nested data can only be read, not set by the client.
    task_details = TaskSerializerForReport(source='task', read_only=True)

    # Explicitly define JSONFields to ensure they are properly serialized as JSON objects/arrays
    # and not as raw strings. Although Django's JSONField usually handles this, explicit
    # declaration can clarify intent and help with documentation.
    latest_scraped_data_summary = serializers.JSONField()
    latest_data_enrichment_summary = serializers.JSONField()
    aggregated_scraped_data = serializers.JSONField()
    aggregated_data_enrichment = serializers.JSONField()
    all_non_fatal_errors = serializers.JSONField()
    all_exceptions = serializers.JSONField()
    all_specific_exception_reasons = serializers.JSONField()
    all_failed_downloads_summary = serializers.JSONField()

    class Meta:
        model = TaskSummaryReport
        fields = '__all__' # Include all fields from the TaskSummaryReport model
        # Make all fields read-only for this API, as TaskSummaryReport is
        # meant to be generated and updated by internal processes (Celery/management command),
        # not directly via the API.
        read_only = True 



class TaskSummaryReportNewSerializer(serializers.ModelSerializer):
    """
    Serializer for the TaskSummaryReportNew model.
    Designed for read-only access to aggregated task summary data.
    """
    task_details = TaskSerializerForReport(source='task', read_only=True)

    
    # Explicitly define JSON fields for clarity and documentation
    critical_events_summary = serializers.JSONField()
    attempt_failed_errors = serializers.JSONField()
    failed_attempt_error_logs = serializers.JSONField()
    login_exceptions_summary = serializers.JSONField()
    page_detection_exceptions_summary = serializers.JSONField()
    locate_element_exceptions_summary = serializers.JSONField()
    page_load_details = serializers.JSONField()

    class Meta:
        model = TaskSummaryReportNew
        fields = '__all__'
        read_only_fields = [
            'id', 'task', 'task_details',
            'critical_events_summary',
            'attempt_failed_errors',
            'failed_attempt_error_logs',
            'login_exceptions_summary',
            'page_detection_exceptions_summary',
            'locate_element_exceptions_summary',
            'page_load_details',
            # add any other fields in your model
        ]