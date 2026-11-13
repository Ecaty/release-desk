"""Cancellable background work. Each job runs in its own thread; long waits and child processes go through this
module so Cancel can stop them: waits end at once and child process trees (SteamCMD, BuildPatch Tool, adb, the
Unity CLI client) are killed. The Unity Editor itself is never killed; a build already running inside it has to be
cancelled in Unity's own progress window."""
import subprocess
import threading

_local = threading.local()


class Cancelled(Exception):
    pass


class Job:
    def __init__(self, name):
        self.name = name
        self.cancel = threading.Event()
        self.procs = []
        self.lock = threading.Lock()

    def stop(self):
        self.cancel.set()
        with self.lock:
            procs = list(self.procs)
        for proc in procs:
            _kill_tree(proc)


def _kill_tree(proc):
    if proc.poll() is None:
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True)


def start(job):
    _local.job = job


def current():
    return getattr(_local, "job", None)


def check():
    job = current()
    if job and job.cancel.is_set():
        raise Cancelled()


def sleep(seconds):
    """time.sleep that ends early (raising Cancelled) when the job is cancelled."""
    job = current()
    if job:
        job.cancel.wait(seconds)
        check()
    else:
        import time
        time.sleep(seconds)


def run(args, timeout=None, **kwargs):
    """subprocess.run with capture_output, registered with the current job so Cancel can kill it."""
    check()
    kwargs.setdefault("text", True)
    proc = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL, **kwargs)
    job = current()
    if job:
        with job.lock:
            job.procs.append(proc)
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _kill_tree(proc)
        proc.communicate()
        raise
    finally:
        if job:
            with job.lock:
                job.procs.remove(proc)
    check()
    return subprocess.CompletedProcess(args, proc.returncode, out, err)
