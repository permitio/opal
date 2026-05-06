package audit.validation.action.validate.logic.policy_0745

# Auto-generated policy 745 (Rego v1 syntax)
# Package: audit.validation.action.validate.logic

# Metadata
metadata := {
    "policy_id": "0745",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0745_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0745_allowed if {
    data.policies.audit.enabled
}
