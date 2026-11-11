"""Durable run operations. Reading a run never executes tools or resumes a graph."""
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.types import Command
from src.discovery_agent import DiscoveryError, ResearchState
from src.full_workflow import build_full_graph, plain

DEFAULT_DB = Path(__file__).resolve().parents[1] / '.marketintel' / 'checkpoints.sqlite'


def _storage_error():
    return DiscoveryError("Checkpoint storage is unavailable. Ensure the project's .marketintel directory "
                          'is writable. Cloud local checkpoints are temporary and may be lost on restarts or redeployments.')


def _config(run_id):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', run_id):
        raise DiscoveryError('Invalid research run ID.')
    return {'configurable': {'thread_id': run_id}, 'recursion_limit': 80}


@contextmanager
def _run_lock(db_path, run_id):
    """OS-released lock prevents concurrent duplicate approvals across processes."""
    path = Path(db_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        handle = open(path.parent / f'{path.name}.{run_id}.lock', 'a+b')
    except OSError:
        raise _storage_error() from None
    acquired = False
    try:
        handle.seek(0, 2)
        if not handle.tell():
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        if os.name == 'nt':
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        acquired = True
        yield
    except (BlockingIOError, PermissionError):
        raise DiscoveryError('This research run is busy. Wait for it to finish, then load its saved state.') from None
    finally:
        if acquired:
            handle.seek(0)
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle, fcntl.LOCK_UN)
        handle.close()


@contextmanager
def research_session(db_path=DEFAULT_DB, **dependencies):
    path = Path(db_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(path), check_same_thread=False, timeout=30)
    except (OSError, sqlite3.Error):
        raise _storage_error() from None
    try:
        yield build_full_graph(SqliteSaver(connection), **dependencies)
    except sqlite3.Error:
        raise _storage_error() from None
    finally:
        connection.close()


def _read(graph, config):
    snapshot = graph.get_state(config)
    values = plain(snapshot.values)
    if not values:
        return {}
    values['_pending_nodes'] = list(snapshot.next)
    values['_interrupted'] = any(task.interrupts for task in snapshot.tasks)
    return values


def start_run(run_id, company, industry, *, competitors=None, db_path=DEFAULT_DB, **dependencies):
    config = _config(run_id)
    if not company.strip() or not industry.strip():
        raise DiscoveryError('Company and industry are required.')
    with _run_lock(db_path, run_id), research_session(db_path, **dependencies) as graph:
        existing = _read(graph, config)
        if existing:
            return existing
        # Input whitelist: configuration, API keys and clients never enter state.
        state = {'company': company.strip(), 'industry': industry.strip(), 'run_id': run_id,
                 'research_timestamp': datetime.now(timezone.utc).isoformat(), 'repair_count': 0,
                 'revision_count': 0, 'retry_count': 0, 'approval_status': 'not_requested',
                 'approval_history': [], 'errors': [], 'final_report': ''}
        if competitors:
            from src.discovery_agent import CompetitorCandidate
            state['competitors'] = [CompetitorCandidate.model_validate(c).model_dump() for c in competitors[:3]]
        graph.invoke(state, config=config)
        return _read(graph, config)


def load_run(run_id, *, db_path=DEFAULT_DB, **dependencies):
    config = _config(run_id)
    with research_session(db_path, **dependencies) as graph:
        return _read(graph, config)


def continue_run(run_id, *, db_path=DEFAULT_DB, **dependencies):
    config = _config(run_id)
    with _run_lock(db_path, run_id), research_session(db_path, **dependencies) as graph:
        state = _read(graph, config)
        if state.get('_pending_nodes') and not state.get('_interrupted'):
            graph.invoke(None, config=config)
        return _read(graph, config)


def review_run(run_id, action, review_token, *, feedback='', db_path=DEFAULT_DB, **dependencies):
    config = _config(run_id)
    if action not in ('approve', 'revise', 'reject'):
        raise DiscoveryError('Choose approve, revise, or reject.')
    with _run_lock(db_path, run_id), research_session(db_path, **dependencies) as graph:
        state = _read(graph, config)
        if state.get('approval_status') != 'pending' or not state.get('_interrupted') or state.get('review_token') != review_token:
            return state  # Stale/double clicks cannot approve or repeat paid work.
        graph.invoke(Command(resume={'action': action, 'review_token': review_token,
                                     'feedback': feedback[:500]}), config=config)
        return _read(graph, config)


def regenerate_briefing(run_id, *, db_path=DEFAULT_DB):
    """Format saved approved evidence only; no graph invoke/resume or provider calls."""
    from src.report_agent import generate_briefing
    config = _config(run_id)
    with _run_lock(db_path, run_id), research_session(db_path) as graph:
        state = _read(graph, config)
        if state.get('approval_status') != 'approved' or state.get('_pending_nodes') or state.get('_interrupted'):
            raise DiscoveryError('Only a completed, approved run can regenerate its briefing. Complete human review first.')
        update = generate_briefing(state)
        if all(state.get(key) == update[key] for key in
               ('final_report', 'report_formatter_version', 'report_source_fingerprint')):
            return state  # Identical evidence and formatter do not create a new checkpoint.
        history = list(state.get('report_history', []))
        prior = state.get('final_report', '')
        if prior and not any(item['report'] == prior for item in history):
            history.append({'report': prior, 'formatter_version': state.get('report_formatter_version', 'legacy'),
                            'source_fingerprint': state.get('report_source_fingerprint', ''),
                            'archived_at': datetime.now(timezone.utc).isoformat()})
        update['original_report'] = state.get('original_report', prior)
        update['report_history'] = history
        # Preserve approval and all evidence. Mark only the existing terminal report
        # node as updated; no Discovery/Research/Extraction/Verification node executes.
        graph.update_state(config, update, as_node='briefing')
        return _read(graph, config)
