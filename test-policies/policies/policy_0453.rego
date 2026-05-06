package audit.monitoring.context.verify.helpers.policy_0453

# Auto-generated policy 453 (Rego v1 syntax)
# Package: audit.monitoring.context.verify.helpers

# Metadata
metadata := {
    "policy_id": "0453",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0453_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0453_allowed if {
    input.user.role == "admin"
}
default policy_0453_allowed = false
