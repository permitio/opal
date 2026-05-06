package compliance.monitoring.action.deny.logic.policy_0674

# Auto-generated policy 674 (Rego v1 syntax)
# Package: compliance.monitoring.action.deny.logic

# Metadata
metadata := {
    "policy_id": "0674",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0674_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0674_allowed if {
    input.user.role == "admin"
}
