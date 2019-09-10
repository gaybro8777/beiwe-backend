from __future__ import print_function

import functools
from datetime import datetime, timedelta

from flask import flash, json, redirect, request, session
from werkzeug.exceptions import abort

from config.constants import ALL_RESEARCHER_TYPES, ResearcherRole
from database.study_models import Study
from database.user_models import Researcher, StudyRelation
from libs.security import generate_easy_alphanumeric_string

SESSION_NAME = "researcher_username"
EXPIRY_NAME = "expiry"
SESSION_UUID = "session_uuid"
STUDY_ADMIN_RESTRICTION = "study_admin_restriction"

################################################################################
############################ Website Functions #################################
################################################################################


def authenticate_researcher_login(some_function):
    """ Decorator for functions (pages) that require a login, redirect to login page on failure. """
    @functools.wraps(some_function)
    def authenticate_and_call(*args, **kwargs):
        if is_logged_in():
            return some_function(*args, **kwargs)
        else:
            return redirect("/")

    return authenticate_and_call


def log_in_researcher(username):
    """ populate session for a researcher """
    session[SESSION_UUID] = generate_easy_alphanumeric_string()
    session[EXPIRY_NAME] = datetime.now() + timedelta(hours=6)
    session[SESSION_NAME] = username


def logout_researcher():
    """ clear session information for a researcher """
    if SESSION_UUID in session:
        del session[SESSION_UUID]
    if EXPIRY_NAME in session:
        del session[EXPIRY_NAME]


def is_logged_in():
    """ automatically logs out the researcher if their session is timed out. """
    if EXPIRY_NAME in session and session[EXPIRY_NAME] > datetime.now():
        return SESSION_UUID in session
    logout_researcher()


def get_session_researcher():
    """ Get the researcher declared in the session, raise 400 (bad request) if it is missing. """
    if "researcher_username" not in session:
        return abort(400)

    # The first thing we do is check if the session researcher has been queried for already
    try:
        return request._beiwe_researcher
    except AttributeError:
        pass

    # if it hasn't then grab it, cache it, return it
    try:
        researcher = Researcher.objects.get(username=session["researcher_username"])
        setattr(request, "_beiwe_researcher", researcher)
        return researcher
    except Researcher.DoesNotExist:
        return abort(400)


def assert_admin(study_id):
    """ This function will throw a 403 forbidden error and stop execution. """
    session_researcher = get_session_researcher()
    if not session_researcher.site_admin and not session_researcher.check_study_admin(study_id):
        return abort(403)


def assert_researcher_under_admin(researcher):
    session_researcher = get_session_researcher()
    if session_researcher.site_admin:
        return

    if researcher.site_admin:
        flash("This user is a site administrator, action rejected.", "danger")
        return abort(403)

    if researcher.study_relations.filter(relationship=ResearcherRole.study_admin).exists():
        flash("This user is a study administrator, action rejected.", "danger")
        return abort(403)

    session_studies = set(session_researcher.get_admin_study_relations().values_list("study_id", flat=True))
    researcher_studies = set(researcher.get_researcher_study_relations().values_list("study_id", flat=True))

    if not session_studies.intersection(researcher_studies):
        flash("You are not an administrator for that researcher, action rejected.", "danger")
        return abort(403)


################################################################################
########################## Study Editing Privileges ############################
################################################################################

class ArgumentMissingException(Exception): pass

def authenticate_researcher_study_access(some_function):
    """ This authentication decorator checks whether the user has permission to to access the
    study/survey they are accessing.
    This decorator requires the specific keywords "survey_id" or "study_id" be provided as
    keywords to the function, and will error if one is not.
    The pattern is for a url with <string:survey/study_id> to pass in this value.
    A site admin is always able to access a study or survey. """
    @functools.wraps(some_function)
    def authenticate_and_call(*args, **kwargs):

        # Check for regular login requirement
        if not is_logged_in():
            return redirect("/")

        # (returns 400 if there is no researcher)
        researcher = get_session_researcher()

        # Get values first from kwargs, then from the POST request
        survey_id = kwargs.get('survey_id', request.values.get('survey_id', None))
        study_id = kwargs.get('study_id', request.values.get('study_id', None))

        # Check proper syntax usage.
        if not survey_id and not study_id:
            raise ArgumentMissingException()

        # We want the survey_id check to execute first if both args are supplied, surveys are
        # attached to studies but do not supply the study id.
        if survey_id:
            # get studies for a survey, fail with 404 if study does not exist
            studies = Study.objects.filter(surveys=survey_id)
            if not studies.exists():
                return abort(404)

            # Check that researcher is either a researcher on the study or a site admin,
            # and populate study_id variable
            study_id = studies.values_list('pk', flat=True).get()

        # assert that such a study exists
        if not Study.objects.filter(pk=study_id).exists():
            return abort(404)

        study_relation = StudyRelation.objects.filter(study_id=study_id, researcher=researcher)

        # always allow site admins
        # currently we allow all study relations.
        if not researcher.site_admin:
            if not study_relation.exists():
                return abort(403)

            if study_relation.get().relationship not in ALL_RESEARCHER_TYPES:
                return abort(403)

        return some_function(*args, **kwargs)

    return authenticate_and_call


