package governance.monitoring.user.check.policy_0462

# Auto-generated policy 462 (Rego v1 syntax)
# Package: governance.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0462",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0462_allowed if {
    data.policies.governance.enabled
}
default policy_0462_allowed = false
policy_0462_allowed if {
    input.user.role == "admin"
}
policy_0462_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
