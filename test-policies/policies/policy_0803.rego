package compliance.monitoring.action.allow.policy_0803

# Auto-generated policy 803 (Rego v1 syntax)
# Package: compliance.monitoring.action.allow

# Metadata
metadata := {
    "policy_id": "0803",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0803_allowed if {
    input.user.role == "admin"
}
policy_0803_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
