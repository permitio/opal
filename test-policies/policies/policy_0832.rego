package governance.monitoring.action.validate.helpers.policy_0832

# Auto-generated policy 832 (Rego v1 syntax)
# Package: governance.monitoring.action.validate.helpers

# Metadata
metadata := {
    "policy_id": "0832",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0832_allowed if {
    data.policies.governance.enabled
}
policy_0832_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
policy_0832_allowed if {
    input.user.role == "admin"
}