def get_researcher_allowed_studies_as_query_set():
    session_researcher = get_session_researcher()
    if session_researcher.site_admin:
        return Study.get_all_studies_by_name()

    return Study.get_all_studies_by_name().filter(
        id__in=session_researcher.study_relations.values_list("id", flat=True)
    )


def get_researcher_allowed_studies(as_json=True):
    """
    Return a list of studies which the currently logged-in researcher is authorized to view and edit.
    """
    session_researcher = get_session_researcher()
    study_set = [
        study for study in
        Study.get_all_studies_by_name().filter(study_relations__researcher=session_researcher)
            .values("name", "object_id", "id", "is_test")
    ]
    if as_json:
        return json.dumps(study_set)
    else:
        return study_set


################################################################################
############################# Site Administrator ###############################
################################################################################

def authenticate_site_admin(some_function):
#    """ Authenticate site admin, checks whether a user is a system admin before allowing access
#    to pages marked with this decorator.  If a study_id variable is supplied as a keyword
#    argument, the decorator will automatically grab the ObjectId in place of the string provided
#    in a route.
#
#    NOTE: if you are using this function along with the authenticate_researcher_study_access decorator
#    you must place this decorator below it, otherwise behavior is undefined and probably causes a
#    500 error inside the authenticate_researcher_study_access decorator. """
    @functools.wraps(some_function)
    def authenticate_and_call(*args, **kwargs):
        # Check for regular login requirement
        if not is_logged_in():
            return redirect("/")

        researcher = get_session_researcher()
        if not researcher.site_admin:
            if not researcher.study_relations.filter(relationship=ResearcherRole.study_admin):
                return abort(403)

        # redirect if a study id is not present and real.
        # TODO: why do we do this?
        if 'study_id' in kwargs:
            if not Study.objects.filter(pk=kwargs['study_id']).exists():
                return redirect("/")

        return some_function(*args, **kwargs)

    return authenticate_and_call


def strictly_site_admin(some_function):
    """ Authenticate site admin, checks whether a user is a system admin before allowing access
        to pages marked with this decorator.  If a study_id variable is supplied as a keyword
        argument, the decorator will automatically grab the ObjectId in place of the string provided
        in a route.

        NOTE: if you are using this function along with the authenticate_researcher_study_access decorator
        you must place this decorator below it, otherwise behavior is undefined and probably causes a
        500 error inside the authenticate_researcher_study_access decorator. """

    @functools.wraps(some_function)
    def authenticate_and_call(*args, **kwargs):
        # Check for regular login requirement
        if not is_logged_in():
            return redirect("/")

        researcher = get_session_researcher()
        if not researcher.site_admin:
            if not researcher.study_relations.filter(relationship=ResearcherRole.study_admin):
                return abort(403)

        # redirect if a study id is not present and real.
        # TODO: why do we do this?
        if 'study_id' in kwargs:
            if not Study.objects.filter(pk=kwargs['study_id']).exists():
                return redirect("/")

        return some_function(*args, **kwargs)

    return authenticate_and_call


# todo: uncomment, reallow usage after reviewing bad imports
# def researcher_is_site_admin():
#     """ Returns whether the current session user is a site admin """
#     researcher = Researcher.objects.get(username=session[SESSION_NAME])
#     return researcher.site_admin


def researcher_is_an_admin():
    """ Returns whether the current session user is a site admin """
    researcher = get_session_researcher()
    return researcher.site_admin or researcher.is_study_admin()
