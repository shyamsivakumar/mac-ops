# MO: heavy jobs get a 45-minute wall-clock ceiling

Every heavy job needs a hard wall-clock ceiling that frees its slot.

## Interface

The tests use these names and signatures, which the change must provide (names only, no behaviour implied):

- `heavy.py`: `constant WALL_CLOCK_REASON`
- `heavy.py`: `def _claim_termination(registry: Registry, job_id: str, reason: str, *, claimant_pid: int, expected_workload: Optional[Dict[str, Any]]=None, takeover: bool=False, observed_termination: Optional[Dict[str, Any]]=None)`
- `heavy.py`: `def _reserve_job(registry: Registry, task_key: str, task_id: str, command_basename: str, sample: Sample, deps: SupervisorDeps, *, queue_id: Optional[str]=None, role: str='ordinary', max_runtime_seconds: Optional[float]=None)`
- `heavy.py`: `def _limit_action(record: Dict[str, Any], now_ns: int, boot_reader: Callable[[], str])`
- `heavy.py`: `def _watchdog_takeover_record(record: Dict[str, Any], workload: Dict[str, Any], claimant_pid: int, observed: Dict[str, Any])`
- `heavy.py`: `def _takeover_termination(registry: Registry, job_id: str, workload: Dict[str, Any], claimant_pid: int, observed: Dict[str, Any])`

The repository is at `/app`. Make the change there. Do not edit test files.
