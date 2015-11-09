from bson import ObjectId
from cronutils import ErrorHandler
from datetime import datetime
from flask import Blueprint, request, abort, json
from collections import defaultdict, deque

from db.data_access_models import FilesToProcess, ChunksRegistry,FileProcessLock,\
    FileToProcess, ChunkRegistry
from db.study_models import Studies, Study
from db.user_models import Admins, Admin
from libs.s3 import s3_retrieve, s3_upload

from config.constants import (API_TIME_FORMAT, CHUNKS_FOLDER, ACCELEROMETER,
    BLUETOOTH, CALL_LOG, GPS, IDENTIFIERS, LOG_FILE, POWER_STATE,
    SURVEY_ANSWERS, SURVEY_TIMINGS, TEXTS_LOG, VOICE_RECORDING,
    WIFI, ALL_DATA_STREAMS, CHUNKABLE_FILES, CHUNK_TIMESLICE_QUANTUM,
    LENGTH_OF_STUDY_ID)
from bson.errors import InvalidId

# Data Notes
# The call log has the timestamp column as the 3rd column instead of the first.
# The Wifi and Identifiers have timestamp in the file name.
# The debug log has many lines without timestamps.

#TODO: determine whether time_stamps that cross an hour boundry are placed in the proper bin

data_access_api = Blueprint('data_access_api', __name__)

@data_access_api.route("/get-data/v1", methods=['POST', "GET"])
def grab_data():
    """
    required: access key, access secret, study_id
    JSON blobs: data streams, users - default to all
    Strings: date-start, date-end - format as "YYYY-MM-DDThh:mm:ss" 
    optional: top-up = a file (registry.dat)
    cases handled: 
        missing creds or study, invalid admin or study, admin does not have access
        admin creds are invalid """
    
    #Flask automatically returns a 400 response if a parameter does not exist in request.values()
    #Case: missing creds or study_id
#     if "access_key" not in request.values:
#         print 1
#         return abort(403)
#     if "secret_key" not in request.values:
#         print 2
#         return abort(403)
#     if "study_id" not in request.values:
#         print 3
#         return abort(400)
    #Case: bad study id
    
    print "oh, y'know...."
    
    try: study_id = ObjectId(request.values["study_id"])
    except InvalidId: study_id = None
    study_obj = Study(study_id)
    print 1
    if not study_obj:
        return abort(404)
    #Case: invalid access creds
    access_key = request.values["access_key"]
    access_secret = request.values["secret_key"]
    
    admin = Admin(access_key_id=access_key)
    print 2
    if not admin:
        return abort(403) #invalid admin (invalid access key)
    print 3
    if admin["_id"] not in study_obj['admins']:
        return abort(403) #illegal admin
    print 4
    if not admin.validate_access_credentials(access_secret):
        return abort(403) #incorrect secret key
    query = {}
    #select data streams
    if "data_streams" in request.values: #TODO: reconsider using "data streams" over "data types"
        query["data_types"] = json.loads(request.values["data_streams"])
        for data_stream in query['data_types']:
            if data_stream not in ALL_DATA_STREAMS:
                return abort(404)
#     else: query["data_streams"] = ALL_DATA_STREAMS #turned into default value in get_chunks_time_range
    #select users
    print 5
    if "user_ids" in request.values:
        query["user_ids"] = [user for user in json.loads(request.values["user_ids"])]
    else: query["user_ids"] = study_obj.get_users_in_study()
    #construct time ranges
    print 6
    if "date_start" in request.values:
        query["start"] = datetime.strptime(request.values["date_start"])
    if "date_end" in request.values:
        query["end"] = datetime.strptime(request.values["date_end"])
    
    chunks = ChunksRegistry.get_chunks_time_range(study_id, **query)
    
