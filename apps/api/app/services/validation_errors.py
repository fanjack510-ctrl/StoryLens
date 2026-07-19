class StructuralValidationError(ValueError):
    """Schema-valid output with invalid coverage, identity, order, or uniqueness."""

    error_code = "STRUCTURAL_VALIDATION_FAILED"

    def __init__(
        self,
        message: str,
        error_code: str | None = None,
        *,
        no_model_repair: bool = False,
        failed_field: str | None = None,
        repair_context: dict | None = None,
    ) -> None:
        super().__init__(message)
        if error_code:
            self.error_code = error_code
        self.no_model_repair = no_model_repair
        self.failed_field = failed_field
        self.repair_context = repair_context
