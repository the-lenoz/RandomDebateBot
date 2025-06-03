import datetime

from googleapiclient.errors import HttpError

from google_integration.auth import authenticate_google


def create_google_meet_event(api_credentials_path: str,
                             summary, description, start_time, end_time,
                             time_zone='Europe/Rome', attendees: list | None = None):
    """
    Creates a Google Calendar event with a Google Meet link.

    Args:
        api_credentials_path (str): path to api credentials file
        summary (str): The summary/title of the event.
        description (str): The description of the event.
        start_time (datetime.datetime): The start time of the event.
        end_time (datetime.datetime): The end time of the event.
        time_zone (str): The time zone of the event (e.g., 'Europe/Rome').
        attendees (list): A list of dictionaries with 'email' keys for attendees.

    Returns:
        dict: The created event resource, or None if an error occurred.
    """
    service = authenticate_google(api_credentials_path)
    if not service:
        return None

    event = {
        'summary': summary,
        'description': description,
        'start': {
            'dateTime': start_time.isoformat(),
            'timeZone': time_zone,
        },
        'end': {
            'dateTime': end_time.isoformat(),
            'timeZone': time_zone,
        },
        'conferenceData': {
            'createRequest': {
                'requestId': f'meet-creation-{datetime.datetime.now().timestamp()}', # Unique ID for the creation request
                'conferenceSolutionKey': {
                    'type': 'hangoutsMeet' # Specifies Google Meet
                }
            }
        },
        'reminders': {
            'useDefault': True,
        },
    }

    if attendees:
        event['attendees'] = [{'email': email} if isinstance(email, str) else email for email in attendees]

    try:
        event = service.events().insert(calendarId='primary', body=event, conferenceDataVersion=1).execute()
        print(f'Event created: {event.get("htmlLink")}')
        return event
    except HttpError as error:
        print(f'An error occurred while creating event: {error}')
        return None

def delete_google_meet_event(api_credentials_path: str, event_id):
    """
    Deletes a Google Calendar event (and its associated Google Meet link).

    Args:
        api_credentials_path (str): Path to api credentials file
        event_id (str): The ID of the event to delete.

    Returns:
        bool: True if deletion was successful, False otherwise.
    """
    service = authenticate_google(api_credentials_path)
    if not service:
        return False

    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        print(f'Event with ID {event_id} deleted successfully.')
        return True
    except HttpError as error:
        print(f'An error occurred while deleting event {event_id}: {error}')
        return False