#     print "\n\n\n", query, "\n", chunks, "\n\n"
    data = {}
    for chunk in chunks:
        file_name = ( ("%s/%s.csv" if chunk['data_type'] != VOICE_RECORDING else "%s/%s.mp4")
                      % (chunk["data_type"], chunk["time_bin"] ) )
        print file_name
        data[file_name] = s3_retrieve(chunk['chunk_path'], chunk["study_id"], raw_path=True)
    import locale
    locale.setlocale(locale.LC_ALL, 'en_US')
    print "total size:", locale.format("%d", sum(len(key) + len(item) for key, item in data.items() ), grouping=True)
    return json.dumps(data)
    
    
    
    
    #TODO: test bytestrings in connection to voicerecording files
    """ "json.dumps?
    Signature: json.dumps(obj, **kwargs)
    Docstring:
    Serialize ``obj`` to a JSON formatted ``str`` by using the application's
    configured encoder (:attr:`~flask.Flask.json_encoder`) if there is an
    application on the stack.
    
    This function can return ``unicode`` strings or ascii-only bytestrings by
    default which coerce into unicode strings automatically.  That behavior by
    default is controlled by the ``JSON_AS_ASCII`` configuration variable
    and can be overriden by the simplejson ``ensure_ascii`` parameter. """
    
    #TODO: 
#     chunk_data = {}
#     if "top_up" in request.values:
#         top_up = json.loads(request.values["top_up"])

"""############################# Hourly Update ##############################"""

def process_file_chunks():
    FileProcessLock.lock()
    error_handler = ErrorHandler()
#     error_handler = null_error_handler
    while True:
        starting_length = len(FilesToProcess())
        print starting_length
        do_process_file_chunks(1000, error_handler)
        if starting_length == len(FilesToProcess()): break
    FileProcessLock.unlock()
    print len(FilesToProcess())
    error_handler.raise_errors()

def do_process_file_chunks(count, error_handler):
    """
    Run through the files to process, pull their data, put it into s3 bins.
    Run the file through the appropriate logic path based on file type.
    
    If a file is empty put its ftp object to the empty_files_list, we can't
        delete objects in-place while iterating over the db. 
    
    All files except for the audio recording mp4 file are in the form of CSVs,
    most of those files can be separated by "time bin" (separated into one-hour
    chunks) and concatenated and sorted trivially. A few files, call log,
    identifier file, and wifi log, require some triage beforehand.  The debug log
    cannot be correctly sorted by time for all elements, because it was not
    actually expected to be used by researchers, but is apparently quite useful.
    
    Any errors are themselves concatenated using the passed in error handler.
    """
    
    #this is how you declare a defaultdict containing a tuple of two deques.
    binified_data = defaultdict( lambda : ( deque(), deque() ) )
    ftps_to_remove = set([]);
    
    for ftp in FilesToProcess()[:count]:
        with error_handler:
            s3_file_path = ftp["s3_file_path"]
#             print s3_file_path
            data_type = file_path_to_data_type(ftp["s3_file_path"])
            if data_type in CHUNKABLE_FILES:
                file_contents = s3_retrieve(s3_file_path[LENGTH_OF_STUDY_ID:], ftp["study_id"])
                newly_binified_data = handle_csv_data(ftp["study_id"],
                                     ftp["user_id"], data_type, file_contents,
                                     s3_file_path)
                if newly_binified_data:
                    append_binified_csvs(binified_data, newly_binified_data, ftp)
                else: # delete empty files from FilesToProcess
                    ftps_to_remove.add(ftp._id)
                continue
            else:
                timestamp = clean_java_timecode( s3_file_path.rsplit("/", 1)[-1][:-4])
#                 print timestamp
                ChunkRegistry.add_new_chunk(ftp["study_id"], ftp["user_id"],
                                            data_type, s3_file_path, timestamp)
                ftps_to_remove.add(ftp._id)
    more_ftps_to_remove = upload_binified_data(binified_data, error_handler)
    ftps_to_remove.update(more_ftps_to_remove)
    for ftp_id in ftps_to_remove:
        FileToProcess(ftp_id).remove()
    
def upload_binified_data(binified_data, error_handler):
    """ Takes in binified csv data and handles uploading/downloading+updating
        older data to/from S3 for each chunk.
        Returns a set of all failed concatenations, raises errors on the passed
        in ErrorHandler."""
    failed_ftps = set([])
    ftps_to_remove = set([])
    for binn, values in binified_data.items():
        data_rows_deque, ftp_deque = values
        with error_handler:
            study_id, user_id, data_type, time_bin, header = binn
            rows = list(data_rows_deque)
            chunk_path = construct_s3_chunk_path(study_id, user_id, data_type, time_bin) 
            chunk = ChunkRegistry(chunk_path=chunk_path)
            if not chunk:
                ensure_sorted_by_timestamp(rows)
                new_contents = construct_csv_string(header, rows)
                s3_upload( chunk_path, new_contents, study_id, raw_path=True )
                ChunkRegistry.add_new_chunk(study_id, user_id, data_type,
                                chunk_path,time_bin, file_contents=new_contents )
            else:
                s3_file_data = s3_retrieve( chunk_path, study_id, raw_path=True )
                old_header, old_rows = csv_to_list(s3_file_data) 
                if old_header != header:
                    failed_ftps.update(ftp_deque)
                    #TODO: this does not add to the delete queue due to the error
                    raise HeaderMismatchException('%s\nvs.\n%s\nin\n%s' %
                                                  (old_header, header, chunk_path) )
                old_rows.extend(rows)
                ensure_sorted_by_timestamp(old_rows)
                new_contents = construct_csv_string(header, old_rows)
                s3_upload( chunk_path, new_contents, study_id, raw_path=True)
                chunk.update_chunk_hash(new_contents)
            ftps_to_remove.update(ftp_deque)
    return ftps_to_remove.difference(failed_ftps)


"""################################ S3 Stuff ################################"""

def construct_s3_chunk_path(study_id, user_id, data_type, time_bin):
    """ S3 file paths for chunks are of this form:
        CHUNKED_DATA/study_id/user_id/data_type/time_bin.csv """
    return "%s/%s/%s/%s/%s.csv" % (CHUNKS_FOLDER, study_id, user_id, data_type,
        datetime.fromtimestamp(time_bin*CHUNK_TIMESLICE_QUANTUM).strftime( API_TIME_FORMAT ) )

# def reverse_s3_chunk_path(path): 
#     """" CHUNKS_FOLDER, study_id, user_id, data_type, time_bin. """
#     return path.split("/")

"""################################# Key ####################################"""

def file_path_to_data_type(file_path):
    if "/accel/" in file_path: return ACCELEROMETER
    if "/bluetoothLog/" in file_path: return BLUETOOTH
    if "/callLog/" in file_path: return CALL_LOG
    if "/gps/" in file_path: return GPS
    if "/identifiers" in file_path: return IDENTIFIERS
    if "/logFile/" in file_path: return LOG_FILE
    if "/powerState/" in file_path: return POWER_STATE
    if "/surveyAnswers/" in file_path: return SURVEY_ANSWERS
    if "/surveyTimings/" in file_path: return SURVEY_TIMINGS
    if "/textsLog/" in file_path: return TEXTS_LOG
    if "/voiceRecording" in file_path: return VOICE_RECORDING
    if "/wifiLog/" in file_path: return WIFI
    raise TypeError("data type unknown: %s" % file_path)

def ensure_sorted_by_timestamp(l):
    """ According to the docs the sort method on a list is in place and should
        faster, this is how to declare a sort by the first column (timestamp). """
    l.sort(key = lambda x: int(x[0]))

def binify_from_timecode(unix_ish_time_code_string):
    """ Takes a unix-ish time code (accepts unix millisecond), and returns an
        integer value of the bin it should go in. """
    actually_a_timecode = clean_java_timecode(unix_ish_time_code_string) # clean java time codes...
    return actually_a_timecode / CHUNK_TIMESLICE_QUANTUM #separate into nice, clean hourly chunks!

