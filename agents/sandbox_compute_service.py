import os
import resource
import secrets
import subprocess
import sys
import tempfile
import time

from pydantic import BaseModel, ConfigDict, Field


class SandboxExecutionRequest(BaseModel):
    """Solicitud de ejecución de código en runtime sandbox aislado."""
    model_config = ConfigDict(extra="forbid")

    request_id: str = Field(default_factory=lambda: f"SBX-{secrets.token_hex(6)}", pattern=r"^SBX-[0-9a-f]{12}$")
    code: str = Field(..., max_length=50_000)
    timeout_seconds: int = Field(default=2, ge=1, le=10)
    max_memory_mb: int = Field(default=64, ge=16, le=256)


class SandboxExecutionResult(BaseModel):
    """Resultado determinista de ejecución en el sandbox."""
    model_config = ConfigDict(extra="forbid")

    request_id: str
    status: str  # SUCCESS, TIMEOUT, MEMORY_EXCEEDED, ERROR
    stdout: str
    stderr: str
    exit_code: int
    execution_time_ms: float
    memory_limit_mb: int


class SandboxComputeService:
    """
    Servicio de ejecución de cómputo efímero en entorno acotado por hardware (RLIMIT).
    Aplica límites estrictos de CPU, memoria virtual (AS), y procesos máximos (NPROC)
    para aislar la ejecución de scripts o tareas evaluadas por agentes.
    """

    def __init__(self):
        self.python_bin = sys.executable

    def _set_resource_limits(self, cpu_seconds: int, max_mem_bytes: int):
        """Función pre-exec invocada en el proceso hijo antes de ejecutar el script."""
        # 1. Límite de tiempo de CPU
        resource.setrlimit(resource.RLIMIT_CPU, (cpu_seconds, cpu_seconds + 1))
        # 2. Límite de memoria virtual
        resource.setrlimit(resource.RLIMIT_AS, (max_mem_bytes, max_mem_bytes))
        # 3. Límite de procesos para mitigar fork bombs
        try:
            resource.setrlimit(resource.RLIMIT_NPROC, (10, 10))
        except (ValueError, OSError):
            pass

    def run_isolated(self, request: SandboxExecutionRequest) -> SandboxExecutionResult:
        """
        Ejecuta el código en un proceso hijo aislado con límites de recursos estrictos y variables de entorno despojadas.
        """
        max_bytes = request.max_memory_mb * 1024 * 1024
        start_time = time.perf_counter()

        with tempfile.NamedTemporaryFile("w", suffix=".py", delete=False) as tmp_file:
            tmp_path = tmp_file.name
            tmp_file.write(request.code)

        try:
            # Entorno mínimo sin acceso a variables de entorno del host
            sandbox_env = {
                "PATH": "/usr/bin:/bin",
                "PYTHONHASHSEED": "0",
                "PYTHONDONTWRITEBYTECODE": "1",
            }

            process = subprocess.Popen(
                [self.python_bin, "-I", tmp_path],  # -I: modo aislado (ignora PYTHONPATH y user site)
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=sandbox_env,
                preexec_fn=lambda: self._set_resource_limits(request.timeout_seconds, max_bytes),  # noqa: PLW1509
            )

            try:
                stdout, stderr = process.communicate(timeout=request.timeout_seconds + 1)
                exit_code = process.returncode
            except subprocess.TimeoutExpired:
                process.kill()
                stdout, stderr = process.communicate()
                elapsed_ms = (time.perf_counter() - start_time) * 1000.0
                return SandboxExecutionResult(
                    request_id=request.request_id,
                    status="TIMEOUT",
                    stdout=stdout or "",
                    stderr=(stderr or "") + "\n[SANDBOX] Tiempo límite de CPU/reloj excedido.",
                    exit_code=-1,
                    execution_time_ms=round(elapsed_ms, 2),
                    memory_limit_mb=request.max_memory_mb,
                )

            elapsed_ms = (time.perf_counter() - start_time) * 1000.0

            # Detección de fallo por memoria (MemoryError o SIGSEGV/SIGKILL por RLIMIT_AS)
            status = "SUCCESS" if exit_code == 0 else "ERROR"
            if "MemoryError" in stderr or exit_code == -9 or exit_code == 137:
                status = "MEMORY_EXCEEDED"
            elif exit_code in (-24, 152):  # SIGXCPU
                status = "TIMEOUT"

            return SandboxExecutionResult(
                request_id=request.request_id,
                status=status,
                stdout=stdout[:10_000],
                stderr=stderr[:10_000],
                exit_code=exit_code,
                execution_time_ms=round(elapsed_ms, 2),
                memory_limit_mb=request.max_memory_mb,
            )

        finally:
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass
