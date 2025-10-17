def get_task_event_stream_topic(task_id: str) -> str:
    """Get the event stream topic for a specific task.

    Args:
        task_id (str): task.id

    Returns:
        str: The event stream topic for the task
    """

    return f"task:{task_id}"
