try:
    from fastapi import FastAPI
except ImportError:  # pragma: no cover
    FastAPI = None


def create_app() -> "FastAPI":
    if FastAPI is None:
        raise RuntimeError("FastAPI is not installed. Install it to enable the API server.")

    app = FastAPI(title="logconsolidator")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