def clean_java_timecode(java_time_code_string):
    return int(java_time_code_string[:10])

def append_binified_csvs(old_binified_rows, new_binified_rows, file_to_process):
    """ Appends binified rows to an existing binified row data structure.
        Should be in-place. """
    #ignore the overwrite builtin namespace warning.
    for binn, rows in new_binified_rows.items():
        old_binified_rows[binn][0].extend(rows)  #Add data rows
        old_binified_rows[binn][1].append(file_to_process._id)  #add ftp id

"""############################## Standard CSVs #############################"""

def handle_csv_data(study_id, user_id, data_type, file_contents, file_path):
    """ Constructs a binified dict of a given list of a csv rows,
        catches csv files with known problems and runs the correct logic. """
    header, csv_rows_list = csv_to_list(file_contents)
    # INSERT more data fixes below as we encounter them.
    if data_type == CALL_LOG: fix_call_log_csv(header, csv_rows_list)
#     if data_type == WIFI: header = fix_wifi_csv(header, csv_rows_list, file_path)
    if data_type == IDENTIFIERS: header = fix_identifier_csv(header, csv_rows_list, file_path)
    # Binify!
    if csv_rows_list:
        return binify_csv_rows(csv_rows_list, study_id, user_id, data_type, header)
    else:
        return None

def binify_csv_rows(rows_list, study_id, user_id, data_type, header):
    """ Assumes a clean csv with element 0 in the rows list as a unix(ish) timestamp.
        sorts data points into the appropriate bin based on the rounded down hour
        value of the entry's unix(ish) timestamp.
        Returns a dict of form {(study_id, user_id, data_type, time_bin, heeader):rows_lists}. """
    ret = defaultdict(deque)
    for row in rows_list:
        ret[(study_id, user_id, data_type,
             binify_from_timecode(row[0]), header)].append(row)
    return ret

""" CSV Fixes """
def fix_call_log_csv(header, rows_list):
    """ The call log has poorly ordered columns, the first column should always be
        the timestamp, it has it in column 3. """
    header_list = header.split(",")
    header_list.insert(0, header_list.pop(2))
    header = ",".join(header_list)
    (row.insert(0, row.pop(2)) for row in rows_list)

def fix_identifier_csv(header, rows_list, file_name):
    """ The identifiers file has its timestamp in the file name. """
    time_stamp = file_name.rsplit("_", 1)[-1][:-4]
    return insert_timestamp_single_row_csv(header, rows_list, time_stamp)

""" fixing wifi requires inserting the same timestamp on EVERY ROW.  not worth it."""
# def fix_wifi_csv(header, rows_list, file_name):
#     """ The wifi file has its timestamp in the filename. """
#     time_stamp = file_name.rsplit("/", 1)[-1][:-4]
#     return insert_timestamp_single_row_csv(header, rows_list, time_stamp)

def insert_timestamp_single_row_csv(header, rows_list, time_stamp):
    """ Inserts the timestamp field into the header of a csv, inserts the timestamp
        value provided into the first column.  Returns the new header string."""
    header_list = header.split(",")
    header_list.insert(0, "timestamp")
    rows_list[0].insert(0, time_stamp)
    return ",".join(header_list)

""" CSV transforms"""
def csv_to_list(csv_string):
    """ Grab a list elements from of every line in the csv, strips off trailing
        whitespace. dumps them into a new list (of lists), and returns the header
        line along with the list of rows. """ 
    lines = [ line for line in csv_string.splitlines() ]
    return lines[0], [row.split(",") for row in lines[1:]]

def construct_csv_string(header, rows_list):
    """ Takes a header list and a csv and returns a single string of a csv"""
    return header + "\n" + "\n".join( [",".join(row) for row in rows_list ] )

""" Exceptions"""
class HeaderMismatchException(Exception): pass