package governance.monitoring.user.check.policy_0179

# Auto-generated policy 179 (Rego v1 syntax)
# Package: governance.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0179",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0179_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
default policy_0179_allowed = false
