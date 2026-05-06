package security.monitoring.user.check.policy_0869

# Auto-generated policy 869 (Rego v1 syntax)
# Package: security.monitoring.user.check

# Metadata
metadata := {
    "policy_id": "0869",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0869_allowed if {
    input.user.role == "admin"
}
policy_0869_denied if {
    input.action == "delete"
    input.user.role != "admin"
}
