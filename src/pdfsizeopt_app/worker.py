from pathlib import Path
import json
import sys
import time
import traceback
from .engine import Cancelled, Settings, compress_pdf


class FileCancellation:
    def __init__(self,path):
        self.path=Path(path)
    def is_set(self):
        return self.path.exists()
    def wait(self,seconds):
        time.sleep(seconds)
        return self.is_set()


def run(job_path):
    job=json.loads(job_path.read_text(encoding='utf-8'))
    cancel=FileCancellation(job['cancel_file'])
    settings=Settings(**job['settings'])
    current=None
    def emit(kind,**data):
        print(json.dumps({'type':kind,'source':current,**data},ensure_ascii=False),flush=True)
    failures=0
    for index,file in enumerate(job['files']):
        if cancel.is_set():break
        current=file
        emit('start',index=index,total=len(job['files']))
        try:
            result=compress_pdf(file,job.get('output_dir') or None,settings,cancel,emit)
            emit('result',result=result)
        except Cancelled:
            emit('cancelled',message='已取消，原文件未改动。')
            break
        except Exception as exc:
            failures+=1
            emit('error',message=str(exc))
            with (job_path.parent/'worker_errors.log').open('a',encoding='utf-8') as handle:
                handle.write(file+'\n'+traceback.format_exc()+'\n')
    emit('finished',failures=failures,cancelled=cancel.is_set())
    return 0
