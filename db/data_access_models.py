from datetime import datetime
from db.mongolia_setup import DatabaseObject, DatabaseCollection, REQUIRED #, ID_KEY
from libs.security import chunk_hash
from config.constants import API_TIME_FORMAT, CHUNKABLE_FILES,\
    CHUNK_TIMESLICE_QUANTUM, ALL_DATA_STREAMS
from mongolia.constants import REQUIRED_STRING

class EverythingsGoneToHellException(Exception): pass

class ChunkRegistry(DatabaseObject):
    PATH = "beiwe.chunk_registry"
    DEFAULTS = {"study_id":REQUIRED,
                "user_id":REQUIRED_STRING,
                "data_type": "",
                #todo: check datetime support in mongolia
                "time_bin": REQUIRED,
                "chunk_hash": None,
                "chunk_path": REQUIRED_STRING,
                "is_chunkable": REQUIRED }
    @classmethod
    def add_new_chunk(cls, study_id, user_id, data_type, s3_file_path,
                      time_bin, file_contents=None):
        is_chunkable = data_type in CHUNKABLE_FILES
        if is_chunkable: time_bin = int(time_bin)*CHUNK_TIMESLICE_QUANTUM 
        ChunkRegistry.create(
            {"study_id": study_id,
            "user_id": user_id,
            "data_type": data_type,
            "chunk_path": s3_file_path,
            "chunk_hash": chunk_hash(file_contents) if is_chunkable else None,
            "time_bin": datetime.fromtimestamp(time_bin),
            #TODO: make sure this datetime matches with the code from chunksregistry collection
            "is_chunkable": is_chunkable },
            random_id=True )
#         print "new chunk:", s3_file_path
    
    def update_chunk_hash(self, data_to_hash):
        self["chunk_hash"] = chunk_hash(data_to_hash)
        self.save()
#         print "upd chunk", self['chunk_path']
    
class FileToProcess(DatabaseObject):
    PATH = "beiwe.file_to_process"
    DEFAULTS = { "s3_file_path":REQUIRED_STRING,
                 "study_id": REQUIRED,
                 "user_id": REQUIRED_STRING }
    @classmethod
    def append_file_for_processing(cls, file_path, study_id, user_id): 
        FileToProcess.create( {"s3_file_path":file_path, "study_id":study_id, "user_id":user_id}, random_id=True)

class FileProcessLock(DatabaseObject):
    PATH = "beiwe.file_process_running"
    DEFAULTS = {"mark":""}
    
    @classmethod
    def lock(cls):
        if len(FileProcessLockCollection()) > 0: raise EverythingsGoneToHellException
        FileProcessLock.create({"mark":"marked"}, random_id=True)
        
    @classmethod
    def unlock(cls):
        for f in FileProcessLockCollection(mark="marked"):
            f.remove()

################################################################################

class ChunksRegistry(DatabaseCollection):
    OBJTYPE = ChunkRegistry
    
    @classmethod
    def get_chunks_time_range(cls, study_id, user_ids=[], data_types=ALL_DATA_STREAMS,
                              start=datetime.fromtimestamp(0), end=datetime.utcnow()):
        """ This function uses mongo query syntax to provide datetimes and have
            mongo do the comparison operation, and the 'in' operator to have
            mongo only match the user list provided. """
        return cls(query={"time_bin": {"$gt": start, "$lt": end },
                          "user_id":{"$in":user_ids },
                          "study_id": study_id,
                          "data_type":{"$in":data_types}
                           } )
            
class FilesToProcess(DatabaseCollection):
    OBJTYPE = FileToProcess
class FileProcessLockCollection(DatabaseCollection):
    OBJTYPE = FileProcessLock